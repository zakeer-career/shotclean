#!/usr/bin/env bash

# Resolve directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Check if Python 3 is installed
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is not installed."
    if [ -d "/data/data/com.termux" ]; then
        echo "Installing Python via Termux..."
        pkg install -y python
    elif command -v apt-get >/dev/null 2>&1; then
        echo "Installing Python via apt..."
        sudo apt-get update && sudo apt-get install -y python3 python3-pip
    elif command -v brew >/dev/null 2>&1; then
        echo "Installing Python via Homebrew..."
        brew install python
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm python python-pip
    else
        echo "Please install Python 3 manually from https://python.org"
        exit 1
    fi
fi

# 2. Execute ShotClean with built-in doctor
python3 "$SCRIPT_DIR/shotclean.py" "$@"
