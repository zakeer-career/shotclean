@echo off
setlocal
cd /d "%~dp0"

:: 1. Check if Python is installed and accessible in PATH
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python is not detected in your PATH.
    echo [*] Attempting to install Python via Windows Package Manager (winget)...
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [X] Automatic installation failed. Please install Python from https://www.python.org/
        pause
        exit /b 1
    )
    echo [✔] Python installed. Please close and re-run run.bat to refresh environment paths.
    pause
    exit /b 0
)

:: 2. Launch the script
python shotclean.py %*
if %errorlevel% neq 0 (
    pause
)
