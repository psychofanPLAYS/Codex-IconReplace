"""
Unit tests for AppUpdateWatcher in src/app_watcher.py.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src/ to python path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app_watcher import AppUpdateWatcher, is_process_running, send_macos_notification
from backup_registry import BackupRegistry
from main import run_auto_repair_delayed


class TestAppUpdateWatcher(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        # Setup mock applications directory
        self.apps_dir = (self.tmp_path / "Applications").resolve()
        self.apps_dir.mkdir(parents=True, exist_ok=True)

        # Generate a test icon image
        sys_icns = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")
        self.test_profile_dir = self.tmp_path / "test_profile"
        self.test_profile_dir.mkdir(parents=True, exist_ok=True)
        self.test_png = self.test_profile_dir / "icon-codex-light.png"
        sips_cmd = [
            "sips",
            "-s",
            "format",
            "png",
            "-z",
            "128",
            "128",
            str(sys_icns),
            "--out",
            str(self.test_png),
        ]
        subprocess.run(sips_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Setup backup registry
        self.backup_root = self.tmp_path / "backups"
        self.backup_registry = BackupRegistry(backup_dir=self.backup_root)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_mock_chatgpt_app(self) -> Path:
        """Helper to construct a mock ChatGPT.app bundle structure."""
        app_dir = self.apps_dir / "ChatGPT.app"
        contents_dir = app_dir / "Contents"
        resources_dir = contents_dir / "Resources"
        resources_dir.mkdir(parents=True, exist_ok=True)

        info_plist = contents_dir / "Info.plist"
        plist_data = {
            "CFBundleDisplayName": "ChatGPT",
            "CFBundleName": "ChatGPT",
            "CFBundleIdentifier": "com.openai.chatgpt",
        }
        with open(info_plist, "wb") as f:
            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

        shutil.copy(self.test_png, resources_dir / "icon.icns")
        return app_dir

    def _create_mock_codex_app(self) -> Path:
        """Helper to construct a mock Codex.app bundle structure."""
        app_dir = self.apps_dir / "Codex.app"
        contents_dir = app_dir / "Contents"
        resources_dir = contents_dir / "Resources"
        resources_dir.mkdir(parents=True, exist_ok=True)

        info_plist = contents_dir / "Info.plist"
        plist_data = {
            "CFBundleDisplayName": "Codex",
            "CFBundleName": "Codex",
            "CFBundleIdentifier": "com.openai.chatgpt",
        }
        with open(info_plist, "wb") as f:
            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

        shutil.copy(self.test_png, resources_dir / "icon.icns")
        return app_dir

    def test_watcher_lifecycle(self):
        watcher = AppUpdateWatcher(
            watch_dirs=[self.apps_dir],
            poll_interval=0.1,
            auto_repair_enabled=False,
        )
        self.assertFalse(watcher.is_running)

        watcher.start()
        self.assertTrue(watcher.is_running)

        # Starting again should be idempotent
        watcher.start()
        self.assertTrue(watcher.is_running)

        watcher.stop()
        self.assertFalse(watcher.is_running)

    def test_get_codex_status_not_found(self):
        watcher = AppUpdateWatcher(watch_dirs=[self.apps_dir])
        status, app_path = watcher.get_codex_status()
        self.assertEqual(status, AppUpdateWatcher.STATUS_NOT_FOUND)
        self.assertIsNone(app_path)

    def test_get_codex_status_needs_patching(self):
        self._create_mock_chatgpt_app()
        watcher = AppUpdateWatcher(watch_dirs=[self.apps_dir])
        status, app_path = watcher.get_codex_status()
        self.assertEqual(status, AppUpdateWatcher.STATUS_NEEDS_PATCHING)
        self.assertEqual(app_path, self.apps_dir / "ChatGPT.app")

    def test_get_codex_status_codex_installed(self):
        self._create_mock_codex_app()
        watcher = AppUpdateWatcher(watch_dirs=[self.apps_dir])
        status, app_path = watcher.get_codex_status()
        self.assertEqual(status, AppUpdateWatcher.STATUS_CODEX_INSTALLED)
        self.assertEqual(app_path, self.apps_dir / "Codex.app")

    @patch("app_watcher.send_macos_notification")
    def test_auto_repair_on_check_now(self, mock_notify):
        mock_notify.return_value = True
        chatgpt_app = self._create_mock_chatgpt_app()

        callback_mock = MagicMock()
        watcher = AppUpdateWatcher(
            watch_dirs=[self.apps_dir],
            profile_dir=self.test_profile_dir,
            auto_repair_enabled=True,
            notifications_enabled=True,
            backup_registry=self.backup_registry,
            on_status_change=callback_mock,
        )

        status, active_path = watcher.check_now()
        # Should repair ChatGPT.app into Codex.app
        self.assertEqual(status, AppUpdateWatcher.STATUS_CODEX_INSTALLED)
        self.assertEqual(active_path, self.apps_dir / "Codex.app")
        self.assertFalse(chatgpt_app.exists())
        self.assertTrue((self.apps_dir / "Codex.app").exists())

        mock_notify.assert_called_once_with(
            title="IconReplace",
            message="Codex updated — dark icon auto-applied!",
        )
        self.assertTrue(callback_mock.called)

    @patch("app_watcher.AppUpdateWatcher._execute_repair")
    def test_auto_repair_idle_when_codex_installed(self, mock_repair):
        """Verifies that when Codex.app exists, check_now auto-repair stays idle and does NOT execute repair sequence."""
        self._create_mock_codex_app()
        watcher = AppUpdateWatcher(
            watch_dirs=[self.apps_dir],
            auto_repair_enabled=True,
        )
        status, active_path = watcher.check_now()
        self.assertEqual(status, AppUpdateWatcher.STATUS_CODEX_INSTALLED)
        self.assertEqual(active_path, self.apps_dir / "Codex.app")
        mock_repair.assert_not_called()

    def test_send_macos_notification_executes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            res = send_macos_notification("Test Title", "Test Message")
            self.assertTrue(res)
            mock_run.assert_called_once()

    @patch("app_watcher.send_macos_notification")
    def test_watchdog_event_driven_auto_repair(self, mock_notify):
        """Verifies watchdog receives filesystem events and triggers auto-repair automatically when ChatGPT.app appears."""
        mock_notify.return_value = True
        watcher = AppUpdateWatcher(
            watch_dirs=[self.apps_dir],
            profile_dir=self.test_profile_dir,
            auto_repair_enabled=True,
            notifications_enabled=True,
            backup_registry=self.backup_registry,
        )
        watcher.start()
        self.assertTrue(watcher.is_running)

        try:
            # Create mock ChatGPT.app while watcher is active
            self._create_mock_chatgpt_app()

            # Wait briefly for kernel filesystem event to propagate to watchdog
            max_wait = 2.0
            start_time = time.time()
            repaired = False
            while time.time() - start_time < max_wait:
                status, active_path = watcher.get_codex_status()
                if status == AppUpdateWatcher.STATUS_CODEX_INSTALLED:
                    repaired = True
                    break
                time.sleep(0.05)

            self.assertTrue(repaired, "Watchdog failed to auto-repair ChatGPT.app via filesystem event")
        finally:
            watcher.stop()
        self.assertFalse(watcher.is_running)

    def test_is_process_running_testing_env(self):
        """Verifies is_process_running behavior under ICONREPLACE_TESTING=1 env overrides."""
        os.environ["ICONREPLACE_TESTING"] = "1"

        os.environ["ICONREPLACE_TEST_PROCESS_RUNNING"] = "1"
        self.assertTrue(is_process_running(["ChatGPT", "Codex"]))

        os.environ["ICONREPLACE_TEST_PROCESS_RUNNING"] = "true"
        self.assertTrue(is_process_running(["ChatGPT"]))

        os.environ["ICONREPLACE_TEST_PROCESS_RUNNING"] = "0"
        self.assertFalse(is_process_running(["ChatGPT"]))

        os.environ.pop("ICONREPLACE_TEST_PROCESS_RUNNING", None)
        self.assertFalse(is_process_running(["ChatGPT"]))

    @patch("subprocess.run")
    def test_is_process_running_real_subprocess(self, mock_run):
        """Verifies is_process_running invokes pgrep / ps when ICONREPLACE_TESTING is not 1."""
        os.environ["ICONREPLACE_TESTING"] = "0"
        try:
            # Test pgrep match
            mock_run.return_value = MagicMock(returncode=0, stdout="5678\n")
            self.assertTrue(is_process_running(["ChatGPT"]))
            mock_run.assert_called_with(
                ["pgrep", "-x", "ChatGPT"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Test pgrep no match and ps fallback match
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),
                MagicMock(returncode=0, stdout="/Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n"),
            ]
            self.assertTrue(is_process_running(["ChatGPT"]))

            # Test no match on either pgrep or ps
            mock_run.side_effect = None
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            self.assertFalse(is_process_running(["ChatGPT"]))
        finally:
            os.environ["ICONREPLACE_TESTING"] = "1"

    @patch("main.send_macos_notification")
    @patch("main.patch_app_icon")
    def test_auto_repair_delayed_process_wait(self, mock_patch, mock_notify):
        """Verifies run_auto_repair_delayed waits while process is running and dispatches notifications."""
        mock_patch.return_value = True

        chatgpt_app = self.apps_dir / "ChatGPT.app"
        chatgpt_app.mkdir(parents=True, exist_ok=True)
        os.environ["ICONREPLACE_TEST_APP_PATH"] = str(chatgpt_app)
        os.environ["ICONREPLACE_TESTING"] = "1"

        # Simulate process running on first call, then stopping on second call
        running_states = [True, False]
        def mock_is_running(procs):
            if running_states:
                return running_states.pop(0)
            return False

        try:
            with patch("main.is_process_running", side_effect=mock_is_running):
                with self.assertRaises(SystemExit) as cm:
                    run_auto_repair_delayed()

                self.assertEqual(cm.exception.code, 0)
                mock_patch.assert_called_once()

                # Verify 3 notifications were sent: initial notification + open notification + completion notification
                self.assertEqual(mock_notify.call_count, 3)
                mock_notify.assert_has_calls([
                    unittest.mock.call(
                        title="IconReplace ⚡",
                        message="Pesky ChatGPT update revert detected! Dark mode icon swap commencing in T-2 minutes. Hang tight!",
                    ),
                    unittest.mock.call(
                        title="IconReplace",
                        message="Codex is currently open. Dark mode icon & rename will apply automatically once the app is closed.",
                    ),
                    unittest.mock.call(
                        title="IconReplace",
                        message="Codex updated — dark mode icon & branding re-applied successfully!",
                    )
                ])
        finally:
            os.environ.pop("ICONREPLACE_TEST_APP_PATH", None)


if __name__ == "__main__":
    unittest.main()


