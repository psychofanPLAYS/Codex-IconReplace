"""
Unit tests for BackupRegistry.
"""

import json
import os
import plistlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add src/ to python path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backup_registry import BackupRegistry


class TestBackupRegistry(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.backup_root = self.tmp_path / "backups"
        self.registry = BackupRegistry(backup_dir=self.backup_root)

        # Create a dummy app bundle: ChatGPT.app
        self.app_dir = self.tmp_path / "ChatGPT.app"
        self.contents_dir = self.app_dir / "Contents"
        self.resources_dir = self.contents_dir / "Resources"
        self.resources_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy Info.plist
        self.info_plist = self.contents_dir / "Info.plist"
        plist_data = {
            "CFBundleDisplayName": "ChatGPT",
            "CFBundleName": "ChatGPT",
            "CFBundleIdentifier": "com.openai.chatgpt",
        }
        with open(self.info_plist, "wb") as f:
            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

        # Create dummy icon file
        self.dummy_icon = self.resources_dir / "icon.icns"
        self.dummy_icon.write_bytes(b"ORIGINAL_ICNS_HEADER_DATA")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_create_backup_success(self):
        backup_path = self.registry.create_backup(self.app_dir)
        self.assertTrue(backup_path.exists())

        # Check metadata
        meta_file = backup_path / "metadata.json"
        self.assertTrue(meta_file.exists())
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["original_app_name"], "ChatGPT")
        self.assertEqual(meta["original_app_path"], str(self.app_dir.resolve()))

        # Check copied files
        self.assertTrue((backup_path / "Info.plist").exists())
        self.assertTrue((backup_path / "Resources" / "icon.icns").exists())

    def test_list_backups(self):
        self.registry.create_backup(self.app_dir)
        backups = self.registry.list_backups("ChatGPT")
        self.assertEqual(len(backups), 1)

    def test_restore_latest_backup(self):
        # 1. Backup original app
        self.registry.create_backup(self.app_dir)

        # 2. Modify app (simulate patch)
        (self.resources_dir / "icon.icns").write_bytes(b"MODIFIED_ICNS_DATA")
        with open(self.info_plist, "wb") as f:
            plistlib.dump({"CFBundleDisplayName": "Codex"}, f, fmt=plistlib.FMT_BINARY)

        # Rename to Codex.app
        codex_app_dir = self.tmp_path / "Codex.app"
        self.app_dir.rename(codex_app_dir)

        # 3. Restore backup
        success = self.registry.restore_latest_backup(
            target_app_name="Codex", target_app_dir=codex_app_dir
        )
        self.assertTrue(success)

        # Check original file content restored
        restored_app = self.tmp_path / "ChatGPT.app"
        self.assertTrue(restored_app.exists())
        restored_icon = restored_app / "Contents" / "Resources" / "icon.icns"
        self.assertEqual(restored_icon.read_bytes(), b"ORIGINAL_ICNS_HEADER_DATA")

        with open(restored_app / "Contents" / "Info.plist", "rb") as f:
            data = plistlib.load(f)
        self.assertEqual(data["CFBundleDisplayName"], "ChatGPT")


if __name__ == "__main__":
    unittest.main()
