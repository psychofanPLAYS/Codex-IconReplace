"""
Unit tests for IconEngine.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure unit tests run completely isolated from live OS system state
os.environ["ICONREPLACE_TESTING"] = "1"

# Add src/ to python path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backup_registry import BackupRegistry
from icon_engine import convert_image_to_icns, patch_app_icon


class TestIconEngine(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        # Generate a real test PNG image using macOS sips command from system icon
        sys_icns = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")
        self.input_png = self.tmp_path / "test_icon.png"
        
        sips_cmd = [
            "sips",
            "-s",
            "format",
            "png",
            "-z",
            "512",
            "512",
            str(sys_icns),
            "--out",
            str(self.input_png),
        ]
        res = subprocess.run(sips_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            self.fail(f"Failed to generate test PNG image: {res.stderr}")
            
        self.test_profile_dir = self.tmp_path / "test_profile"
        self.test_profile_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.input_png, self.test_profile_dir / "icon-codex-light.png")

        # Setup mock app bundle
        self.app_dir = self.tmp_path / "ChatGPT.app"
        self.contents_dir = self.app_dir / "Contents"
        self.resources_dir = self.contents_dir / "Resources"
        self.resources_dir.mkdir(parents=True, exist_ok=True)

        self.info_plist = self.contents_dir / "Info.plist"
        plist_data = {
            "CFBundleDisplayName": "ChatGPT",
            "CFBundleName": "ChatGPT",
            "CFBundleIdentifier": "com.openai.chatgpt",
        }
        with open(self.info_plist, "wb") as f:
            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

        self.stock_icon = self.resources_dir / "icon.icns"
        shutil.copy(sys_icns, self.stock_icon)

        # Setup backup registry with temporary location
        self.backup_root = self.tmp_path / "backups"
        self.backup_registry = BackupRegistry(backup_dir=self.backup_root)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_convert_image_to_icns(self):
        output_icns = self.tmp_path / "output.icns"
        success = convert_image_to_icns(self.input_png, output_icns)
        self.assertTrue(success)
        self.assertTrue(output_icns.exists())
        self.assertGreater(output_icns.stat().st_size, 0)

    def test_patch_app_icon(self):
        success = patch_app_icon(
            target_app_path=self.app_dir,
            profile_dir=self.test_profile_dir,
            rename_to_codex=True,
            backup_registry=self.backup_registry,
        )
        self.assertTrue(success)

        # Check backup was registered
        backups = self.backup_registry.list_backups("ChatGPT")
        self.assertEqual(len(backups), 1)

        # Check bundle was renamed to Codex.app
        codex_app = self.tmp_path / "Codex.app"
        self.assertTrue(codex_app.exists())

        # Check Info.plist was updated
        with open(codex_app / "Contents" / "Info.plist", "rb") as f:
            plist_data = plistlib.load(f)
        self.assertEqual(plist_data["CFBundleDisplayName"], "Codex")

        # Check icon file exists
        patched_icon = codex_app / "Contents" / "Resources" / "icon.icns"
        self.assertTrue(patched_icon.exists())
        self.assertGreater(patched_icon.stat().st_size, 0)

    def test_patch_app_icon_without_rename(self):
        success = patch_app_icon(
            target_app_path=self.app_dir,
            profile_dir=self.test_profile_dir,
            rename_to_codex=False,
            backup_registry=self.backup_registry,
        )
        self.assertTrue(success)
        self.assertTrue(self.app_dir.exists())

        with open(self.app_dir / "Contents" / "Info.plist", "rb") as f:
            plist_data = plistlib.load(f)
        self.assertEqual(plist_data["CFBundleDisplayName"], "ChatGPT")


if __name__ == "__main__":
    unittest.main()
