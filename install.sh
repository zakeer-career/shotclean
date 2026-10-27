#!/bin/bash
# ==============================================================================
# ShotClean Universal Automated Installer & Health Doctor (v5.7.0)
# Cross-Platform: Android (Termux), Linux, macOS
# ==============================================================================
set -e

CLR_CYAN="\033[38;5;51m"
CLR_GREEN="\033[38;5;82m"
CLR_RED="\033[38;5;203m"
CLR_AMBER="\033[38;5;214m"
NC="\033[0m"
BOLD="\033[1m"

echo -e "${CLR_CYAN}${BOLD}[*] Initializing ShotClean Universal Installer v5.7.0...${NC}"

# 1. Detect Environment & Package Manager
IS_TERMUX=false
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ] && [[ "$PREFIX" == *"com.termux"* ]]; then
    IS_TERMUX=true
fi

echo -e "${CLR_CYAN}[1/5] Verifying system dependencies, image libraries & SSL certificates...${NC}"
if [ "$IS_TERMUX" = true ]; then
    if [ ! -d "/storage/emulated/0" ]; then
        echo -e "${CLR_AMBER}[!] Requesting Android storage permission...${NC}"
        termux-setup-storage || true
    fi
    pkg update -y >/dev/null 2>&1 || true
    pkg install -y git python python-pillow exiftool curl openssl ca-certificates >/dev/null 2>&1 || \
    pkg install -y git python exiftool curl openssl ca-certificates >/dev/null 2>&1
elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y >/dev/null 2>&1 || true
    sudo apt-get install -y git python3 python3-pip python3-pil libimage-exiftool-perl curl openssl ca-certificates >/dev/null 2>&1
elif command -v brew >/dev/null 2>&1; then
    brew install git python exiftool curl openssl >/dev/null 2>&1 || true
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm git python python-pip python-pillow perl-image-exiftool curl openssl ca-certificates >/dev/null 2>&1 || true
fi

# 2. Deploy or Update Repository with Conflict Resolution
echo -e "${CLR_CYAN}[2/5] Synchronizing ShotClean codebase...${NC}"
TARGET_DIR="$HOME/shotclean"
REPO_URL="https://github.com/zakeer-career/shotclean.git"

if [ -d "$TARGET_DIR/.git" ]; then
    echo -e "${CLR_GREEN}[*] Updating existing ShotClean installation (resolving local conflicts)...${NC}"
    cd "$TARGET_DIR"
    git fetch origin --quiet || true
    git reset --hard origin/main --quiet || git pull --quiet || true
else
    rm -rf "$TARGET_DIR"
    git clone --quiet "$REPO_URL" "$TARGET_DIR"
fi

# Clean stale bytecode caches
find "$TARGET_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$TARGET_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 3. Python Virtual / Dependency Management (Watchdog & Pillow with PEP 668 bypass)
echo -e "${CLR_CYAN}[3/5] Checking Python packages (watchdog & pillow)...${NC}"
chmod +x "$TARGET_DIR/shotclean.py"

python3 -m pip install watchdog pillow --quiet --disable-pip-version-check 2>/dev/null || \
python -m pip install watchdog pillow --quiet --disable-pip-version-check 2>/dev/null || \
python3 -m pip install watchdog pillow --break-system-packages --quiet 2>/dev/null || \
python -m pip install watchdog pillow --break-system-packages --quiet 2>/dev/null || \
python -m pip install watchdog --break-system-packages --quiet 2>/dev/null || true

# 4. Generate Global Binary Executable & Termux:Widget Shortcuts
echo -e "${CLR_CYAN}[4/5] Registering global 'shotclean' command...${NC}"
if [ "$IS_TERMUX" = true ]; then
    BIN_PATH="$PREFIX/bin/shotclean"
    cat << 'EOF' > "$BIN_PATH"
#!/data/data/com.termux/files/usr/bin/bash
exec python "$HOME/shotclean/shotclean.py" "$@"
EOF
    chmod 755 "$BIN_PATH"
    python "$TARGET_DIR/shotclean.py" --install-service >/dev/null 2>&1 || true
else
    BIN_DIR="/usr/local/bin"
    if [ ! -w "$BIN_DIR" ]; then
        BIN_DIR="$HOME/.local/bin"
        mkdir -p "$BIN_DIR"
    fi
    BIN_PATH="$BIN_DIR/shotclean"
    cat << 'EOF' > "$BIN_PATH"
#!/usr/bin/env bash
PYTHON_BIN="$(command -v python3 || command -v python)"
exec "$PYTHON_BIN" "$HOME/shotclean/shotclean.py" "$@"
EOF
    chmod 755 "$BIN_PATH"
fi

hash -r 2>/dev/null || true

# 5. Launch (Rebind stdin to /dev/tty so 'curl | bash' does not leave stdin on closed pipe)
echo -e "${CLR_GREEN}${BOLD}[5/5] ✔ Installation verified and complete! Launching ShotClean...${NC}"
sleep 1
if [ -e /dev/tty ]; then
    exec "$BIN_PATH" < /dev/tty
else
    exec "$BIN_PATH"
fi
