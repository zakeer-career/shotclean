#!/usr/bin/env python3
"""
ShotClean Universal Studio v4.1
Cross-platform metadata stripper with live GitHub update detection and 1-click upgrade.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

# Enable ANSI formatting on Windows CMD / PowerShell
if platform.system() == "Windows":
    os.system("")

# ==============================================================================
# VERSION & GITHUB UPDATE SYSTEM
# ==============================================================================

CURRENT_VERSION = "4.0.0"

# CHANGE THIS to your GitHub username and repository:
GITHUB_REPO = "your_username/shotclean"

LATEST_VERSION = None
UPDATE_AVAILABLE = False


def check_updates_background():
    """Silently queries GitHub Releases API in the background."""
    global LATEST_VERSION, UPDATE_AVAILABLE
    if GITHUB_REPO == "your_username/shotclean":
        return  # Skip if placeholder has not been replaced yet

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"ShotClean/{CURRENT_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            remote_tag = data.get("tag_name", "").lstrip("v")
            if remote_tag and remote_tag != CURRENT_VERSION:
                LATEST_VERSION = remote_tag
                UPDATE_AVAILABLE = True
    except Exception:
        # Fails silently if user is offline or GitHub rate-limits
        pass


def perform_git_update():
    """Runs git pull and re-launches the script automatically."""
    print(f"\n  {CLR_CYAN}Pulling latest updates from GitHub...{NC}")
    try:
        res = subprocess.run(["git", "pull"], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  {CLR_GREEN}{BOLD}✔ Update successful! Restarting ShotClean...{NC}\n")
            time.sleep(1.2)
            # Replaces the current process with the newly pulled code
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            print(f"  {CLR_RED}✖ Update failed:{NC}\n{res.stderr}")
            input("  Press [Enter] to continue...")
    except Exception as e:
        print(f"  {CLR_RED}✖ Git command failed: {e}{NC}")
        input("  Press [Enter] to continue...")


# Start background update check immediately on boot
threading.Thread(target=check_updates_background, daemon=True).start()

# ==============================================================================
# STYLING & CORE CONFIGURATION
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

HOME = Path.home()
SHOTCLEAN_DIR = HOME / ".shotclean"
CONFIG_FILE = SHOTCLEAN_DIR / "config.json"
LOG_FILE = SHOTCLEAN_DIR / "activity.log"
VAULT_DIR = SHOTCLEAN_DIR / "vault"

SHOTCLEAN_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)


def detect_default_folder() -> Path:
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        return Path("/storage/emulated/0/Pictures/Screenshots")
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
    "random_hash": True,
    "prefix": "img_",
    "clamp_time": True,
    "enable_backup": False,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)


CONFIG = load_config()


def log_event(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")


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
        print(f"{CLR_CYAN}│{NC}  {BOLD}🩺  SHOTCLEAN · Dependency Diagnostic Check{NC}        {CLR_CYAN}│{NC}")
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

        print(f"\n  {CLR_AMBER}{BOLD}Action Needed:{NC} Dependencies required.")
        choice = input("  Install them automatically now? [Y/n]: ").strip().lower()

        if choice in ["n", "no"]:
            print(f"\n  {CLR_RED}Dependencies missing. Exiting...{NC}")
            sys.exit(1)

        if missing_pip:
            print(f"\n  {CLR_CYAN}Installing 'watchdog' via pip...{NC}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])

        if "exiftool" in missing_bins:
            print(f"\n  {CLR_CYAN}Installing 'exiftool' via system package manager...{NC}")
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
                    print(f"  {CLR_RED}No supported package manager found. Please install exiftool manually.{NC}")
                    sys.exit(1)
            except Exception as e:
                print(f"  {CLR_RED}Auto-install error: {e}{NC}")
                sys.exit(1)

        print(f"\n  {CLR_GREEN}{BOLD}✔ All tools successfully installed!{NC}\n")
        time.sleep(1)
        return True


SystemDoctor.check_and_install(interactive=True)

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ==============================================================================
# SANITIZER & WATCHER ENGINE
# ==============================================================================

def is_file_ready(filepath: Path, timeout: float = 3.5) -> bool:
    start_time = time.time()
    last_size = -1
    while time.time() - start_time < timeout:
        try:
            if not filepath.exists():
                return False
            current_size = filepath.stat().st_size
            if current_size == 0 or current_size != last_size:
                last_size = current_size
                time.sleep(0.2)
                continue
            with open(filepath, "r+b"):
                return True
        except (PermissionError, IOError, OSError):
            time.sleep(0.2)
    return False


def process_image_file(filepath: Path):
    cfg = load_config()
    prefix = cfg.get("prefix", "img_")

    if (
        filepath.name.startswith(".")
        or filepath.name.startswith(prefix)
        or filepath.suffix.lower() not in VALID_EXTENSIONS
    ):
        return

    if not is_file_ready(filepath):
        return

    time.sleep(0.1)

    if cfg.get("enable_backup", False):
        try:
            backup_name = f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
            shutil.copy2(filepath, VAULT_DIR / backup_name)
        except Exception:
            pass

    if cfg.get("strip_exif", True):
        try:
            subprocess.run(
                ["exiftool", "-all=", "-overwrite_original_in_place", str(filepath)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log_event(f"ExifTool error on {filepath.name}: {e}")
            return

    target_path = filepath

    if cfg.get("random_hash", True):
        rand_token = uuid.uuid4().hex[:12]
        new_name = f"{prefix}{rand_token}{filepath.suffix.lower()}"
        target_path = filepath.parent / new_name
        try:
            filepath.rename(target_path)
        except OSError:
            target_path = filepath

    if cfg.get("clamp_time", True):
        try:
            epoch_2020 = 1577836800.0
            os.utime(target_path, (epoch_2020, epoch_2020))
        except OSError:
            pass

    if "com.termux" in os.environ.get("PREFIX", ""):
        subprocess.run(
            ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    log_event(f"Sanitized: {filepath.name} -> {target_path.name}")


class WatcherHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            process_image_file(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            process_image_file(Path(event.dest_path))


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
        handler = WatcherHandler()
        for folder in valid_folders:
            cls.observer.schedule(handler, path=str(folder), recursive=False)

        cls.observer.start()
        cls.is_running = True
        log_event(f"Engine started. Monitoring {len(valid_folders)} folder(s).")

    @classmethod
    def stop(cls):
        if not cls.is_running or not cls.observer:
            return
        cls.observer.stop()
        cls.observer.join()
        cls.is_running = False
        cls.observer = None
        log_event("Engine stopped.")

    @classmethod
    def restart(cls):
        if cls.is_running:
            cls.stop()
            cls.start()


# ==============================================================================
# UI DASHBOARD & TOOLS
# ==============================================================================

def pill(val: bool) -> str:
    return f"{CLR_GREEN}[ 🟢 ON  ]{NC}" if val else f"{CLR_GRAY}[ ⚪ OFF ]{NC}"


def draw_dashboard():
    os.system("cls" if os.name == "nt" else "clear")
    cfg = load_config()
    folder_count = len(cfg.get("folders", []))
    status_text = f"{CLR_GREEN}● RUNNING{NC}" if DaemonManager.is_running else f"{CLR_RED}○ STOPPED{NC}"

    print(f"{CLR_CYAN}╭────────────────────────────────────────────────────────╮{NC}")
    print(f"{CLR_CYAN}│{NC}  {BOLD}🛡️  S H O T C L E A N{NC}  {CLR_GRAY}·{NC}  {CLR_PURPLE}v{CURRENT_VERSION} Studio{NC}            {CLR_CYAN}│{NC}")
    print(f"{CLR_CYAN}│{NC}  {DIM}Cross-Platform Privacy & Anti-Forensics Suite         {NC}{CLR_CYAN}│{NC}")
    print(f"{CLR_CYAN}╰────────────────────────────────────────────────────────╯{NC}")

    # LIVE UPDATE BANNER
    if UPDATE_AVAILABLE:
        print(f"{CLR_AMBER}╭────────────────────────────────────────────────────────╮{NC}")
        print(f"{CLR_AMBER}│{NC}  {BOLD}🔔 UPDATE AVAILABLE: v{LATEST_VERSION}{NC}                           {CLR_AMBER}│{NC}")
        print(f"{CLR_AMBER}│{NC}  Press {CLR_CYAN}[U]{NC} to pull and install update automatically     {CLR_AMBER}│{NC}")
        print(f"{CLR_AMBER}╰────────────────────────────────────────────────────────╯{NC}")

    print(f"{CLR_BORDER}╭── {CLR_BLUE}{BOLD}SYSTEM HEALTH{NC}{CLR_BORDER} ───────────────────────────────────────╮{NC}")
    print(f"{CLR_BORDER}│{NC}  OS Environment :  {BOLD}{SystemDoctor.get_os_string()}{NC}")
    print(f"{CLR_BORDER}│{NC}  Engine Status  :  {status_text}")
    print(f"{CLR_BORDER}│{NC}  Watched Paths  :  {BOLD}{folder_count} directory registered{NC}")
    print(f"{CLR_BORDER}╰────────────────────────────────────────────────────────╯{NC}")

    print(f"{CLR_BORDER}╭── {CLR_AMBER}{BOLD}PRIVACY SHIELD STATUS{NC}{CLR_BORDER} ───────────────────────────────╮{NC}")
    print(f"{CLR_BORDER}│{NC}  EXIF Scrubbing : {pill(cfg['strip_exif'])}   Hash Rename  : {pill(cfg['random_hash'])}")
    print(f"{CLR_BORDER}│{NC}  Anti-Forensics : {pill(cfg['clamp_time'])}   Backup Vault : {pill(cfg['enable_backup'])}")
    print(f"{CLR_BORDER}╰────────────────────────────────────────────────────────╯{NC}")

    print(f"{CLR_BORDER}╭── {CLR_WHITE}{BOLD}CONTROLS & CONFIGURATION{NC}{CLR_BORDER} ────────────────────────────╮{NC}")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[1]{NC} ⚡ Toggle Engine ({'Halt' if DaemonManager.is_running else 'Start'})")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[2]{NC} 📁 Manage Monitored Folders")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[3]{NC} 🎭 Privacy Profiles (Ghost / Balanced / Preserve)")
    print(f"{CLR_BORDER}╰────────────────────────────────────────────────────────╯{NC}")

    print(f"{CLR_BORDER}╭── {CLR_WHITE}{BOLD}QUICK TOGGLES{NC}{CLR_BORDER} ───────────────────────────────────────╮{NC}")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[4]{NC} 🏷️  EXIF Stripping       {CLR_CYAN}[5]{NC} 🎲 Hash Renaming")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[6]{NC} ⏱️  Anti-Forensic Time   {CLR_CYAN}[7]{NC} 🔐 Backup Vault")
    print(f"{CLR_BORDER}╰────────────────────────────────────────────────────────╯{NC}")

    print(f"{CLR_BORDER}╭── {CLR_WHITE}{BOLD}AUDIT & TOOLS{NC}{CLR_BORDER} ───────────────────────────────────────╮{NC}")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[8]{NC} 🔍 Live EXIF Audit      {CLR_CYAN}[9]{NC} 🧹 Bulk Clean Folders")
    print(f"{CLR_BORDER}│{NC}  {CLR_CYAN}[10]{NC} 📜 Activity Logs       {CLR_CYAN}[11]{NC} 🩺 System Doctor")
    if UPDATE_AVAILABLE:
        print(f"{CLR_BORDER}│{NC}  {CLR_AMBER}[U]  🚀 Update to v{LATEST_VERSION}{NC}")
    print(f"{CLR_BORDER}│{NC}  {CLR_RED}[0]   🚪 Exit Suite{NC}")
    print(f"{CLR_BORDER}╰────────────────────────────────────────────────────────╯{NC}")


def tool_live_audit():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{CLR_CYAN}=== Live EXIF Audit ==={NC}\n")
    cfg = load_config()
    candidates = []
    for f in cfg.get("folders", []):
        p = Path(f)
        if p.exists():
            for ext in VALID_EXTENSIONS:
                candidates.extend(p.glob(f"*{ext}"))

    if not candidates:
        print(f"  {CLR_AMBER}No images found to audit.{NC}\n")
        input("  Press [Enter] to return...")
        return

    latest_file = max(candidates, key=lambda f: f.stat().st_mtime)
    print(f"  Target: {BOLD}{latest_file.name}{NC}\n")

    res = subprocess.run(
        ["exiftool", "-exif:all", "-xmp:all", "-iptc:all", str(latest_file)],
        capture_output=True, text=True
    )
    if not res.stdout.strip():
        print(f"  {CLR_GREEN}{BOLD}✔ 100% CLEAN - ZERO METADATA DETECTED!{NC}")
    else:
        print(f"  {CLR_RED}{BOLD}⚠ LEAKS DETECTED:{NC}\n{res.stdout}")

    st = latest_file.stat()
    print(f"\n  Modified: {time.ctime(st.st_mtime)}")
    print(f"  Accessed: {time.ctime(st.st_atime)}\n")
    input("  Press [Enter] to return...")


def tool_bulk_clean():
    os.system("cls" if os.name == "nt" else "clear")
    cfg = load_config()
    print(f"{CLR_CYAN}=== Bulk Scrubber ==={NC}\n")
    folders = [Path(f) for f in cfg.get("folders", []) if Path(f).exists()]
    confirm = input("  Scrub all existing photos across monitored folders? [y/N]: ").strip().lower()
    if confirm not in ["y", "yes"]:
        return

    count = 0
    for folder in folders:
        for ext in VALID_EXTENSIONS:
            for img in folder.glob(f"*{ext}"):
                if not img.name.startswith("."):
                    subprocess.run(
                        ["exiftool", "-all=", "-overwrite_original_in_place", str(img)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    if cfg.get("clamp_time", True):
                        os.utime(img, (1577836800.0, 1577836800.0))
                    count += 1
    print(f"\n  {CLR_GREEN}✔ Scrubbed {count} images.{NC}\n")
    time.sleep(1.2)


def tool_manage_folders():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        cfg = load_config()
        folders = cfg.get("folders", [])
        print(f"{CLR_CYAN}=== Monitored Folders ==={NC}\n")
        for i, f in enumerate(folders, 1):
            p = Path(f)
            status = f"{CLR_GREEN}Active{NC}" if p.exists() else f"{CLR_RED}Missing{NC}"
            print(f"  [{i}] {f} ({status})")
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
    print(f"{CLR_CYAN}=== Profiles ==={NC}\n")
    print("  [1] Ghost (Scrub + Rename + Time Clamp)")
    print("  [2] Balanced (Scrub + Rename)")
    print("  [3] Preserve (Scrub only, keep filename)")
    c = input("\n  Select [1-3]: ").strip()
    if c == "1":
        cfg["strip_exif"] = True; cfg["random_hash"] = True; cfg["clamp_time"] = True
    elif c == "2":
        cfg["strip_exif"] = True; cfg["random_hash"] = True; cfg["clamp_time"] = False
    elif c == "3":
        cfg["strip_exif"] = True; cfg["random_hash"] = False; cfg["clamp_time"] = False
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
# MAIN LOOP
# ==============================================================================

def main():
    DaemonManager.start()

    while True:
        draw_dashboard()
        choice = input(" ❯ Select option: ").strip()

        if choice.lower() == "u" and UPDATE_AVAILABLE:
            perform_git_update()
        elif choice == "1":
            DaemonManager.stop() if DaemonManager.is_running else DaemonManager.start()
        elif choice == "2":
            tool_manage_folders()
        elif choice == "3":
            tool_profiles()
        elif choice == "4":
            toggle_cfg("strip_exif")
        elif choice == "5":
            toggle_cfg("random_hash")
        elif choice == "6":
            toggle_cfg("clamp_time")
        elif choice == "7":
            toggle_cfg("enable_backup")
        elif choice == "8":
            tool_live_audit()
        elif choice == "9":
            tool_bulk_clean()
        elif choice == "10":
            os.system("cls" if os.name == "nt" else "clear")
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    print("".join(f.readlines()[-25:]))
            input("\n  Press [Enter] to return...")
        elif choice == "11":
            os.system("cls" if os.name == "nt" else "clear")
            SystemDoctor.check_and_install(interactive=True)
            input("  Press [Enter] to return...")
        elif choice == "0":
            DaemonManager.stop()
            print(f"\n  {CLR_GREEN}Shutdown complete. Stay safe!{NC}\n")
            sys.exit(0)


if __name__ == "__main__":
    main()
