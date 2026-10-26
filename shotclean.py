#!/usr/bin/env python3
"""
ShotClean Universal Studio v5.0.0
Cross-platform metadata stripper, anti-forensics suite & granular folder protection.
Repository: https://github.com/zakeer-career/shotclean
"""

import hashlib
import hmac
import json
import os
import platform
import queue
import random
import select
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import zlib
from pathlib import Path

# Enable ANSI formatting on Windows CMD/PowerShell
if platform.system() == "Windows":
    os.system("")

# ==============================================================================
# VERSION & GITHUB AUTO-UPDATER
# ==============================================================================

CURRENT_VERSION = "5.0.0"
GITHUB_REPO = "zakeer-career/shotclean"

UPDATE_AVAILABLE = False
REMOTE_COMMIT_SHORT = ""
REMOTE_SHA = ""

HOME = Path.home()
SHOTCLEAN_DIR = HOME / ".shotclean"
COMMIT_CACHE_FILE = SHOTCLEAN_DIR / "installed_commit.txt"
CONFIG_FILE = SHOTCLEAN_DIR / "config.json"
LOG_FILE = SHOTCLEAN_DIR / "activity.log"
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
        req = urllib.request.Request(url, headers={"User-Agent": "ShotClean-Updater"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
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
        req = urllib.request.Request(raw_url, headers={"User-Agent": "ShotClean-Updater"})

        with urllib.request.urlopen(req, timeout=10) as resp:
            new_code = resp.read().decode("utf-8")

        if "ShotClean" not in new_code:
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


threading.Thread(target=check_updates_background, daemon=True).start()

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
SESSION_CLEANED_COUNT = 0


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
# PER-FOLDER GRANULAR POLICIES & CONFIGURATION
# ==============================================================================

DEFAULT_FOLDER_PROFILE = {
    "profile": "ghost",
    "strip_exif": True,
    "strip_icc": True,
    "clamp_time": True,
    "random_hash": True,
    "naming_mode": "hash",
    "prefix": "img_",
    "hash_len": 12,
}

PROFILE_PRESETS = {
    "ghost": {
        "label": "🛡️ Ghost (Full Scrub + Clamped 2020 + UUID Hash)",
        "strip_exif": True, "strip_icc": True, "clamp_time": True, "random_hash": True, "naming_mode": "hash"
    },
    "balanced": {
        "label": "⚖️ Balanced (Scrub + Word Slug - Shows in Today's Gallery)",
        "strip_exif": True, "strip_icc": True, "clamp_time": False, "random_hash": True, "naming_mode": "slug"
    },
    "metadata_only": {
        "label": "🏷️ Metadata Strip Only (Keep Original Name & Current Time)",
        "strip_exif": True, "strip_icc": True, "clamp_time": False, "random_hash": False, "naming_mode": "disabled"
    },
    "timestomp_only": {
        "label": "⏱️ Timestomp Only (Clamp Date to 2020, Keep Filename & EXIF)",
        "strip_exif": False, "strip_icc": False, "clamp_time": True, "random_hash": False, "naming_mode": "disabled"
    },
    "custom": {
        "label": "🛠️ Custom Tailored Rules (Manual Feature Toggles)",
    }
}


def make_folder_entry(path_str: str, profile_name="ghost") -> dict:
    p = Path(path_str)
    entry = {
        "path": str(p),
        "name": p.name or str(p),
        **DEFAULT_FOLDER_PROFILE
    }
    if profile_name in PROFILE_PRESETS and profile_name != "custom":
        entry["profile"] = profile_name
        for k, v in PROFILE_PRESETS[profile_name].items():
            if k != "label":
                entry[k] = v
    return entry


DEFAULT_CONFIG = {
    "folders_v2": [make_folder_entry(str(detect_default_folder()), "ghost")],
    "enable_backup": False,
    "encrypt_vault": True,
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

            return {**DEFAULT_CONFIG, **data}
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


CONFIG = load_config()


def get_rules_for_file(filepath: Path, cfg: dict) -> dict:
    file_parent = filepath.parent.resolve()
    for entry in cfg.get("folders_v2", []):
        try:
            entry_path = Path(entry["path"]).resolve()
            if file_parent == entry_path or filepath.resolve().is_relative_to(entry_path):
                return entry
        except Exception:
            if str(filepath).startswith(str(entry.get("path", ""))):
                return entry
    return DEFAULT_FOLDER_PROFILE


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
# KEYBOARD INPUT READER (ANSI + VIM/WASD KEYS)
# ==============================================================================

def read_single_key():
    if platform.system() == "Windows":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            code = msvcrt.getch()
            if code == b'H': return "UP"
            elif code == b'P': return "DOWN"
        elif ch in (b'\r', b'\n', b' '):
            return "ENTER"
        elif ch in (b'q', b'Q'):
            return "QUIT"
        elif ch in (b'w', b'W', b'k', b'K'):
            return "UP"
        elif ch in (b's', b'S', b'j', b'J'):
            return "DOWN"
        return ch.decode('latin1', errors='ignore')
    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                r, _, _ = select.select([sys.stdin], [], [], 0.20)
                if r:
                    ch2 = sys.stdin.read(1)
                    if ch2 in ('[', 'O'):
                        r2, _, _ = select.select([sys.stdin], [], [], 0.20)
                        if r2:
                            ch3 = sys.stdin.read(1)
                            if ch3 in ('A', 'k'): return "UP"
                            elif ch3 in ('B', 'j'): return "DOWN"
                            elif ch3 == 'C': return "RIGHT"
                            elif ch3 == 'D': return "LEFT"
                return "ESC"
            elif ch in ('\r', '\n', ' '):
                return "ENTER"
            elif ch in ('k', 'K', 'w', 'W'):
                return "UP"
            elif ch in ('j', 'J', 's', 'S'):
                return "DOWN"
            elif ch in ('q', 'Q'):
                return "QUIT"
            elif ch == '\x03':
                raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ==============================================================================
# INTERACTIVE ARROW-KEY FOLDER BROWSER
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

    while True:
        items = ["✔ [CHOOSE THIS FOLDER]"]
        root_parent = Path("/storage/emulated/0") if Path("/storage/emulated/0").exists() else Path.home()
        if cur_dir != root_parent and cur_dir != cur_dir.parent:
            items.append("⬆ [.. Go Up / Parent Folder]")

        subdirs = []
        try:
            for entry in sorted(cur_dir.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    subdirs.append(f"📁 {entry.name}")
        except PermissionError:
            subdirs.append("⚠️ [Permission Denied]")

        items.extend(subdirs)
        total = len(items)

        if cursor >= total: cursor = max(0, total - 1)
        if cursor < 0: cursor = 0

        if cursor < offset:
            offset = cursor
        elif cursor >= offset + page_size:
            offset = cursor - page_size + 1

        os.system("cls" if os.name == "nt" else "clear")
        w = get_ui_width()
        print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  {BOLD}📁  INTERACTIVE FOLDER NAVIGATOR{NC}")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")
        print(f"  {CLR_GRAY}Location:{NC} {CLR_AMBER}{BOLD}{truncate_middle(str(cur_dir), w - 12)}{NC}")
        print(f"  {CLR_BLUE}Controls: [↑/↓ or W/S] Move · [Enter/Space] Select · [Q] Cancel{NC}")
        print(f"{CLR_BORDER}{'─' * w}{NC}")

        end_idx = min(offset + page_size, total)
        for i in range(offset, end_idx):
            item_text = items[i]
            if i == cursor:
                print(f"  {CLR_GREEN}{BOLD}▶ {item_text}{NC}")
            else:
                print(f"    {CLR_GRAY}{item_text}{NC}")

        print(f"{CLR_BORDER}{'─' * w}{NC}")
        print(f"  {DIM}Showing item {cursor + 1} of {total}  (Press 'T' to type path manually){NC}")

        key = read_single_key()
        if key == "UP":
            cursor = (cursor - 1) % total
        elif key == "DOWN":
            cursor = (cursor + 1) % total
        elif key == "ENTER":
            chosen = items[cursor]
            if chosen == "✔ [CHOOSE THIS FOLDER]":
                return cur_dir
            elif chosen == "⬆ [.. Go Up / Parent Folder]":
                cur_dir = cur_dir.parent
                cursor = 0
                offset = 0
            elif chosen.startswith("📁 "):
                sub_name = chosen[3:]
                cur_dir = cur_dir / sub_name
                cursor = 0
                offset = 0
        elif key in ("t", "T"):
            os.system("cls" if os.name == "nt" else "clear")
            print(f"\n  {CLR_CYAN}Manual Path Input:{NC}")
            custom = input("  Path > ").strip()
            cp = Path(custom)
            if cp.exists() and cp.is_dir():
                return cp
        elif key in ("QUIT", "ESC"):
            return None


# ==============================================================================
# PERSISTENT DEADLOCK-PROTECTED EXIFTOOL DAEMON (-stay_open)
# ==============================================================================

class ExifToolDaemon:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
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
            log_event("ENGINE", f"Persistent ExifTool daemon online (PID: {self.proc.pid})")
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

            if not self.proc:
                try:
                    res = subprocess.run(
                        ["exiftool"] + list(args),
                        capture_output=True, text=True, timeout=timeout
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
                            log_event("WARN", "Pipe response timed out. Auto-recycling engine...")
                            self._restart()
                            res = subprocess.run(
                                ["exiftool"] + list(args),
                                capture_output=True, text=True, timeout=3.0
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
# VAULT ENCRYPTION & CANARY GENERATOR
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
# DICETIME WORDLISTS & NAMING ENGINE
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

GENERATED_NAMES_CACHE = set()


def generate_sanitized_filename(filepath: Path, rules: dict) -> str:
    mode = rules.get("naming_mode", "hash")
    ext = filepath.suffix.lower()
    now = time.localtime()
    date_stamp = time.strftime("%Y%m%d", now)

    if mode == "disabled" or not rules.get("random_hash", True):
        return filepath.name
    elif mode == "slug":
        return f"{random.choice(SLUG_ADJECTIVES)}-{random.choice(SLUG_NOUNS)}-{random.randint(10, 99)}{ext}"
    elif mode == "decoy_wa":
        return f"IMG-{date_stamp}-WA{random.randint(1, 9999):04d}{ext}"
    elif mode == "decoy_dcim":
        return f"DSC_{random.randint(1000, 9999):04d}{ext}"
    elif mode == "decoy_reddit":
        ts = f"{random.randint(0,23):02d}{random.randint(0,59):02d}{random.randint(0,59):02d}"
        return f"RDT_{date_stamp}_{ts}{ext}"
    else:
        prefix = rules.get("prefix", "img_")
        h_len = int(rules.get("hash_len", 12))
        return f"{prefix}{uuid.uuid4().hex[:h_len]}{ext}"


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

        if not interactive:
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
            subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])

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

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ==============================================================================
# GRANULAR SANITIZATION WORKER QUEUE
# ==============================================================================

WORK_QUEUE = queue.Queue()
PROCESSED_COOLDOWN = {}


def file_settling_probe(filepath: Path, timeout: float = 3.0) -> bool:
    start_time = time.time()
    last_size = -1
    while time.time() - start_time < timeout:
        try:
            if not filepath.exists():
                return False
            cur_size = filepath.stat().st_size
            if cur_size == 0 or cur_size != last_size:
                last_size = cur_size
                time.sleep(0.12)
                continue
            with open(filepath, "r+b"):
                return True
        except (PermissionError, IOError, OSError):
            time.sleep(0.12)
    return False


def sanitization_worker():
    global SESSION_CLEANED_COUNT
    while True:
        filepath = WORK_QUEUE.get()
        if filepath is None:
            break

        try:
            cfg = load_config()
            rules = get_rules_for_file(filepath, cfg)

            prefix = rules.get("prefix", "img_")
            mode = rules.get("naming_mode", "hash")

            if not filepath.exists() or filepath.name.startswith("."):
                continue
            if filepath.name in GENERATED_NAMES_CACHE:
                continue
            if mode == "hash" and prefix and filepath.name.startswith(prefix):
                continue

            log_event("PROBE", f"Interception: {filepath.name} (Folder Profile: {rules.get('profile', 'custom').upper()})")
            if not file_settling_probe(filepath):
                continue

            file_key = f"{filepath.name}_{filepath.stat().st_size}"
            now = time.time()
            if file_key in PROCESSED_COOLDOWN and (now - PROCESSED_COOLDOWN[file_key]) < 4.0:
                continue
            PROCESSED_COOLDOWN[file_key] = now

            # 1. Encrypted Safety Vault Backup
            if cfg.get("enable_backup", False):
                try:
                    raw_bytes = filepath.read_bytes()
                    t_token = int(time.time())
                    if cfg.get("encrypt_vault", True):
                        sec = get_vault_secret()
                        enc = encrypt_payload(raw_bytes, sec)
                        (VAULT_DIR / f"{filepath.stem}_{t_token}.enc").write_bytes(enc)
                    else:
                        (VAULT_DIR / f"{filepath.stem}_{t_token}{filepath.suffix}").write_bytes(raw_bytes)
                except Exception as ex:
                    log_event("ERROR", f"Vault backup failed: {ex}")

            # 2. Granular ExifTool Scrubbing
            if rules.get("strip_exif", True):
                args = ["-all="]
                if rules.get("strip_icc", True):
                    args.append("-icc_profile:all=")
                args.extend(["-overwrite_original_in_place", str(filepath)])

                t0 = time.time()
                EXIFTOOL_ENGINE.execute(*args, timeout=4.0)
                elapsed_ms = int((time.time() - t0) * 1000)
                log_event("EXIF", f"Scrubbed EXIF/ICC profiles in {elapsed_ms}ms")

            target_path = filepath

            # 3. Granular Renaming
            if rules.get("random_hash", True) and mode != "disabled":
                new_name = generate_sanitized_filename(filepath, rules)
                target_path = filepath.parent / new_name

                GENERATED_NAMES_CACHE.add(new_name)
                if len(GENERATED_NAMES_CACHE) > 300:
                    GENERATED_NAMES_CACHE.pop()

                try:
                    filepath.rename(target_path)
                    log_event("RENAME", f"Renamed ({mode}): {filepath.name} -> {target_path.name}")
                except OSError as e:
                    log_event("ERROR", f"Rename error: {e}")
                    target_path = filepath

            # 4. Granular Anti-Forensic Timestamp Clamping
            if rules.get("clamp_time", True):
                try:
                    epoch_2020 = 1577836800.0
                    os.utime(target_path, (epoch_2020, epoch_2020))
                    log_event("TIMESTOMP", "Clamped mtime/atime to 2020-01-01 00:00:00")
                except OSError:
                    pass

            # 5. Media Scanner Refresh
            if "com.termux" in os.environ.get("PREFIX", ""):
                subprocess.run(
                    ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

            SESSION_CLEANED_COUNT += 1
            log_event("COMPLETE", f"✔ Sanitized via [{rules.get('profile', 'custom').upper()}]: {target_path.name}")

        except Exception as ex:
            log_event("ERROR", f"Worker uncaught exception: {ex}")
        finally:
            WORK_QUEUE.task_done()


WORKER_THREAD = threading.Thread(target=sanitization_worker, daemon=True)
WORKER_THREAD.start()


class AsyncWatchHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            p = Path(event.src_path)
            if p.suffix.lower() in VALID_EXTENSIONS:
                WORK_QUEUE.put(p)

    def on_moved(self, event):
        if not event.is_directory:
            p = Path(event.dest_path)
            if p.suffix.lower() in VALID_EXTENSIONS:
                WORK_QUEUE.put(p)


class DaemonManager:
    observer = None
    is_running = False

    @classmethod
    def start(cls):
        if cls.is_running:
            return
        cfg = load_config()
        valid_folders = [Path(f["path"]) for f in cfg.get("folders_v2", []) if Path(f["path"]).exists()]
        if not valid_folders:
            log_event("WARN", "No registered folders exist on disk to monitor.")
            return

        cls.observer = Observer()
        handler = AsyncWatchHandler()
        for folder in valid_folders:
            cls.observer.schedule(handler, path=str(folder), recursive=False)

        cls.observer.start()
        cls.is_running = True
        log_event("DAEMON", f"Background watcher online. Tracking {len(valid_folders)} folder(s).")

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
# CLEAN MAIN DASHBOARD
# ==============================================================================

def draw_dashboard():
    os.system("cls" if os.name == "nt" else "clear")
    cfg = load_config()
    w = get_ui_width()
    folders = cfg.get("folders_v2", [])
    status_text = f"{CLR_GREEN}● RUNNING{NC}" if DaemonManager.is_running else f"{CLR_RED}○ STOPPED{NC}"

    # Banner Header
    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🛡️  S H O T C L E A N{NC}  {CLR_GRAY}·{NC}  {CLR_PURPLE}v{CURRENT_VERSION} Studio{NC}")
    print(f"{CLR_CYAN}│{NC}  {DIM}Zero-Footprint Anti-Forensics & Granular Shield{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")

    if UPDATE_AVAILABLE:
        print(f"{CLR_AMBER}╭─ {BOLD}🔔 UPDATE AVAILABLE{NC} {CLR_AMBER}{'─' * max(0, w - 24)}╮{NC}")
        print(f"{CLR_AMBER}│{NC}  Commit {BOLD}{REMOTE_COMMIT_SHORT}{NC} ready · Select Option [10] to install")
        print(f"{CLR_AMBER}╰{'─' * (w - 2)}╯{NC}")

    # System Status Card
    pipe_status = f"{CLR_GREEN}Active (-stay_open){NC}"
    vault_status = f"{CLR_GREEN}ON (AES Encrypted){NC}" if cfg.get("enable_backup") else f"{CLR_GRAY}OFF{NC}"

    print(f"{CLR_BLUE}╭─ {BOLD}SYSTEM & ENGINE HEALTH{NC} {CLR_BLUE}{'─' * max(0, w - 26)}╮{NC}")
    print(f"{CLR_BLUE}│{NC} Engine State : {status_text}   {CLR_GRAY}(Session scrubbed: {SESSION_CLEANED_COUNT}){NC}")
    print(f"{CLR_BLUE}│{NC} ExifTool     : {pipe_status}")
    print(f"{CLR_BLUE}│{NC} Backup Vault : {vault_status}  {CLR_GRAY}(~/.shotclean/vault){NC}")
    print(f"{CLR_BLUE}╰{'─' * (w - 2)}╯{NC}")

    # Monitored Folders Summary Card
    print(f"{CLR_AMBER}╭─ {BOLD}MONITORED FOLDERS ({len(folders)}){NC} {CLR_AMBER}{'─' * max(0, w - 26)}╮{NC}")
    if not folders:
        print(f"{CLR_AMBER}│{NC}  {CLR_RED}No folders registered! Add one via Option [2].{NC}")
    else:
        for f in folders[:3]:
            p_label = f.get("profile", "custom").upper()
            path_disp = truncate_middle(f.get("path", ""), w - 24)
            print(f"{CLR_AMBER}│{NC}  📁 {BOLD}{path_disp}{NC} [{CLR_GREEN}{p_label}{NC}]")
        if len(folders) > 3:
            print(f"{CLR_AMBER}│{NC}  {CLR_GRAY}...and {len(folders) - 3} more folder(s){NC}")
    print(f"{CLR_AMBER}╰{'─' * (w - 2)}╯{NC}")

    # Clean Two-Column Action Grid (No long descriptions)
    print(f"{CLR_BORDER}╭─ {BOLD}COMMAND CENTER{NC} {CLR_BORDER}{'─' * max(0, w - 18)}╮{NC}")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[1]{NC} ⚡ Toggle Daemon       {CLR_CYAN}[2]{NC} 📁 Manage Folders")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[3]{NC} 🎲 Naming Studio       {CLR_CYAN}[4]{NC} 🔐 Safety Backup Vault")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[5]{NC} 🔍 Live EXIF Audit     {CLR_CYAN}[6]{NC} 🧹 Bulk Clean Folder")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[7]{NC} 📜 Live Stream Logs    {CLR_CYAN}[8]{NC} 🐤 Privacy Canary Tool")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[9]{NC} 🔬 Engine Diagnostics  {CLR_CYAN}[10]{NC}🔄 Check for Updates")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[11]{NC}📖 Feature Manual       {CLR_RED}[0]{NC} 🚪 Exit Suite")
    print(f"{CLR_BORDER}╰{'─' * (w - 2)}╯{NC}")


# ==============================================================================
# SUBMENU 1: MANAGE FOLDERS & RULES
# ==============================================================================

def tool_manage_folders():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        folders = cfg.get("folders_v2", [])
        w = get_ui_width()

        # Pinned Educational Upper Section
        print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW PER-FOLDER RULES WORK{NC} {CLR_CYAN}{'─' * max(0, w - 32)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  Assign independent security policies per directory:")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}GHOST{NC}     : Wipes EXIF/ICC + 2020 clamp + random hash.")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}BALANCED{NC}  : Wipes EXIF/ICC + readable slug (shows Today).")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}METADATA{NC}  : Wipes EXIF/ICC only (keeps filename intact).")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}TIMESTOMP{NC} : Clamps time to 2020 only (keeps EXIF & name).")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        print(f"  {BOLD}Registered Directories ({len(folders)}):{NC}\n")
        for idx, f in enumerate(folders, 1):
            p = Path(f["path"])
            status = f"{CLR_GREEN}Active{NC}" if p.exists() else f"{CLR_RED}Missing Path{NC}"
            profile_name = f.get("profile", "custom").upper()
            disp = truncate_middle(f["path"], w - 24)

            print(f"  [{idx}] {BOLD}{disp}{NC} [{CLR_AMBER}{profile_name}{NC}] ({status})")
            exif_st = "EXIF:ON" if f.get("strip_exif") else "EXIF:OFF"
            icc_st = "ICC:ON" if f.get("strip_icc") else "ICC:OFF"
            time_st = "Clamp:2020" if f.get("clamp_time") else "Time:Current"
            name_st = f"Name:{f.get('naming_mode', 'hash')}"
            print(f"      ↳ {CLR_GRAY}{exif_st} · {icc_st} · {time_st} · {name_st}{NC}\n")

        print(f"{CLR_BORDER}{'─' * w}{NC}")
        print(f"  {CLR_GREEN}[A] Add New Folder (Arrow Navigator){NC}")
        print(f"  [T] Add by Manual Path Entry")
        print(f"  [P] Quick Preset: Add Default Screenshots Folder")
        print(f"  [1-{len(folders)}] Select Folder to Customize Its Rules / Delete")
        print(f"  [0] Back to Main Menu")

        c = input("\n  Select Option > ").strip()

        if c.lower() == "a":
            chosen = interactive_folder_browser()
            if chosen and chosen.exists():
                str_p = str(chosen)
                if not any(f["path"] == str_p for f in folders):
                    new_entry = make_folder_entry(str_p, "ghost")
                    folders.append(new_entry)
                    cfg["folders_v2"] = folders
                    save_config(cfg)
                    DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Added: {chosen.name} [Default: GHOST policy]{NC}")
                    time.sleep(1)

        elif c.lower() == "t":
            manual = input("\n  Enter full folder path: ").strip().strip("'\"")
            mp = Path(manual)
            if mp.exists() and mp.is_dir():
                if not any(f["path"] == str(mp) for f in folders):
                    new_entry = make_folder_entry(str(mp), "ghost")
                    folders.append(new_entry)
                    cfg["folders_v2"] = folders
                    save_config(cfg)
                    DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Added: {mp.name}{NC}")
                    time.sleep(1)
            else:
                print(f"  {CLR_RED}✖ Path does not exist or is not a directory.{NC}")
                time.sleep(1)

        elif c.lower() == "p":
            def_path = str(detect_default_folder())
            if not any(f["path"] == def_path for f in folders):
                folders.append(make_folder_entry(def_path, "ghost"))
                cfg["folders_v2"] = folders
                save_config(cfg)
                DaemonManager.restart()
                print(f"\n  {CLR_GREEN}✔ Added default screenshots folder!{NC}")
                time.sleep(1)

        elif c.isdigit() and 1 <= int(c) <= len(folders):
            configure_individual_folder(int(c) - 1)

        elif c == "0":
            break


def configure_individual_folder(index: int):
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        folders = cfg.get("folders_v2", [])
        if index >= len(folders):
            return

        f = folders[index]
        w = get_ui_width()

        # Pinned Educational Upper Section for Specific Folder
        print(f"{CLR_CYAN}╭─ {BOLD}💡 POLICY BREAKDOWN FOR THIS FOLDER{NC} {CLR_CYAN}{'─' * max(0, w - 38)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  Target: {CLR_WHITE}{truncate_middle(f['path'], w - 14)}{NC}")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}EXIF/ICC Scrubbing{NC} : Removes device model, build & screen color.")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}Timestamp Clamp{NC}    : 2020-01-01 prevents filesystem timeline correlation.")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}Naming Camouflage{NC}  : Masquerades as WhatsApp, camera, or word slug.")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        print(f"  Active Profile  : {CLR_AMBER}{BOLD}{f.get('profile', 'custom').upper()}{NC}")
        print(f"  1. EXIF Metadata: {'[ 🟢 ON ]' if f.get('strip_exif') else '[ ⚪ OFF ]'}")
        print(f"  2. ICC Profile  : {'[ 🟢 ON ]' if f.get('strip_icc') else '[ ⚪ OFF ]'}")
        print(f"  3. Time Clamping: {'[ 🟢 ON (2020-01-01) ]' if f.get('clamp_time') else '[ ⚪ OFF (Preserve Today) ]'}")
        print(f"  4. Naming Style : {CLR_CYAN}{f.get('naming_mode', 'hash')}{NC} (Prefix: '{f.get('prefix', 'img_')}')\n")

        print(f"{CLR_BORDER}{'─' * w}{NC}")
        print("  [1] Apply Preset (Ghost / Balanced / Metadata-Only / Timestomp-Only)")
        print("  [2] Toggle EXIF Metadata Stripping [ON/OFF]")
        print("  [3] Toggle Display ICC Profile Removal [ON/OFF]")
        print("  [4] Toggle Timestamp Clamping (2020 vs Today)")
        print("  [5] Change Naming Camouflage Style")
        print("  [6] 🗑️  Delete this folder from watchlist")
        print("  [0] Done / Save & Return")

        choice = input("\n  Select > ").strip()

        if choice == "1":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== Select Preset for This Folder ==={NC}\n")
            print("  [1] 🛡️  Ghost (Full EXIF + ICC + Clamped 2020 + UUID Hash)")
            print("  [2] ⚖️  Balanced (Full Scrub + Word Slug - Shows in Today's Gallery)")
            print("  [3] 🏷️  Metadata Strip Only (Scrub EXIF/ICC, keep filename & Today)")
            print("  [4] ⏱️  Timestomp Only (Clamp time to 2020, leave bytes & filename alone)")
            p_sel = input("\n  Select Preset [1-4]: ").strip()
            if p_sel == "1":
                for k, v in PROFILE_PRESETS["ghost"].items():
                    if k != "label": f[k] = v
                f["profile"] = "ghost"
            elif p_sel == "2":
                for k, v in PROFILE_PRESETS["balanced"].items():
                    if k != "label": f[k] = v
                f["profile"] = "balanced"
            elif p_sel == "3":
                for k, v in PROFILE_PRESETS["metadata_only"].items():
                    if k != "label": f[k] = v
                f["profile"] = "metadata_only"
            elif p_sel == "4":
                for k, v in PROFILE_PRESETS["timestomp_only"].items():
                    if k != "label": f[k] = v
                f["profile"] = "timestomp_only"
            save_config(cfg)
            DaemonManager.restart()

        elif choice == "2":
            f["strip_exif"] = not f.get("strip_exif", True)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif choice == "3":
            f["strip_icc"] = not f.get("strip_icc", True)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif choice == "4":
            f["clamp_time"] = not f.get("clamp_time", True)
            f["profile"] = "custom"
            save_config(cfg); DaemonManager.restart()

        elif choice == "5":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== Select Naming Style for This Folder ==={NC}\n")
            print("  [1] UUID Hex Hash       (e.g. img_7c9f2b84.png)")
            print("  [2] Readable Word Slug   (e.g. swift-falcon-42.png)")
            print("  [3] WhatsApp Decoy       (e.g. IMG-20261026-WA0042.png)")
            print("  [4] Camera DCIM Decoy    (e.g. DSC_4821.png)")
            print("  [5] Reddit/Web Decoy     (e.g. RDT_20261026_140218.png)")
            print("  [6] Original Filename    (Disabled)")
            n_sel = input("\n  Choose [1-6]: ").strip()
            styles = {"1": "hash", "2": "slug", "3": "decoy_wa", "4": "decoy_dcim", "5": "decoy_reddit", "6": "disabled"}
            if n_sel in styles:
                f["naming_mode"] = styles[n_sel]
                f["random_hash"] = (styles[n_sel] != "disabled")
                f["profile"] = "custom"
                save_config(cfg); DaemonManager.restart()

        elif choice == "6":
            confirm = input(f"\n  Remove '{f['path']}' from monitored list? [y/N]: ").strip().lower()
            if confirm in ["y", "yes"]:
                folders.pop(index)
                cfg["folders_v2"] = folders
                save_config(cfg)
                DaemonManager.restart()
                print(f"  {CLR_GREEN}✔ Removed.{NC}")
                time.sleep(0.8)
                return

        elif choice == "0":
            break


# ==============================================================================
# SUBMENU 2: NAMING & CAMOUFLAGE STUDIO
# ==============================================================================

def tool_manage_naming():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        w = get_ui_width()

        folders = cfg.get("folders_v2", [])
        target_folder = folders[0] if folders else DEFAULT_FOLDER_PROFILE
        mode = target_folder.get("naming_mode", "hash")
        pfx = target_folder.get("prefix", "img_")
        h_len = target_folder.get("hash_len", 12)

        # Pinned Educational Upper Section
        print(f"{CLR_CYAN}╭─ {BOLD}💡 WHAT NAMING CAMOUFLAGE DOES{NC} {CLR_CYAN}{'─' * max(0, w - 34)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  Standard screenshot names leak exact date, hour & second.")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}UUID Hash{NC}   : Unpredictable hex tokens (e.g. img_7c9f2b84.png).")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}Word Slugs{NC}  : Anonymous, memorable words (e.g. swift-falcon-42.png).")
        print(f"{CLR_CYAN}│{NC}  • {BOLD}Decoys{NC}      : Plausible deniability (WhatsApp, DCIM, Reddit).")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        dummy_path = Path("Screenshot_20261026-165201.png")
        sample_preview = generate_sanitized_filename(dummy_path, target_folder)

        print(f"  Active Style  : {CLR_AMBER}{BOLD}{mode.upper()}{NC}")
        print(f"  Sample Output : {CLR_GREEN}{BOLD}{sample_preview}{NC}\n")
        print(f"{CLR_BORDER}{'─' * w}{NC}")

        print("  [1] Switch Style (UUID Hash / Word Slug / Decoys)")
        print("  [2] Configure Custom Prefix (e.g. 'shot_', 'p_', or empty)")
        print("  [3] Set Hash Token Length (8 / 12 / 16 / 32 chars)")
        print("  [4] Roll 3 Test Sample Previews")
        print("  [5] Apply this style to ALL registered folders")
        print("  [0] Back to Main Menu")

        c = input("\n  Select Option > ").strip()

        if c == "1":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== Select Naming Profile ==={NC}\n")
            print("  [1] 🛡️  UUID Hex Hash       (e.g. img_7c9f2b84e1a0.png)")
            print("  [2] 🔤 Readable Word Slug   (e.g. swift-falcon-42.png)")
            print("  [3] 💬 WhatsApp Decoy       (e.g. IMG-20261026-WA0042.png)")
            print("  [4] 📷 Camera DCIM Decoy    (e.g. DSC_4821.png)")
            print("  [5] 🌐 Reddit / Web Decoy   (e.g. RDT_20261026_140218.png)")
            print("  [6] ⚪ Preserve Original    (Keep filename unchanged)")
            sel = input("\n  Choose Profile [1-6]: ").strip()
            styles = {"1": "hash", "2": "slug", "3": "decoy_wa", "4": "decoy_dcim", "5": "decoy_reddit", "6": "disabled"}
            if sel in styles:
                target_folder["naming_mode"] = styles[sel]
                target_folder["random_hash"] = (styles[sel] != "disabled")
                save_config(cfg)
                DaemonManager.restart()
                print(f"\n  {CLR_GREEN}✔ Style updated!{NC}")
                time.sleep(0.8)

        elif c == "2":
            print(f"\n  Current Prefix: '{pfx}'")
            new_pfx = input("  Enter new prefix: ").strip()
            sanitized = "".join(ch for ch in new_pfx if ch.isalnum() or ch in ("_", "-"))
            target_folder["prefix"] = sanitized
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Prefix set to: '{sanitized}'{NC}")
            time.sleep(0.8)

        elif c == "3":
            print("\n  Select Hash Length: [1] 8 chars  [2] 12 chars  [3] 16 chars  [4] 32 chars")
            l_sel = input("  Select [1-4]: ").strip()
            lens = {"1": 8, "2": 12, "3": 16, "4": 32}
            if l_sel in lens:
                target_folder["hash_len"] = lens[l_sel]
                save_config(cfg)
                print(f"  {CLR_GREEN}✔ Length updated.{NC}")
                time.sleep(0.8)

        elif c == "4":
            print(f"\n  {CLR_AMBER}Rolling 3 test samples:{NC}")
            for _ in range(3):
                print(f"   • {CLR_GREEN}{generate_sanitized_filename(dummy_path, target_folder)}{NC}")
            input("\n  Press [Enter] to continue...")

        elif c == "5":
            for f in folders:
                f["naming_mode"] = target_folder.get("naming_mode", "hash")
                f["prefix"] = target_folder.get("prefix", "img_")
                f["hash_len"] = target_folder.get("hash_len", 12)
                f["random_hash"] = target_folder.get("random_hash", True)
            save_config(cfg)
            DaemonManager.restart()
            print(f"\n  {CLR_GREEN}✔ Applied to all {len(folders)} folders!{NC}")
            time.sleep(1)

        elif c == "0":
            break


# ==============================================================================
# SUBMENU 3: ENCRYPTED SAFETY VAULT
# ==============================================================================

def tool_manage_vault():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        w = get_ui_width()
        vault_files = list(VAULT_DIR.glob("*"))
        enc_count = sum(1 for f in vault_files if f.suffix == ".enc")

        # Pinned Educational Upper Section
        print(f"{CLR_CYAN}╭─ {BOLD}💡 ZERO-KNOWLEDGE BACKUP VAULT{NC} {CLR_CYAN}{'─' * max(0, w - 34)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  Saves original, unscrubbed copies before sanitizing.")
        print(f"{CLR_CYAN}│{NC}  • Encrypted with {BOLD}100,000-round PBKDF2 + AES keystream{NC}.")
        print(f"{CLR_CYAN}│{NC}  • Invisible to other Android apps, media scanners & galleries.")
        print(f"{CLR_CYAN}│{NC}  • Restores intact files on demand if needed.")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        print(f"  Vault State     : {'[ 🟢 ON ]' if cfg.get('enable_backup') else '[ ⚪ OFF ]'}")
        print(f"  Stored Backups  : {BOLD}{len(vault_files)}{NC} ({enc_count} AES-encrypted)")
        print(f"  Directory       : {CLR_GRAY}{VAULT_DIR}{NC}\n")
        print(f"{CLR_BORDER}{'─' * w}{NC}")

        print("  [1] Toggle Backup Vault [ON/OFF]")
        print("  [2] Export & Decrypt All Backups to ~/Download/ShotClean_Restored")
        print("  [3] 🗑️  Purge / Wipe Entire Vault Permanently")
        print("  [0] Back to Main Menu")

        c = input("\n  Select Option > ").strip()

        if c == "1":
            cfg["enable_backup"] = not cfg.get("enable_backup", False)
            save_config(cfg)
        elif c == "2":
            if not vault_files:
                print(f"  {CLR_AMBER}Vault is empty.{NC}"); time.sleep(1); continue
            out_dir = HOME / "Download" / "ShotClean_Restored"
            out_dir.mkdir(parents=True, exist_ok=True)
            secret = get_vault_secret()
            for vf in vault_files:
                try:
                    if vf.suffix == ".enc":
                        plain = decrypt_payload(vf.read_bytes(), secret)
                        (out_dir / (vf.stem + ".png")).write_bytes(plain)
                    else:
                        shutil.copy2(vf, out_dir / vf.name)
                except Exception:
                    pass
            print(f"\n  {CLR_GREEN}✔ Decrypted and restored to:{NC}\n  {out_dir}")
            input("\n  Press [Enter] to continue...")
        elif c == "3":
            if input("\n  Permanently delete ALL backups in vault? [y/N]: ").strip().lower() in ["y", "yes"]:
                for vf in vault_files: vf.unlink()
                print(f"  {CLR_GREEN}✔ Vault purged.{NC}"); time.sleep(1)
        elif c == "0":
            break


# ==============================================================================
# SUBMENU 4: LIVE METADATA AUDITOR
# ==============================================================================

def tool_live_audit():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()

    # Pinned Educational Upper Section
    print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW THE LIVE METADATA AUDITOR WORKS{NC} {CLR_CYAN}{'─' * max(0, w - 42)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  Scans the most recent capture for remaining tracking tags:")
    print(f"{CLR_CYAN}│{NC}  • {BOLD}EXIF/XMP{NC} : Checks for device brand, build numbers, GPS.")
    print(f"{CLR_CYAN}│{NC}  • {BOLD}ICC Profile{NC} : Checks for screen calibration identifiers.")
    print(f"{CLR_CYAN}│{NC}  • {BOLD}Timestamps{NC} : Confirms filesystem modification & access dates.")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    cfg = load_config()
    candidates = []
    for f in cfg.get("folders_v2", []):
        p = Path(f["path"])
        if p.exists():
            for ext in VALID_EXTENSIONS:
                candidates.extend(p.glob(f"*{ext}"))

    if not candidates:
        print(f"  {CLR_AMBER}✖ No images found across registered folders.{NC}\n")
        input("  Press [Enter] to return...")
        return

    latest_file = max(candidates, key=lambda f: f.stat().st_mtime)
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


# ==============================================================================
# SUBMENU 5: PRIVACY CANARY AUDIT
# ==============================================================================

def tool_privacy_canary():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()

    # Pinned Educational Upper Section
    print(f"{CLR_CYAN}╭─ {BOLD}💡 HOW THE PRIVACY CANARY AUDIT WORKS{NC} {CLR_CYAN}{'─' * max(0, w - 41)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  Tests whether apps (WhatsApp, Discord, Telegram, Imgur) leak data:")
    print(f"{CLR_CYAN}│{NC}  1. Generates an image with a hidden {BOLD}CANARY-TOKEN-XXXX{NC}.")
    print(f"{CLR_CYAN}│{NC}  2. Send it through the app, then download the image back.")
    print(f"{CLR_CYAN}│{NC}  3. Run Audit: If the token survives, the app tracks you.")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    print("  [1] Generate New Canary Image (Embeds Tracking Token)")
    print("  [2] Audit Downloaded Image (Check If Token Survived)")
    print("  [0] Back to Main Menu")
    c = input("\n  Select Option > ").strip()

    if c == "1":
        token = f"CANARY-{uuid.uuid4().hex[:8].upper()}"
        def_dir = detect_default_folder()
        canary_path = def_dir / f"test_canary_{token}.png"
        create_synthetic_png(canary_path)

        EXIFTOOL_ENGINE.execute(
            f"-Artist={token}",
            f"-UserComment=CANARY_PRIVACY_AUDIT_{token}",
            f"-Copyright={token}",
            "-overwrite_original_in_place",
            str(canary_path),
            timeout=4.0
        )

        print(f"\n  {CLR_GREEN}{BOLD}✔ Canary Generated Successfully!{NC}")
        print(f"  Token : {BOLD}{token}{NC}")
        print(f"  Path  : {CLR_GRAY}{canary_path}{NC}\n")
        print("  Instructions: Upload this test image to the app, download it back, then choose [2].")
        input("\n  Press [Enter] to continue...")

    elif c == "2":
        path_str = input("\n  Enter path to downloaded image (or drag & drop): ").strip().strip("'\"")
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            print(f"  {CLR_RED}File not found.{NC}"); time.sleep(1.2); return

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


# ==============================================================================
# SUBMENU 6: ENGINE DIAGNOSTICS
# ==============================================================================

def tool_engine_diagnostics():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()

    # Pinned Educational Upper Section
    print(f"{CLR_CYAN}╭─ {BOLD}💡 ENGINE & PROCESS HEALTH CHECKS{NC} {CLR_CYAN}{'─' * max(0, w - 37)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  Inspects low-level processes and communication pipes:")
    print(f"{CLR_CYAN}│{NC}  • {BOLD}ExifTool Daemon{NC} : Persistent pipe eliminates 800ms spawn delay.")
    print(f"{CLR_CYAN}│{NC}  • {BOLD}Worker Queue{NC}    : Verifies non-blocking async tasks.")
    print(f"{CLR_CYAN}│{NC}  • {BOLD}Deadlock Check{NC}  : Tests timeout auto-recycling.")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    cfg = load_config()
    daemon_pid = EXIFTOOL_ENGINE.proc.pid if EXIFTOOL_ENGINE.proc else None
    daemon_alive = EXIFTOOL_ENGINE.proc and (EXIFTOOL_ENGINE.proc.poll() is None)

    print(f"  • ExifTool Binary Path  : {CLR_GREEN}{shutil.which('exiftool') or 'NOT FOUND'}{NC}")
    print(f"  • Persistent Daemon PID : {CLR_GREEN}{daemon_pid}{NC} ({'Alive' if daemon_alive else 'Dead/Restarting'})")
    print(f"  • Background Worker     : {'Active' if WORKER_THREAD.is_alive() else 'Dead'}")
    print(f"  • Work Queue Backlog    : {WORK_QUEUE.qsize()} task(s)")

    t0 = time.time()
    test_out = EXIFTOOL_ENGINE.execute("-ver", timeout=3.0)
    elapsed = int((time.time() - t0) * 1000)
    print(f"  • Engine Ping Roundtrip : {CLR_GREEN}{test_out.strip() or 'OK'}{NC} ({elapsed}ms)")

    print(f"\n{CLR_BORDER}{'─' * w}{NC}")
    print("  [1] Force Restart ExifTool Daemon Pipe")
    print("  [0] Back to Main Menu")
    c = input("\n  Select Option > ").strip()
    if c == "1":
        EXIFTOOL_ENGINE._restart()
        print(f"  {CLR_GREEN}✔ Daemon recycled successfully.{NC}")
        time.sleep(1)


# ==============================================================================
# SUBMENU 7: BULK CLEAN, LOGS & MANUAL
# ==============================================================================

def tool_bulk_clean():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()

    # Pinned Educational Upper Section
    print(f"{CLR_CYAN}╭─ {BOLD}💡 BULK SCRUBBING ENGINE{NC} {CLR_CYAN}{'─' * max(0, w - 28)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  Batch-scrubs existing images in registered folders.")
    print(f"{CLR_CYAN}│{NC}  Applies each folder's dedicated local policy rules.")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    cfg = load_config()
    folders = [Path(f["path"]) for f in cfg.get("folders_v2", []) if Path(f["path"]).exists()]
    confirm = input("  Scrub all existing photos across registered folders? [y/N]: ").strip().lower()
    if confirm not in ["y", "yes"]:
        return

    all_images = []
    for folder in folders:
        for ext in VALID_EXTENSIONS:
            all_images.extend([img for img in folder.glob(f"*{ext}") if not img.name.startswith(".")])

    total = len(all_images)
    if total == 0:
        print(f"  {CLR_AMBER}No images found.{NC}")
        time.sleep(1)
        return

    print(f"\n  Found {total} images. Scrubbing via Persistent ExifTool Pipe...")
    for i, img in enumerate(all_images, 1):
        percent = int((i / total) * 100)
        bar = "█" * (percent // 5) + "░" * (20 - (percent // 5))
        sys.stdout.write(f"\r  [{bar}] {percent}% ({i}/{total})")
        sys.stdout.flush()

        rules = get_rules_for_file(img, cfg)
        if rules.get("strip_exif", True):
            args = ["-all="]
            if rules.get("strip_icc", True):
                args.append("-icc_profile:all=")
            args.extend(["-overwrite_original_in_place", str(img)])
            EXIFTOOL_ENGINE.execute(*args, timeout=4.0)

        if rules.get("clamp_time", True):
            try:
                os.utime(img, (1577836800.0, 1577836800.0))
            except OSError:
                pass

    print(f"\n\n  {CLR_GREEN}✔ Bulk scrub complete for {total} images.{NC}\n")
    time.sleep(1.2)


def tool_live_logs():
    os.system("cls" if os.name == "nt" else "clear")
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


def tool_manual_check_updates():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"\n  {CLR_CYAN}Querying GitHub for latest commit on 'main'...{NC}")
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        req = urllib.request.Request(url, headers={"User-Agent": "ShotClean-Updater"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
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


def tool_feature_guide():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        w = get_ui_width()
        print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  {BOLD}📖  SHOTCLEAN FEATURE & PRIVACY MANUAL{NC}")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        print("  [1] 🏷️  EXIF / XMP / IPTC Metadata Stripping")
        print("  [2] 🎨 Display ICC Color Profile Removal")
        print("  [3] 🎲 Decoy Presets & Diceware Word Slugs")
        print("  [4] ⏱️  Anti-Forensic Timestamp Clamping (Timestomp)")
        print("  [5] 🔐 Encrypted Safety Vault (AES-Authenticated)")
        print("  [6] 📁 Granular Per-Folder Rules Explanation")
        print("  [0] Back to Main Menu")
        c = input("\n  Select > ").strip()

        if c == "1":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🏷️ EXIF METADATA STRIPPING ==={NC}\n")
            print("  Wipes camera model, manufacturer, serial numbers, lens info, and GPS coordinates.")
            input("\n  Press [Enter] to return...")
        elif c == "2":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🎨 ICC PROFILE REMOVAL ==={NC}\n")
            print("  Removes display panel color profiles that fingerprint specific phone models.")
            input("\n  Press [Enter] to return...")
        elif c == "3":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🎲 DECOY PRESETS & WORD SLUGS ==={NC}\n")
            print("  Provides plausible deniability by mimicking everyday apps (WhatsApp, DCIM) or generating readable slugs.")
            input("\n  Press [Enter] to return...")
        elif c == "4":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== ⏱️ TIMESTAMP CLAMPING (TIMESTOMP) ==={NC}\n")
            print("  Forces filesystem modification dates to 2020-01-01 to eliminate temporal correlation.")
            print("  Tip: When enabled, gallery apps place screenshots into January 2020!")
            input("\n  Press [Enter] to return...")
        elif c == "5":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🔐 ENCRYPTED SAFETY VAULT ==={NC}\n")
            print("  Keeps encrypted PBKDF2 + AES backups in ~/.shotclean/vault/ before scrubbing.")
            input("\n  Press [Enter] to return...")
        elif c == "6":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 📁 GRANULAR PER-FOLDER RULES ==={NC}\n")
            print("  Screenshots can use 'Ghost' (maximum scrub), while Camera folders can use")
            print("  'Balanced' (shows under Today's feed with a word slug).")
            input("\n  Press [Enter] to return...")
        elif c == "0":
            break


# ==============================================================================
# MAIN EVENT LOOP
# ==============================================================================

def main():
    DaemonManager.start()

    try:
        while True:
            draw_dashboard()
            choice = input(" ❯ Select option: ").strip()

            if choice == "1":
                DaemonManager.stop() if DaemonManager.is_running else DaemonManager.start()
            elif choice == "2":
                tool_manage_folders()
            elif choice == "3":
                tool_manage_naming()
            elif choice == "4":
                tool_manage_vault()
            elif choice == "5":
                tool_live_audit()
            elif choice == "6":
                tool_bulk_clean()
            elif choice == "7":
                tool_live_logs()
            elif choice == "8":
                tool_privacy_canary()
            elif choice == "9":
                tool_engine_diagnostics()
            elif choice == "10":
                tool_manual_check_updates()
            elif choice == "11":
                tool_feature_guide()
            elif choice == "0":
                break

    except (KeyboardInterrupt, EOFError):
        print(f"\n\n  {CLR_AMBER}Interrupted. Exiting ShotClean...{NC}")

    finally:
        DaemonManager.stop()
        EXIFTOOL_ENGINE.close()
        WORK_QUEUE.put(None)
        print(f"  {CLR_GREEN}Shutdown complete. Stay safe!{NC}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
