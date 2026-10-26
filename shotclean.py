#!/usr/bin/env python3
"""
ShotClean · Universal Metadata Stripper & Anti-Forensics Engine
Features an automatic environment doctor and dependency installer.
"""

import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Enable ANSI escape sequences on Windows cmd/PowerShell
if platform.system() == "Windows":
    os.system("")

# ANSI Visual Styling
CLR_CYAN = "\033[38;5;51m"
CLR_GREEN = "\033[38;5;82m"
CLR_RED = "\033[38;5;203m"
CLR_AMBER = "\033[38;5;214m"
CLR_GRAY = "\033[38;5;245m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"


# ==============================================================================
# 1. ENVIRONMENT DOCTOR & AUTOMATIC DEPENDENCY RESOLVER
# ==============================================================================

class SystemDoctor:
    def __init__(self):
        self.os_type = self._detect_os()
        self.missing_pip = []
        self.missing_bins = []

    def _detect_os(self):
        """Identifies OS and distinguishes standard Linux from Android/Termux."""
        if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
            return "Android (Termux)"
        elif platform.system() == "Darwin":
            return "macOS"
        elif platform.system() == "Windows":
            return "Windows"
        elif platform.system() == "Linux":
            distro = self._get_linux_distro()
            return f"Linux ({distro})" if distro else "Linux"
        return platform.system()

    def _get_linux_distro(self):
        if Path("/etc/os-release").exists():
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=")[1].strip().strip('"')
        return None

    def run_diagnostics(self):
        """Audits python version, python packages, and system binaries."""
        print(f"\n{CLR_CYAN}╭──────────────────────────────────────────────────────╮{NC}")
        print(f"{CLR_CYAN}│{NC}  {BOLD}🛡️  SHOTCLEAN · System Doctor & Pre-Flight Check{NC}    {CLR_CYAN}│{NC}")
        print(f"{CLR_CYAN}╰──────────────────────────────────────────────────────╯{NC}")
        print(f"  {CLR_GRAY}Detected System:{NC} {BOLD}{self.os_type}{NC} ({platform.machine()})\n")

        # 1. Python Version Check
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 8):
            print(f"  {CLR_GREEN}[✔]{NC} Python Runtime      : {py_ver}")
        else:
            print(f"  {CLR_RED}[✖]{NC} Python Runtime      : {py_ver} (Requires 3.8+)")
            sys.exit(1)

        # 2. Python Package Check (watchdog)
        try:
            import watchdog
            print(f"  {CLR_GREEN}[✔]{NC} Package 'watchdog'  : Installed")
        except ImportError:
            print(f"  {CLR_RED}[✖]{NC} Package 'watchdog'  : {CLR_AMBER}Missing{NC}")
            self.missing_pip.append("watchdog")

        # 3. System Binary Check (exiftool)
        if shutil.which("exiftool"):
            print(f"  {CLR_GREEN}[✔]{NC} Engine 'exiftool'   : Installed ({shutil.which('exiftool')})")
        else:
            print(f"  {CLR_RED}[✖]{NC} Engine 'exiftool'   : {CLR_AMBER}Missing from PATH{NC}")
            self.missing_bins.append("exiftool")

        print(f"\n{CLR_CYAN}────────────────────────────────────────────────────────{NC}")

        # If everything is installed, proceed directly
        if not self.missing_pip and not self.missing_bins:
            print(f"  {CLR_GREEN}{BOLD}All dependencies verified. Initializing privacy shield...{NC}\n")
            time.sleep(1)
            return True

        # Otherwise, offer one-click installation
        self._prompt_auto_install()
        return True

    def _prompt_auto_install(self):
        print(f"\n  {CLR_AMBER}{BOLD}Action Required:{NC} Some dependencies need to be installed.")
        choice = input("  Would you like ShotClean to install them automatically? [Y/n]: ").strip().lower()

        if choice in ["n", "no"]:
            print(f"\n  {CLR_RED}Aborted. Please install dependencies manually and restart.{NC}")
            sys.exit(0)

        # Step A: Install Python Packages
        if self.missing_pip:
            print(f"\n  {CLR_CYAN}Installing Python packages via pip...{NC}")
            for pkg in self.missing_pip:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            print(f"  {CLR_GREEN}✔ Python packages installed.{NC}")

        # Step B: Install System Binaries (exiftool)
        if "exiftool" in self.missing_bins:
            print(f"\n  {CLR_CYAN}Installing 'exiftool' for {self.os_type}...{NC}")
            success = self._install_exiftool()
            if not success:
                print(f"\n  {CLR_RED}Automatic installation failed for your package manager.{NC}")
                self._show_manual_instructions()
                sys.exit(1)

        print(f"\n  {CLR_GREEN}{BOLD}✔ All dependencies successfully installed! Launching...{NC}\n")
        time.sleep(1.5)

    def _install_exiftool(self):
        try:
            if "Android (Termux)" in self.os_type:
                subprocess.check_call(["pkg", "install", "-y", "exiftool"])
                return True
            elif "macOS" in self.os_type:
                if shutil.which("brew"):
                    subprocess.check_call(["brew", "install", "exiftool"])
                    return True
                else:
                    print(f"  {CLR_RED}Homebrew not found. Please install Homebrew first (brew.sh).{NC}")
                    return False
            elif "Windows" in self.os_type:
                if shutil.which("winget"):
                    subprocess.check_call([
                        "winget", "install", "OliverBetz.ExifTool",
                        "--accept-source-agreements", "--accept-package-agreements"
                    ])
                    return True
                elif shutil.which("choco"):
                    subprocess.check_call(["choco", "install", "exiftool", "-y"])
                    return True
                return False
            else:  # Linux Distros
                if shutil.which("apt-get"):
                    subprocess.check_call(["sudo", "apt-get", "update"])
                    subprocess.check_call(["sudo", "apt-get", "install", "-y", "libimage-exiftool-perl"])
                    return True
                elif shutil.which("pacman"):
                    subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "perl-image-exiftool"])
                    return True
                elif shutil.which("dnf"):
                    subprocess.check_call(["sudo", "dnf", "install", "-y", "perl-Image-ExifTool"])
                    return True
        except Exception as e:
            print(f"  {CLR_RED}Installation error: {e}{NC}")
            return False
        return False

    def _show_manual_instructions(self):
        print(f"\n  Please install 'exiftool' manually using your terminal:")
        print(f"   • {BOLD}Windows{NC} : winget install OliverBetz.ExifTool")
        print(f"   • {BOLD}macOS{NC}   : brew install exiftool")
        print(f"   • {BOLD}Debian/Ubuntu{NC}: sudo apt install libimage-exiftool-perl")
        print(f"   • {BOLD}Arch/Manjaro{NC} : sudo pacman -S perl-image-exiftool")
        print(f"   • {BOLD}Android/Termux{NC}: pkg install exiftool")


# Run Diagnostics on Launch
doctor = SystemDoctor()
doctor.run_diagnostics()

# ==============================================================================
# 2. PRIVACY & ANTI-FORENSICS ENGINE
# ==============================================================================

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

VALID_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

def detect_default_folder():
    home = Path.home()
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        return Path("/storage/emulated/0/Pictures/Screenshots")
    elif platform.system() == "Windows":
        return home / "Pictures" / "Screenshots"
    elif platform.system() == "Darwin":
        return home / "Desktop"
    else:
        linux_path = home / "Pictures" / "Screenshots"
        return linux_path if linux_path.exists() else home / "Pictures"

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

class PrivacyHandler(FileSystemEventHandler):
    def __init__(self, prefix: str = "img_", clamp_time: bool = True):
        super().__init__()
        self.prefix = prefix
        self.clamp_time = clamp_time
        self.processed = set()

    def process_image(self, src_path: str):
        filepath = Path(src_path).resolve()

        if (
            filepath.name.startswith(".")
            or filepath.name.startswith(self.prefix)
            or filepath.suffix.lower() not in VALID_EXTENSIONS
            or str(filepath) in self.processed
        ):
            return

        if not is_file_ready(filepath):
            return

        self.processed.add(str(filepath))
        time.sleep(0.1)

        print(f"  {CLR_CYAN}[+] Detected File:{NC} {filepath.name}")

        # 1. Strip EXIF Metadata In-Place
        try:
            subprocess.run(
                ["exiftool", "-all=", "-overwrite_original_in_place", str(filepath)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"   ├── {CLR_GREEN}[✔] EXIF & device headers wiped{NC}")
        except Exception as e:
            print(f"   ├── {CLR_RED}[!] ExifTool error: {e}{NC}")
            return

        # 2. Randomize File Name
        rand_token = uuid.uuid4().hex[:12]
        new_name = f"{self.prefix}{rand_token}{filepath.suffix.lower()}"
        target_path = filepath.parent / new_name

        try:
            filepath.rename(target_path)
            print(f"   ├── {CLR_GREEN}[✔] Renamed to random hash:{NC} {target_path.name}")
        except OSError as e:
            print(f"   ├── {CLR_AMBER}[!] Rename skipped: {e}{NC}")
            target_path = filepath

        # 3. Clamp Filesystem Timestamps (2020-01-01 00:00:00)
        if self.clamp_time:
            try:
                epoch_2020 = 1577836800.0
                os.utime(target_path, (epoch_2020, epoch_2020))
                print(f"   └── {CLR_GREEN}[✔] Timestamp clamped to 2020 (Anti-Forensics){NC}\n")
            except OSError:
                print(f"   └── {CLR_AMBER}[!] Timestamp clamping skipped{NC}\n")

        # Notify Android MediaStore if on Termux
        if "com.termux" in os.environ.get("PREFIX", ""):
            subprocess.run(
                ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{target_path}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        if len(self.processed) > 200:
            self.processed.clear()

    def on_created(self, event):
        if not event.is_directory:
            self.process_image(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.process_image(event.dest_path)


def main():
    watch_dir = detect_default_folder()
    watch_dir.mkdir(parents=True, exist_ok=True)

    print(f"{CLR_CYAN}╭── PRIVACY SHIELD ACTIVE ─────────────────────────────╮{NC}")
    print(f"  {BOLD}Monitoring Path{NC} : {watch_dir}")
    print(f"  {BOLD}EXIF Scrubbing{NC}  : {CLR_GREEN}ACTIVE{NC}")
    print(f"  {BOLD}Hash Renaming{NC}   : {CLR_GREEN}ACTIVE (img_xxxxxxxxxxxx.ext){NC}")
    print(f"  {BOLD}Anti-Forensics{NC}  : {CLR_GREEN}ACTIVE (Clamped: 2020-01-01){NC}")
    print(f"{CLR_CYAN}╰──────────────────────────────────────────────────────╯{NC}")
    print(f"  {CLR_GRAY}Watching for new screenshots... (Press Ctrl+C to halt){NC}\n")

    handler = PrivacyHandler()
    observer = Observer()
    observer.schedule(handler, path=str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n  {CLR_AMBER}Halting watcher engine...{NC}")
        observer.stop()
    observer.join()
    print(f"  {CLR_GREEN}Shutdown clean.{NC}\n")


if __name__ == "__main__":
    main()
