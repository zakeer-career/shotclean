#!/data/data/com.termux/files/usr/bin/bash
set -e

echo -e "\033[38;5;51m[*] Installing ShotClean automatically...\033[0m"

# 1. Install prerequisites silently
pkg update -y >/dev/null 2>&1 || true
pkg install -y git python exiftool >/dev/null 2>&1

# 2. Setup or update repository in user home
TARGET_DIR="$HOME/shotclean"
if [ -d "$TARGET_DIR/.git" ]; then
    echo -e "\033[38;5;82m[*] Updating existing ShotClean installation...\033[0m"
    cd "$TARGET_DIR" && git pull --quiet
else
    rm -rf "$TARGET_DIR"
    git clone --quiet https://github.com/zakeer-career/shotclean.git "$TARGET_DIR"
fi

# 3. Ensure permissions and dependencies
chmod +x "$TARGET_DIR/shotclean.py"
python -m pip install watchdog --quiet --disable-pip-version-check 2>/dev/null || true

# 4. Create global executable wrapper in PATH
BIN_PATH="$PREFIX/bin/shotclean"
cat << 'EOF' > "$BIN_PATH"
#!/data/data/com.termux/files/usr/bin/bash
exec python "$HOME/shotclean/shotclean.py" "$@"
EOF
chmod 755 "$BIN_PATH"
hash -r 2>/dev/null || true

echo -e "\033[38;5;82m[✔] Installation complete! Launching ShotClean...\033[0m"
sleep 1
exec "$BIN_PATH"
