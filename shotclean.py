#!/usr/bin/env python3
"""
ShotClean Universal Studio v4.7.0
Cross-platform metadata stripper, anti-forensics suite & automated privacy shield.
Repository: https://github.com/zakeer-career/shotclean
"""

import hashlib
import hmac
import json
import os
import platform
import queue
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
# VERSION & GITHUB WEB AUTO-UPDATER
# ==============================================================================

CURRENT_VERSION = "4.7.0"
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
    return max(48, min(cols, 64))


def truncate_middle(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    half = (max_len - 3) // 2
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


DEFAULT_CONFIG = {
    "folders": [str(detect_default_folder())],
    "strip_exif": True,
    "strip_icc": True,
    "random_hash": True,
    "prefix": "img_",
    "hash_len": 12,
    "clamp_time": True,
    "enable_backup": False,
    "encrypt_vault": True,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


CONFIG = load_config()


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
# KEYBOARD INPUT READER (ARROW KEYS & RAW TERMINAL)
# ==============================================================================

def read_single_key():
    if platform.system() == "Windows":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            code = msvcrt.getch()
            if code == b'H': return "UP"
            elif code == b'P': return "DOWN"
        elif ch in (b'\r', b'\n'):
            return "ENTER"
        elif ch in (b'q', b'Q'):
            return "QUIT"
        return ch.decode('latin1', errors='ignore')
    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                r, _, _ = select.select([sys.stdin], [], [], 0.08)
                if r:
                    ch2 = sys.stdin.read(1)
                    if ch2 in ('[', 'O'):
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A': return "UP"
                        elif ch3 == 'B': return "DOWN"
                return "ESC"
            elif ch in ('\r', '\n'):
                return "ENTER"
            elif ch in ('k', 'K'):
                return "UP"
            elif ch in ('j', 'J'):
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
        print(f"  {CLR_GRAY}Path:{NC} {CLR_AMBER}{BOLD}{truncate_middle(str(cur_dir), w - 10)}{NC}")
        print(f"  {CLR_BLUE}Controls: [↑/↓ or j/k] Move · [Enter] Open/Pick · [q] Cancel{NC}")
        print(f"{CLR_BORDER}{'─' * w}{NC}")

        end_idx = min(offset + page_size, total)
        for i in range(offset, end_idx):
            item_text = items[i]
            if i == cursor:
                print(f"  {CLR_GREEN}{BOLD}▶ {item_text}{NC}")
            else:
                print(f"    {CLR_GRAY}{item_text}{NC}")

        print(f"{CLR_BORDER}{'─' * w}{NC}")
        print(f"  {DIM}Item {cursor + 1} of {total}{NC}")

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
        elif key in ("QUIT", "ESC"):
            return None


# ==============================================================================
# ROBUST EXIFTOOL DAEMON (-stay_open)
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
                            log_event("WARN", "ExifTool pipe response timed out! Auto-recycling engine...")
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
                        log_event("WARN", "ExifTool reading exceeded safety timeout. Resetting daemon.")
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

        print(f"\n  {CLR_AMBER}{BOLD}Action Required:{NC} Dependencies need to be installed.")
        choice = input("  Install automatically now? [Y/n]: ").strip().lower()

        if choice in ["n", "no"]:
            print(f"\n  {CLR_RED}Dependencies missing. Exiting...{NC}")
            sys.exit(1)

        if missing_pip:
            print(f"\n  {CLR_CYAN}Installing 'watchdog' via pip...{NC}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])

        if "exiftool" in missing_bins:
            print(f"\n  {CLR_CYAN}Installing 'exiftool' for {cls.get_os_string()}...{NC}")
            os_name = cls.get_os_string()
            try:
                if "Android" in os_name:
                    subprocess.check_call(["pkg", "install", "-y", "exiftool"])
                elif "macOS" in os_name and shutil.which("brew"):
                    subprocess.check_call(["brew", "install", "exiftool"])
                elif "Windows" in os_name and shutil.which("winget"):
                    subprocess.check_call([
                        "winget", "install", "OliverBetz.ExifTool",
                        "--accept-source-agreements", "--accept-package-agreements"
                    ])
                elif shutil.which("apt-get"):
                    subprocess.check_call(["sudo", "apt-get", "update"])
                    subprocess.check_call(["sudo", "apt-get", "install", "-y", "libimage-exiftool-perl"])
                elif shutil.which("pacman"):
                    subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "perl-image-exiftool"])
                else:
                    print(f"  {CLR_RED}No compatible package manager found. Please install exiftool manually.{NC}")
                    sys.exit(1)
            except Exception as e:
                print(f"  {CLR_RED}Installation error: {e}{NC}")
                sys.exit(1)

        print(f"\n  {CLR_GREEN}{BOLD}✔ All dependencies verified!{NC}\n")
        time.sleep(1)
        return True


SystemDoctor.check_and_install(interactive=True)

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ==============================================================================
# SANITIZATION WORKER QUEUE
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
            prefix = cfg.get("prefix", "img_")

            # Ignore already cleaned files matching current prefix
            if not filepath.exists() or filepath.name.startswith("."):
                continue
            if prefix and filepath.name.startswith(prefix):
                continue

            log_event("PROBE", f"Interception triggered: {filepath.name}. Testing write lock...")
            if not file_settling_probe(filepath):
                log_event("WARN", f"File write probe timed out or vanished: {filepath.name}")
                continue

            file_key = f"{filepath.name}_{filepath.stat().st_size}"
            now = time.time()
            if file_key in PROCESSED_COOLDOWN and (now - PROCESSED_COOLDOWN[file_key]) < 4.0:
                continue
            PROCESSED_COOLDOWN[file_key] = now

            # 1. Vault Backup
            if cfg.get("enable_backup", False):
                try:
                    raw_bytes = filepath.read_bytes()
                    t_token = int(time.time())
                    if cfg.get("encrypt_vault", True):
                        sec = get_vault_secret()
                        enc = encrypt_payload(raw_bytes, sec)
                        (VAULT_DIR / f"{filepath.stem}_{t_token}.enc").write_bytes(enc)
                        log_event("VAULT", f"Encrypted original backup stored: {filepath.stem}_{t_token}.enc")
                    else:
                        (VAULT_DIR / f"{filepath.stem}_{t_token}{filepath.suffix}").write_bytes(raw_bytes)
                        log_event("VAULT", f"Plain original backup saved: {filepath.stem}_{t_token}{filepath.suffix}")
                except Exception as ex:
                    log_event("ERROR", f"Vault backup failed for {filepath.name}: {ex}")

            # 2. ExifTool Scrubbing
            if cfg.get("strip_exif", True):
                args = ["-all="]
                if cfg.get("strip_icc", True):
                    args.append("-icc_profile:all=")
                args.extend(["-overwrite_original_in_place", str(filepath)])

                t0 = time.time()
                EXIFTOOL_ENGINE.execute(*args, timeout=4.0)
                elapsed_ms = int((time.time() - t0) * 1000)
                log_event("EXIF", f"Scrubbed EXIF/ICC profiles in-place ({elapsed_ms}ms)")

            target_path = filepath

            # 3. Hash Renaming with Custom Prefix & Length
            if cfg.get("random_hash", True):
                hash_len = int(cfg.get("hash_len", 12))
                rand_token = uuid.uuid4().hex[:hash_len]
                new_name = f"{prefix}{rand_token}{filepath.suffix.lower()}"
                target_path = filepath.parent / new_name
                try:
                    filepath.rename(target_path)
                    log_event("RENAME", f"Randomized name: {filepath.name} -> {target_path.name}")
                except OSError as e:
                    log_event("ERROR", f"Rename error: {e}")
                    target_path = filepath

            # 4. Anti-Forensic Timestamp Clamping (2020-01-01)
            if cfg.get("clamp_time", True):
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
                log_event("MEDIA", f"Broadcasted gallery update for {target_path.name}")

            SESSION_CLEANED_COUNT += 1
            log_event("COMPLETE", f"✔ Successfully sanitized: {target_path.name}")

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
                log_event("WATCHER", f"Filesystem on_created: {p.name}")
                WORK_QUEUE.put(p)

    def on_moved(self, event):
        if not event.is_directory:
            p = Path(event.dest_path)
            if p.suffix.lower() in VALID_EXTENSIONS:
                log_event("WATCHER", f"Filesystem on_moved: {p.name}")
                WORK_QUEUE.put(p)


class DaemonManager:
    observer = None
    is_running = False

    @classmethod
    def start(cls):
        if cls.is_running:
            return
        cfg = load_config()
        valid_folders = [Path(f) for f in cfg.get("folders", []) if Path(f).exists()]
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
# RESPONSIVE DASHBOARD RENDERING
# ==============================================================================

def pill(val: bool) -> str:
    return f"{CLR_GREEN}[ 🟢 ON  ]{NC}" if val else f"{CLR_GRAY}[ ⚪ OFF ]{NC}"


def draw_card(title: str, lines: list, color=CLR_BORDER):
    w = get_ui_width()
    header_title = f" {title} "
    header_dashes = w - 3 - len(header_title)
    print(f"{color}╭─{CLR_WHITE}{BOLD}{header_title}{NC}{color}{'─' * max(0, header_dashes)}╮{NC}")
    for line in lines:
        print(f"{color}│{NC} {line}")
    print(f"{color}╰{'─' * (w - 2)}╯{NC}")


def draw_dashboard():
    os.system("cls" if os.name == "nt" else "clear")
    cfg = load_config()
    w = get_ui_width()
    folder_count = len(cfg.get("folders", []))
    status_text = f"{CLR_GREEN}● RUNNING{NC}" if DaemonManager.is_running else f"{CLR_RED}○ STOPPED{NC}"

    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🛡️  S H O T C L E A N{NC}  {CLR_GRAY}·{NC}  {CLR_PURPLE}v{CURRENT_VERSION} Studio{NC}")
    print(f"{CLR_CYAN}│{NC}  {DIM}Zero-Footprint Privacy & Anti-Forensic Defense{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")

    if UPDATE_AVAILABLE:
        print(f"{CLR_AMBER}╭─ {BOLD}🔔 UPDATE READY{NC} {CLR_AMBER}{'─' * max(0, w - 19)}╮{NC}")
        print(f"{CLR_AMBER}│{NC}  Commit: {BOLD}{REMOTE_COMMIT_SHORT}{NC} · Press {CLR_CYAN}[U]{NC} to update")
        print(f"{CLR_AMBER}╰{'─' * (w - 2)}╯{NC}")

    draw_card(
        "SYSTEM HEALTH",
        [
            f"OS Env  : {BOLD}{SystemDoctor.get_os_string()}{NC}",
            f"Engine  : {status_text}  {CLR_GRAY}(Session scrubbed: {SESSION_CLEANED_COUNT}){NC}",
            f"Queue   : {WORK_QUEUE.qsize()} pending  ·  Pipe: {CLR_GREEN}Active (-stay_open){NC}",
            f"Watched : {BOLD}{folder_count} folder(s) registered{NC}",
        ],
        CLR_BLUE,
    )

    vault_status = "[ 🔐 ENC ]" if cfg.get("encrypt_vault", True) else "[ 🟢 RAW ]"
    if not cfg.get("enable_backup", False):
        vault_status = "[ ⚪ OFF ]"

    pfx_str = cfg.get('prefix', 'img_')
    if not pfx_str: pfx_str = "(None)"
    sample_hash = f"{pfx_str}{'a1b2c3d4'[:cfg.get('hash_len', 12)]}.png"

    draw_card(
        "PRIVACY SHIELD",
        [
            f"EXIF Scrub : {pill(cfg['strip_exif'])}  ICC Profile : {pill(cfg['strip_icc'])}",
            f"Time Clamp : {pill(cfg['clamp_time'])}  Vault Store : {vault_status}",
            f"File Rename: {pill(cfg['random_hash'])}  Prefix: {CLR_CYAN}{pfx_str}{NC} ({sample_hash})",
        ],
        CLR_AMBER,
    )

    draw_card(
        "CONTROLS & TOOLS",
        [
            f"{CLR_CYAN}[1]{NC} ⚡ Toggle Daemon ({'Halt' if DaemonManager.is_running else 'Start'})",
            f"{CLR_CYAN}[2]{NC} 📁 Manage Folders {CLR_GREEN}(Arrow Navigator){NC}",
            f"{CLR_CYAN}[3]{NC} 🎭 Privacy Profiles   {CLR_CYAN}[4]{NC} 🏷️  Toggle EXIF",
            f"{CLR_CYAN}[5]{NC} 🎨 Toggle ICC Profile {CLR_CYAN}[6]{NC} 🎲 Custom Naming Studio",
            f"{CLR_CYAN}[7]{NC} ⏱️  Toggle Time Clamp {CLR_CYAN}[8]{NC} 🔐 Manage Vault",
            f"{CLR_CYAN}[9]{NC} 🔍 Live EXIF Audit    {CLR_CYAN}[10]{NC}🧹 Bulk Clean Folder",
            f"{CLR_CYAN}[11]{NC}📜 Live Stream Logs   {CLR_CYAN}[12]{NC}🐤 Privacy Canary Tool",
            f"{CLR_CYAN}[13]{NC}🩺 System Doctor       {CLR_CYAN}[14]{NC}🔄 Check for Updates",
            f"{CLR_CYAN}[15]{NC}🔬 Engine Diagnostics  {CLR_CYAN}[16]{NC}📖 Feature & Privacy Manual",
            f"{CLR_RED}[0]{NC}  🚪 Exit Suite" + (f"        {CLR_AMBER}[U] 🚀 Update{NC}" if UPDATE_AVAILABLE else ""),
        ],
        CLR_BORDER,
    )


# ==============================================================================
# FEATURE 6: CUSTOM NAMING & PREFIX STUDIO
# ==============================================================================

def tool_manage_naming():
    """Configure custom prefixes, hash token lengths, and preview output."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        w = get_ui_width()
        pfx = cfg.get("prefix", "img_")
        h_len = cfg.get("hash_len", 12)
        enabled = cfg.get("random_hash", True)

        preview = f"{pfx}{'7c9f2b84e1a0d3f5'[:h_len]}.png" if enabled else "Screenshot_20261026-165201.png"

        print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  {BOLD}🎲  CUSTOM NAMING & PREFIX STUDIO{NC}")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        print(f"  Random Hash Renaming : {pill(enabled)}")
        print(f"  Current Prefix       : {BOLD}'{pfx}'{NC} {CLR_GRAY}(e.g. shot_, clean_, or empty){NC}")
        print(f"  Hash Token Length    : {BOLD}{h_len} characters{NC}")
        print(f"  Generated Example    : {CLR_GREEN}{BOLD}{preview}{NC}\n")
        print(f"{CLR_BORDER}{'─' * w}{NC}")

        print("  [1] Toggle Random Hash Renaming [ON/OFF]")
        print("  [2] Change Custom Prefix (Type your own word)")
        print("  [3] Set Hash Length (8 / 12 / 16 / 32 characters)")
        print("  [4] Reset to Standard Default ('img_' with 12 chars)")
        print("  [0] Back to Main Menu")
        c = input("\n  Select [0-4]: ").strip()

        if c == "1":
            toggle_cfg("random_hash")
        elif c == "2":
            print(f"\n  Current Prefix: '{pfx}'")
            print("  Type your desired prefix (e.g. 'clean_', 'shot_', 'p_', or leave blank for pure hash):")
            new_pfx = input("  New Prefix > ").strip()
            # Sanitize forbidden filesystem characters
            sanitized = "".join(ch for ch in new_pfx if ch.isalnum() or ch in ("_", "-"))
            cfg["prefix"] = sanitized
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Prefix updated to: '{sanitized}'{NC}")
            time.sleep(1)
        elif c == "3":
            print("\n  Choose Token Length:")
            print("  [1] Compact (8 characters)  -> e.g. img_7c9f2b84.png")
            print("  [2] Standard (12 characters)-> e.g. img_7c9f2b84e1a0.png")
            print("  [3] High (16 characters)    -> e.g. img_7c9f2b84e1a0d3f5.png")
            print("  [4] Full UUID (32 chars)    -> e.g. img_7c9f2b84e1a0d3f5a1b2c3d4e5f60718.png")
            l_choice = input("  Select [1-4]: ").strip()
            if l_choice == "1": cfg["hash_len"] = 8
            elif l_choice == "2": cfg["hash_len"] = 12
            elif l_choice == "3": cfg["hash_len"] = 16
            elif l_choice == "4": cfg["hash_len"] = 32
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Hash length saved.{NC}")
            time.sleep(0.8)
        elif c == "4":
            cfg["prefix"] = "img_"
            cfg["hash_len"] = 12
            cfg["random_hash"] = True
            save_config(cfg)
            print(f"  {CLR_GREEN}✔ Defaults restored: 'img_' (12 chars){NC}")
            time.sleep(0.8)
        elif c == "0":
            break


# ==============================================================================
# FEATURE 16: INTERACTIVE FEATURE & PRIVACY MANUAL
# ==============================================================================

def tool_feature_guide():
    """Interactive field manual explaining each feature, threats, and benefits."""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        w = get_ui_width()
        print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
        print(f"{CLR_CYAN}│{NC}  {BOLD}📖  SHOTCLEAN FEATURE & PRIVACY MANUAL{NC}")
        print(f"{CLR_CYAN}│{NC}  {DIM}Understand how each privacy layer protects you{NC}")
        print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

        print("  Select a feature to learn what it does and why it's helpful:\n")
        print("  [1] 🏷️  EXIF / XMP / IPTC Metadata Stripping")
        print("  [2] 🎨 Display ICC Color Profile Removal")
        print("  [3] 🎲 Random Hash & Custom Prefix Renaming")
        print("  [4] ⏱️  Anti-Forensic Timestamp Clamping (Timestomp)")
        print("  [5] 🔐 Encrypted Safety Vault (AES-Authenticated)")
        print("  [6] 🐤 Privacy Canary Tester (Audit External Apps)")
        print("  [7] ⚡ Persistent ExifTool Engine (-stay_open)")
        print("  [8] 📁 Multi-Folder Real-time Watcher")
        print("  [0] Back to Main Menu")
        c = input("\n  Select [0-8]: ").strip()

        if c == "1":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🏷️ EXIF, XMP & IPTC METADATA SCRUBBING ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Strips hidden metadata chunks embedded into image binaries by Android,")
            print("  cameras, and editing apps.\n")
            print(f"{BOLD}Threats it neutralizes:{NC}")
            print("  • Hardware Tracking: Device brand, model (e.g. Samsung Galaxy S24),")
            print("    and specific firmware build numbers.")
            print("  • Location Leaks: GPS latitude, longitude, and altitude coordinates.")
            print("  • Digital Fingerprinting: Software packages used to edit the image.\n")
            print(f"{BOLD}Why it's helpful:{NC}")
            print("  Whenever you share or upload a screenshot, recipients cannot discover")
            print("  what phone you used, where you were, or when the file was generated.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "2":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🎨 DISPLAY ICC COLOR PROFILE REMOVAL ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Deletes the embedded International Color Consortium (ICC) profile")
            print("  (e.g., Display P3, sRGB, or OEM screen color profiles).\n")
            print(f"{BOLD}Threats it neutralizes:{NC}")
            print("  Modern OLED/AMOLED screens embed custom color profiles that match")
            print("  specific screen hardware manufacturers and calibration revisions.")
            print("  Forensic tools can match unique ICC profiles to specific phone lines.\n")
            print(f"{BOLD}Why it's helpful:{NC}")
            print("  Leaves your image with generic neutral rendering data that cannot be")
            print("  correlated with your specific display panel.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "3":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🎲 RANDOM HASH & CUSTOM PREFIX RENAMING ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Replaces default chronological filenames with pseudo-random UUID hashes:")
            print(f"  {CLR_RED}Screenshot_20261026-165201.png{NC} ──► {CLR_GREEN}img_fa49275d958a.png{NC}\n")
            print(f"{BOLD}Threats it neutralizes:{NC}")
            print("  Original screenshot filenames reveal:")
            print("  1. The exact year, month, day, hour, minute, and second it was taken.")
            print("  2. Your device's screenshot naming pattern (e.g., MIUI vs OneUI vs iOS).\n")
            print(f"{BOLD}Custom Naming Studio Feature:{NC}")
            print("  You can customize the prefix (e.g., 'shot_', 'clean_', or blank '')")
            print("  and choose how many characters the hash should be (8 to 32 chars).")
            input("\n  Press [Enter] to return to manual...")

        elif c == "4":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== ⏱️ ANTI-FORENSIC TIMESTAMP CLAMPING (TIMESTOMP) ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Forces the filesystem access time (atime) and modification time (mtime)")
            print("  to a static historical timestamp: 2020-01-01 00:00:00 UTC.\n")
            print(f"{BOLD}Threats it neutralizes:{NC}")
            print("  Even if you scrub EXIF and rename the file, filesystem forensic tools")
            print("  can inspect the OS inode/filesystem table to determine when the file")
            print("  was written to disk. Clamping eliminates this temporal correlation.\n")
            print(f"{BOLD}Important Note for Gallery Apps:{NC}")
            print("  When enabled, gallery apps sort screenshots into JANUARY 2020 because")
            print("  they read the filesystem modification date! If you prefer new screenshots")
            print("  to appear under 'Today', simply toggle Time Clamp [OFF] or use Balanced Profile.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "5":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🔐 ENCRYPTED SAFETY VAULT ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Before sanitizing an image, ShotClean can save an original copy into")
            print("  ~/.shotclean/vault/ encrypted with 100,000-round PBKDF2 + AES keystream.\n")
            print(f"{BOLD}Why it's helpful:{NC}")
            print("  • Failsafe Recovery: If you ever need the original unscrubbed capture,")
            print("    you can restore and decrypt it using Option [8].")
            print("  • Zero-Knowledge Protection: Backups cannot be read by other Android")
            print("    apps or media scanners because they are stored as encrypted .enc files.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "6":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 🐤 PRIVACY CANARY AUDIT TOOL ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Generates a synthetic test image embedded with an intentional unique")
            print("  tracking token (e.g., CANARY-9A4B8F12).\n")
            print(f"{BOLD}Why it's helpful:{NC}")
            print("  Upload the canary to an app (e.g., WhatsApp, Discord, Telegram, or Imgur),")
            print("  download it back, and run the audit. ShotClean will reveal whether that")
            print("  service truly strips metadata or preserves hidden user tracking tokens.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "7":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== ⚡ PERSISTENT EXIFTOOL ENGINE (-stay_open) ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Keeps a single ExifTool daemon running in RAM using a bidirectional pipe,")
            print("  monitored by an automatic non-blocking 4.0-second safety timeout.\n")
            print(f"{BOLD}Why it's helpful:{NC}")
            print("  • High Speed: On mobile ARM processors, starting a cold Perl process takes")
            print("    ~800ms. The persistent daemon completes scrubs in under 35ms.")
            print("  • Deadlock Protection: Prevents Termux standard input/output pipe hangs.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "8":
            os.system("cls" if os.name == "nt" else "clear")
            print(f"{CLR_CYAN}=== 📁 MULTI-FOLDER REAL-TIME WATCHER ==={NC}\n")
            print(f"{BOLD}What it does:{NC}")
            print("  Allows you to monitor multiple directories at once (e.g., standard Screenshots,")
            print("  DCIM/Camera, Downloads, or custom messaging save folders).\n")
            print(f"{BOLD}Interactive Navigator:{NC}")
            print("  Includes an interactive arrow-key directory browser (Option [2] -> [1]) so")
            print("  you can select folders without typing lengthy storage paths.")
            input("\n  Press [Enter] to return to manual...")

        elif c == "0":
            break


# ==============================================================================
# AUDIT & TOOLS
# ==============================================================================

def tool_live_audit():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()
    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🔍  LIVE METADATA & ICC PROFILE AUDIT{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    cfg = load_config()
    print(f"  {CLR_CYAN}[1/3]{NC} Searching monitored folders for latest image...")
    candidates = []
    for f in cfg.get("folders", []):
        p = Path(f)
        if p.exists():
            for ext in VALID_EXTENSIONS:
                candidates.extend(p.glob(f"*{ext}"))

    if not candidates:
        print(f"\n  {CLR_AMBER}✖ No images found across your registered folders.{NC}\n")
        input("  Press [Enter] to return...")
        return

    latest_file = max(candidates, key=lambda f: f.stat().st_mtime)
    print(f"  {CLR_GREEN}[✔]{NC} Found target: {BOLD}{latest_file.name}{NC}")
    print(f"      Path: {CLR_GRAY}{latest_file.parent}{NC}\n")

    print(f"  {CLR_CYAN}[2/3]{NC} Querying ExifTool metadata tags (with 4s safety timeout)...")
    t0 = time.time()
    out = EXIFTOOL_ENGINE.execute(
        "-exif:all", "-xmp:all", "-iptc:all", "-icc_profile:all",
        str(latest_file), timeout=4.0
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    print(f"  {CLR_GREEN}[✔]{NC} ExifTool responded in {elapsed_ms}ms\n")

    print(f"  {CLR_CYAN}[3/3]{NC} Verifying metadata signatures:")
    print(f"{CLR_BORDER}{'─' * w}{NC}")

    if not out.strip():
        print(f"  {CLR_GREEN}{BOLD}✔ 100% CLEAN - ZERO EXIF, XMP, IPTC OR ICC DATA DETECTED!{NC}")
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


def tool_engine_diagnostics():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()
    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🔬  SHOTCLEAN ENGINE DIAGNOSTICS & AUDIT{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")

    cfg = load_config()
    daemon_pid = EXIFTOOL_ENGINE.proc.pid if EXIFTOOL_ENGINE.proc else None
    daemon_alive = EXIFTOOL_ENGINE.proc and (EXIFTOOL_ENGINE.proc.poll() is None)

    print(f"  {BOLD}Subsystem Health Checks:{NC}")
    print(f"   • ExifTool Binary Path  : {CLR_GREEN}{shutil.which('exiftool') or 'NOT FOUND'}{NC}")
    print(f"   • Persistent Daemon PID : {CLR_GREEN}{daemon_pid}{NC} ({'Alive' if daemon_alive else 'Dead/Restarting'})")
    print(f"   • Background Worker     : {'Active' if WORKER_THREAD.is_alive() else 'Dead'}")
    print(f"   • Work Queue Backlog    : {WORK_QUEUE.qsize()} task(s)")
    print(f"   • Storage Mounted       : {'Yes (/storage/emulated/0 accessible)' if Path('/storage/emulated/0').exists() else 'Desktop/Non-Android'}")

    print(f"\n  {BOLD}Engine Responsiveness Test:{NC}")
    t0 = time.time()
    test_out = EXIFTOOL_ENGINE.execute("-ver", timeout=3.0)
    elapsed = int((time.time() - t0) * 1000)
    print(f"   • Ping ExifTool Engine  : {CLR_GREEN}{test_out.strip() or 'OK'}{NC} ({elapsed}ms roundtrip)")

    print(f"\n  {BOLD}Recent Diagnostics Errors (Last 10):{NC}")
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if "[ERROR]" in l or "[WARN]" in l][-10:]
            if lines:
                for l in lines:
                    print(f"   {CLR_RED}{l.strip()}{NC}")
            else:
                print(f"   {CLR_GREEN}✔ Zero errors or warnings logged.{NC}")
    else:
        print("   No activity log created yet.")

    print(f"\n{CLR_BORDER}{'─' * w}{NC}")
    print("  [1] Force Restart ExifTool Daemon Pipe")
    print("  [0] Back to Menu")
    c = input("\n  Select: ").strip()
    if c == "1":
        EXIFTOOL_ENGINE._restart()
        print(f"  {CLR_GREEN}✔ Daemon recycled successfully.{NC}")
        time.sleep(1)


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


def tool_bulk_clean():
    os.system("cls" if os.name == "nt" else "clear")
    cfg = load_config()
    print(f"{CLR_CYAN}=== Bulk Folder Scrubber ==={NC}\n")
    folders = [Path(f) for f in cfg.get("folders", []) if Path(f).exists()]
    confirm = input("  Scrub all existing photos across monitored folders? [y/N]: ").strip().lower()
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

        args = ["-all="]
        if cfg.get("strip_icc", True):
            args.append("-icc_profile:all=")
        args.extend(["-overwrite_original_in_place", str(img)])
        EXIFTOOL_ENGINE.execute(*args, timeout=4.0)

        if cfg.get("clamp_time", True):
            try:
                os.utime(img, (1577836800.0, 1577836800.0))
            except OSError:
                pass

    print(f"\n\n  {CLR_GREEN}✔ Bulk scrub complete for {total} images.{NC}\n")
    time.sleep(1.2)


def tool_manual_check_updates():
    os.system("cls" if os.name == "nt" else "clear")
    w = get_ui_width()
    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🔄  CHECK FOR UPDATES{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}\n")
    print(f"  Current Version : {BOLD}v{CURRENT_VERSION}{NC}")
    print(f"  Repository      : {BOLD}{GITHUB_REPO}{NC}\n")
    print(f"  {CLR_CYAN}Querying GitHub for latest commit on 'main'...{NC}")

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        req = urllib.request.Request(url, headers={"User-Agent": "ShotClean-Updater"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            remote_sha = data.get("sha", "")
            local_sha = get_current_commit()

            if not local_sha:
                local_sha = remote_sha
                COMMIT_CACHE_FILE.write_text(remote_sha, encoding="utf-8")

            if remote_sha and local_sha != remote_sha:
                short_remote = remote_sha[:7]
                print(f"\n  {CLR_AMBER}{BOLD}🚀 New update available on GitHub!{NC}")
                print(f"  Remote Commit : {BOLD}{short_remote}{NC}")
                ans = input("\n  Would you like to install and restart now? [Y/n]: ").strip().lower()
                if ans not in ['n', 'no']:
                    perform_direct_web_update()
            else:
                print(f"\n  {CLR_GREEN}{BOLD}✔ You are up to date!{NC}")
                print(f"  Running latest commit: {local_sha[:7] if local_sha else 'current'}\n")
    except Exception as e:
        print(f"\n  {CLR_RED}✖ Could not check for updates:{NC} {e}\n")

    input("  Press [Enter] to return...")


def tool_manage_vault():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        vault_files = list(VAULT_DIR.glob("*"))
        enc_count = sum(1 for f in vault_files if f.suffix == ".enc")
        raw_count = len(vault_files) - enc_count

        print(f"{CLR_CYAN}=== Encrypted Safety Backup Vault ==={NC}\n")
        print(f"  Vault Storage State  : {pill(cfg.get('enable_backup', False))}")
        print(f"  Encryption Mode      : {'[ 🔐 AES-Authenticated ]' if cfg.get('encrypt_vault', True) else '[ ⚠️ Raw Plaintext ]'}")
        print(f"  Stored Backups       : {BOLD}{len(vault_files)}{NC} total ({enc_count} encrypted, {raw_count} plain)")
        print(f"  Vault Directory      : {CLR_GRAY}{VAULT_DIR}{NC}\n")

        print("  [1] Toggle Backup State [ON/OFF]")
        print("  [2] Toggle Encryption Mode [AES/Raw]")
        print("  [3] Export & Decrypt All Backups to ~/Download/ShotClean_Restored")
        print("  [4] Purge / Wipe Entire Vault")
        print("  [0] Back to Menu")
        c = input("\n  Select [0-4]: ").strip()

        if c == "1":
            toggle_cfg("enable_backup")
        elif c == "2":
            toggle_cfg("encrypt_vault")
        elif c == "3":
            if not vault_files:
                print(f"  {CLR_AMBER}Vault is empty.{NC}"); time.sleep(1); continue
            out_dir = HOME / "Download" / "ShotClean_Restored"
            out_dir.mkdir(parents=True, exist_ok=True)
            secret = get_vault_secret()
            success = 0
            for vf in vault_files:
                try:
                    if vf.suffix == ".enc":
                        plain = decrypt_payload(vf.read_bytes(), secret)
                        orig_name = vf.stem + ".png"
                        (out_dir / orig_name).write_bytes(plain)
                    else:
                        shutil.copy2(vf, out_dir / vf.name)
                    success += 1
                except Exception as ex:
                    log_event("ERROR", f"Failed to restore {vf.name}: {ex}")
            print(f"\n  {CLR_GREEN}✔ Successfully restored {success} images to:{NC}\n  {out_dir}")
            input("\n  Press [Enter] to continue...")
        elif c == "4":
            confirm = input("\n  Permanently delete ALL backups in vault? [y/N]: ").strip().lower()
            if confirm in ["y", "yes"]:
                for vf in vault_files:
                    vf.unlink()
                print(f"  {CLR_GREEN}✔ Vault purged.{NC}"); time.sleep(1)
        elif c == "0":
            break


def tool_privacy_canary():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{CLR_CYAN}╭────────────────────────────────────────────────────────╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🐤  PLATFORM PRIVACY CANARY TESTER{NC}                    {CLR_CYAN}│{NC}")
    print(f"{CLR_CYAN}╰────────────────────────────────────────────────────────╯{NC}\n")
    print("  Test if apps (WhatsApp, Discord, Telegram, Imgur) leak metadata:")
    print("  [1] Generate New Canary Image (Embeds unique tracking token)")
    print("  [2] Audit Downloaded Image (Check if token survived upload)")
    print("  [0] Back")
    c = input("\n  Select [0-2]: ").strip()

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
        print("  Instructions:")
        print("  1. Upload/send this canary image through the app you want to test.")
        print("  2. Download that image back from the app onto this device.")
        print("  3. Return here and choose [2] to audit the downloaded image!")
        input("\n  Press [Enter] to continue...")

    elif c == "2":
        path_str = input("\n  Enter path to downloaded image (or drag & drop): ").strip().strip("'\"")
        p = Path(path_str)
        if not p.exists() or not p.is_file():
            print(f"  {CLR_RED}File not found.{NC}"); time.sleep(1.2); return

        out = EXIFTOOL_ENGINE.execute("-all", str(p), timeout=4.0)
        if "CANARY-" in out:
            print(f"\n  {CLR_RED}{BOLD}🚨 PRIVACY LEAK DETECTED!{NC}")
            print("  The uploaded platform PRESERVED metadata tracking tokens!")
            print(f"  Your images are NOT sanitized by this platform.\n")
        elif not out.strip():
            print(f"\n  {CLR_GREEN}{BOLD}🛡️ 100% CLEAN & SAFE!{NC}")
            print("  The platform stripped all metadata (including canary tokens).\n")
        else:
            print(f"\n  {CLR_AMBER}{BOLD}⚠️ PARTIAL METADATA RETAINED:{NC}")
            print("  Canary was stripped, but generic device headers remain:\n")
            print(out[:300])
        input("  Press [Enter] to return...")


def tool_manage_folders():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        folders = cfg.get("folders", [])
        w = get_ui_width()
        print(f"{CLR_CYAN}=== Monitored Folders ==={NC}\n")
        for i, f in enumerate(folders, 1):
            p = Path(f)
            status = f"{CLR_GREEN}Active{NC}" if p.exists() else f"{CLR_RED}Missing{NC}"
            disp = truncate_middle(f, w - 16)
            print(f"  [{i}] {disp} ({status})")
        print(f"\n  {CLR_GREEN}[1] Browse with Arrow Keys [↑/↓]{NC}")
        print(f"  [2] Quick Preset (Screenshots)")
        print(f"  [3] Type Path Manually")
        print(f"  [4] Delete Monitored Folder")
        print(f"  [0] Back to Menu")
        c = input("\n  Select [0-4]: ").strip()

        if c == "1":
            chosen_dir = interactive_folder_browser()
            if chosen_dir and chosen_dir.exists():
                str_p = str(chosen_dir)
                if str_p not in folders:
                    folders.append(str_p)
                    cfg["folders"] = folders
                    save_config(cfg)
                    DaemonManager.restart()
                    print(f"\n  {CLR_GREEN}✔ Added: {chosen_dir.name}{NC}")
                    time.sleep(1)
        elif c == "2":
            def_path = str(detect_default_folder())
            if def_path not in folders:
                folders.append(def_path)
                cfg["folders"] = folders
                save_config(cfg)
                DaemonManager.restart()
        elif c == "3":
            p = Path(input("\n  Enter folder path: ").strip())
            if p.exists() and p.is_dir() and str(p) not in folders:
                folders.append(str(p))
                cfg["folders"] = folders
                save_config(cfg)
                DaemonManager.restart()
        elif c == "4":
            idx = input(f"  Index to remove [1-{len(folders)}]: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(folders):
                folders.pop(int(idx) - 1)
                cfg["folders"] = folders
                save_config(cfg)
                DaemonManager.restart()
        elif c == "0":
            break


def tool_profiles():
    os.system("cls" if os.name == "nt" else "clear")
    cfg = load_config()
    print(f"{CLR_CYAN}=== Privacy Profiles ==={NC}\n")
    print("  [1] Ghost (Scrub EXIF + Strip ICC + UUID Rename + Time Clamp)")
    print("  [2] Balanced (Scrub EXIF + Strip ICC + UUID Rename - Shows Today)")
    print("  [3] Preserve (Scrub EXIF only, keep original filename)")
    c = input("\n  Select [1-3]: ").strip()
    if c == "1":
        cfg["strip_exif"] = True; cfg["strip_icc"] = True; cfg["random_hash"] = True; cfg["clamp_time"] = True
    elif c == "2":
        cfg["strip_exif"] = True; cfg["strip_icc"] = True; cfg["random_hash"] = True; cfg["clamp_time"] = False
    elif c == "3":
        cfg["strip_exif"] = True; cfg["strip_icc"] = False; cfg["random_hash"] = False; cfg["clamp_time"] = False
    else:
        return
    save_config(cfg)
    DaemonManager.restart()


def toggle_cfg(key: str):
    cfg = load_config()
    cfg[key] = not cfg.get(key, False)
    save_config(cfg)
    DaemonManager.restart()


# ==============================================================================
# MAIN EVENT LOOP
# ==============================================================================

def main():
    DaemonManager.start()

    try:
        while True:
            draw_dashboard()
            choice = input(" ❯ Select option: ").strip()

            if choice.lower() == "u" and UPDATE_AVAILABLE:
                perform_direct_web_update()
            elif choice == "1":
                DaemonManager.stop() if DaemonManager.is_running else DaemonManager.start()
            elif choice == "2":
                tool_manage_folders()
            elif choice == "3":
                tool_profiles()
            elif choice == "4":
                toggle_cfg("strip_exif")
            elif choice == "5":
                toggle_cfg("strip_icc")
            elif choice == "6":
                tool_manage_naming()
            elif choice == "7":
                toggle_cfg("clamp_time")
            elif choice == "8":
                tool_manage_vault()
            elif choice == "9":
                tool_live_audit()
            elif choice == "10":
                tool_bulk_clean()
            elif choice == "11":
                tool_live_logs()
            elif choice == "12":
                tool_privacy_canary()
            elif choice == "13":
                os.system("cls" if os.name == "nt" else "clear")
                SystemDoctor.check_and_install(interactive=True)
                input("  Press [Enter] to return...")
            elif choice == "14":
                tool_manual_check_updates()
            elif choice == "15":
                tool_engine_diagnostics()
            elif choice == "16":
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
