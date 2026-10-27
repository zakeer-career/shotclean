#!/usr/bin/env python3
"""
ShotClean Universal Studio v5.7.0
Cross-platform metadata stripper, anti-forensics suite & granular folder protection.
Repository: https://github.com/zakeer-career/shotclean
"""

import argparse
import collections
import hashlib
import hmac
import json
import os
import platform
import queue
import random
import select
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import uuid
import zlib
from pathlib import Path

# Enable ANSI formatting on Windows CMD/PowerShell
if platform.system() == "Windows":
    os.system("")

# ==============================================================================
# ROBUST HTTP CLIENT (FALLBACK TO CURL FOR SSL/HTTPS ISSUES)
# ==============================================================================

def fetch_web_resource(url: str, timeout: float = 6.0) -> str:
    """Fetches text over HTTP/HTTPS with automatic curl fallback for broken SSL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShotClean-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as urllib_err:
        if shutil.which("curl"):
            try:
                res = subprocess.run(
                    ["curl", "-fsSL", "-m", str(int(timeout)), "-A", "ShotClean-Updater", url],
                    capture_output=True,
                    text=True,
                    timeout=timeout + 2,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout
            except Exception:
                pass
        raise urllib_err

# ==============================================================================
# VERSION & BULLETPROOF AUTO-UPDATER
# ==============================================================================

CURRENT_VERSION = "5.7.0"
GITHUB_REPO = "zakeer-career/shotclean"

UPDATE_AVAILABLE = False
REMOTE_COMMIT_SHORT = ""
REMOTE_SHA = ""

HOME = Path.home()
SHOTCLEAN_DIR = HOME / ".shotclean"
COMMIT_CACHE_FILE = SHOTCLEAN_DIR / "installed_commit.txt"
CONFIG_FILE = SHOTCLEAN_DIR / "config.json"
LEDGER_FILE = SHOTCLEAN_DIR / "scrubbed_ledger.json"
LOG_FILE = SHOTCLEAN_DIR / "activity.log"
PID_FILE = SHOTCLEAN_DIR / "shotclean.pid"
VAULT_DIR = SHOTCLEAN_DIR / "vault"
VAULT_KEY_FILE = SHOTCLEAN_DIR / ".vault_key"

SHOTCLEAN_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)


def get_current_commit():
    if COMMIT_CACHE_FILE.exists():
        try:
            return COMMIT_CACHE_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


def check_updates_background():
    global UPDATE_AVAILABLE, REMOTE_COMMIT_SHORT, REMOTE_SHA
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        content = fetch_web_resource(url, timeout=4.0)
        data = json.loads(content)
        REMOTE_SHA = data.get("sha", "")
        local_sha = get_current_commit()

        if not local_sha and REMOTE_SHA:
            COMMIT_CACHE_FILE.write_text(REMOTE_SHA, encoding="utf-8")
            return

        if REMOTE_SHA and local_sha != REMOTE_SHA:
            REMOTE_COMMIT_SHORT = REMOTE_SHA[:7]
            UPDATE_AVAILABLE = True
    except Exception:
        pass


def perform_direct_web_update():
    print(f"\n  {CLR_CYAN}Downloading latest update from GitHub...{NC}")
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/shotclean.py"
        new_code = fetch_web_resource(raw_url, timeout=12.0)

        # Bulletproof: strip accidental markdown fences, text headers, or AI labels
        if "#!/usr/bin/env python3" in new_code:
            idx = new_code.find("#!/usr/bin/env python3")
            new_code = new_code[idx:]
        elif "ShotClean" not in new_code:
            print(f"  {CLR_RED}✖ Downloaded file was invalid. Aborting.{NC}")
            input("  Press [Enter] to continue...")
            return

        current_script = Path(__file__).resolve()
        current_script.write_text(new_code, encoding="utf-8")

        if REMOTE_SHA:
            COMMIT_CACHE_FILE.write_text(REMOTE_SHA, encoding="utf-8")

        print(f"  {CLR_GREEN}{BOLD}✔ Updated successfully! Restarting...{NC}\n")
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"  {CLR_RED}✖ Update failed: {e}{NC}")
        input("  Press [Enter] to continue...")


# ==============================================================================
# UI COLOR PALETTE & DYNAMIC LAYOUT
# ==============================================================================

CLR_CYAN = "\033[38;5;51m"
CLR_BLUE = "\033[38;5;75m"
CLR_GREEN = "\033[38;5;82m"
CLR_RED = "\033[38;5;203m"
CLR_AMBER = "\033[38;5;214m"
CLR_PURPLE = "\033[38;5;141m"
CLR_GRAY = "\033[38;5;245m"
CLR_WHITE = "\033[38;5;255m"
CLR_BORDER = "\033[38;5;241m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"

VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
EXTRA_MEDIA_EXTENSIONS = {".mp4", ".mov", ".pdf"}
ALL_SUPPORTED_EXTENSIONS = VALID_EXTENSIONS | EXTRA_MEDIA_EXTENSIONS
SESSION_CLEANED_COUNT = 0


def get_valid_extensions_for_rules(rules: dict) -> set:
    if rules.get("include_media_docs", False):
        return ALL_SUPPORTED_EXTENSIONS
    return VALID_EXTENSIONS


def get_ui_width():
    cols = shutil.get_terminal_size((52, 20)).columns
    return max(48, min(cols, 66))


def truncate_middle(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    half = max(2, (max_len - 3) // 2)
    return text[:half] + "..." + text[-half:]


def detect_default_folder() -> Path:
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        candidates = [
            Path("/storage/emulated/0/Pictures/Screenshots"),
            Path("/storage/emulated/0/DCIM/Screenshots"),
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]
    elif platform.system() == "Windows":
        return HOME / "Pictures" / "Screenshots"
    elif platform.system() == "Darwin":
        return HOME / "Desktop"
    else:
        linux_path = HOME / "Pictures" / "Screenshots"
        return linux_path if linux_path.exists() else HOME / "Pictures"


# ==============================================================================
# PERSISTENT SCRUBBED-FILE LEDGER (PREVENTS RE-RENAMING ACROSS RESTARTS)
# ==============================================================================

LEDGER_LOCK = threading.Lock()


def _load_ledger_unlocked() -> dict:
    if LEDGER_FILE.exists():
        try:
            with open(LEDGER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def _save_ledger_unlocked(ledger: dict):
    try:
        if len(ledger) > 2000:
            # Keep most recent 1500 entries
            keys = list(ledger.keys())[-1500:]
            ledger = {k: ledger[k] for k in keys}
        with open(LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(ledger, f)
    except Exception:
        pass


def is_file_in_ledger(filepath: Path) -> bool:
    """Checks if file path with exact current size and mtime is already sanitized."""
    try:
        if not filepath.exists():
            return False
        st = filepath.stat()
        key = str(filepath.resolve())
        sig = [st.st_size, int(st.st_mtime)]
        with LEDGER_LOCK:
            ledger = _load_ledger_unlocked()
            return ledger.get(key) == sig
    except Exception:
        return False


def record_file_in_ledger(filepath: Path):
    """Records sanitized file signature in persistent ledger."""
    try:
        if not filepath.exists():
            return
        st = filepath.stat()
        key = str(filepath.resolve())
        sig = [st.st_size, int(st.st_mtime)]
        with LEDGER_LOCK:
            ledger = _load_ledger_unlocked()
            ledger[key] = sig
            _save_ledger_unlocked(ledger)
    except Exception:
        pass


# ==============================================================================
# DYNAMIC EPHEMERAL WAKELOCK & SYSTEM NOTIFICATIONS
# ==============================================================================

HAS_WAKELOCK = False
WAKELOCK_LOCK = threading.Lock()


def acquire_wake_lock():
    global HAS_WAKELOCK
    if "com.termux" in os.environ.get("PREFIX", "") and shutil.which("termux-wake-lock"):
        with WAKELOCK_LOCK:
            if not HAS_WAKELOCK:
                subprocess.run(["termux-wake-lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                HAS_WAKELOCK = True


def release_wake_lock():
    global HAS_WAKELOCK
    if "com.termux" in os.environ.get("PREFIX", "") and shutil.which("termux-wake-unlock"):
        with WAKELOCK_LOCK:
            if HAS_WAKELOCK:
                subprocess.run(["termux-wake-unlock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                HAS_WAKELOCK = False


def send_system_notification(title: str, msg: str):
    cfg = load_config()
    if not cfg.get("enable_notifications", False):
        return
    try:
        if "com.termux" in os.environ.get("PREFIX", "") and shutil.which("termux-notification"):
            subprocess.run(
                ["termux-notification", "--id", "999", "--title", title, "--content", msg, "--priority", "low"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "-a", "ShotClean", title, msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif platform.system() == "Darwin":
            subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ==============================================================================
# SCORCHED EARTH PIXEL RE-ENCODING & SUB-PERCEPTUAL PIXEL DITHERING
# ==============================================================================

def reencode_scorched_earth(filepath: Path, pixel_dither: bool = False) -> bool:
    """Demuxes raw image data, optionally applies sub-perceptual LSB dithering, and rebuilds container."""
    if filepath.suffix.lower() not in VALID_EXTENSIONS:
        return False

    try:
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                clean = Image.new(img.mode, img.size)
                pixels = list(img.getdata())

                if pixel_dither and pixels:
                    # Apply +-1 LSB jitter to ~2% of pixels to defeat perceptual hashing & LSB watermarks
                    total_px = len(pixels)
                    step = max(1, total_px // max(1, int(total_px * 0.02)))
                    if isinstance(pixels[0], tuple):
                        for idx in range(0, total_px, step):
                            px = list(pixels[idx])
                            ch_idx = idx % min(3, len(px))
                            delta = 1 if (idx % 2 == 0) else -1
                            px[ch_idx] = max(0, min(255, px[ch_idx] + delta))
                            pixels[idx] = tuple(px)
                    elif isinstance(pixels[0], int):
                        for idx in range(0, total_px, step):
                            delta = 1 if (idx % 2 == 0) else -1
                            pixels[idx] = max(0, min(255, pixels[idx] + delta))

                clean.putdata(pixels)
                save_kwargs = {}
                if filepath.suffix.lower() in (".jpg", ".jpeg"):
                    save_kwargs["quality"] = 95
                    save_kwargs["optimize"] = True
                clean.save(filepath, **save_kwargs)
                return True
        except ImportError:
            pass

        # Pure-Python fallback for PNG containers
        data = filepath.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return False

        pos = 8
        ihdr_data = None
        idat_chunks = []
        while pos < len(data):
            if pos + 8 > len(data):
                break
            length = struct.unpack(">I", data[pos:pos+4])[0]
            chunk_type = data[pos+4:pos+8]
            chunk_data = data[pos+8:pos+8+length]
            pos += 12 + length

            if chunk_type == b"IHDR":
                ihdr_data = chunk_data
            elif chunk_type == b"IDAT":
                idat_chunks.append(chunk_data)
            elif chunk_type == b"IEND":
                break

        if not ihdr_data or not idat_chunks:
            return False

        raw_idat = bytearray(zlib.decompress(b"".join(idat_chunks)))
        if pixel_dither and len(raw_idat) > 32:
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", ihdr_data)
            if bit_depth == 8 and interlace == 0:
                bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 0)
                if bpp > 0:
                    stride = 1 + width * bpp
                    if len(raw_idat) == height * stride:
                        for row in range(0, height, max(1, height // 10)):
                            row_start = row * stride
                            if raw_idat[row_start] == 0 and stride > 2:
                                col_offset = row_start + 1 + ((row * 7) % (width * bpp))
                                raw_idat[col_offset] = raw_idat[col_offset] ^ 1

        recompressed = zlib.compress(bytes(raw_idat), level=6)

        def make_chunk(tag: bytes, payload: bytes) -> bytes:
            crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
            return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

        new_png = (
            b"\x89PNG\r\n\x1a\n"
            + make_chunk(b"IHDR", ihdr_data)
            + make_chunk(b"IDAT", recompressed)
            + make_chunk(b"IEND", b"")
        )
        filepath.write_bytes(new_png)
        return True
    except Exception:
        return False


# ==============================================================================
# PER-FOLDER GRANULAR POLICIES & PRESETS
# ==============================================================================

DEFAULT_FOLDER_PROFILE = {
    "profile": "ghost",
    "strip_exif": True,
    "strip_icc": True,
    "scorched_earth": False,
    "pixel_dither": False,
    "recursive": False,
    "include_media_docs": False,
    "clamp_time": True,
    "clamp_mode": "static_2020",
    "clamp_custom_date": "2020-01-01 00:00:00",
    "clamp_mtime": True,
    "clamp_atime": True,
    "random_hash": True,
    "naming_mode": "hash",
    "prefix": "img_",
    "suffix": "",
    "casing": "lower",
    "hash_len": 12,
    "seq_padding": 4,
    "seq_counter": 1,
}

SYSTEM_PRESETS = {
    "ghost": {
        "label": "🛡️ Ghost (Full Scrub + Clamped 2020 + UUID Hash)",
        "strip_exif": True, "strip_icc": True, "scorched_earth": False, "pixel_dither": False,
        "clamp_time": True, "clamp_mode": "static_2020", "random_hash": True, "naming_mode": "hash",
        "prefix": "img_", "suffix": ""
    },
    "balanced": {
        "label": "⚖️ Balanced (Full Scrub + Word Slug - Shows in Today's Gallery)",
        "strip_exif": True, "strip_icc": True, "scorched_earth": False, "pixel_dither": False,
        "clamp_time": False, "clamp_mode": "day_fuzz", "random_hash": True, "naming_mode": "slug",
        "prefix": "", "suffix": ""
    },
    "scorched": {
        "label": "🔥 Scorched Earth (Pixel Re-encoding + Dither + Scrub + Clamped 2020)",
        "strip_exif": True, "strip_icc": True, "scorched_earth": True, "pixel_dither": True,
        "clamp_time": True, "clamp_mode": "static_2020", "random_hash": True, "naming_mode": "hash",
        "prefix": "clean_", "suffix": ""
    },
    "sequential": {
        "label": "🔢 Sequential (Full Scrub + Clean Numbering: IMG_0001)",
        "strip_exif": True, "strip_icc": True, "scorched_earth": False, "pixel_dither": False,
        "clamp_time": False, "clamp_mode": "day_fuzz", "random_hash": True, "naming_mode": "seq",
        "prefix": "IMG_", "seq_padding": 4, "suffix": ""
    },
    "metadata_only": {
        "label": "🏷️ Metadata Strip Only (Keep Original Name & Current Time)",
        "strip_exif": True, "strip_icc": True, "scorched_earth": False, "pixel_dither": False,
        "clamp_time": False, "random_hash": False, "naming_mode": "disabled"
    },
    "timestomp_only": {
        "label": "⏱️ Timestomp Only (Clamp Date to 2020, Keep Filename & EXIF)",
        "strip_exif": False, "strip_icc": False, "scorched_earth": False, "pixel_dither": False,
        "clamp_time": True, "clamp_mode": "static_2020", "random_hash": False, "naming_mode": "disabled"
    }
}


def make_folder_entry(path_str: str, profile_name="ghost") -> dict:
    p = Path(path_str)
    entry = {
        "path": str(p),
        "name": p.name or str(p),
        **DEFAULT_FOLDER_PROFILE
    }
    if profile_name in SYSTEM_PRESETS:
        entry["profile"] = profile_name
        for k, v in SYSTEM_PRESETS[profile_name].items():
            if k != "label":
                entry[k] = v
    return entry


DEFAULT_CONFIG = {
    "folders_v2": [make_folder_entry(str(detect_default_folder()), "ghost")],
    "user_presets": {},
    "enable_backup": False,
    "encrypt_vault": True,
    "vault_max_mb": 250,
    "vault_max_days": 7,
    "active_sweeper": True,
    "sweep_interval_mins": 10,
    "enable_notifications": False,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "folders" in data and "folders_v2" not in data:
                v2 = []
                for item in data["folders"]:
                    if isinstance(item, str):
                        v2.append(make_folder_entry(item, "ghost"))
                    elif isinstance(item, dict):
                        v2.append(item)
                data["folders_v2"] = v2

            for f in data.get("folders_v2", []):
                for k, v in DEFAULT_FOLDER_PROFILE.items():
                    if k not in f:
                        f[k] = v

            if "user_presets" not in data:
                data["user_presets"] = {}

            return {**DEFAULT_CONFIG, **data}
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


CONFIG = load_config()


def get_rules_for_file(filepath: Path, cfg: dict) -> dict:
    """Matches file to its most specific registered folder rule."""
    file_parent = filepath.parent.resolve()
    best_match = None
    best_len = -1

    for entry in cfg.get("folders_v2", []):
        try:
            entry_path = Path(entry["path"]).resolve()
            if file_parent == entry_path or (entry.get("recursive", False) and filepath.resolve().is_relative_to(entry_path)):
                path_len = len(str(entry_path))
                if path_len > best_len:
                    best_match = entry
                    best_len = path_len
        except Exception:
            p_str = str(entry.get("path", ""))
            if str(filepath).startswith(p_str) and len(p_str) > best_len:
                best_match = entry
                best_len = len(p_str)

    return best_match if best_match is not None else DEFAULT_FOLDER_PROFILE


def log_event(category: str, msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{category.upper():<7}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")

        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 150000:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 600:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-300:])
    except Exception:
        pass


# ==============================================================================
# KEYBOARD INPUT ENGINE (TTY RE-ATTACHMENT & FLICKER-FREE RENDERING)
# ==============================================================================

def clear_screen():
    """Flicker-free terminal clear using direct ANSI escape sequences."""
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()


def ensure_tty_stdin() -> bool:
    """Re-attaches stdin (fd 0) to /dev/tty if launched via a pipe (e.g. curl | bash)."""
    if platform.system() == "Windows":
        return sys.stdin.isatty()
    if sys.stdin.isatty():
        return True
    try:
        tty_fd = os.open("/dev/tty", os.O_RDONLY)
        os.dup2(tty_fd, 0)
        os.close(tty_fd)
        sys.stdin = open(0, "r", encoding="utf-8", errors="replace", closefd=False)
        return os.isatty(0)
    except Exception:
        return False


def read_single_key():
    if platform.system() == "Windows":
        import msvcrt
        try:
            ch = msvcrt.getch()
        except Exception:
            time.sleep(0.1)
            return ""

        if ch in (b'\x00', b'\xe0'):
            code = msvcrt.getch()
            if code == b'H': return "UP"
            elif code == b'P': return "DOWN"
            elif code == b'M': return "RIGHT"
            elif code == b'K': return "LEFT"
        elif ch in (b'\r', b'\n', b' '):
            return "ENTER"
        elif ch in (b'q', b'Q'):
            return "QUIT"
        elif ch in (b'w', b'W', b'k', b'K'):
            return "UP"
        elif ch in (b's', b'S', b'j', b'J'):
            return "DOWN"
        elif ch in (b'a', b'A', b'h', b'H'):
            return "LEFT"
        elif ch in (b'd', b'D', b'l', b'L'):
            return "RIGHT"
        elif ch == b'\x03':
            raise KeyboardInterrupt
        return ch.decode('latin1', errors='ignore')
    else:
        import termios, tty
        if not ensure_tty_stdin():
            time.sleep(0.5)
            return "NO_TTY"

        fd = 0
        try:
            old = termios.tcgetattr(fd)
        except Exception:
            time.sleep(0.5)
            return "NO_TTY"

        try:
            tty.setraw(fd)
            raw_attr = termios.tcgetattr(fd)
            raw_attr[6][termios.VMIN] = 1
            raw_attr[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, raw_attr)

            raw = os.read(fd, 32)
            if not raw:
                time.sleep(0.1)
                return ""

            if raw == b'\x1b':
                r, _, _ = select.select([fd], [], [], 0.12)
                if r:
                    raw += os.read(fd, 32)

            if raw in (b'\x1b[A', b'\x1bOA', b'\x1b[a'):
                return "UP"
            elif raw in (b'\x1b[B', b'\x1bOB', b'\x1b[b'):
                return "DOWN"
            elif raw in (b'\x1b[C', b'\x1bOC', b'\x1b[c'):
                return "RIGHT"
            elif raw in (b'\x1b[D', b'\x1bOD', b'\x1b[d'):
                return "LEFT"
            elif raw.startswith(b'\x1b'):
                if b'A' in raw: return "UP"
                if b'B' in raw: return "DOWN"
                if b'C' in raw: return "RIGHT"
                if b'D' in raw: return "LEFT"
                return "ESC"
            elif raw in (b'\r', b'\n', b' '):
                return "ENTER"
            elif raw in (b'k', b'K', b'w', b'W'):
                return "UP"
            elif raw in (b'j', b'J', b's', b'S'):
                return "DOWN"
            elif raw in (b'h', b'H', b'a', b'A'):
                return "LEFT"
            elif raw in (b'l', b'L', b'd', b'D'):
                return "RIGHT"
            elif raw in (b'q', b'Q'):
                return "QUIT"
            elif raw == b'\x03':
                raise KeyboardInterrupt
            try:
                return raw.decode('utf-8', errors='ignore')
            except Exception:
                return ""
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass


def run_arrow_menu(header_fn, items, title="COMMAND CENTER", default_idx=0, is_main=False):
    cursor = default_idx
    total = len(items)
    w = get_ui_width()
    needs_redraw = True

    while True:
        if needs_redraw:
            clear_screen()
            if header_fn:
                header_fn()

            print(f"{CLR_BORDER}╭─ {BOLD}{title}{NC} {CLR_BORDER}{'─' * max(0, w - 5 - len(title))}╮{NC}")
            for idx, (hotkey, label, _) in enumerate(items):
                disp_label = truncate_middle(label, w - 12)
                if idx == cursor:
                    print(f"{CLR_BORDER}│{NC}  {CLR_GREEN}{BOLD}▶ [{hotkey}] {disp_label}{NC}")
                else:
                    print(f"{CLR_BORDER}│{NC}    {CLR_GRAY}[{hotkey}] {disp_label}{NC}")
            print(f"{CLR_BORDER}╰{'─' * (w - 2)}╯{NC}")

            if is_main:
                print(f"  {CLR_BLUE}Move: [↑/↓ or W/S] · Open: [Enter/Space] · Exit: [0]{NC}")
            else:
                print(f"  {CLR_BLUE}Move: [↑/↓ or W/S] · Select: [Enter/Space] · Back: [Q or Left]{NC}")

        needs_redraw = False
        key = read_single_key()
        if key == "NO_TTY":
            return "exit"
        elif key == "" or key is None:
            continue
        elif key == "UP":
            cursor = (cursor - 1) % total
            needs_redraw = True
        elif key == "DOWN":
            cursor = (cursor + 1) % total
            needs_redraw = True
        elif key in ("ENTER", "RIGHT"):
            return items[cursor][2]
        elif key in ("QUIT", "ESC", "LEFT"):
            if is_main:
                continue
            else:
                for hk, _, act in items:
                    if hk in ("0", "q", "Q", "Back", "back"):
                        return act
                return "back"
        else:
            for idx, (hk, _, act) in enumerate(items):
                if key.lower() == str(hk).lower():
                    return act


# ==============================================================================
# INTERACTIVE FOLDER BROWSER
# ==============================================================================

def interactive_folder_browser(start_dir: Path = None) -> Path:
    if start_dir is None or not start_dir.exists():
        if Path("/storage/emulated/0").exists():
            cur_dir = Path("/storage/emulated/0")
        else:
            cur_dir = Path.home()
    else:
        cur_dir = start_dir.resolve()

    cursor = 0
    offset = 0
    page_size = 8
    needs_redraw = True

    while True:
        items = [("✔ [CHOOSE THIS FOLDER]", "SELECT")]
        root_parent = Path("/storage") if Path("/storage").exists() else Path("/")
        if cur_dir != root_parent and cur_dir != cur_dir.parent:
            items.append(("⬆ [.. Go Up / Parent Folder]", "UP"))

        try:
            for entry in sorted(cur_dir.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    items.append((f"📁 {entry.name}", entry))
        except (PermissionError, OSError):
            items.append(("⚠️ [Permission Denied]", "DENIED"))

        total = len(items)
        if cursor >= total: cursor = max(0, total - 1)
        if cursor < 0: cursor = 0

        if cursor < offset:
            offset = cursor
        elif cursor >= offset + page_size:
            offset = cursor - page_size + 1

        if needs_redraw:
            clear_screen()
            w = get_ui_width()
            print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  {BOLD}📁  INTERACTIVE FOLDER NAVIGATOR{NC}")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")
            print(f"  {CLR_GRAY}Location:{NC} {CLR_AMBER}{BOLD}{truncate_middle(str(cur_dir), w - 12)}{NC}")
            print(f"  {CLR_BLUE}Controls: [↑/↓ or W/S] Move · [Enter/Space] Select · [Q] Cancel{NC}")
            print(f"{CLR_BORDER}{'─' * w}{NC}")

            end_idx = min(offset + page_size, total)
            for i in range(offset, end_idx):
                item_text, _ = items[i]
                disp = truncate_middle(item_text, w - 8)
                if i == cursor:
                    print(f"  {CLR_GREEN}{BOLD}▶ {disp}{NC}")
                else:
                    print(f"    {CLR_GRAY}{disp}{NC}")

            print(f"{CLR_BORDER}{'─' * w}{NC}")
            print(f"  {DIM}Showing {cursor + 1}/{total}  (Press 'T' to type path manually){NC}")

        needs_redraw = False
        key = read_single_key()
        if key in ("NO_TTY", "QUIT", "ESC", "LEFT"):
            return None
        elif key == "" or key is None:
            continue
        elif key == "UP":
            cursor = (cursor - 1) % total
            needs_redraw = True
        elif key == "DOWN":
            cursor = (cursor + 1) % total
            needs_redraw = True
        elif key in ("ENTER", "RIGHT"):
            _, action_obj = items[cursor]
            if action_obj == "SELECT":
                return cur_dir
            elif action_obj == "UP":
                cur_dir = cur_dir.parent
                cursor = 0
                offset = 0
                needs_redraw = True
            elif action_obj != "DENIED" and isinstance(action_obj, Path):
                cur_dir = action_obj
                cursor = 0
                offset = 0
                needs_redraw = True
        elif key in ("t", "T"):
            clear_screen()
            print(f"\n  {CLR_CYAN}Manual Path Input:{NC}")
            custom = input("  Path > ").strip().strip("'\"")
            cp = Path(custom)
            if cp.exists() and cp.is_dir():
                return cp
            needs_redraw = True


# ==============================================================================
# PERSISTENT EXIFTOOL DAEMON (WITH 250-COMMAND AUTO-RECYCLE MEMORY CAP)
# ==============================================================================

class ExifToolDaemon:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.cmd_count = 0
        self._start()

    def _start(self):
        if not shutil.which("exiftool"):
            return
        try:
            self.proc = subprocess.Popen(
                ["exiftool", "-stay_open", "True", "-@", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )
            self.proc.stdin.write("-charset\nfilename=utf8\n-execute\n")
            self.proc.stdin.flush()
            while True:
                line = self.proc.stdout.readline()
                if not line or line.strip() == "{ready}":
                    break
            self.cmd_count = 0
            log_event("ENGINE", f"ExifTool persistent daemon online (PID: {self.proc.pid})")
        except Exception as e:
            log_event("ERROR", f"Failed starting ExifTool daemon: {e}")
            self.proc = None

    def _restart(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self._start()

    def execute(self, *args, timeout: float = 4.0) -> str:
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self._start()

            self.cmd_count += 1
            if self.cmd_count >= 250:
                log_event("ENGINE", "ExifTool operation cap reached (250). Auto-recycling engine memory...")
                self._restart()

            if not self.proc:
                try:
                    res = subprocess.run(
                        ["exiftool"] + list(args),
                        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace"
                    )
                    return res.stdout
                except Exception as e:
                    log_event("ERROR", f"Direct ExifTool fallback failed: {e}")
                    return ""

            cmd = "\n".join(args) + "\n-execute\n"
            try:
                self.proc.stdin.write(cmd)
                self.proc.stdin.flush()

                output_lines = []
                start_wait = time.time()

                while True:
                    if platform.system() != "Windows":
                        remaining = max(0.05, timeout - (time.time() - start_wait))
                        r, _, _ = select.select([self.proc.stdout], [], [], remaining)
                        if not r:
                            log_event("WARN", "ExifTool pipe timed out. Recycling engine...")
                            self._restart()
                            res = subprocess.run(
                                ["exiftool"] + list(args),
                                capture_output=True, text=True, timeout=3.0, encoding="utf-8", errors="replace"
                            )
                            return res.stdout

                    line = self.proc.stdout.readline()
                    if not line or line.strip() == "{ready}":
                        break
                    output_lines.append(line)

                    if time.time() - start_wait > timeout:
                        log_event("WARN", "ExifTool read safety timeout reached. Resetting.")
                        self._restart()
                        break

                return "".join(output_lines)
            except Exception as e:
                log_event("ERROR", f"Daemon I/O communication error: {e}")
                self._restart()
                return ""

    def close(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write("-stay_open\nFalse\n-execute\n")
                    self.proc.stdin.flush()
                    self.proc.communicate(timeout=1.0)
                except Exception:
                    self.proc.kill()
                self.proc = None


EXIFTOOL_ENGINE = ExifToolDaemon()

# ==============================================================================
# VAULT ENCRYPTION, EXTENSION PRESERVATION & AUTO-PRUNING QUOTA
# ==============================================================================

def get_vault_secret() -> str:
    if VAULT_KEY_FILE.exists():
        try:
            return VAULT_KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    secret = uuid.uuid4().hex + uuid.uuid4().hex
    VAULT_KEY_FILE.write_text(secret, encoding="utf-8")
    return secret


def encrypt_payload(data: bytes, key: str) -> bytes:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, 100000)
    nonce = os.urandom(12)
    out = bytearray(len(data))
    block_idx = 0
    for i in range(0, len(data), 32):
        keystream = hashlib.sha256(derived + nonce + block_idx.to_bytes(4, "big")).digest()
        chunk_len = min(32, len(data) - i)
        for j in range(chunk_len):
            out[i + j] = data[i + j] ^ keystream[j]
        block_idx += 1
    tag = hashlib.sha256(derived + salt + nonce + out).digest()
    return b"ENC1" + salt + nonce + tag + bytes(out)


def decrypt_payload(data: bytes, key: str) -> bytes:
    if not data.startswith(b"ENC1"):
        raise ValueError("Invalid format: Not an encrypted ShotClean vault archive.")
    salt = data[4:20]
    nonce = data[20:32]
    tag = data[32:64]
    ciphertext = data[64:]
    derived = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, 100000)
    expected_tag = hashlib.sha256(derived + salt + nonce + ciphertext).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Decryption failed: Integrity check mismatch.")
    out = bytearray(len(ciphertext))
    block_idx = 0
    for i in range(0, len(ciphertext), 32):
        keystream = hashlib.sha256(derived + nonce + block_idx.to_bytes(4, "big")).digest()
        chunk_len = min(32, len(ciphertext) - i)
        for j in range(chunk_len):
            out[i + j] = ciphertext[i + j] ^ keystream[j]
        block_idx += 1
    return bytes(out)


def prune_vault_storage(cfg: dict):
    """Automatically prunes expired backups or enforces MB quota on ~/.shotclean/vault."""
    try:
        max_days = int(cfg.get("vault_max_days", 7))
        max_mb = int(cfg.get("vault_max_mb", 250))
        now = time.time()
        files = [f for f in VAULT_DIR.glob("*") if f.is_file()]

        # 1. Prune by age
        if max_days > 0:
            cutoff = now - (max_days * 86400)
            for vf in list(files):
                try:
                    if vf.stat().st_mtime < cutoff:
                        vf.unlink()
                        files.remove(vf)
                except OSError:
                    pass

        # 2. Prune oldest files if total size exceeds max_mb
        if max_mb > 0 and files:
            max_bytes = max_mb * 1024 * 1024
            files.sort(key=lambda f: f.stat().st_mtime)
            total_bytes = sum(f.stat().st_size for f in files)
            while total_bytes > max_bytes and files:
                oldest = files.pop(0)
                try:
                    sz = oldest.stat().st_size
                    oldest.unlink()
                    total_bytes -= sz
                except OSError:
                    pass
    except Exception:
        pass


def create_synthetic_png(target_path: Path):
    width, height = 200, 200
    raw_scanlines = b"".join(b"\x00" + b"\x1e\x88\xe5" * width for _ in range(height))
    compressed_idat = zlib.compress(raw_scanlines)

    def write_chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + write_chunk(b"IHDR", ihdr_data)
        + write_chunk(b"IDAT", compressed_idat)
        + write_chunk(b"IEND", b"")
    )
    target_path.write_bytes(png_bytes)


# ==============================================================================
# SEQUENTIAL NUMBERING & NAMING ENGINE
# ==============================================================================

SLUG_ADJECTIVES = (
    "swift", "silent", "amber", "quiet", "frost", "brave", "calm", "neon",
    "solar", "lunar", "shadow", "crimson", "azure", "mystic", "rapid", "steel",
    "wild", "subtle", "vivid", "dark", "bright", "golden", "silver", "gentle",
    "bold", "zenith", "polar", "cosmic", "astral", "rustic"
)

SLUG_NOUNS = (
    "falcon", "river", "pebble", "ember", "wolf", "canyon", "harbor", "summit",
    "meadow", "breeze", "orbit", "comet", "forest", "shield", "echo", "beacon",
    "island", "feather", "glacier", "ridge", "lotus", "sparrow", "crystal", "horizon",
    "valley", "timber", "aurora", "pulsar", "grove", "quartz"
)

GENERATED_NAMES_HISTORY = collections.deque(maxlen=600)


def get_next_sequence_number(folder: Path, rules: dict, preview=False) -> int:
    counter = rules.get("seq_counter", 1)
    prefix = rules.get("prefix", "IMG_")
    padding = rules.get("seq_padding", 4)
    suffix = rules.get("suffix", "")
    casing = rules.get("casing", "lower")

    if preview:
        return counter

    while True:
        token = str(counter).zfill(padding)
        candidate_base = f"{prefix}{token}{suffix}"
        if casing == "upper":
            candidate_base = candidate_base.upper()
        else:
            candidate_base = candidate_base.lower()

        matched = False
        for ext in ALL_SUPPORTED_EXTENSIONS:
            if (folder / f"{candidate_base}{ext}").exists() or (folder / f"{candidate_base.upper()}{ext.upper()}").exists():
                counter += 1
                matched = True
                break
        if not matched:
            break

    rules["seq_counter"] = counter + 1
    cfg = load_config()
    for f in cfg.get("folders_v2", []):
        try:
            if Path(f.get("path", "")).resolve() == Path(rules.get("path", "")).resolve():
                f["seq_counter"] = counter + 1
                break
        except Exception:
            pass
    save_config(cfg)
    return counter


def generate_sanitized_filename(filepath: Path, rules: dict, preview=False) -> str:
    mode = rules.get("naming_mode", "hash")
    ext = filepath.suffix.lower()
    now = time.localtime()
    date_stamp = time.strftime("%Y%m%d", now)
    suffix = rules.get("suffix", "")
    casing = rules.get("casing", "lower")

    if mode == "disabled" or not rules.get("random_hash", True):
        return filepath.name

    elif mode == "seq":
        seq_num = get_next_sequence_number(filepath.parent, rules, preview=preview)
        padding = int(rules.get("seq_padding", 4))
        seq_str = str(seq_num).zfill(padding)
        prefix = rules.get("prefix", "IMG_")
        base = f"{prefix}{seq_str}"
        if suffix: base += f"_{suffix}"
        res = f"{base}{ext}"

    elif mode == "slug":
        adj = random.choice(SLUG_ADJECTIVES)
        noun = random.choice(SLUG_NOUNS)
        num = random.randint(10, 99)
        base = f"{adj}-{noun}-{num}"
        if suffix: base += f"_{suffix}"
        res = f"{base}{ext}"

    elif mode == "decoy_wa":
        seq = random.randint(1, 9999)
        res = f"IMG-{date_stamp}-WA{seq:04d}{ext}"

    elif mode == "decoy_dcim":
        seq = random.randint(1000, 9999)
        res = f"DSC_{seq:04d}{ext}"

    elif mode == "decoy_reddit":
        ts = f"{random.randint(0,23):02d}{random.randint(0,59):02d}{random.randint(0,59):02d}"
        res = f"RDT_{date_stamp}_{ts}{ext}"

    else:
        prefix = rules.get("prefix", "img_")
        h_len = int(rules.get("hash_len", 12))
        token = uuid.uuid4().hex[:h_len]
        base = f"{prefix}{token}"
        if suffix: base += f"_{suffix}"
        res = f"{base}{ext}"

    return res.upper() if casing == "upper" else res.lower()


# ==============================================================================
# ANTI-FORENSIC TIMESTOMP CLAMPING ENGINE
# ==============================================================================

def compute_clamp_epoch(rules: dict) -> float:
    mode = rules.get("clamp_mode", "static_2020")
    if mode == "static_2020":
        return 1577836800.0
    elif mode == "epoch_1970":
        return 315532800.0 if platform.system() == "Windows" else 0.0
    elif mode == "day_fuzz":
        now = time.localtime()
        midnight = time.struct_time((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
        return time.mktime(midnight)
    elif mode == "random_fuzz":
        return float(random.randint(1577836800, 1672531199))
    elif mode == "custom":
        custom_str = rules.get("clamp_custom_date", "2020-01-01 00:00:00")
        try:
            st = time.strptime(custom_str, "%Y-%m-%d %H:%M:%S")
            return time.mktime(st)
        except Exception:
            return 1577836800.0
    return 1577836800.0


# ==============================================================================
# SYSTEM DOCTOR
# ==============================================================================

class SystemDoctor:
    @staticmethod
    def get_os_string():
        if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
            return "Android (Termux)"
        elif platform.system() == "Darwin":
            return "macOS"
        elif platform.system() == "Windows":
            return f"Windows ({platform.release()})"
        return f"Linux ({platform.release()})"

    @classmethod
    def check_and_install(cls, interactive=True):
        missing_pip = []
        missing_bins = []

        try:
            import watchdog
        except ImportError:
            missing_pip.append("watchdog")

        if not shutil.which("exiftool"):
            missing_bins.append("exiftool")

        if not missing_pip and not missing_bins:
            return True

        if not interactive or not sys.stdin.isatty() or any(arg in sys.argv for arg in ("-h", "--help")):
            return False

        print(f"\n{CLR_CYAN}╭──────────────────────────────────────────────────────╮{NC}")
        print(f"{CLR_CYAN}│{NC}  {BOLD}🩺  SHOTCLEAN · System Health & Pre-Flight Check{NC}   {CLR_CYAN}│{NC}")
        print(f"{CLR_CYAN}╰──────────────────────────────────────────────────────╯{NC}")
        print(f"  {CLR_GRAY}Detected OS:{NC} {BOLD}{cls.get_os_string()}{NC}\n")

        if missing_pip:
            print(f"  {CLR_RED}[✖]{NC} Python library: 'watchdog' {CLR_AMBER}(Missing){NC}")
        else:
            print(f"  {CLR_GREEN}[✔]{NC} Python library: 'watchdog' (Installed)")

        if missing_bins:
            print(f"  {CLR_RED}[✖]{NC} Core binary   : 'exiftool' {CLR_AMBER}(Missing from PATH){NC}")
        else:
            print(f"  {CLR_GREEN}[✔]{NC} Core binary   : 'exiftool' (Installed)")

        choice = input("\n  Install dependencies automatically? [Y/n]: ").strip().lower()
        if choice in ["n", "no"]:
            print(f"\n  {CLR_RED}Dependencies missing. Exiting...{NC}")
            sys.exit(1)

        if missing_pip:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])
            except subprocess.CalledProcessError:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog", "--break-system-packages"])

        if "exiftool" in missing_bins:
            os_name = cls.get_os_string()
            if "Android" in os_name:
                subprocess.check_call(["pkg", "install", "-y", "exiftool"])
            elif "macOS" in os_name and shutil.which("brew"):
                subprocess.check_call(["brew", "install", "exiftool"])
            elif "Windows" in os_name and shutil.which("winget"):
                subprocess.check_call(["winget", "install", "OliverBetz.ExifTool"])
            elif shutil.which("apt-get"):
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "libimage-exiftool-perl"])
            elif shutil.which("pacman"):
                subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "perl-image-exiftool"])

        print(f"\n  {CLR_GREEN}{BOLD}✔ All dependencies ready!{NC}\n")
        time.sleep(1)
        return True


SystemDoctor.check_and_install(interactive=True)

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    class FileSystemEventHandler:
        pass
    Observer = None

# ==============================================================================
# WORKER QUEUE & SANITIZATION ENGINE
# ==============================================================================

WORK_QUEUE = queue.Queue()
PROCESSED_COOLDOWN = {}


def clean_expired_cooldowns():
    now = time.time()
    expired = [k for k, t in PROCESSED_COOLDOWN.items() if now - t > 60.0]
    for k in expired:
        del PROCESSED_COOLDOWN[k]


def file_settling_probe(filepath: Path, timeout: float = 5.0) -> bool:
    start_time = time.time()
    last_size = -1
    while time.time() - start_time < timeout:
        try:
            if not filepath.exists():
                return False
            cur_size = filepath.stat().st_size
            if cur_size == 0 or cur_size != last_size:
                last_size = cur_size
                time.sleep(0.15)
                continue
            with open(filepath, "r+b"):
                return True
        except (PermissionError, IOError, OSError):
            time.sleep(0.15)
    return False


def sanitize_single_file(filepath: Path) -> Path:
    """Core pipeline: scrubs, re-encodes, renames, clamps, and records in persistent ledger."""
    cfg = load_config()
    rules = get_rules_for_file(filepath, cfg)

    prefix = rules.get("prefix", "")
    mode = rules.get("naming_mode", "hash")

    if not filepath.exists() or filepath.name.startswith("."):
        return filepath
    if filepath.name in GENERATED_NAMES_HISTORY or is_file_in_ledger(filepath):
        return filepath
    if prefix and filepath.name.startswith(prefix) and mode in ("hash", "seq"):
        record_file_in_ledger(filepath)
        return filepath

    log_event("PROBE", f"Interception: {filepath.name} [{rules.get('profile', 'custom').upper()}]")
    if not file_settling_probe(filepath):
        return filepath

    file_key = f"{filepath.name}_{filepath.stat().st_size}"
    if len(PROCESSED_COOLDOWN) > 200:
        clean_expired_cooldowns()

    now = time.time()
    if file_key in PROCESSED_COOLDOWN and (now - PROCESSED_COOLDOWN[file_key]) < 4.0:
        return filepath
    PROCESSED_COOLDOWN[file_key] = now

    # 1. Encrypted Safety Vault Backup (Preserves Original Extension)
    if cfg.get("enable_backup", False):
        try:
            raw_bytes = filepath.read_bytes()
            t_token = int(time.time())
            ext_sfx = filepath.suffix.lower() or ".png"
            if cfg.get("encrypt_vault", True):
                sec = get_vault_secret()
                enc = encrypt_payload(raw_bytes, sec)
                (VAULT_DIR / f"{filepath.stem}_{t_token}{ext_sfx}.enc").write_bytes(enc)
            else:
                (VAULT_DIR / f"{filepath.stem}_{t_token}{ext_sfx}").write_bytes(raw_bytes)
            prune_vault_storage(cfg)
        except Exception as ex:
            log_event("ERROR", f"Vault backup failed: {ex}")

    # 2. Scorched Earth Deep Re-encoding & Optional LSB Dithering
    if rules.get("scorched_earth", False):
        dither = bool(rules.get("pixel_dither", False))
        if reencode_scorched_earth(filepath, pixel_dither=dither):
            log_event("SCORCH", f"Pixel-level canvas re-encoded (dither={dither}): {filepath.name}")

    # 3. ExifTool Scrubbing
    if rules.get("strip_exif", True):
        args = ["-all="]
        if rules.get("strip_icc", True):
            args.append("-icc_profile:all=")
        if not rules.get("clamp_time", True):
            args.append("-P")
        args.extend(["-overwrite_original_in_place", str(filepath)])

        t0 = time.time()
        EXIFTOOL_ENGINE.execute(*args, timeout=4.0)
        elapsed_ms = int((time.time() - t0) * 1000)
        log_event("EXIF", f"Scrubbed EXIF/ICC profiles in {elapsed_ms}ms")

    target_path = filepath
    old_original_path = filepath

    # 4. Renaming
    if rules.get("random_hash", True) and mode != "disabled":
        new_name = generate_sanitized_filename(filepath, rules)
        target_path = filepath.parent / new_name

        try:
            if target_path != filepath:
                if target_path.exists():
                    token = uuid.uuid4().hex[:4]
                    target_path = filepath.parent / f"{target_path.stem}_{token}{target_path.suffix}"
                GENERATED_NAMES_HISTORY.append(target_path.name)
                os.replace(filepath, target_path)
                log_event("RENAME", f"Renamed ({mode}): {filepath.name} -> {target_path.name}")
            else:
                GENERATED_NAMES_HISTORY.append(target_path.name)
        except OSError as e:
            log_event("ERROR", f"Rename error: {e}")
            target_path = filepath

    # 5. Anti-Forensic Timestamp Clamping
    if rules.get("clamp_time", True):
        try:
            target_epoch = compute_clamp_epoch(rules)
            curr_stat = target_path.stat()
            atime = target_epoch if rules.get("clamp_atime", True) else curr_stat.st_atime
            mtime = target_epoch if rules.get("clamp_mtime", True) else curr_stat.st_mtime
            os.utime(target_path, (atime, mtime))
            log_event("TIMESTOMP", f"Clamped ({rules.get('clamp_mode', 'static_2020')}): mtime={time.ctime(mtime)}")
        except OSError:
            pass

    # Record final file state in persistent ledger so restarts never re-rename it
    record_file_in_ledger(target_path)

    # 6. Android MediaStore Pruning & Invalidation
    if "com.termux" in os.environ.get("PREFIX", ""):
        if old_original_path != target_path:
            subprocess.run(
                ["content", "delete", "--uri", "content://media/external/images/media", "--where", f"_data='{old_original_path}'"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{old_original_path}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        if shutil.which("termux-media-scan"):
            subprocess.run(["termux-media-scan", str(target_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    send_system_notification("ShotClean Shield", f"Sanitized: {target_path.name}")
    log_event("COMPLETE", f"✔ Sanitized via [{rules.get('profile', 'custom').upper()}]: {target_path.name}")
    return target_path


def sanitization_worker():
    global SESSION_CLEANED_COUNT
    while True:
        filepath = WORK_QUEUE.get()
        if filepath is None:
            break

        acquire_wake_lock()
        try:
            res = sanitize_single_file(filepath)
            if res:
                SESSION_CLEANED_COUNT += 1
        except Exception as ex:
            log_event("ERROR", f"Worker uncaught exception: {ex}")
        finally:
            WORK_QUEUE.task_done()
            if WORK_QUEUE.empty():
                release_wake_lock()


WORKER_THREAD = threading.Thread(target=sanitization_worker, daemon=True)
WORKER_THREAD.start()

# ==============================================================================
# ACTIVE DIRECTORY SWEEPER ENGINE (CATCH-UP & PERIODIC)
# ==============================================================================

def check_file_has_metadata(filepath: Path) -> bool:
    """Fast probe: checks if file contains EXIF, XMP, IPTC, or ICC tags."""
    try:
        out = EXIFTOOL_ENGINE.execute("-exif:all", "-xmp:all", "-iptc:all", "-icc_profile:all", "-s", str(filepath), timeout=2.0)
        return bool(out.strip())
    except Exception:
        return False


def iter_monitored_files(folder_path: Path, folder_cfg: dict):
    """Yields matching files in folder_path respecting recursive and media/doc settings."""
    exts = get_valid_extensions_for_rules(folder_cfg)
    recursive = bool(folder_cfg.get("recursive", False))
    iterator = folder_path.rglob("*") if recursive else folder_path.glob("*")
    for item in iterator:
        try:
            if not item.is_file() or item.name.startswith("."):
                continue
            if ".shotclean" in item.parts:
                continue
            if item.suffix.lower() in exts:
                yield item
        except OSError:
            continue


def run_active_directory_sweep():
    """Scans all monitored folders for unscrubbed files taken while offline."""
    cfg = load_config()
    if not cfg.get("active_sweeper", True):
        return

    log_event("SWEEPER", "Active Directory Sweep started...")
    total_found = 0

    for folder_cfg in cfg.get("folders_v2", []):
        p = Path(folder_cfg.get("path", ""))
        if not p.exists():
            continue

        prefix = folder_cfg.get("prefix", "")
        mode = folder_cfg.get("naming_mode", "hash")

        for img in iter_monitored_files(p, folder_cfg):
            if img.name in GENERATED_NAMES_HISTORY or is_file_in_ledger(img):
                continue

            is_cleaned_name = prefix and img.name.startswith(prefix) and mode in ("hash", "seq")
            if is_cleaned_name:
                if not check_file_has_metadata(img):
                    record_file_in_ledger(img)
                    continue

            # If naming_mode is disabled (Metadata Only / Timestomp Only), only queue if metadata or timestamp is uncleaned
            if mode == "disabled" or not folder_cfg.get("random_hash", True):
                needs_exif = folder_cfg.get("strip_exif", True) and check_file_has_metadata(img)
                needs_clamp = False
                if folder_cfg.get("clamp_time", True):
                    target_ep = compute_clamp_epoch(folder_cfg)
                    if abs(img.stat().st_mtime - target_ep) > 60:
                        needs_clamp = True
                if not needs_exif and not needs_clamp:
                    record_file_in_ledger(img)
                    continue

            WORK_QUEUE.put(img)
            total_found += 1
            time.sleep(0.05)

    if total_found > 0:
        log_event("SWEEPER", f"Active Sweep queued {total_found} unscrubbed file(s) for sanitization.")
    else:
        log_event("SWEEPER", "Active Sweep completed: 100% clean.")


def sweeper_daemon_thread():
    """Background periodic heartbeat daemon."""
    time.sleep(3)
    run_active_directory_sweep()

    while True:
        cfg = load_config()
        interval = int(cfg.get("sweep_interval_mins", 10))
        if interval <= 0 or not cfg.get("active_sweeper", True):
            time.sleep(60)
            continue
        time.sleep(interval * 60)
        run_active_directory_sweep()


threading.Thread(target=sweeper_daemon_thread, daemon=True).start()


class AsyncWatchHandler(FileSystemEventHandler):
    def _handle_path(self, raw_path: str):
        p = Path(raw_path)
        cfg = load_config()
        rules = get_rules_for_file(p, cfg)
        if p.suffix.lower() in get_valid_extensions_for_rules(rules):
            WORK_QUEUE.put(p)

    def on_created(self, event):
        if not event.is_directory:
            self._handle_path(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_path(event.dest_path)


class DaemonManager:
    observer = None
    is_running = False

    @classmethod
    def start(cls):
        if cls.is_running:
            return
        cfg = load_config()
        valid_entries = [f for f in cfg.get("folders_v2", []) if Path(f["path"]).exists()]
        if not valid_entries:
            log_event("WARN", "No registered folders exist on disk to monitor.")
            return

        if Observer is None:
            log_event("ERROR", "watchdog library is missing. Cannot start directory watcher.")
            return
        cls.observer = Observer()
        handler = AsyncWatchHandler()
        for f_entry in valid_entries:
            cls.observer.schedule(
                handler,
                path=str(f_entry["path"]),
                recursive=bool(f_entry.get("recursive", False)),
            )

        cls.observer.start()
        cls.is_running = True
        log_event("DAEMON", f"Background watcher online. Tracking {len(valid_entries)} folder(s).")
        threading.Thread(target=run_active_directory_sweep, daemon=True).start()

    @classmethod
    def stop(cls):
        if not cls.is_running or not cls.observer:
            return
        cls.observer.stop()
        cls.observer.join()
        cls.is_running = False
        cls.observer = None
        log_event("DAEMON", "Background watcher halted.")

    @classmethod
    def restart(cls):
        if cls.is_running:
            cls.stop()
            cls.start()


# ==============================================================================
# MAIN DASHBOARD RENDERER
# ==============================================================================

def draw_main_header():
    w = get_ui_width()
    cfg = load_config()
    folders = cfg.get("folders_v2", [])
    status_text = f"{CLR_GREEN}● RUNNING{NC}" if DaemonManager.is_running else f"{CLR_RED}○ STOPPED{NC}"

    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🛡️  S H O T C L E A N{NC}  {CLR_GRAY}·{NC}  {CLR_PURPLE}v{CURRENT_VERSION} Studio{NC}")
    print(f"{CLR_CYAN}│{NC}  {DIM}Zero-Footprint Anti-Forensics & Granular Shield{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")

    if UPDATE_AVAILABLE:
        print(f"{CLR_AMBER}╭─ {BOLD}🔔 UPDATE AVAILABLE{NC} {CLR_AMBER}{'─' * max(0, w - 24)}╮{NC}")
        print(f"{CLR_AMBER}│{NC}  Commit {BOLD}{REMOTE_COMMIT_SHORT}{NC} ready · Select Option [13] to install")
        print(f"{CLR_AMBER}╰{'─' * (w - 2)}╯{NC}")

    pipe_status = f"{CLR_GREEN}Active (-stay_open){NC}"
    vault_status = f"{CLR_GREEN}ON (AES · {cfg.get('vault_max_mb', 250)}MB Cap){NC}" if cfg.get("enable_backup") else f"{CLR_GRAY}OFF{NC}"
    sweep_status = f"{CLR_GREEN}ON (Every {cfg.get('sweep_interval_mins', 10)}m){NC}" if cfg.get("active_sweeper", True) else f"{CLR_GRAY}OFF{NC}"

    print(f"{CLR_BLUE}╭─ {BOLD}SYSTEM & ENGINE HEALTH{NC} {CLR_BLUE}{'─' * max(0, w - 26)}╮{NC}")
    print(f"{CLR_BLUE}│{NC} Engine State : {status_text}   {CLR_GRAY}(Session scrubbed: {SESSION_CLEANED_COUNT}){NC}")
    print(f"{CLR_BLUE}│{NC} Auto-Sweeper : {sweep_status}  ·  ExifTool: {pipe_status}")
    print(f"{CLR_BLUE}│{NC} Backup Vault : {vault_status}")
    print(f"{CLR_BLUE}╰{'─' * (w - 2)}╯{NC}")

    print(f"{CLR_AMBER}╭─ {BOLD}MONITORED FOLDERS ({len(folders)}){NC} {CLR_AMBER}{'─' * max(0, w - 26)}╮{NC}")
    if not folders:
        print(f"{CLR_AMBER}│{NC}  {CLR_RED}No folders registered! Add one below.{NC}")
    else:
        for f in folders[:3]:
            p_label = f.get("profile", "custom").upper()
            rec_tag = " [R]" if f.get("recursive") else ""
            path_disp = truncate_middle(f.get("path", ""), w - 28)
            print(f"{CLR_AMBER}│{NC}  📁 {BOLD}{path_disp}{NC} [{CLR_GREEN}{p_label}{rec_tag}{NC}]")
        if len(folders) > 3:
            print(f"{CLR_AMBER}│{NC}  {CLR_GRAY}...and {len(folders) - 3} more folder(s){NC}")
    print(f"{CLR_AMBER}╰{'─' * (w - 2)}╯{NC}")


# ==============================================================================
# SUBMENU: ACTIVE SWEEPER SETTINGS
# ==============================================================================

def tool_manage_sweeper():
    while True:
        cfg = load_config()
        w = get_ui_width()
        enabled = cfg.get("active_sweeper", True)
        interval = cfg.get("sweep_interval_mins", 10)
        ledger_count = len(_load_ledger_unlocked())

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 ACTIVE EXIF SWEEPER & CATCH-UP GUARD{NC} {CLR_CYAN}{'─' * max(0, w - 43)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Automatically finds and scrubs photos taken while ShotClean was OFF.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Catch-Up Sweep{NC}   : Scans on startup when you launch the app.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Periodic Guard{NC}   : Checks every {interval} mins in background.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Scrubbed Ledger{NC}  : {ledger_count} verified clean files tracked across restarts.")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        menu_items = [
            ("1", f"⚡ Toggle Active Sweeper [{'🟢 ON' if enabled else '⚪ OFF'}]", "toggle"),
            ("2", "🧹 Trigger Immediate Catch-Up Sweep Now", "run_now"),
            ("3", f"⏱️  Set Periodic Sweep Frequency [{interval} mins]", "interval"),
            ("4", f"🗑️  Reset Scrubbed File Ledger ({ledger_count} entries)", "clear_ledger"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="SWEEPER SETTINGS")

        if action == "toggle":
            cfg["active_sweeper"] = not enabled
            save_config(cfg)

        elif action == "run_now":
            clear_screen()
            print(f"\n  {CLR_CYAN}Running active folder sweep across all monitored paths...{NC}\n")
            run_active_directory_sweep()
            print(f"\n  {CLR_GREEN}{BOLD}✔ Sweep complete! Any unscrubbed files were queued.{NC}\n")
            time.sleep(1.2)

        elif action == "interval":
            def int_header():
                print(f"{CLR_CYAN}=== Select Background Sweep Frequency ==={NC}\n")
            i_items = [
                ("1", "Every 5 Minutes (Maximum Coverage)", 5),
                ("2", "Every 10 Minutes (Recommended Balance)", 10),
                ("3", "Every 30 Minutes (Battery Saver)", 30),
                ("4", "Startup Only (No Background Sweeps)", 0),
                ("0", "🔙 Cancel", "back"),
            ]
            chosen_i = run_arrow_menu(int_header, i_items, title="SWEEP INTERVAL")
            if chosen_i is not None and chosen_i != "back":
                cfg["sweep_interval_mins"] = chosen_i
                save_config(cfg)

        elif action == "clear_ledger":
            with LEDGER_LOCK:
                _save_ledger_unlocked({})
            print(f"\n  {CLR_GREEN}✔ Scrubbed ledger cleared.{NC}")
            time.sleep(0.8)

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: CUSTOM PRESET STUDIO
# ==============================================================================

def tool_manage_presets():
    while True:
        cfg = load_config()
        w = get_ui_width()
        user_presets = cfg.get("user_presets", {})
        folders = cfg.get("folders_v2", [])

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 CUSTOM PRESET STUDIO{NC} {CLR_CYAN}{'─' * max(0, w - 27)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Create and manage reusable privacy rule profiles.")
            print(f"{CLR_CYAN}│{NC}  Saved Presets: {BOLD}{len(user_presets)}{NC} custom preset(s) active.")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        menu_items = [
            ("1", "➕ Save Current Folder #1 Settings as New Preset", "save_current"),
        ]

        idx = 2
        for p_name in sorted(user_presets.keys()):
            menu_items.append((str(idx), f"🚀 Apply Preset: '{p_name}' to a Folder", ("apply", p_name)))
            idx += 1
            menu_items.append((str(idx), f"🗑️  Delete Preset: '{p_name}'", ("delete", p_name)))
            idx += 1

        menu_items.append(("0", "🔙 Back to Main Menu", "back"))

        action = run_arrow_menu(header_card, menu_items, title="PRESET STUDIO")

        if action == "save_current":
            clear_screen()
            if not folders:
                print(f"  {CLR_RED}No folders registered to extract settings from.{NC}"); time.sleep(1); continue

            src = folders[0]
            print(f"\n  {CLR_CYAN}Creating Preset from Folder: '{src['path']}'{NC}")
            name = input("  Enter a name for this custom preset: ").strip()
            if not name:
                continue

            sanitized_name = "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-")).lower()
            user_presets[sanitized_name] = {
                "label": f"⭐ {name}",
                "strip_exif": src.get("strip_exif", True),
                "strip_icc": src.get("strip_icc", True),
                "scorched_earth": src.get("scorched_earth", False),
                "pixel_dither": src.get("pixel_dither", False),
                "recursive": src.get("recursive", False),
                "include_media_docs": src.get("include_media_docs", False),
                "clamp_time": src.get("clamp_time", True),
                "clamp_mode": src.get("clamp_mode", "static_2020"),
                "clamp_custom_date": src.get("clamp_custom_date", "2020-01-01 00:00:00"),
                "clamp_mtime": src.get("clamp_mtime", True),
                "clamp_atime": src.get("clamp_atime", True),
                "random_hash": src.get("random_hash", True),
                "naming_mode": src.get("naming_mode", "hash"),
                "prefix": src.get("prefix", "img_"),
                "suffix": src.get("suffix", ""),
                "casing": src.get("casing", "lower"),
                "seq_padding": src.get("seq_padding", 4),
            }
            cfg["user_presets"] = user_presets
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Custom preset '{sanitized_name}' saved!{NC}")
            time.sleep(1)

        elif isinstance(action, tuple) and action[0] == "apply":
            p_name = action[1]
            p_data = user_presets.get(p_name)
            if p_data and folders:
                def pick_folder_header():
                    print(f"{CLR_CYAN}=== Apply Preset '{p_name}' to Which Folder? ==={NC}\n")
                f_items = [(str(i + 1), f["path"], i) for i, f in enumerate(folders)]
                f_items.append(("A", "🚀 Apply to ALL Registered Folders", "ALL"))
                f_items.append(("0", "🔙 Cancel", "back"))
                pick = run_arrow_menu(pick_folder_header, f_items, title="SELECT TARGET")
                if pick == "ALL":
                    for f in folders:
                        f["profile"] = p_name
                        for k, v in p_data.items():
                            if k != "label": f[k] = v
                    save_config(cfg); DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Applied to all folders!{NC}"); time.sleep(1)
                elif isinstance(pick, int) and pick < len(folders):
                    target = folders[pick]
                    target["profile"] = p_name
                    for k, v in p_data.items():
                        if k != "label": target[k] = v
                    save_config(cfg); DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Applied to {target['name']}!{NC}"); time.sleep(1)

        elif isinstance(action, tuple) and action[0] == "delete":
            p_name = action[1]
            if p_name in user_presets:
                del user_presets[p_name]
                cfg["user_presets"] = user_presets
                save_config(cfg)
                print(f"\n  {CLR_GREEN}✔ Preset '{p_name}' deleted.{NC}")
                time.sleep(0.8)

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: MANAGE FOLDERS & GRANULAR RULES
# ==============================================================================

def tool_manage_folders():
    cursor_idx = 0
    while True:
        cfg = load_config()
        folders = cfg.get("folders_v2", [])
        w = get_ui_width()

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW PER-FOLDER RULES WORK{NC} {CLR_CYAN}{'─' * max(0, w - 32)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Assign independent security policies per directory:")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}GHOST{NC}      : Wipes EXIF/ICC + 2020 clamp + random hash.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}BALANCED{NC}   : Wipes EXIF/ICC + readable slug (shows Today).")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}SCORCHED{NC}   : Pixel re-encoding + LSB dither + full strip.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}SEQUENTIAL{NC} : Scrub + structured sequential counters.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}METADATA{NC}   : Wipes EXIF/ICC only (keeps filename intact).")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")
            print(f"  {BOLD}Registered Directories ({len(folders)}):{NC}")
            for idx, f in enumerate(folders, 1):
                p = Path(f["path"])
                status = f"{CLR_GREEN}Active{NC}" if p.exists() else f"{CLR_RED}Missing Path{NC}"
                rec_badge = " · Recursive" if f.get("recursive") else ""
                disp = truncate_middle(f["path"], w - 28)
                print(f"  [{idx}] {BOLD}{disp}{NC} [{CLR_AMBER}{f.get('profile', 'custom').upper()}{rec_badge}{NC}] ({status})")
            print()

        menu_items = [
            ("A", "➕ Add New Folder (Arrow Navigator)", "add_arrow"),
            ("T", "✍️  Add by Manual Path Entry", "add_manual"),
            ("P", "⚡ Quick Preset: Add Default Screenshots Folder", "add_preset"),
        ]

        for i, f in enumerate(folders):
            label = f"⚙️  Configure Rules: {Path(f['path']).name or f['path']}"
            menu_items.append((str(i + 1), label, ("config", i)))

        menu_items.append(("0", "🔙 Back to Main Menu", "back"))

        action = run_arrow_menu(header_card, menu_items, title="FOLDERS & RULES", default_idx=cursor_idx)

        if action == "add_arrow":
            chosen = interactive_folder_browser()
            if chosen and chosen.exists():
                str_p = str(chosen)
                if not any(f["path"] == str_p for f in folders):
                    folders.append(make_folder_entry(str_p, "ghost"))
                    cfg["folders_v2"] = folders
                    save_config(cfg)
                    DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Added: {chosen.name} [Default: GHOST policy]{NC}")
                    time.sleep(1)

        elif action == "add_manual":
            clear_screen()
            manual = input("\n  Enter full folder path: ").strip().strip("'\"")
            mp = Path(manual)
            if mp.exists() and mp.is_dir():
                if not any(f["path"] == str(mp) for f in folders):
                    folders.append(make_folder_entry(str(mp), "ghost"))
                    cfg["folders_v2"] = folders
                    save_config(cfg)
                    DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Added: {mp.name}{NC}")
                    time.sleep(1)
            else:
                print(f"  {CLR_RED}✖ Path does not exist or is not a directory.{NC}")
                time.sleep(1)

        elif action == "add_preset":
            def_path = str(detect_default_folder())
            if not any(f["path"] == def_path for f in folders):
                folders.append(make_folder_entry(def_path, "ghost"))
                cfg["folders_v2"] = folders
                save_config(cfg)
                DaemonManager.restart()
                print(f"\n  {CLR_GREEN}✔ Added default screenshots folder!{NC}")
                time.sleep(1)

        elif isinstance(action, tuple) and action[0] == "config":
            configure_individual_folder(action[1])

        elif action in ("back", None):
            break


def configure_individual_folder(index: int):
    while True:
        cfg = load_config()
        folders = cfg.get("folders_v2", [])
        if index >= len(folders):
            return

        f = folders[index]
        w = get_ui_width()

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 POLICY BREAKDOWN FOR THIS FOLDER{NC} {CLR_CYAN}{'─' * max(0, w - 38)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Target: {CLR_WHITE}{truncate_middle(f['path'], w - 14)}{NC}")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Active Policy{NC} : {CLR_AMBER}{f.get('profile', 'custom').upper()}{NC}")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}EXIF/ICC Strip{NC}: {'ON' if f.get('strip_exif') else 'OFF'} / {'ON' if f.get('strip_icc') else 'OFF'}")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Scorched/Dither{NC}: {'ON' if f.get('scorched_earth') else 'OFF'} / {'ON' if f.get('pixel_dither') else 'OFF'}")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Scope{NC}         : {'Recursive Subfolders' if f.get('recursive') else 'Top-Level Only'} · {'+MP4/PDF' if f.get('include_media_docs') else 'Images Only'}")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        pfx = f.get('prefix', 'img_')
        sfx = f.get('suffix', '')

        menu_items = [
            ("1", "🛡️  Apply Policy Preset (Ghost / Balanced / Scorched / Sequential)", "preset"),
            ("2", f"🏷️  Toggle EXIF Metadata Scrubbing [{'ON' if f.get('strip_exif') else 'OFF'}]", "toggle_exif"),
            ("3", f"🎨 Toggle Display ICC Profile Removal [{'ON' if f.get('strip_icc') else 'OFF'}]", "toggle_icc"),
            ("4", f"🔥 Toggle Scorched Earth Pixel Re-encoding [{'ON' if f.get('scorched_earth') else 'OFF'}]", "toggle_scorch"),
            ("5", f"🧬 Toggle Anti-pHash Sub-Perceptual Dithering [{'ON' if f.get('pixel_dither') else 'OFF'}]", "toggle_dither"),
            ("6", f"📂 Toggle Recursive Subfolder Monitoring [{'ON' if f.get('recursive') else 'OFF'}]", "toggle_recursive"),
            ("7", f"🎬 Toggle Video/PDF Sanitization (.mp4/.mov/.pdf) [{'ON' if f.get('include_media_docs') else 'OFF'}]", "toggle_media"),
            ("8", f"⏱️  Timestamp Clamping Settings [{'ON' if f.get('clamp_time') else 'OFF'}]", "config_time"),
            ("9", f"🎲 Naming Camouflage Style [{f.get('naming_mode', 'hash')}]", "naming_style"),
            ("P", f"✏️  Configure Prefix ['{pfx}'] & Suffix ['{sfx or '(None)'}']", "prefix_suffix"),
            ("R", f"🔢 Reset Sequential Counter [Current: {f.get('seq_counter', 1)}]", "reset_counter"),
            ("D", "🗑️  Delete this folder from watchlist", "delete"),
            ("0", "🔙 Done / Save & Return", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="FOLDER RULE CONFIGURATION")

        if action == "preset":
            def preset_header():
                print(f"{CLR_CYAN}=== Select Policy Preset for this Folder ==={NC}\n")
            p_items = [
                ("1", "🛡️  Ghost (Full EXIF + ICC + Clamped 2020 + UUID Hash)", "ghost"),
                ("2", "⚖️  Balanced (Full Scrub + Word Slug - Shows in Today's Gallery)", "balanced"),
                ("3", "🔥 Scorched Earth (Pixel Re-encoding + Dither + Clamped 2020)", "scorched"),
                ("4", "🔢 Sequential (Full Scrub + Clean Numbering: IMG_0001)", "sequential"),
                ("5", "🏷️  Metadata Strip Only (Scrub EXIF/ICC, keep filename & Today)", "metadata_only"),
                ("6", "⏱️  Timestomp Only (Clamp time to 2020, leave bytes & filename alone)", "timestomp_only"),
            ]
            for u_k, u_v in cfg.get("user_presets", {}).items():
                p_items.append((str(len(p_items) + 1), u_v.get("label", u_k), u_k))
            p_items.append(("0", "🔙 Cancel", "back"))

            chosen_p = run_arrow_menu(preset_header, p_items, title="PRESETS")
            if chosen_p and chosen_p != "back":
                preset_dict = {**SYSTEM_PRESETS, **cfg.get("user_presets", {})}.get(chosen_p, {})
                for k, v in preset_dict.items():
                    if k != "label": f[k] = v
                f["profile"] = chosen_p
                save_config(cfg); DaemonManager.restart()

        elif action == "toggle_exif":
            f["strip_exif"] = not f.get("strip_exif", True)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif action == "toggle_icc":
            f["strip_icc"] = not f.get("strip_icc", True)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif action == "toggle_scorch":
            f["scorched_earth"] = not f.get("scorched_earth", False)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif action == "toggle_dither":
            f["pixel_dither"] = not f.get("pixel_dither", False)
            if f["pixel_dither"]:
                f["scorched_earth"] = True
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif action == "toggle_recursive":
            f["recursive"] = not f.get("recursive", False)
            save_config(cfg); DaemonManager.restart()

        elif action == "toggle_media":
            f["include_media_docs"] = not f.get("include_media_docs", False)
            save_config(cfg); DaemonManager.restart()

        elif action == "config_time":
            def time_header():
                print(f"{CLR_CYAN}=== Configure Timestamp Clamping for this Folder ==={NC}\n")
            t_items = [
                ("1", f"⏱️  Toggle Clamping [{'ON' if f.get('clamp_time') else 'OFF'}]", "toggle"),
                ("2", "🛡️  Static 2020-01-01 (Standard Anti-Forensic)", "static_2020"),
                ("3", "☀️  Today at 00:00:00 (Day-Fuzz: Shows in Today's Gallery)", "day_fuzz"),
                ("4", "🎲 Random Past Date (2020-2022 Fuzzing)", "random_fuzz"),
                ("5", "🕰️  Unix Epoch Zero (1980 / 1970)", "epoch_1970"),
                ("6", f"✍️  Custom Date String [{f.get('clamp_custom_date', '2020-01-01 00:00:00')}]", "custom"),
                ("0", "🔙 Done", "back")
            ]
            t_action = run_arrow_menu(time_header, t_items, title="TIMESTOMP OPTIONS")
            if t_action == "toggle":
                f["clamp_time"] = not f.get("clamp_time", True)
            elif t_action in ("static_2020", "day_fuzz", "random_fuzz", "epoch_1970"):
                f["clamp_mode"] = t_action
                f["clamp_time"] = True
            elif t_action == "custom":
                clear_screen()
                inp = input("\n  Enter custom timestamp (YYYY-MM-DD HH:MM:SS): ").strip()
                try:
                    time.strptime(inp, "%Y-%m-%d %H:%M:%S")
                    f["clamp_custom_date"] = inp
                    f["clamp_mode"] = "custom"
                    f["clamp_time"] = True
                except ValueError:
                    print(f"  {CLR_RED}Invalid format.{NC}"); time.sleep(1)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif action == "naming_style":
            def style_header():
                print(f"{CLR_CYAN}=== Select Naming Style for this Folder ==={NC}\n")
            s_items = [
                ("1", "🛡️  UUID Hex Hash       (e.g. img_7c9f2b84.png)", "hash"),
                ("2", "🔢 Sequential Numbering (e.g. IMG_0001.png)", "seq"),
                ("3", "🔤 Readable Word Slug   (e.g. swift-falcon-42.png)", "slug"),
                ("4", "💬 WhatsApp Decoy       (e.g. IMG-20261026-WA0042.png)", "decoy_wa"),
                ("5", "📷 Camera DCIM Decoy    (e.g. DSC_4821.png)", "decoy_dcim"),
                ("6", "🌐 Reddit / Web Decoy   (e.g. RDT_20261026_140218.png)", "decoy_reddit"),
                ("7", "⚪ Original Filename    (Keep unchanged)", "disabled"),
                ("0", "🔙 Cancel", "back")
            ]
            chosen_s = run_arrow_menu(style_header, s_items, title="NAMING CAMOUFLAGE")
            if chosen_s and chosen_s != "back":
                f["naming_mode"] = chosen_s
                f["random_hash"] = (chosen_s != "disabled")
                f["profile"] = "custom"
                save_config(cfg); DaemonManager.restart()

        elif action == "prefix_suffix":
            clear_screen()
            print(f"\n  Current Prefix: '{f.get('prefix', '')}'")
            np = input("  New Prefix (leave blank for none): ").strip()
            f["prefix"] = "".join(ch for ch in np if ch.isalnum() or ch in ("_", "-"))

            print(f"\n  Current Suffix: '{f.get('suffix', '')}'")
            ns = input("  New Suffix (leave blank for none): ").strip()
            f["suffix"] = "".join(ch for ch in ns if ch.isalnum() or ch in ("_", "-"))
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()
            print(f"  {CLR_GREEN}✔ Saved.{NC}"); time.sleep(0.8)

        elif action == "reset_counter":
            clear_screen()
            print(f"\n  Current Sequential Counter: {f.get('seq_counter', 1)}")
            new_cnt = input("  Enter new starting counter number (e.g. 1): ").strip()
            if new_cnt.isdigit() and int(new_cnt) >= 1:
                f["seq_counter"] = int(new_cnt)
                save_config(cfg)
                print(f"  {CLR_GREEN}✔ Counter set to {new_cnt}.{NC}")
            time.sleep(1)

        elif action == "delete":
            clear_screen()
            confirm = input(f"\n  Remove '{f['path']}' from monitored list? [y/N]: ").strip().lower()
            if confirm in ["y", "yes"]:
                folders.pop(index)
                cfg["folders_v2"] = folders
                save_config(cfg)
                DaemonManager.restart()
                print(f"  {CLR_GREEN}✔ Removed.{NC}")
                time.sleep(0.8)
                return

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: NAMING & CAMOUFLAGE STUDIO
# ==============================================================================

def tool_manage_naming():
    while True:
        cfg = load_config()
        w = get_ui_width()
        folders = cfg.get("folders_v2", [])
        target_folder = folders[0] if folders else DEFAULT_FOLDER_PROFILE
        mode = target_folder.get("naming_mode", "hash")

        dummy_path = Path("Screenshot_20261026-165201.png")
        sample_preview = generate_sanitized_filename(dummy_path, target_folder, preview=True)

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 WHAT NAMING CAMOUFLAGE DOES{NC} {CLR_CYAN}{'─' * max(0, w - 34)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Standard screenshot names leak exact date, hour & second.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}UUID Hash{NC}   : Unpredictable hex tokens (e.g. img_7c9f2b84.png).")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Sequential{NC}  : Clean indexed counters (e.g. IMG_0001.png).")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Word Slugs{NC}  : Anonymous, memorable words (e.g. swift-falcon-42.png).")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Decoys{NC}      : Plausible deniability (WhatsApp, DCIM, Reddit).")
            print(f"{CLR_CYAN}│{NC}  Sample Result: {CLR_GREEN}{BOLD}{sample_preview}{NC}")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        pfx = target_folder.get('prefix', 'img_')
        sfx = target_folder.get('suffix', '')
        casing = target_folder.get('casing', 'lower')
        padding = target_folder.get('seq_padding', 4)

        menu_items = [
            ("1", f"🎭 Switch Naming Style [{mode.upper()}]", "style"),
            ("2", f"✏️  Configure Prefix ['{pfx}']", "prefix"),
            ("3", f"🏷️  Configure Suffix ['{sfx or '(None)'}']", "suffix"),
            ("4", f"🔢 Set Sequential Number Padding [{padding} digits: e.g. {'0'*padding}]", "padding"),
            ("5", f"🔄 Reset Sequential Counter [Current: {target_folder.get('seq_counter', 1)}]", "reset_counter"),
            ("6", f"🔠 Toggle Casing Formatter [{casing.upper()}]", "casing"),
            ("7", f"🔢 Set Hash Token Length [{target_folder.get('hash_len', 12)} chars]", "length"),
            ("8", "🎲 Roll 3 Test Previews", "preview"),
            ("9", "🚀 Apply this naming style to ALL registered folders", "apply_all"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="NAMING & CAMOUFLAGE STUDIO")

        if action == "style":
            def style_header():
                print(f"{CLR_CYAN}=== Select Naming Style ==={NC}\n")
            s_items = [
                ("1", "🛡️  UUID Hex Hash       (e.g. img_7c9f2b84e1a0.png)", "hash"),
                ("2", "🔢 Sequential Numbering (e.g. IMG_0001.png)", "seq"),
                ("3", "🔤 Readable Word Slug   (e.g. swift-falcon-42.png)", "slug"),
                ("4", "💬 WhatsApp Decoy       (e.g. IMG-20261026-WA0042.png)", "decoy_wa"),
                ("5", "📷 Camera DCIM Decoy    (e.g. DSC_4821.png)", "decoy_dcim"),
                ("6", "🌐 Reddit / Web Decoy   (e.g. RDT_20261026_140218.png)", "decoy_reddit"),
                ("7", "⚪ Preserve Original    (Keep filename unchanged)", "disabled"),
                ("0", "🔙 Cancel", "back")
            ]
            chosen_s = run_arrow_menu(style_header, s_items, title="PROFILES")
            if chosen_s and chosen_s != "back":
                target_folder["naming_mode"] = chosen_s
                target_folder["random_hash"] = (chosen_s != "disabled")
                save_config(cfg); DaemonManager.restart()

        elif action == "prefix":
            clear_screen()
            print(f"\n  Current Prefix: '{pfx}'")
            new_pfx = input("  Enter new prefix (e.g. 'IMG_', 'shot_', or blank): ").strip()
            sanitized = "".join(ch for ch in new_pfx if ch.isalnum() or ch in ("_", "-"))
            target_folder["prefix"] = sanitized
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Prefix updated to: '{sanitized}'{NC}")
            time.sleep(0.8)

        elif action == "suffix":
            clear_screen()
            print(f"\n  Current Suffix: '{sfx}'")
            new_sfx = input("  Enter new suffix (e.g. 'clean', 'vault', or blank): ").strip()
            sanitized = "".join(ch for ch in new_sfx if ch.isalnum() or ch in ("_", "-"))
            target_folder["suffix"] = sanitized
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Suffix updated to: '{sanitized}'{NC}")
            time.sleep(0.8)

        elif action == "padding":
            def pad_header():
                print(f"{CLR_CYAN}=== Select Sequential Zero-Padding ==={NC}\n")
            p_items = [
                ("1", "3 digits (e.g. 001, 002)", 3),
                ("2", "4 digits (e.g. 0001, 0002)", 4),
                ("3", "5 digits (e.g. 00001, 00002)", 5),
                ("4", "6 digits (e.g. 000001, 000002)", 6),
                ("0", "🔙 Cancel", "back")
            ]
            chosen_p = run_arrow_menu(pad_header, p_items, title="PADDING")
            if chosen_p and chosen_p != "back":
                target_folder["seq_padding"] = chosen_p
                save_config(cfg); time.sleep(0.8)

        elif action == "reset_counter":
            clear_screen()
            print(f"\n  Current Sequential Counter: {target_folder.get('seq_counter', 1)}")
            new_cnt = input("  Enter new starting counter number (e.g. 1): ").strip()
            if new_cnt.isdigit() and int(new_cnt) >= 1:
                target_folder["seq_counter"] = int(new_cnt)
                save_config(cfg)
                print(f"  {CLR_GREEN}✔ Counter set to {new_cnt}.{NC}")
            time.sleep(1)

        elif action == "casing":
            target_folder["casing"] = "upper" if casing == "lower" else "lower"
            save_config(cfg)

        elif action == "length":
            def len_header():
                print(f"{CLR_CYAN}=== Select Hash Token Length ==={NC}\n")
            l_items = [
                ("1", "8 characters  (e.g. img_7c9f2b84.png)", 8),
                ("2", "12 characters (e.g. img_7c9f2b84e1a0.png)", 12),
                ("3", "16 characters (e.g. img_7c9f2b84e1a0d3f5.png)", 16),
                ("4", "32 characters (Full UUID Hash)", 32),
                ("0", "🔙 Cancel", "back")
            ]
            chosen_l = run_arrow_menu(len_header, l_items, title="TOKEN LENGTH")
            if chosen_l and chosen_l != "back":
                target_folder["hash_len"] = chosen_l
                save_config(cfg); time.sleep(0.8)

        elif action == "preview":
            clear_screen()
            print(f"\n  {CLR_AMBER}Rolling 3 test samples for '{mode.upper()}':{NC}\n")
            for _ in range(3):
                print(f"   • {CLR_GREEN}{BOLD}{generate_sanitized_filename(dummy_path, target_folder, preview=True)}{NC}")
            input("\n  Press [Enter] to continue...")

        elif action == "apply_all":
            for f in folders:
                f["naming_mode"] = target_folder.get("naming_mode", "hash")
                f["prefix"] = target_folder.get("prefix", "img_")
                f["suffix"] = target_folder.get("suffix", "")
                f["casing"] = target_folder.get("casing", "lower")
                f["hash_len"] = target_folder.get("hash_len", 12)
                f["seq_padding"] = target_folder.get("seq_padding", 4)
                f["random_hash"] = target_folder.get("random_hash", True)
            save_config(cfg); DaemonManager.restart()
            print(f"\n  {CLR_GREEN}✔ Applied to all {len(folders)} folders!{NC}")
            time.sleep(1)

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: TIMESTOMP & CLAMPING STUDIO
# ==============================================================================

def tool_manage_clamping():
    while True:
        cfg = load_config()
        w = get_ui_width()
        folders = cfg.get("folders_v2", [])
        target_folder = folders[0] if folders else DEFAULT_FOLDER_PROFILE

        mode = target_folder.get("clamp_mode", "static_2020")
        custom_date = target_folder.get("clamp_custom_date", "2020-01-01 00:00:00")
        clamp_enabled = target_folder.get("clamp_time", True)

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW ANTI-FORENSIC TIMESTOMPING WORKS{NC} {CLR_CYAN}{'─' * max(0, w - 44)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Filesystem table entries leak creation and access minutes.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Static 2020{NC}   : Freezes time to 2020-01-01 (breaks timeline tracking).")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Day Fuzz{NC}      : Stamps to Today at 00:00:00 (Shows in Today's Gallery).")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Random Fuzz{NC}   : Random dates (2020-2022) to avoid batch clustering.")
            print(f"{CLR_CYAN}│{NC}  • {BOLD}Custom Date{NC}   : Set any exact historical date you prefer.")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        mode_labels = {
            "static_2020": "Static 2020-01-01 00:00:00 (Standard)",
            "day_fuzz": "Today's Midnight (Shows in Today's Gallery)",
            "random_fuzz": "Random Past Date (2020-2022 Fuzzing)",
            "epoch_1970": "Unix Epoch (1980 on Windows, 1970 on POSIX)",
            "custom": f"Custom: {custom_date}",
        }

        menu_items = [
            ("1", f"⏱️  Toggle Timestamp Clamping [{'🟢 ON' if clamp_enabled else '⚪ OFF'}]", "toggle_clamp"),
            ("2", f"📅 Select Clamp Target Mode [{mode_labels.get(mode, mode)}]", "select_mode"),
            ("3", f"✍️  Set Custom Date/Time String ['{custom_date}']", "set_custom"),
            ("4", f"🏷️  Clamp Modification Time (mtime) [{'🟢 ON' if target_folder.get('clamp_mtime', True) else '⚪ OFF'}]", "toggle_mtime"),
            ("5", f"👁️  Clamp Access Time (atime) [{'🟢 ON' if target_folder.get('clamp_atime', True) else '⚪ OFF'}]", "toggle_atime"),
            ("6", "🚀 Apply this clamping rule to ALL registered folders", "apply_all"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="TIMESTOMP & CLAMPING STUDIO")

        if action == "toggle_clamp":
            target_folder["clamp_time"] = not target_folder.get("clamp_time", True)
            save_config(cfg); DaemonManager.restart()

        elif action == "select_mode":
            def mode_header():
                print(f"{CLR_CYAN}=== Select Clamping Target Strategy ==={NC}\n")
            m_items = [
                ("1", "🛡️  Static 2020-01-01 00:00:00 (Maximum Forensic Cloak)", "static_2020"),
                ("2", "☀️  Today at 00:00:00 (Fuzzes Seconds, Shows in Today's Gallery)", "day_fuzz"),
                ("3", "🎲 Random Past Date (2020-2022, Prevents Batch Clustering)", "random_fuzz"),
                ("4", "🕰️  Unix Epoch Zero (1980 / 1970)", "epoch_1970"),
                ("5", f"✏️  Custom User Date ({custom_date})", "custom"),
                ("0", "🔙 Cancel", "back")
            ]
            chosen_m = run_arrow_menu(mode_header, m_items, title="CLAMPING TARGET")
            if chosen_m and chosen_m != "back":
                target_folder["clamp_mode"] = chosen_m
                target_folder["clamp_time"] = True
                save_config(cfg); DaemonManager.restart()

        elif action == "set_custom":
            clear_screen()
            print(f"\n  Current Custom Date: '{custom_date}'")
            print("  Enter custom timestamp format: YYYY-MM-DD HH:MM:SS")
            inp = input("  Target Time > ").strip()
            try:
                time.strptime(inp, "%Y-%m-%d %H:%M:%S")
                target_folder["clamp_custom_date"] = inp
                target_folder["clamp_mode"] = "custom"
                target_folder["clamp_time"] = True
                save_config(cfg)
                print(f"  {CLR_GREEN}✔ Custom target date updated!{NC}")
            except ValueError:
                print(f"  {CLR_RED}✖ Invalid format. Example: 2018-05-20 14:30:00{NC}")
            time.sleep(1)

        elif action == "toggle_mtime":
            target_folder["clamp_mtime"] = not target_folder.get("clamp_mtime", True)
            save_config(cfg)

        elif action == "toggle_atime":
            target_folder["clamp_atime"] = not target_folder.get("clamp_atime", True)
            save_config(cfg)

        elif action == "apply_all":
            for f in folders:
                f["clamp_time"] = target_folder.get("clamp_time", True)
                f["clamp_mode"] = target_folder.get("clamp_mode", "static_2020")
                f["clamp_custom_date"] = target_folder.get("clamp_custom_date", "2020-01-01 00:00:00")
                f["clamp_mtime"] = target_folder.get("clamp_mtime", True)
                f["clamp_atime"] = target_folder.get("clamp_atime", True)
            save_config(cfg); DaemonManager.restart()
            print(f"\n  {CLR_GREEN}✔ Applied to all {len(folders)} folders!{NC}")
            time.sleep(1)

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: ENCRYPTED SAFETY VAULT (EXTENSION-AWARE & AUTO-PRUNING)
# ==============================================================================

def tool_manage_vault():
    while True:
        cfg = load_config()
        w = get_ui_width()
        vault_files = [f for f in VAULT_DIR.glob("*") if f.is_file()]
        enc_count = sum(1 for f in vault_files if f.suffix == ".enc")
        total_mb = sum(f.stat().st_size for f in vault_files) / (1024 * 1024)

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 ZERO-KNOWLEDGE BACKUP VAULT{NC} {CLR_CYAN}{'─' * max(0, w - 34)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Saves original, unscrubbed copies before sanitizing.")
            print(f"{CLR_CYAN}│{NC}  • Encrypted with {BOLD}100,000-round PBKDF2 + AES keystream{NC}.")
            print(f"{CLR_CYAN}│{NC}  • Stored: {BOLD}{len(vault_files)}{NC} files ({total_mb:.1f} MB / {cfg.get('vault_max_mb', 250)} MB Cap).")
            print(f"{CLR_CYAN}│{NC}  • Auto-Prune: Removes backups older than {cfg.get('vault_max_days', 7)} days.")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        v_state = "[🟢 ON]" if cfg.get("enable_backup") else "[⚪ OFF]"
        menu_items = [
            ("1", f"🔐 Toggle Backup Vault {v_state}", "toggle"),
            ("2", "📦 Export & Decrypt All Backups to ~/Download/ShotClean_Restored", "export"),
            ("3", f"📏 Configure Storage Quota [{cfg.get('vault_max_mb', 250)} MB / {cfg.get('vault_max_days', 7)} Days]", "quota"),
            ("4", "🗑️  Purge / Wipe Entire Vault Permanently", "purge"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="SAFETY VAULT")

        if action == "toggle":
            cfg["enable_backup"] = not cfg.get("enable_backup", False)
            save_config(cfg)

        elif action == "export":
            clear_screen()
            if not vault_files:
                print(f"  {CLR_AMBER}Vault is empty.{NC}"); time.sleep(1); continue
            out_dir = HOME / "Download" / "ShotClean_Restored"
            out_dir.mkdir(parents=True, exist_ok=True)
            secret = get_vault_secret()
            restored_count = 0
            for vf in vault_files:
                try:
                    if vf.suffix == ".enc":
                        plain = decrypt_payload(vf.read_bytes(), secret)
                        # Preserve original extension if present in vf.stem (e.g. photo_170000.jpg.enc -> photo_170000.jpg)
                        out_name = vf.stem if Path(vf.stem).suffix else (vf.stem + ".png")
                        (out_dir / out_name).write_bytes(plain)
                    else:
                        shutil.copy2(vf, out_dir / vf.name)
                    restored_count += 1
                except Exception:
                    pass
            print(f"\n  {CLR_GREEN}✔ Decrypted and restored {restored_count} file(s) to:{NC}\n  {out_dir}")
            input("\n  Press [Enter] to continue...")

        elif action == "quota":
            clear_screen()
            print(f"\n  Current Max Vault Size: {cfg.get('vault_max_mb', 250)} MB")
            mb_in = input("  New Max Size in MB (e.g. 250, or 0 for unlimited): ").strip()
            if mb_in.isdigit():
                cfg["vault_max_mb"] = int(mb_in)
            print(f"\n  Current Retention Days: {cfg.get('vault_max_days', 7)} Days")
            days_in = input("  New Retention Days (e.g. 7, or 0 for unlimited): ").strip()
            if days_in.isdigit():
                cfg["vault_max_days"] = int(days_in)
            save_config(cfg)
            prune_vault_storage(cfg)
            print(f"  {CLR_GREEN}✔ Vault quota updated and applied.{NC}")
            time.sleep(0.8)

        elif action == "purge":
            clear_screen()
            if input("\n  Permanently delete ALL backups in vault? [y/N]: ").strip().lower() in ["y", "yes"]:
                for vf in vault_files: vf.unlink()
                print(f"  {CLR_GREEN}✔ Vault purged.{NC}"); time.sleep(1)

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: PRIVACY CANARY AUDIT
# ==============================================================================

def tool_privacy_canary():
    while True:
        w = get_ui_width()
        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW THE PRIVACY CANARY AUDIT WORKS{NC} {CLR_CYAN}{'─' * max(0, w - 41)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Tests whether apps (WhatsApp, Discord, Telegram, Imgur) leak data:")
            print(f"{CLR_CYAN}│{NC}  1. Generates an image with a hidden {BOLD}CANARY-TOKEN-XXXX{NC}.")
            print(f"{CLR_CYAN}│{NC}  2. Send it through the app, then download the image back.")
            print(f"{CLR_CYAN}│{NC}  3. Run Audit: If the token survives, the app tracks you.")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        menu_items = [
            ("1", "🐤 Generate New Canary Image (Embeds Tracking Token)", "generate"),
            ("2", "🔍 Audit Downloaded Image (Check If Token Survived)", "audit"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="PRIVACY CANARY")

        if action == "generate":
            clear_screen()
            token = f"CANARY-{uuid.uuid4().hex[:8].upper()}"
            def_dir = detect_default_folder()
            def_dir.mkdir(parents=True, exist_ok=True)
            canary_path = def_dir / f"test_canary_{token}.png"
            create_synthetic_png(canary_path)
            GENERATED_NAMES_HISTORY.append(canary_path.name)

            EXIFTOOL_ENGINE.execute(
                f"-Artist={token}",
                f"-UserComment=CANARY_PRIVACY_AUDIT_{token}",
                f"-Copyright={token}",
                "-overwrite_original_in_place",
                str(canary_path),
                timeout=4.0
            )
            record_file_in_ledger(canary_path)

            print(f"\n  {CLR_GREEN}{BOLD}✔ Canary Generated Successfully!{NC}")
            print(f"  Token : {BOLD}{token}{NC}")
            print(f"  Path  : {CLR_GRAY}{canary_path}{NC}\n")
            print("  Instructions: Upload this test image to the app, download it back, then run [2].")
            input("\n  Press [Enter] to continue...")

        elif action == "audit":
            clear_screen()
            path_str = input("\n  Enter path to downloaded image (or drag & drop): ").strip().strip("'\"")
            p = Path(path_str)
            if not p.exists() or not p.is_file():
                print(f"  {CLR_RED}File not found.{NC}"); time.sleep(1.2); continue

            out = EXIFTOOL_ENGINE.execute("-all", str(p), timeout=4.0)
            if "CANARY-" in out:
                print(f"\n  {CLR_RED}{BOLD}🚨 PRIVACY LEAK DETECTED!{NC}")
                print("  The platform preserved metadata tracking tokens! Your images leak data.\n")
            elif not out.strip():
                print(f"\n  {CLR_GREEN}{BOLD}🛡️ 100% CLEAN & SAFE!{NC}")
                print("  The platform completely stripped all metadata and canary tokens.\n")
            else:
                print(f"\n  {CLR_AMBER}{BOLD}⚠️ PARTIAL METADATA RETAINED:{NC}\n{out[:300]}")
            input("  Press [Enter] to return...")

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: ENGINE DIAGNOSTICS, WIDGET SHORTCUTS & SYSTEM SETTINGS
# ==============================================================================

def install_termux_widget_shortcuts():
    """Creates one-tap home screen scripts in ~/.shortcuts for Termux:Widget."""
    shortcuts_dir = HOME / ".shortcuts"
    shortcuts_dir.mkdir(parents=True, exist_ok=True)

    scripts = {
        "ShotClean_Sweep_Now.sh": (
            "#!/data/data/com.termux/files/usr/bin/bash\n"
            "shotclean --sweep\n"
            "command -v termux-toast >/dev/null 2>&1 && termux-toast -g bottom 'ShotClean: Folder Sweep Complete!'\n"
        ),
        "ShotClean_Status.sh": (
            "#!/data/data/com.termux/files/usr/bin/bash\n"
            "shotclean --status\n"
            "echo ''\n"
            "read -p 'Press [Enter] to close...'\n"
        ),
        "ShotClean_Start_Daemon.sh": (
            "#!/data/data/com.termux/files/usr/bin/bash\n"
            "shotclean --daemon >> \"$HOME/.shotclean/boot.log\" 2>&1 &\n"
            "command -v termux-toast >/dev/null 2>&1 && termux-toast -g bottom 'ShotClean: Background Shield Started'\n"
        ),
        "ShotClean_Stop_Daemon.sh": (
            "#!/data/data/com.termux/files/usr/bin/bash\n"
            "shotclean --stop\n"
            "command -v termux-toast >/dev/null 2>&1 && termux-toast -g bottom 'ShotClean: Background Shield Stopped'\n"
        ),
    }

    for name, content in scripts.items():
        sp = shortcuts_dir / name
        sp.write_text(content, encoding="utf-8")
        sp.chmod(0o755)

    return shortcuts_dir


def tool_engine_diagnostics():
    while True:
        w = get_ui_width()
        cfg = load_config()
        daemon_pid = EXIFTOOL_ENGINE.proc.pid if EXIFTOOL_ENGINE.proc else None
        daemon_alive = EXIFTOOL_ENGINE.proc and (EXIFTOOL_ENGINE.proc.poll() is None)
        notif_state = "[🟢 ON]" if cfg.get("enable_notifications", False) else "[⚪ OFF]"

        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 ENGINE & PROCESS HEALTH CHECKS{NC} {CLR_CYAN}{'─' * max(0, w - 37)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  • ExifTool Binary Path  : {CLR_GREEN}{shutil.which('exiftool') or 'NOT FOUND'}{NC}")
            print(f"{CLR_CYAN}│{NC}  • Persistent Daemon PID : {CLR_GREEN}{daemon_pid}{NC} ({'Alive' if daemon_alive else 'Dead/Restarting'})")
            print(f"{CLR_CYAN}│{NC}  • Background Worker     : {'Active' if WORKER_THREAD.is_alive() else 'Dead'}")
            print(f"{CLR_CYAN}│{NC}  • Work Queue Backlog    : {WORK_QUEUE.qsize()} task(s)")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        menu_items = [
            ("1", "⚡ Force Restart ExifTool Daemon Pipe", "restart"),
            ("2", "🏓 Ping Daemon Latency", "ping"),
            ("3", f"🔔 Toggle System Notification Toasts {notif_state}", "toggle_notif"),
            ("4", "📱 Install Termux:Widget Home Screen Shortcuts (~/.shortcuts)", "widget"),
            ("5", "🚀 Install Auto-Boot Service (Termux:Boot / systemd / LaunchAgent)", "boot_service"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="ENGINE DIAGNOSTICS")

        if action == "restart":
            EXIFTOOL_ENGINE._restart()
            print(f"\n  {CLR_GREEN}✔ Daemon recycled successfully.{NC}")
            time.sleep(1)

        elif action == "ping":
            clear_screen()
            t0 = time.time()
            test_out = EXIFTOOL_ENGINE.execute("-ver", timeout=3.0)
            elapsed = int((time.time() - t0) * 1000)
            print(f"\n  ExifTool Version : {BOLD}{test_out.strip()}{NC}")
            print(f"  Ping Roundtrip   : {CLR_GREEN}{elapsed}ms{NC}\n")
            input("  Press [Enter] to continue...")

        elif action == "toggle_notif":
            cfg["enable_notifications"] = not cfg.get("enable_notifications", False)
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Notifications toggled.{NC}")
            time.sleep(0.8)

        elif action == "widget":
            clear_screen()
            s_dir = install_termux_widget_shortcuts()
            print(f"\n  {CLR_GREEN}{BOLD}✔ Termux:Widget shortcuts installed to:{NC} {s_dir}")
            print("  Add the Termux:Widget widget to your Android home screen to tap:")
            print("   • ShotClean_Sweep_Now.sh")
            print("   • ShotClean_Start_Daemon.sh")
            print("   • ShotClean_Stop_Daemon.sh")
            print("   • ShotClean_Status.sh\n")
            input("  Press [Enter] to continue...")

        elif action == "boot_service":
            clear_screen()
            install_system_service()
            input("\n  Press [Enter] to continue...")

        elif action in ("back", None):
            break


# ==============================================================================
# SUBMENU: FIELD MANUAL
# ==============================================================================

def tool_feature_guide():
    while True:
        w = get_ui_width()
        def header_card():
            print(f"{CLR_CYAN}╭─ {BOLD}💡 PRIVACY THREAT MODEL & DEFENSE GUIDE{NC} {CLR_CYAN}{'─' * max(0, w - 43)}╮{NC}")
            print(f"{CLR_CYAN}│{NC}  Select any feature below to understand what it protects.")
            print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        menu_items = [
            ("1", "🏷️  EXIF / XMP / IPTC Metadata Stripping", "exif"),
            ("2", "🎨 Display ICC Color Profile Removal", "icc"),
            ("3", "🔥 Scorched Earth & Anti-pHash Pixel Dithering", "scorch"),
            ("4", "🎲 Decoy Presets & Diceware Word Slugs", "naming"),
            ("5", "🔢 Sequential Numbering & State Tracking", "seq"),
            ("6", "⏱️  Anti-Forensic Timestamp Clamping & Day-Fuzzing", "time"),
            ("7", "🧹 Active Sweeper & Persistent Scrubbed Ledger", "sweeper"),
            ("8", "🔐 Encrypted Safety Vault (Extension-Aware + Quota)", "vault"),
            ("9", "📁 Granular Per-Folder Rules & Recursive Scope", "folders"),
            ("0", "🔙 Back to Main Menu", "back"),
        ]

        action = run_arrow_menu(header_card, menu_items, title="FIELD MANUAL")

        if action == "exif":
            clear_screen()
            print(f"{CLR_CYAN}=== 🏷️ EXIF METADATA STRIPPING ==={NC}\n")
            print("  Wipes camera model, manufacturer, serial numbers, lens info, and GPS coordinates.")
            input("\n  Press [Enter] to return...")
        elif action == "icc":
            clear_screen()
            print(f"{CLR_CYAN}=== 🎨 ICC PROFILE REMOVAL ==={NC}\n")
            print("  Removes display panel color profiles that fingerprint specific phone models.")
            input("\n  Press [Enter] to return...")
        elif action == "scorch":
            clear_screen()
            print(f"{CLR_CYAN}=== 🔥 SCORCHED EARTH & SUB-PERCEPTUAL PIXEL DITHERING ==={NC}\n")
            print("  Demuxes raw pixels into memory and writes a clean image container from scratch.")
            print("  Drops all trailing payloads after IEND, hardware signatures, and steganographic data.")
            print("  When Pixel Dithering is ON, applies a +-1 RGB jitter to 2% of pixels to defeat perceptual")
            print("  hashing (pHash/dHash) and LSB watermarks without any visible change.")
            input("\n  Press [Enter] to return...")
        elif action == "naming":
            clear_screen()
            print(f"{CLR_CYAN}=== 🎲 DECOY PRESETS & WORD SLUGS ==={NC}\n")
            print("  Provides plausible deniability by mimicking everyday apps (WhatsApp, DCIM) or generating readable slugs.")
            input("\n  Press [Enter] to return...")
        elif action == "seq":
            clear_screen()
            print(f"{CLR_CYAN}=== 🔢 SEQUENTIAL NUMBERING ==={NC}\n")
            print("  Generates ordered series (IMG_0001, IMG_0002) with persistent state tracking.")
            input("\n  Press [Enter] to return...")
        elif action == "time":
            clear_screen()
            print(f"{CLR_CYAN}=== ⏱️ TIMESTAMP CLAMPING & DAY-FUZZING ==={NC}\n")
            print("  Static 2020: Forces modification dates to 2020-01-01 to eliminate temporal correlation.")
            print("  Day-Fuzz: Stamps photos to Today at 00:00:00 so they stay in Today's Gallery feed while masking seconds!")
            input("\n  Press [Enter] to return...")
        elif action == "sweeper":
            clear_screen()
            print(f"{CLR_CYAN}=== 🧹 ACTIVE SWEEPER & PERSISTENT LEDGER ==={NC}\n")
            print("  Automatically checks monitored folders on startup or periodically every X minutes.")
            print("  Maintains ~/.shotclean/scrubbed_ledger.json so files using Word Slugs or Decoy names")
            print("  are never re-renamed across restarts.")
            input("\n  Press [Enter] to return...")
        elif action == "vault":
            clear_screen()
            print(f"{CLR_CYAN}=== 🔐 ENCRYPTED SAFETY VAULT ==={NC}\n")
            print("  Keeps encrypted PBKDF2 + AES backups in ~/.shotclean/vault/ before scrubbing,")
            print("  preserving original extensions (.jpg, .webp, .png) and auto-pruning by size/age.")
            input("\n  Press [Enter] to return...")
        elif action == "folders":
            clear_screen()
            print(f"{CLR_CYAN}=== 📁 GRANULAR PER-FOLDER RULES & RECURSIVE SCOPE ==={NC}\n")
            print("  Each folder has independent rules, optional Recursive Subfolder monitoring,")
            print("  and optional support for screen recordings (.mp4/.mov) and PDF documents.")
            input("\n  Press [Enter] to return...")
        elif action in ("back", None):
            break


# ==============================================================================
# AUDIT & LOG TOOLS
# ==============================================================================

def tool_live_audit():
    clear_screen()
    w = get_ui_width()
    print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW THE LIVE METADATA AUDITOR WORKS{NC} {CLR_CYAN}{'─' * max(0, w - 42)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  Scans the most recent capture for remaining tracking tags.")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    cfg = load_config()
    candidates = []
    for f in cfg.get("folders_v2", []):
        p = Path(f["path"])
        if p.exists():
            candidates.extend(iter_monitored_files(p, f))

    valid_candidates = [c for c in candidates if c.exists()]
    if not valid_candidates:
        print(f"  {CLR_AMBER}✖ No files found across registered folders.{NC}\n")
        input("  Press [Enter] to return...")
        return

    latest_file = max(valid_candidates, key=lambda f: f.stat().st_mtime)
    print(f"  Target File : {BOLD}{latest_file.name}{NC}")
    print(f"  Directory   : {CLR_GRAY}{latest_file.parent}{NC}\n")

    t0 = time.time()
    out = EXIFTOOL_ENGINE.execute(
        "-exif:all", "-xmp:all", "-iptc:all", "-icc_profile:all",
        str(latest_file), timeout=4.0
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    print(f"  ExifTool Scan Speed: {CLR_GREEN}{elapsed_ms}ms{NC}\n")

    if not out.strip():
        print(f"  {CLR_GREEN}{BOLD}✔ 100% CLEAN - ZERO METADATA OR ICC PROFILES DETECTED!{NC}")
    else:
        print(f"  {CLR_RED}{BOLD}🚨 LEAK DETECTED - Remaining tags:{NC}\n")
        for line in out.splitlines():
            print(f"    {CLR_RED}• {line}{NC}")

    st = latest_file.stat()
    print(f"\n{CLR_BORDER}── FILESYSTEM TIMESTAMPS ────────────────────────────{NC}")
    print(f"  Modified Time : {time.ctime(st.st_mtime)}")
    print(f"  Access Time   : {time.ctime(st.st_atime)}")
    print(f"{CLR_BORDER}{'─' * w}{NC}\n")
    input("  Press [Enter] to return...")


def tool_live_logs():
    clear_screen()
    w = get_ui_width()
    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}📜  LIVE ACTIVITY LOG STREAM{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")
    print(f"  {CLR_AMBER}Streaming real-time events... (Press Ctrl+C to return){NC}\n")

    if not LOG_FILE.exists():
        LOG_FILE.touch()

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for l in lines[-15:]:
                print(f"  {CLR_GRAY}{l.strip()}{NC}")
            f.seek(0, os.SEEK_END)

            while True:
                line = f.readline()
                if line:
                    stripped = line.strip()
                    if "[ERROR]" in stripped:
                        print(f"  {CLR_RED}🚨 {stripped}{NC}")
                    elif "[COMPLETE]" in stripped:
                        print(f"  {CLR_GREEN}✔  {stripped}{NC}")
                    else:
                        print(f"  {CLR_CYAN}❯  {stripped}{NC}")
                else:
                    time.sleep(0.3)
    except KeyboardInterrupt:
        print(f"\n  {CLR_AMBER}Returned from live log stream.{NC}")
        time.sleep(0.6)


def tool_bulk_clean():
    clear_screen()
    cfg = load_config()
    print(f"{CLR_CYAN}=== Bulk Folder Scrubber ==={NC}\n")
    confirm = input("  Scrub all existing files across registered folders? [y/N]: ").strip().lower()
    if confirm not in ["y", "yes"]:
        return

    all_images = []
    for folder_cfg in cfg.get("folders_v2", []):
        p = Path(folder_cfg["path"])
        if p.exists():
            all_images.extend(iter_monitored_files(p, folder_cfg))

    total = len(all_images)
    if total == 0:
        print(f"  {CLR_AMBER}No matching files found.{NC}")
        time.sleep(1)
        return

    print(f"\n  Found {total} files. Scrubbing via Persistent ExifTool Pipe...")
    for i, img in enumerate(all_images, 1):
        percent = int((i / total) * 100)
        bar = "█" * (percent // 5) + "░" * (20 - (percent // 5))
        sys.stdout.write(f"\r  [{bar}] {percent}% ({i}/{total})")
        sys.stdout.flush()

        rules = get_rules_for_file(img, cfg)
        if rules.get("scorched_earth", False):
            reencode_scorched_earth(img, pixel_dither=bool(rules.get("pixel_dither", False)))

        if rules.get("strip_exif", True):
            args = ["-all="]
            if rules.get("strip_icc", True):
                args.append("-icc_profile:all=")
            if not rules.get("clamp_time", True):
                args.append("-P")
            args.extend(["-overwrite_original_in_place", str(img)])
            EXIFTOOL_ENGINE.execute(*args, timeout=4.0)

        if rules.get("clamp_time", True):
            try:
                target_epoch = compute_clamp_epoch(rules)
                curr_stat = img.stat()
                atime = target_epoch if rules.get("clamp_atime", True) else curr_stat.st_atime
                mtime = target_epoch if rules.get("clamp_mtime", True) else curr_stat.st_mtime
                os.utime(img, (atime, mtime))
            except OSError:
                pass

        record_file_in_ledger(img)

    print(f"\n\n  {CLR_GREEN}✔ Bulk scrub complete for {total} files.{NC}\n")
    time.sleep(1.2)


def tool_manual_check_updates():
    clear_screen()
    print(f"\n  {CLR_CYAN}Querying GitHub for latest commit on 'main'...{NC}")
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        content = fetch_web_resource(url, timeout=5.0)
        data = json.loads(content)
        remote_sha = data.get("sha", "")
        local_sha = get_current_commit()

        if remote_sha and local_sha != remote_sha:
            print(f"\n  {CLR_AMBER}🚀 Update available ({remote_sha[:7]})!{NC}")
            ans = input("  Install and restart now? [Y/n]: ").strip().lower()
            if ans not in ['n', 'no']:
                perform_direct_web_update()
        else:
            print(f"\n  {CLR_GREEN}✔ You are up to date!{NC}\n")
    except Exception as e:
        print(f"\n  {CLR_RED}✖ Error checking updates:{NC} {e}\n")
    input("  Press [Enter] to return...")


# ==============================================================================
# CLI SERVICE GENERATOR & HEADLESS ACTIONS
# ==============================================================================

def install_system_service():
    """Generates and deploys background service unit + Termux:Widget shortcuts."""
    os_name = SystemDoctor.get_os_string()
    print(f"\n  {CLR_CYAN}Installing ShotClean background service for: {os_name}...{NC}")

    if "Android" in os_name:
        boot_dir = HOME / ".termux" / "boot"
        boot_dir.mkdir(parents=True, exist_ok=True)
        boot_script = boot_dir / "start-shotclean.sh"
        boot_script.write_text(
            '#!/data/data/com.termux/files/usr/bin/bash\n'
            'termux-wake-lock\n'
            'exec shotclean --daemon >> "$HOME/.shotclean/boot.log" 2>&1 &\n'
        )
        boot_script.chmod(0o755)
        s_dir = install_termux_widget_shortcuts()
        print(f"  {CLR_GREEN}✔ Created Termux:Boot daemon script: {boot_script}{NC}")
        print(f"  {CLR_GREEN}✔ Created Termux:Widget home screen shortcuts: {s_dir}{NC}")

    elif "Linux" in os_name:
        systemd_dir = HOME / ".config" / "systemd" / "user"
        systemd_dir.mkdir(parents=True, exist_ok=True)
        service_file = systemd_dir / "shotclean.service"
        py_bin = sys.executable
        script_path = Path(__file__).resolve()
        service_file.write_text(
            f"[Unit]\nDescription=ShotClean Background Privacy Daemon\nAfter=network.target\n\n"
            f"[Service]\nExecStart={py_bin} {script_path} --daemon\nRestart=always\nRestartSec=5\n\n"
            f"[Install]\nWantedBy=default.target\n"
        )
        print(f"  {CLR_GREEN}✔ Created systemd user unit: {service_file}{NC}")
        print("  Run: systemctl --user daemon-reload && systemctl --user enable --now shotclean")

    elif "macOS" in os_name:
        launch_dir = HOME / "Library" / "LaunchAgents"
        launch_dir.mkdir(parents=True, exist_ok=True)
        plist = launch_dir / "com.shotclean.daemon.plist"
        py_bin = sys.executable
        script_path = Path(__file__).resolve()
        plist.write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            f'<plist version="1.0">\n<dict>\n'
            f'<key>Label</key><string>com.shotclean.daemon</string>\n'
            f'<key>ProgramArguments</key><array><string>{py_bin}</string><string>{script_path}</string><string>--daemon</string></array>\n'
            f'<key>RunAtLoad</key><true/>\n<key>KeepAlive</key><true/>\n'
            f'</dict>\n</plist>\n'
        )
        print(f"  {CLR_GREEN}✔ Created macOS LaunchAgent: {plist}{NC}")
        print("  Run: launchctl load -w ~/Library/LaunchAgents/com.shotclean.daemon.plist")


def run_daemon_mode():
    PID_FILE.write_text(str(os.getpid()))
    DaemonManager.start()
    log_event("DAEMON", f"Headless ShotClean daemon online (PID {os.getpid()})")
    print(f"ShotClean background daemon running (PID: {os.getpid()}). Press Ctrl+C to halt.")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        graceful_shutdown()


def stop_daemon_mode():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            PID_FILE.unlink(missing_ok=True)
            print(f"✔ Stopped background daemon (PID {pid}).")
            return
        except ProcessLookupError:
            PID_FILE.unlink(missing_ok=True)
            print("Process was not running. Cleared stale PID.")
            return
        except Exception as e:
            print(f"Error stopping daemon: {e}")
            return
    print("No active daemon PID file found.")


def show_cli_status():
    running = False
    pid_str = "None"
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if platform.system() != "Windows":
                os.kill(pid, 0)
                running = True
                pid_str = str(pid)
            else:
                running = True
                pid_str = str(pid)
        except (ProcessLookupError, ValueError):
            pass

    cfg = load_config()
    folders = cfg.get("folders_v2", [])
    ledger_count = len(_load_ledger_unlocked())
    print(f"ShotClean v{CURRENT_VERSION} System Status:")
    print(f"  Daemon State       : {'RUNNING (PID ' + pid_str + ')' if running else 'STOPPED'}")
    print(f"  Active Sweeper     : {'Enabled' if cfg.get('active_sweeper', True) else 'Disabled'}")
    print(f"  Scrubbed Ledger    : {ledger_count} tracked file(s)")
    print(f"  Notifications      : {'Enabled' if cfg.get('enable_notifications', False) else 'Disabled'}")
    print(f"  Watched Directories: {len(folders)}")
    for f in folders:
        rec = " (Recursive)" if f.get("recursive") else ""
        print(f"    • {f.get('path')} [{f.get('profile', 'custom').upper()}]{rec}")


# ==============================================================================
# MAIN EVENT LOOP & SIGNAL SHIELD
# ==============================================================================

_SHUTDOWN_CALLED = False

def graceful_shutdown(signum=None, frame=None):
    global _SHUTDOWN_CALLED
    if _SHUTDOWN_CALLED:
        return
    _SHUTDOWN_CALLED = True
    DaemonManager.stop()
    EXIFTOOL_ENGINE.close()
    WORK_QUEUE.put(None)
    PID_FILE.unlink(missing_ok=True)
    release_wake_lock()
    print(f"\n  {CLR_GREEN}Shutdown complete. Stay safe!{NC}\n")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_shutdown)
if platform.system() != "Windows":
    signal.signal(signal.SIGTERM, graceful_shutdown)


def main():
    parser = argparse.ArgumentParser(description="ShotClean Universal Anti-Forensics & Privacy Shield")
    parser.add_argument("--daemon", action="store_true", help="Run as silent headless background daemon")
    parser.add_argument("--stop", action="store_true", help="Stop any active background daemon")
    parser.add_argument("--status", action="store_true", help="Print active daemon and monitoring status")
    parser.add_argument("--sweep", action="store_true", help="Run an immediate one-shot catch-up sweep across watched folders")
    parser.add_argument("--clean", type=str, help="One-shot clean a single file or directory and exit")
    parser.add_argument("--install-service", action="store_true", help="Install auto-start system service and Termux:Widget shortcuts")
    args = parser.parse_args()

    if args.daemon:
        run_daemon_mode()
        return

    if args.stop:
        stop_daemon_mode()
        return

    if args.status:
        show_cli_status()
        return

    if args.sweep:
        run_active_directory_sweep()
        WORK_QUEUE.join()
        print("✔ Active folder sweep finished.")
        return

    if args.clean:
        p = Path(args.clean)
        if p.is_file():
            res = sanitize_single_file(p)
            print(f"Cleaned: {res}")
        elif p.is_dir():
            for ext in ALL_SUPPORTED_EXTENSIONS:
                for img in p.glob(f"*{ext}"):
                    sanitize_single_file(img)
            print(f"Scrubbed directory: {p}")
        else:
            print(f"Error: path does not exist: {p}")
        return

    if args.install_service:
        install_system_service()
        return

    # Interactive TUI mode (ensure stdin is attached to /dev/tty even if piped from curl | bash)
    if not ensure_tty_stdin():
        run_daemon_mode()
        return
    DaemonManager.start()
    threading.Thread(target=check_updates_background, daemon=True).start()

    main_menu_items = [
        ("1", "⚡ Toggle Daemon (Start / Halt)", "toggle"),
        ("2", "📁 Manage Folders & Granular Rules", "folders"),
        ("3", "🧹 Active Catch-Up Sweeper Settings", "sweeper"),
        ("4", "🎨 Custom Preset Studio (Save & Load)", "presets"),
        ("5", "🎲 Naming & Camouflage Studio", "naming"),
        ("6", "⏱️  Timestomp & Clamping Studio", "clamping"),
        ("7", "🔐 Safety Backup Vault", "vault"),
        ("8", "🔍 Live EXIF & Metadata Audit", "audit"),
        ("9", "🧹 Bulk Folder Scrubber", "bulk"),
        ("10", "📜 Live Event Stream Logs", "logs"),
        ("11", "🐤 Privacy Canary Tester", "canary"),
        ("12", "🔬 Engine Diagnostics & Shortcuts", "diagnostics"),
        ("13", "🔄 Check for Updates", "update"),
        ("14", "📖 Privacy Field Manual", "manual"),
        ("0", "🚪 Exit Suite", "exit"),
    ]

    cursor = 0
    try:
        while True:
            choice = run_arrow_menu(draw_main_header, main_menu_items, title="COMMAND CENTER", default_idx=cursor, is_main=True)

            if choice == "toggle":
                DaemonManager.stop() if DaemonManager.is_running else DaemonManager.start()
                cursor = 0
            elif choice == "folders":
                tool_manage_folders()
                cursor = 1
            elif choice == "sweeper":
                tool_manage_sweeper()
                cursor = 2
            elif choice == "presets":
                tool_manage_presets()
                cursor = 3
            elif choice == "naming":
                tool_manage_naming()
                cursor = 4
            elif choice == "clamping":
                tool_manage_clamping()
                cursor = 5
            elif choice == "vault":
                tool_manage_vault()
                cursor = 6
            elif choice == "audit":
                tool_live_audit()
                cursor = 7
            elif choice == "bulk":
                tool_bulk_clean()
                cursor = 8
            elif choice == "logs":
                tool_live_logs()
                cursor = 9
            elif choice == "canary":
                tool_privacy_canary()
                cursor = 10
            elif choice == "diagnostics":
                tool_engine_diagnostics()
                cursor = 11
            elif choice == "update":
                tool_manual_check_updates()
                cursor = 12
            elif choice == "manual":
                tool_feature_guide()
                cursor = 13
            elif choice == "exit":
                break

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        graceful_shutdown()


if __name__ == "__main__":
    main()
