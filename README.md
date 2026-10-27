# 🛡️ ShotClean Universal Studio (v5.7.0)

**Zero-Footprint Anti-Forensics, Real-Time Metadata Sanitizer & Granular Media Privacy Shield**  
*Cross-Platform Support: Android (Termux), Linux, macOS, and Windows*

---

## ⚡ Quick One-Line Installation

Run this single command in **Termux**, **Linux**, or **macOS** to install dependencies (`exiftool`, `watchdog`, `pillow`, SSL certificates), resolve any local Git conflicts, register the global `shotclean` command, and launch the studio:

```bash
curl -sL https://raw.githubusercontent.com/zakeer-career/shotclean/main/install.sh | bash
```

---

## 🌟 What's New in v5.7.0

* **🔥 Scorched Earth & Anti-pHash Pixel Dithering:** Optional pixel-level canvas re-encoding strips trailing bytes after `IEND`, proprietary OEM quantization tables, and steganographic payloads. Enabling **Sub-Perceptual Pixel Dithering** applies a $\pm 1$ RGB value jitter to $2\%$ of pixels to defeat perceptual hashing (`pHash`/`dHash`) and LSB watermarks with zero visible change.
* **🧾 Persistent Scrubbed-File Ledger (`scrubbed_ledger.json`):** Tracks `[file_size, mtime]` signatures across restarts so files renamed with **Word Slugs**, **Decoy Presets**, or **Metadata Strip Only** are never re-renamed or re-queued when ShotClean restarts.
* **🧹 Active Catch-Up & Periodic Sweeper:** Automatically detects and sanitizes screenshots taken while ShotClean or Termux was closed—both on startup and via a configurable background heartbeat ($5$, $10$, or $30$ minutes).
* **📁 Granular Per-Folder Policies & Recursive Scope:** Assign independent rules to each folder (`Screenshots`, `DCIM/Camera`, `Download`, `Pictures`), toggle **Recursive Subfolder Monitoring** (`[R]`), and optionally sanitize screen recordings and documents (`.mp4`, `.mov`, `.pdf`).
* **🔐 Extension-Aware AES Safety Vault with Auto-Quota:** Encrypts original backups using $100,000$-round `PBKDF2-HMAC-SHA256` + stream cipher + HMAC authentication (`ENC1`), preserves original file extensions (`.jpg`, `.webp`, `.png`) upon restoration, and enforces an automatic storage quota (default $250\text{ MB}$ / $7\text{ days}$).
* **📱 Android 11+ MediaStore Pruning & Termux:Widget Shortcuts:** Eliminates orphaned "gray box" broken thumbnails in the Android Gallery via direct `content delete` provider calls and installs one-tap home screen shortcuts (`~/.shortcuts/`).
* **⌨️ Flicker-Free Universal Arrow Navigation:** Navigate every menu and folder browser using `↑`/`↓` arrows (or `W`/`S` and `K`/`J`), `Enter`/`Space` to select, and `Q`/`Left` to go back—with automatic `/dev/tty` re-attachment.

---

## 🎭 Built-In Privacy Presets

Each monitored folder can run one of the 6 built-in presets or your own saved **Custom Presets**:

| Preset | EXIF / ICC Scrub | Scorched Earth / Dither | Timestamp Clamping | Naming Camouflage | Best Used For |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **🛡️ Ghost** | ✅ ON | ⚪ OFF | `2020-01-01 00:00:00` | UUID Hex Hash (`img_7c9f2b84.png`) | Maximum anonymity for sensitive screenshots |
| **⚖️ Balanced** | ✅ ON | ⚪ OFF | `Today 00:00:00` (Day-Fuzz) | Word Slug (`swift-falcon-42.png`) | Daily screenshots that stay in Today's Gallery feed |
| **🔥 Scorched Earth** | ✅ ON | ✅ ON (+Dither) | `2020-01-01 00:00:00` | UUID Hex Hash (`clean_9a4f1c02.png`) | Defeating steganography, trailing data & pHash tracking |
| **🔢 Sequential** | ✅ ON | ⚪ OFF | `Today 00:00:00` (Day-Fuzz) | Indexed (`IMG_0001.png`) | Ordered tutorials, receipts, and sequential archives |
| **🏷️ Metadata Only** | ✅ ON | ⚪ OFF | Preserved (`-P`) | Original Filename | Cleaning camera roll photos without renaming files |
| **⏱️ Timestomp Only** | ⚪ OFF | ⚪ OFF | `2020-01-01 00:00:00` | Original Filename | Hiding capture creation times while keeping tags |

---

## 🎲 Naming & Camouflage Modes

Standard screenshot filenames (e.g., `Screenshot_20261027-081542_Chrome.png`) leak the exact date, second, and foreground application. ShotClean replaces them with:

1. **🛡️ UUID Hex Hash:** `img_7c9f2b84e1a0.png` (Configurable prefix, suffix, casing, and $8$/$12$/$16$/$32$-character length)
2. **🔢 Sequential Numbering:** `IMG_0001.png` (Persistent counter with collision detection and $3$ to $6$ digit zero-padding)
3. **🔤 Readable Word Slug:** `amber-falcon-42.png` (Memorable Diceware-style adjective-noun-number combinations)
4. **💬 WhatsApp Decoy:** `IMG-20261027-WA0042.jpg` (Blends seamlessly into chat media folders)
5. **📷 Camera DCIM Decoy:** `DSC_4821.jpg` (Mimics standard digital camera captures)
6. **🌐 Reddit / Web Decoy:** `RDT_20261027_140218.png` (Mimics saved web images)
7. **⚪ Disabled:** Preserves the original filename untouched.

---

## 💻 Command-Line Interface (CLI) & Headless Mode

In addition to the interactive Terminal UI (`shotclean`), you can automate ShotClean via CLI flags:

```bash
# Launch the interactive Arrow-Key Studio TUI
shotclean

# Run silently in the background as a headless daemon
shotclean --daemon

# Check daemon status, active folder rules, and scrubbed ledger count
shotclean --status

# Run an immediate one-shot catch-up sweep across all watched folders
shotclean --sweep

# Sanitize a specific file or directory immediately and exit
shotclean --clean /path/to/image_or_folder

# Stop an active background daemon
shotclean --stop

# Install auto-start boot scripts & Termux:Widget home screen shortcuts
shotclean --install-service
```

---

## 📱 Android Auto-Start & Home Screen Widgets (Termux)

When you run `shotclean --install-service` (or select **Option `[12] Engine Diagnostics & Shortcuts`** in the menu), ShotClean automatically configures:

1. **Termux:Boot Auto-Start (`~/.termux/boot/start-shotclean.sh`):**  
   Automatically launches the background shield whenever your phone reboots.
2. **Termux:Widget One-Tap Shortcuts (`~/.shortcuts/`):**  
   Add the **Termux:Widget** widget to your Android home screen for instant one-tap actions:
   * `ShotClean_Sweep_Now.sh` — Scrub all monitored folders immediately
   * `ShotClean_Start_Daemon.sh` — Start background protection
   * `ShotClean_Stop_Daemon.sh` — Pause background protection
   * `ShotClean_Status.sh` — View live protection status

---

## 📂 Configuration & Data Paths

All configuration files and encrypted backups are stored locally in `~/.shotclean/`:

* `~/.shotclean/config.json` — Per-folder policies, custom presets, and sweeper settings
* `~/.shotclean/scrubbed_ledger.json` — Persistent `[size, mtime]` ledger of sanitized files
* `~/.shotclean/activity.log` — Auto-rotating event log ($150\text{ KB}$ cap)
* `~/.shotclean/vault/` — Zero-knowledge AES-encrypted original image backups (`.enc`)
* `~/.shotclean/.vault_key` — Local $256$-bit master entropy key for vault decryption

---

## 📖 Documentation

For a deep dive into the threat model, forensic layers, and step-by-step feature guides, read the **[ShotClean Privacy Field Manual (MANUAL.md)](./MANUAL.md)**.
