#!/usr/bin/env python3
"""
replace_codex.py

Icon replacement and app renaming tool for ChatGPT.app -> Codex.app.
Dynamically anchors to REPO_DIR (directory containing this script).
Backs up old icons, replaces icon files from assets/, renames ChatGPT.app
to Codex.app (if applicable), updates Info.plist, re-signs the app bundle,
sets custom Finder preview icon, and gently flushes icon caches.
"""

import os
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Dynamically anchor REPO_DIR to directory containing this script
REPO_DIR = Path(__file__).resolve().parent

ICON_FILES = [
    "icon-codex-light.png",
    "icon-chatgpt.png",
    "icon-codex-dark-color.png",
    "icon-chatgpt.icns",
    "electron.icns",
    "app.icns",
]


def handle_permission_error(target: Path, err: Exception = None):
    print(f"\n[ERROR] Permission denied when accessing or modifying: {target}", file=sys.stderr)
    if err:
        print(f"Details: {err}", file=sys.stderr)
    print("Opening macOS System Settings -> Privacy & Security -> App Management...", file=sys.stderr)
    try:
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AppManagement"],
            check=False
        )
    except Exception as open_err:
        print(f"Failed to open System Settings: {open_err}", file=sys.stderr)
    print("\nPlease grant Terminal / Python permission in App Management and re-run this script.\n", file=sys.stderr)
    sys.exit(1)


def resolve_apps() -> tuple[Path, Path]:
    sys_chatgpt = Path("/Applications/ChatGPT.app")
    sys_codex = Path("/Applications/Codex.app")
    user_chatgpt = Path.home() / "Applications" / "ChatGPT.app"
    user_codex = Path.home() / "Applications" / "Codex.app"

    if sys_chatgpt.exists():
        return sys_chatgpt, sys_codex
    elif user_chatgpt.exists():
        return user_chatgpt, user_codex
    elif sys_codex.exists():
        return sys_codex, sys_codex
    elif user_codex.exists():
        return user_codex, user_codex
    else:
        return sys_chatgpt, sys_codex


def check_permissions(app_path: Path):
    if not app_path.exists():
        return
    if not os.access(app_path, os.W_OK):
        handle_permission_error(app_path)
    resources_dir = app_path / "Contents" / "Resources"
    if resources_dir.exists() and not os.access(resources_dir, os.W_OK):
        handle_permission_error(resources_dir)


def update_info_plist(plist_path: Path):
    if not plist_path.exists():
        return
    print("Updating Info.plist display name to 'Codex'...")
    updated = False
    try:
        with open(plist_path, "rb") as f:
            plist_data = plistlib.load(f)
        plist_data["CFBundleDisplayName"] = "Codex"
        plist_data["CFBundleName"] = "Codex"
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)
        updated = True
        print("  Updated Info.plist via plistlib.")
    except Exception as e:
        print(f"  plistlib update skipped ({e}), falling back to PlistBuddy...")

    if not updated:
        try:
            subprocess.run(
                ["/usr/libexec/PlistBuddy", "-c", "Add :CFBundleDisplayName string 'Codex'", str(plist_path)],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["/usr/libexec/PlistBuddy", "-c", "Set :CFBundleDisplayName 'Codex'", str(plist_path)],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["/usr/libexec/PlistBuddy", "-c", "Add :CFBundleName string 'Codex'", str(plist_path)],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["/usr/libexec/PlistBuddy", "-c", "Set :CFBundleName 'Codex'", str(plist_path)],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print("  Updated Info.plist via PlistBuddy.")
        except PermissionError as e:
            handle_permission_error(plist_path, e)


def main():
    print(f"Anchor point (REPO_DIR): {REPO_DIR}")

    source_app, target_app = resolve_apps()
    print(f"Source app path: {source_app}")
    print(f"Target app path: {target_app}")

    if not source_app.exists() and not target_app.exists():
        print(f"[ERROR] Neither {source_app.name} nor {target_app.name} was found.", file=sys.stderr)
        print("Make sure ChatGPT.app or Codex.app is installed in /Applications or ~/Applications.", file=sys.stderr)
        sys.exit(1)

    working_app = source_app if source_app.exists() else target_app

    check_permissions(working_app)
    if working_app != target_app and target_app.exists():
        check_permissions(target_app)

    resources_dir = working_app / "Contents" / "Resources"
    if not resources_dir.exists():
        print(f"[ERROR] Resources folder not found: {resources_dir}", file=sys.stderr)
        sys.exit(1)

    assets_dir = REPO_DIR / "assets"
    if not assets_dir.exists():
        print(f"[ERROR] Assets folder not found: {assets_dir}", file=sys.stderr)
        sys.exit(1)

    # Ensure all required assets exist
    for icon_name in ICON_FILES:
        src_file = assets_dir / icon_name
        if not src_file.exists():
            print(f"[ERROR] Missing source icon in assets: {src_file}", file=sys.stderr)
            sys.exit(1)

    # 1. Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = REPO_DIR / "_backups"
    backup_dir = backup_root / timestamp

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        handle_permission_error(backup_dir, e)

    print(f"Backing up existing icons to: {backup_dir}")
    for icon_name in ICON_FILES:
        dst_file = resources_dir / icon_name
        if dst_file.exists():
            try:
                shutil.copy2(dst_file, backup_dir / icon_name)
                print(f"  Backed up: {icon_name}")
            except PermissionError as e:
                handle_permission_error(dst_file, e)

    # 2. Copy replacement icons into app bundle
    print("Replacing icons in app bundle...")
    copy_count = 0
    for icon_name in ICON_FILES:
        src_file = assets_dir / icon_name
        dst_file = resources_dir / icon_name
        try:
            shutil.copy2(src_file, dst_file)
            copy_count += 1
            print(f"  Updated: {icon_name}")
        except PermissionError as e:
            handle_permission_error(dst_file, e)

    # 3. Rename app if necessary (ChatGPT.app -> Codex.app)
    if working_app != target_app:
        print(f"Renaming {working_app} to {target_app}...")
        try:
            if target_app.exists():
                print(f"  Removing existing {target_app} before move...")
                shutil.rmtree(target_app)
            shutil.move(str(working_app), str(target_app))
            working_app = target_app
        except PermissionError as e:
            handle_permission_error(working_app, e)

    # 4. Update Info.plist display name
    info_plist = working_app / "Contents" / "Info.plist"
    update_info_plist(info_plist)

    # 5. Strip quarantine & Re-sign app bundle
    print("Re-signing app bundle...")
    try:
        subprocess.run(["xattr", "-cr", str(working_app)], check=False, stderr=subprocess.DEVNULL)
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(working_app)],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except PermissionError as e:
        handle_permission_error(working_app, e)

    # 6. Set Finder custom preview icon
    preview_icon = assets_dir / "app.icns"
    if preview_icon.exists():
        print("Setting custom Finder (Cmd+I) preview icon...")
        swift_snippet = (
            'import AppKit; '
            f'if let img = NSImage(contentsOfFile: "{preview_icon}") {{ '
            f'_ = NSWorkspace.shared.setIcon(img, forFile: "{working_app}", options: []) '
            '}'
        )
        subprocess.run(["swift", "-e", swift_snippet], check=False, stderr=subprocess.DEVNULL)

    # 7. Refresh Finder & Dock icon caches
    print("Refreshing Finder & Dock icon caches...")
    lsregister_path = Path("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister")
    if lsregister_path.exists():
        subprocess.run([str(lsregister_path), "-f", str(working_app)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["lsregister", "-f", str(working_app)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        working_app.touch()
        (working_app / "Contents" / "Resources").touch()
    except Exception:
        pass

    subprocess.run(["qlmanage", "-r"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["qlmanage", "-r", "cache"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["killall", "Finder"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["killall", "Dock"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        working_app.touch()
        (working_app / "Contents" / "Resources").touch()
    except Exception:
        pass

    print("=" * 60)
    print(f"Successfully replaced icons and configured {working_app.name}!")
    print(f"Icons updated: {copy_count}")
    print(f"Backup saved in: {backup_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
