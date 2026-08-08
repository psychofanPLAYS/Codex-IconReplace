# IconReplace ⚡

> **Keep Codex looking like Codex.**  
> An automated, zero-resource macOS utility that restores dark mode icons and branding whenever OpenAI updates the desktop application.

---

## 😤 The Problem

Every time OpenAI updates the Mac app:
1. It renames your customized **Codex.app** back to **ChatGPT.app**.
2. It resets your sleek dark mode icon back to the bright white stock icon.
3. Your Dock gets stuck with a light mode icon that sticks out like a sore thumb.

Re-applying icons manually after every single update is frustrating and annoying.

---

## 🎨 The Solution: IconReplace

`IconReplace` fixes this problem permanently with **zero effort**:

* **✨ 1-Click Dark Mode Swap**: Turn `ChatGPT.app` into `Codex.app` with a beautiful custom dark mode icon in one click.
* **⚡ Zero-Resource Auto-Repair**: Registers a native macOS trigger (`launchd`) that sleeps 99.99% of the time (**0% CPU, 0 MB RAM**). When OpenAI pushes an update, macOS quietly wakes up `IconReplace` to restore your dark icon automatically.
* **↺ 1-Click Undo / Backup**: Every modification creates a safe backup in `_backups/`. Restore stock condition anytime with 1-click.
* **🖼️ Custom Icon & Preview**: See a live preview of your icon before applying, or drop in your own custom `.png` or `.icns` file.
* **🛡️ Mac Safe**: Non-destructive, fully compatible with macOS 15+ (Sequoia) and Apple Silicon.

---

## 🚀 Quick Start Guide

### Option 1: Double-Click App Bundle
1. Open the project folder.
2. Double-click `IconReplace.app`.
3. Click **"✨ Apply Dark Mode Icon"**.
4. (Optional) Turn on **"Auto-Repair when Codex updates"** to automate future updates.

### Option 2: Command Line (CLI)
```bash
# Apply dark mode icon patch
python3 app/src/main.py --patch

# Restore stock backup
python3 app/src/main.py --restore

# Run unit tests
python3 -m unittest discover app/tests
```

---

## ⚙️ How Auto-Repair Works (In Plain English)

Instead of keeping a background app running all day and draining your battery, `IconReplace` uses macOS kernel file triggers (`WatchPaths` via `launchd`):

1. **Idle**: The app does **not** run in the background. It uses **0% CPU** and **0 MB RAM**.
2. **OpenAI Update**: When an update arrives and replaces `ChatGPT.app`, macOS detects the file change.
3. **Auto-Fix**: macOS briefly invokes `IconReplace` in the background for 2 seconds to re-apply your dark mode icon, update bundle names, and send a desktop banner notification.

---

## 🛠️ Requirements & Compatibility

* **OS**: macOS 11.0+ (Tested through macOS 15+ Sequoia)
* **Architecture**: Apple Silicon (M1/M2/M3/M4) & Intel Macs
* **Dependencies**: Python 3 (built-in on macOS)

---

## 📜 License

MIT License. Free for everyone to use and customize.
