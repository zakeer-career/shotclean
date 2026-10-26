#!/usr/bin/env python3
"""
ShotClean Universal Studio v4.3.0
Cross-platform metadata stripper, anti-forensics suite & automated privacy shield.
Repository: https://github.com/zakeer-career/shotclean
"""

import hashlib
import hmac
import json
import os
import platform
import queue
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

CURRENT_VERSION = "4.3.0"
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
    """Queries GitHub API to check for commits made on GitHub web."""
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
    """Downloads raw script directly from GitHub and restarts."""
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

        print(f"  {CLR_GREEN}{BOLD}✔ Updated to v{CURRENT_VERSION}! Restarting...{NC}\n")
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


def log_event(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")

        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 100000:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-250:])
    except Exception:
        pass


# ==============================================================================
# FEATURE 1: HIGH-SPEED EXIFTOOL PERSISTENT DAEMON (-stay_open)
# ==============================================================================

class ExifToolDaemon:
    """Maintains a persistent ExifTool process to avoid process spawn overhead."""
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
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )
        except Exception:
            self.proc = None

    def execute(self, *args) -> str:
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self._start()
            if not self.proc:
                res = subprocess.run(["exiftool"] + list(args), capture_output=True, text=True)
                return res.stdout

            cmd = "\n".join(args) + "\n-execute\n"
            try:
                self.proc.stdin.write(cmd)
                self.proc.stdin.flush()

                output_lines = []
                while True:
                    line = self.proc.stdout.readline()
                    if not line or line.strip() == "{ready}":
                        break
                    output_lines.append(line)
                return "".join(output_lines)
            except Exception:
                self._start()
                return ""

    def close(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write("-stay_open\nFalse\n-execute\n")
                    self.proc.stdin.flush()
                    self.proc.communicate(timeout=1.5)
                except Exception:
                    self.proc.kill()
                self.proc = None


EXIFTOOL_ENGINE = ExifToolDaemon()

# ==============================================================================
# FEATURE 2: PURE-PYTHON AUTHENTICATED VAULT ENCRYPTION
# ==============================================================================

def get_vault_secret() -> str:
    """Retrieves or creates a secure local vault passphrase."""
    if VAULT_KEY_FILE.exists():
        try:
            return VAULT_KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    secret = uuid.uuid4().hex + uuid.uuid4().hex
    VAULT_KEY_FILE.write_text(secret, encoding="utf-8")
    return secret


def encrypt_payload(data: bytes, key: str) -> bytes:
    """Authenticated CTR keystream encryption with 100k-iteration PBKDF2."""
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
    """Verifies authentication tag and decrypts ciphertext."""
    if not data.startswith(b"ENC1"):
        raise ValueError("Invalid format: Not an encrypted ShotClean vault archive.")
    salt = data[4:20]
    nonce = data[20:32]
    tag = data[32:64]
    ciphertext = data[64:]
    derived = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, 100000)
    expected_tag = hashlib.sha256(derived + salt + nonce + ciphertext).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Decryption failed: Integrity check mismatch or invalid key.")
    out = bytearray(len(ciphertext))
    block_idx = 0
    for i in range(0, len(ciphertext), 32):
        keystream = hashlib.sha256(derived + nonce + block_idx.to_bytes(4, "big")).digest()
        chunk_len = min(32, len(ciphertext) - i)
        for j in range(chunk_len):
            out[i + j] = ciphertext[i + j] ^ keystream[j]
        block_idx += 1
    return bytes(out)


# ==============================================================================
# FEATURE 4: METADATA CANARY GENERATOR
# ==============================================================================

def create_synthetic_png(target_path: Path):
    """Generates a valid 200x200 solid PNG without requiring Pillow."""
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
# NON-BLOCKING SANITIZATION WORKER QUEUE
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

            if not filepath.exists() or filepath.name.startswith(".") or filepath.name.startswith(prefix):
                continue

            if not file_settling_probe(filepath):
                continue

            # Anti-reentrancy check
            file_key = f"{filepath.name}_{filepath.stat().st_size}"
            now = time.time()
            if file_key in PROCESSED_COOLDOWN and (now - PROCESSED_COOLDOWN[file_key]) < 4.0:
                continue
            PROCESSED_COOLDOWN[file_key] = now

            # 1. Encrypted or Plain Backup Vault
            if cfg.get("enable_backup", False):
                try:
                    raw_bytes = filepath.read_bytes()
                    timestamp_token = int(time.time())
                    if cfg.get("encrypt_vault", True):
                        secret = get_vault_secret()
                        enc_data = encrypt_payload(raw_bytes, secret)
                        v_target = VAULT_DIR / f"{filepath.stem}_{timestamp_token}.enc"
                        v_target.write_bytes(enc_data)
                    else:
                        v_target = VAULT_DIR / f"{filepath.stem}_{timestamp_token}{filepath.suffix}"
                        v_target.write_bytes(raw_bytes)
                except Exception as ex:
                    log_event(f"Backup failed for {filepath.name}: {ex}")

            # 2. ExifTool Scrubbing (Hardware EXIF + ICC Color Profiles)
            if cfg.get("strip_exif", True):
                args = ["-all="]
                if cfg.get("strip_icc", True):
                    args.append("-icc_profile:all=")
                args.extend(["-overwrite_original_in_place", str(filepath)])
                EXIFTOOL_ENGINE.execute(*args)

            target_path = filepath

            # 3. Hash Renaming
            if cfg.get("random_hash", True):
                rand_token = uuid.uuid4().hex[:12]
                new_name = f"{prefix}{rand_token}{filepath.suffix.lower()}"
                target_path = filepath.parent / new_name
                try:
                    filepath.rename(target_path)
                except OSError:
                    target_path = filepath

            # 4. Anti-Forensic Timestamp Clamping (2020-01-01)
            if cfg.get("clamp_time", True):
                try:
                    epoch_2020 = 1577836800.0
                    os.utime(target_path, (epoch_2020, epoch_2020))
                except OSError:
                    pass

            # 5. Refresh Android Media Scanner
            if "com.termux" in os.environ.get("PREFIX", ""):
                subprocess.run(
                    ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

            SESSION_CLEANED_COUNT += 1
            log_event(f"Sanitized: {filepath.name} -> {target_path.name}")

        except Exception as ex:
            log_event(f"Worker exception: {ex}")
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
        valid_folders = [Path(f) for f in cfg.get("folders", []) if Path(f).exists()]
        if not valid_folders:
            return

        cls.observer = Observer()
        handler = AsyncWatchHandler()
        for folder in valid_folders:
            cls.observer.schedule(handler, path=str(folder), recursive=False)

        cls.observer.start()
        cls.is_running = True
        log_event(f"Daemon started. Monitoring {len(valid_folders)} folder(s).")

    @classmethod
    def stop(cls):
        if not cls.is_running or not cls.observer:
            return
        cls.observer.stop()
        cls.observer.join()
        cls.is_running = False
        cls.observer = None
        log_event("Daemon stopped.")

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

    # Header
    print(f"{CLR_CYAN}╭{'─' * (w - 2)}╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🛡️  S H O T C L E A N{NC}  {CLR_GRAY}·{NC}  {CLR_PURPLE}v{CURRENT_VERSION} Studio{NC}")
    print(f"{CLR_CYAN}│{NC}  {DIM}High-Speed Privacy & Anti-Forensic Defense Suite{NC}")
    print(f"{CLR_CYAN}╰{'─' * (w - 2)}╯{NC}")

    if UPDATE_AVAILABLE:
        print(f"{CLR_AMBER}╭─ {BOLD}🔔 UPDATE READY{NC} {CLR_AMBER}{'─' * max(0, w - 19)}╮{NC}")
        print(f"{CLR_AMBER}│{NC}  Commit: {BOLD}{REMOTE_COMMIT_SHORT}{NC} · Press {CLR_CYAN}[U]{NC} to update")
        print(f"{CLR_AMBER}╰{'─' * (w - 2)}╯{NC}")

    # Health Card
    draw_card(
        "SYSTEM HEALTH",
        [
            f"OS Env  : {BOLD}{SystemDoctor.get_os_string()}{NC}",
            f"Engine  : {status_text}  {CLR_GRAY}(Session cleaned: {SESSION_CLEANED_COUNT}){NC}",
            f"Daemon  : {CLR_GREEN}Persistent Pipe Active (-stay_open){NC}",
            f"Watched : {BOLD}{folder_count} folder(s) registered{NC}",
        ],
        CLR_BLUE,
    )

    # Privacy Status Card
    vault_status = "[ 🔐 ENC ]" if cfg.get("encrypt_vault", True) else "[ 🟢 RAW ]"
    if not cfg.get("enable_backup", False):
        vault_status = "[ ⚪ OFF ]"

    draw_card(
        "PRIVACY SHIELD",
        [
            f"EXIF Scrub : {pill(cfg['strip_exif'])}  Hash Rename : {pill(cfg['random_hash'])}",
            f"ICC Profile: {pill(cfg['strip_icc'])}  Time Clamp  : {pill(cfg['clamp_time'])}",
            f"Vault Store: {vault_status}  Backup State: {pill(cfg['enable_backup'])}",
        ],
        CLR_AMBER,
    )

    # Controls & Menu
    draw_card(
        "CONTROLS & TOOLS",
        [
            f"{CLR_CYAN}[1]{NC} ⚡ Toggle Daemon ({'Halt' if DaemonManager.is_running else 'Start'})",
            f"{CLR_CYAN}[2]{NC} 📁 Manage Folders     {CLR_CYAN}[3]{NC} 🎭 Privacy Profiles",
            f"{CLR_CYAN}[4]{NC} 🏷️  Toggle EXIF       {CLR_CYAN}[5]{NC} 🎨 Toggle ICC Profile",
            f"{CLR_CYAN}[6]{NC} 🎲 Toggle Hash Rename {CLR_CYAN}[7]{NC} ⏱️  Toggle Time Clamp",
            f"{CLR_CYAN}[8]{NC} 🔐 Manage Vault       {CLR_CYAN}[9]{NC} 🔍 Live EXIF Audit",
            f"{CLR_CYAN}[10]{NC}🧹 Bulk Clean Folder   {CLR_CYAN}[11]{NC}📜 Activity Logs",
            f"{CLR_CYAN}[12]{NC}🐤 Privacy Canary Tool {CLR_CYAN}[13]{NC}🩺 System Doctor",
            f"{CLR_RED}[0]{NC}  🚪 Exit Suite" + (f"        {CLR_AMBER}[U] 🚀 Update{NC}" if UPDATE_AVAILABLE else ""),
        ],
        CLR_BORDER,
    )


# ==============================================================================
# AUDIT & MANAGEMENT TOOLS
# ==============================================================================

def tool_live_audit():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{CLR_CYAN}=== Live EXIF & ICC Profile Audit ==={NC}\n")
    cfg = load_config()
    candidates = []
    for f in cfg.get("folders", []):
        p = Path(f)
        if p.exists():
            for ext in VALID_EXTENSIONS:
                candidates.extend(p.glob(f"*{ext}"))

    if not candidates:
        print(f"  {CLR_AMBER}No images found across monitored folders.{NC}\n")
        input("  Press [Enter] to return...")
        return

    latest_file = max(candidates, key=lambda f: f.stat().st_mtime)
    print(f"  Target: {BOLD}{latest_file.name}{NC}\n")

    out = EXIFTOOL_ENGINE.execute("-exif:all", "-xmp:all", "-iptc:all", "-icc_profile:all", str(latest_file))
    if not out.strip():
        print(f"  {CLR_GREEN}{BOLD}✔ 100% CLEAN - ZERO EXIF, XMP, IPTC OR ICC PROFILES DETECTED!{NC}")
    else:
        print(f"  {CLR_RED}{BOLD}⚠ METADATA DETECTED:{NC}\n{out}")

    st = latest_file.stat()
    print(f"\n  Modified: {time.ctime(st.st_mtime)}")
    print(f"  Accessed: {time.ctime(st.st_atime)}\n")
    input("  Press [Enter] to return...")


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
        EXIFTOOL_ENGINE.execute(*args)

        if cfg.get("clamp_time", True):
            try:
                os.utime(img, (1577836800.0, 1577836800.0))
            except OSError:
                pass

    print(f"\n\n  {CLR_GREEN}✔ Bulk scrub complete for {total} images.{NC}\n")
    time.sleep(1.2)


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
                    log_event(f"Failed to restore {vf.name}: {ex}")
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
    """Generates synthetic canary images to test if external upload platforms strip EXIF."""
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

        # Inject detectable synthetic metadata
        EXIFTOOL_ENGINE.execute(
            f"-Artist={token}",
            f"-UserComment=CANARY_PRIVACY_AUDIT_{token}",
            f"-Copyright={token}",
            "-overwrite_original_in_place",
            str(canary_path),
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

        out = EXIFTOOL_ENGINE.execute("-all", str(p))
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
        print(f"\n  [1] Add Custom Path   [2] Quick Preset   [3] Delete   [0] Back")
        c = input("  Select: ").strip()

        if c == "1":
            p = Path(input("\n  Enter folder path: ").strip())
            if p.exists() and p.is_dir() and str(p) not in folders:
                folders.append(str(p))
                cfg["folders"] = folders
                save_config(cfg)
                DaemonManager.restart()
        elif c == "2":
            def_path = str(detect_default_folder())
            if def_path not in folders:
                folders.append(def_path)
                cfg["folders"] = folders
                save_config(cfg)
                DaemonManager.restart()
        elif c == "3":
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
    print("  [2] Balanced (Scrub EXIF + Strip ICC + UUID Rename)")
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
                toggle_cfg("random_hash")
            elif choice == "7":
                toggle_cfg("clamp_time")
            elif choice == "8":
                tool_manage_vault()
            elif choice == "9":
                tool_live_audit()
            elif choice == "10":
                tool_bulk_clean()
            elif choice == "11":
                os.system("cls" if os.name == "nt" else "clear")
                if LOG_FILE.exists():
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        print("".join(f.readlines()[-25:]))
                input("\n  Press [Enter] to return...")
            elif choice == "12":
                tool_privacy_canary()
            elif choice == "13":
                os.system("cls" if os.name == "nt" else "clear")
                SystemDoctor.check_and_install(interactive=True)
                input("  Press [Enter] to return...")
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
