# 🛡️ ShotClean

> **Cross-Platform Automated Screenshot Sanitizer & Anti-Forensics Privacy Suite**  
> Strips EXIF/XMP hardware fingerprints, randomizes filenames to UUID hashes, and clamps filesystem timestamps automatically in real time.

---

## ⚡ Features

* 🏷️ **Hardware Scrubbing:** Strips EXIF, XMP, IPTC, and device fingerprints using `exiftool`.
* 🎲 **UUID Hash Renaming:** Renames `Screenshot_20261026-140112.png` to `img_7c9f2b84e1a0.png` to stop timestamp leaks.
* ⏱️ **Anti-Forensic Timestomp:** Clamps filesystem access and modification times (`mtime` / `atime`) to fixed dates (`2020-01-01`).
* 🩺 **Pre-Flight System Doctor:** Auto-detects missing dependencies (`watchdog`, `exiftool`) and installs them automatically.
* 🔄 **One-Click Web Updater:** Checks for commits on GitHub automatically; press `U` to update seamlessly.
* 🔍 **Live EXIF Inspector:** Verify the latest capture directly in the terminal with one keypress.
* 🧹 **Bulk Scrubber:** Strip existing directories in seconds.

---

## 🚀 Quick Install & Run

### 📱 Android (Termux)
Open Termux and run:
```bash
pkg update -y && pkg install -y git python
git clone [https://github.com/zakeer-career/shotclean.git](https://github.com/zakeer-career/shotclean.git)
cd shotclean
python shotclean.py
