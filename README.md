# IconReplace

> Native macOS application icon and branding management utility with automated update persistence and backup verification.

![IconReplace UI](docs/assets/screenshot.png)

## Overview

**IconReplace** is a specialized macOS utility built with PySide6/CustomTkinter and native macOS system integrations. It enables developers and power users to replace application icons and bundle branding across macOS system and third-party applications. 

To counteract automated application updates that overwrite custom resources, IconReplace configures lightweight `launchd` kernel file watchers (`WatchPaths`) that automatically re-apply custom icon sets upon file modification with zero persistent CPU or memory overhead.

---

## Key Features

- **Liquid Glass Interface**: High-DPI dark-mode user interface designed for macOS Sonoma and Sequoia.
- **Automated Update Persistence**: Registers a native macOS `launchd` LaunchAgent that monitors target application bundles in `/Applications` and re-applies custom icon sets instantly upon app updates.
- **Zero-Overhead Daemon**: Uses kernel file system event notifications (`WatchPaths`); consumes 0% background CPU and 0 MB RAM when idle.
- **Automated Resource Backup**: Pre-modification verification creates checksum-verified backups of original `.icns` resources in `~/.iconreplace_backups/` before applying patches.
- **Instant Rollback**: One-click restoration of stock bundle assets and icon caches.
- **Cache Management**: Automatically triggers `touch` on application bundles and resets macOS `dockutil` / `lsregister` caches for immediate Dock visual refresh without system reboot.

---

## Architecture & System Requirements

### Platform Support
- **Operating System**: macOS 11.0 Big Sur through macOS 15+ Sequoia
- **Architecture**: Apple Silicon (M1/M2/M3/M4) and Intel x86_64
- **Permissions**: Requires macOS App Management or Full Disk Access permissions for `/Applications` bundle modifications.

### Repository Structure
```
Codex-IconReplace/
├── app/
│   ├── src/
│   │   ├── main.py              # CLI & GUI Application Entrypoint
│   │   ├── gui.py               # CustomTkinter / Liquid Glass UI Architecture
│   │   ├── icon_engine.py       # Core ICNS Manipulation & Dock Cache Management
│   │   ├── app_watcher.py       # Event Monitoring & LaunchAgent Dispatch
│   │   ├── launchd_manager.py   # System LaunchAgent Registration (.plist)
│   │   └── backup_registry.py   # Checksum & Backup Management
│   ├── scripts/
│   │   ├── build_app.sh         # PyInstaller Standalone Application Builder
│   │   └── create_icns.py       # PNG-to-ICNS Converter Script
│   └── tests/                   # Automated Unit Test Suite
├── docs/assets/
│   └── screenshot.png           # High-DPI Interface Screenshot
├── IconReplace.spec             # PyInstaller Packaging Specification
└── README.md
```

---

## Installation & Usage

### 1. Running the Standalone Application
If built using PyInstaller, execute the compiled macOS application bundle:
```bash
open IconReplace.app
```

### 2. Running from Source
Ensure Python 3.10+ and required dependencies are installed:
```bash
pip install -r app/requirements.txt
PYTHONPATH=app/src python3 app/src/main.py
```

### 3. Command Line Interface (CLI)
IconReplace supports headless operation for automated workflows and scripting:

```bash
# Apply custom icon patch to target application
python3 app/src/main.py --patch --app "/Applications/Xcode.app" --icon "custom_icon.icns"

# Enable background launchd update protection
python3 app/src/main.py --enable-watcher

# Restore original stock icon from backup
python3 app/src/main.py --restore --app "/Applications/Xcode.app"

# Display application status and backup registry
python3 app/src/main.py --status
```

---

## Building Standalone Application Bundle

To package IconReplace into a standalone macOS `.app` bundle using PyInstaller:

```bash
chmod +x app/scripts/build_app.sh
./app/scripts/build_app.sh
```
The compiled application bundle will be generated at `./IconReplace.app`.

---

## Testing & Verification

Run the automated test suite to verify core icon manipulation, backup registry integrity, and launchd configuration generators:

```bash
python3 -m unittest discover -s app/tests -p "test_*.py"
```

---

## License

Distributed under the MIT License. See [LICENSE](app/LICENSE) for complete terms.
