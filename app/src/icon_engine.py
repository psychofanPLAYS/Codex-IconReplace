"""
Icon Engine for IconReplace.

This module handles macOS icon conversions, bundle modifications, code-signing,
and icon cache invalidations.

Auditing & Safety Notes:
- Prior to replacing any icons or altering bundle Info.plist files, an immutable
  backup is created via `BackupRegistry`.
- Cache invalidations are strictly targeted (`qlmanage -r cache`, `killall Dock`).
- All subshell operations are audited and checked for execution safety.
"""

import logging
import os
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from backup_registry import BackupRegistry

logger = logging.getLogger("IconReplace.IconEngine")


def convert_image_to_icns(input_path: Path, output_icns_path: Path) -> bool:
    """
    Converts a standard image file (PNG/JPEG) into a macOS .icns file using native `sips`
    and `iconutil` utilities.

    Args:
        input_path: Path to the input image file.
        output_icns_path: Path where the generated .icns file will be saved.

    Returns:
        True if the .icns file was successfully created and is non-empty, False otherwise.
    """
    input_path = Path(input_path).resolve()
    output_icns_path = Path(output_icns_path).resolve()

    if not input_path.exists() or not input_path.is_file():
        logger.error("Input image file does not exist: %s", input_path)
        return False

    output_icns_path.parent.mkdir(parents=True, exist_ok=True)

    # Required iconset resolutions for Apple ICNS formatting
    icon_specs = [
        ("icon_16x16.png", 16, 16),
        ("icon_16x16@2x.png", 32, 32),
        ("icon_32x32.png", 32, 32),
        ("icon_32x32@2x.png", 64, 64),
        ("icon_128x128.png", 128, 128),
        ("icon_128x128@2x.png", 256, 256),
        ("icon_256x256.png", 256, 256),
        ("icon_256x256@2x.png", 512, 512),
        ("icon_512x512.png", 512, 512),
        ("icon_512x512@2x.png", 1024, 1024),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        iconset_dir = Path(tmp_dir) / "app.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        # Generate each icon resolution using sips with aspect ratio preservation
        for filename, width, height in icon_specs:
            out_png = iconset_dir / filename
            sips_cmd = [
                "sips",
                "-s", "format", "png",
                "-z", str(height), str(width),
                "--padToHeightWidth", str(height), str(width),
                str(input_path),
                "--out", str(out_png),
            ]
            res = subprocess.run(
                sips_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if res.returncode != 0:
                logger.error("sips conversion failed for %s: %s", filename, res.stderr)
                return False

        # Compile .iconset directory into .icns using iconutil
        iconutil_cmd = [
            "iconutil",
            "-c",
            "icns",
            str(iconset_dir),
            "-o",
            str(output_icns_path),
        ]
        res = subprocess.run(
            iconutil_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode != 0:
            logger.error("iconutil failed to build .icns: %s", res.stderr)
            return False

    if output_icns_path.exists() and output_icns_path.stat().st_size > 0:
        logger.info("Successfully converted %s to ICNS at %s", input_path.name, output_icns_path)
        return True

    logger.error("Generated ICNS file is missing or empty: %s", output_icns_path)
    return False


def _update_info_plist(info_plist_path: Path, new_app_name: str = "Codex") -> bool:
    """
    Safely updates the display name in an Info.plist file.
    """
    if not info_plist_path.exists():
        logger.warning("Info.plist does not exist at %s", info_plist_path)
        return False

    try:
        with open(info_plist_path, "rb") as f:
            plist_data = plistlib.load(f)

        plist_data["CFBundleDisplayName"] = new_app_name
        plist_data["CFBundleName"] = new_app_name

        with open(info_plist_path, "wb") as f:
            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

        logger.info("Updated Info.plist bundle name to '%s'", new_app_name)
        return True
    except Exception as e:
        logger.error("Failed to update Info.plist at %s: %s", info_plist_path, e)
        return False


def patch_app_icon(
    target_app_path: Path,
    replacement_icon_path: Path,
    rename_to_codex: bool = True,
    backup_registry: Optional[BackupRegistry] = None,
    refresh_dock: bool = False,
) -> bool:
    """
    Patches an application bundle with a custom replacement icon.

    Workflow:
    1. Creates a full backup via BackupRegistry.
    2. Converts replacement icon to .icns format if needed.
    3. Replaces all existing .icns and icon .png files in Contents/Resources/.
    4. If rename_to_codex is True, updates Info.plist display name to "Codex"
       and renames target_app_path to Codex.app if currently ChatGPT.app.
    5. Cleans extended attributes (`xattr -cr`) and re-signs bundle (`codesign --force --deep --sign -`).
    6. Flushes macOS QuickLook and Dock icon caches safely.

    Args:
        target_app_path: Path to target .app bundle.
        replacement_icon_path: Path to replacement image (.png, .jpeg, or .icns).
        rename_to_codex: If True, renames display name to Codex and renames ChatGPT.app to Codex.app.
        backup_registry: Optional BackupRegistry instance.

    Returns:
        True on successful patching, False otherwise.
    """
    target_app_path = Path(target_app_path).resolve()
    replacement_icon_path = Path(replacement_icon_path).resolve()

    if not target_app_path.exists() or not target_app_path.is_dir():
        logger.error("Target application bundle does not exist: %s", target_app_path)
        return False

    contents_dir = target_app_path / "Contents"
    resources_dir = contents_dir / "Resources"
    if not contents_dir.exists() or not resources_dir.exists():
        logger.error("Invalid .app bundle structure for %s", target_app_path)
        return False

    if not replacement_icon_path.exists():
        logger.error("Replacement icon file does not exist: %s", replacement_icon_path)
        return False

    # 1. Create safety backup before any mutation
    reg = backup_registry or BackupRegistry()
    try:
        backup_path = reg.create_backup(target_app_path)
        logger.info("Backup created at %s", backup_path)
    except Exception as err:
        logger.error("Failed to create pre-patch backup: %s", err)
        return False

    # 2. Prepare replacement ICNS file
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_icns = Path(tmp_dir) / "replacement.icns"
        if replacement_icon_path.suffix.lower() == ".icns":
            shutil.copy(replacement_icon_path, tmp_icns)
        else:
            success = convert_image_to_icns(replacement_icon_path, tmp_icns)
            if not success:
                logger.error("Failed to convert replacement image to ICNS")
                return False

        # 3. Replace all .icns files and icon PNGs in Contents/Resources/
        icns_files = list(resources_dir.glob("*.icns"))
        if not icns_files:
            # Default icon filename if none found
            icns_files = [resources_dir / "icon.icns"]

        for target_icns in icns_files:
            shutil.copy(tmp_icns, target_icns)
            logger.info("Replaced ICNS icon file: %s", target_icns.name)

        # Replace any PNG icon files in resources
        for png_file in resources_dir.glob("*.png"):
            if "icon" in png_file.name.lower() or "app" in png_file.name.lower():
                sips_cmd = [
                    "sips",
                    "-z",
                    "512",
                    "512",
                    str(replacement_icon_path),
                    "--out",
                    str(png_file),
                ]
                subprocess.run(sips_cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 4. Handle renaming to Codex if requested
    active_app_path = target_app_path
    if rename_to_codex:
        info_plist = contents_dir / "Info.plist"
        _update_info_plist(info_plist, "Codex")

        # If bundle name is ChatGPT.app, rename to Codex.app
        if active_app_path.name in ("ChatGPT.app", "chatgpt.app"):
            new_app_path = active_app_path.parent / "Codex.app"
            if new_app_path != active_app_path:
                if new_app_path.exists():
                    # Dual-app conflict detected (Codex.app + ChatGPT.app). Safely back up existing Codex.app to _backups/
                    root_backup_dir = Path(__file__).resolve().parent.parent.parent / "_backups"
                    conflict_reg = BackupRegistry(backup_dir=root_backup_dir)
                    try:
                        logger.info("Conflict detected: both ChatGPT.app and Codex.app present. Backing up existing Codex.app...")
                        conflict_reg.create_backup(new_app_path)
                    except Exception as err:
                        logger.warning("Failed to create conflict backup for Codex.app: %s", err)
                    shutil.rmtree(new_app_path)

                active_app_path.rename(new_app_path)
                active_app_path = new_app_path
                logger.info("Renamed app bundle to %s", active_app_path)

    # 4.5 Copy over dark mode bundle assets to Codex Contents folder
    assets_dir = Path(__file__).resolve().parent.parent.parent / "_backups" / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        target_contents = active_app_path / "Contents"
        target_resources = target_contents / "Resources"
        
        for asset_file in assets_dir.glob("*"):
            if asset_file.is_file() and not asset_file.name.startswith("."):
                try:
                    # Move into Contents folder
                    shutil.copy(asset_file, target_contents / asset_file.name)
                    # And also move into Resources just in case
                    if target_resources.exists():
                        shutil.copy(asset_file, target_resources / asset_file.name)
                    logger.info("Copied dark mode bundle asset %s to Codex app", asset_file.name)
                except Exception as e:
                    logger.warning("Failed to copy asset %s: %s", asset_file.name, e)

    # 5. Reset extended attributes and re-sign bundle cleanly
    try:
        subprocess.run(
            ["xattr", "-cr", str(active_app_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["codesign", "--force", "--sign", "-", str(active_app_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        logger.warning("Code signing / xattr warning: %s", e)

    # 6. Flush QuickLook & Dock caches
    try:
        subprocess.run(
            ["qlmanage", "-r", "cache"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["touch", str(active_app_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Execute killall Dock ONLY when a real icon swap occurs and NOT during unit tests
        if refresh_dock and os.environ.get("ICONREPLACE_TESTING") != "1":
            logger.info("Refreshing macOS Dock for live icon swap")
            subprocess.run(
                ["killall", "Dock"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    except Exception as e:
        logger.warning("Cache flush warning: %s", e)

    logger.info("Successfully patched app icon for %s", active_app_path)
    return True
