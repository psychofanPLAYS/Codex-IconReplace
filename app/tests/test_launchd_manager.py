"""
Unit tests for LaunchAgentManager in src/launchd_manager.py and --auto-repair-delayed in main.py.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src/ to sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from launchd_manager import LaunchAgentManager
from main import run_auto_repair_delayed


class TestLaunchAgentManager(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.plist_path = self.tmp_path / "com.antigravity.iconreplace.plist"
        self.mgr = LaunchAgentManager(plist_path=self.plist_path)

        # Force ICONREPLACE_TESTING=1 for test isolation safety
        self._orig_testing = os.environ.get("ICONREPLACE_TESTING")
        os.environ["ICONREPLACE_TESTING"] = "1"

    def tearDown(self):
        if self._orig_testing is not None:
            os.environ["ICONREPLACE_TESTING"] = self._orig_testing
        else:
            os.environ.pop("ICONREPLACE_TESTING", None)
        self.tmp_dir.cleanup()

    def test_install_agent_creates_plist_with_watchpaths(self):
        exec_path = Path("/usr/local/bin/iconreplace")
        success = self.mgr.install_agent(exec_path)
        self.assertTrue(success)
        self.assertTrue(self.plist_path.exists())

        with open(self.plist_path, "rb") as f:
            data = plistlib.load(f)

        self.assertEqual(data.get("Label"), "com.antigravity.iconreplace")
        self.assertEqual(data.get("ProgramArguments"), [str(exec_path), "--auto-repair-delayed"])

        watch_paths = data.get("WatchPaths", [])
        self.assertIn("/Applications/ChatGPT.app", watch_paths)
        self.assertIn(str(Path.home() / "Applications" / "ChatGPT.app"), watch_paths)

    def test_install_agent_with_python_script(self):
        script_path = self.tmp_path / "main.py"
        script_path.touch()
        success = self.mgr.install_agent(script_path)
        self.assertTrue(success)

        with open(self.plist_path, "rb") as f:
            data = plistlib.load(f)

        expected_args = [sys.executable, str(script_path.resolve()), "--auto-repair-delayed"]
        self.assertEqual(data.get("ProgramArguments"), expected_args)

    def test_is_agent_installed(self):
        self.assertFalse(self.mgr.is_agent_installed())
        self.mgr.install_agent()
        self.assertTrue(self.mgr.is_agent_installed())

    def test_uninstall_agent_removes_plist(self):
        self.mgr.install_agent()
        self.assertTrue(self.plist_path.exists())

        success = self.mgr.uninstall_agent()
        self.assertTrue(success)
        self.assertFalse(self.plist_path.exists())
        self.assertFalse(self.mgr.is_agent_installed())

    @patch("subprocess.run")
    def test_launchctl_mocked_out_when_testing(self, mock_run):
        """Verifies that launchctl subshell commands are completely mocked out when ICONREPLACE_TESTING=1."""
        self.mgr.install_agent()
        mock_run.assert_not_called()

        self.mgr.is_agent_installed()
        mock_run.assert_not_called()

        self.mgr.uninstall_agent()
        mock_run.assert_not_called()

    @patch("main.send_macos_notification")
    @patch("main.patch_app_icon")
    def test_run_auto_repair_delayed(self, mock_patch, mock_notify):
        """Verifies CLI --auto-repair-delayed execution logic."""
        mock_patch.return_value = True

        # Setup mock ChatGPT.app inside temp directory
        apps_dir = self.tmp_path / "Applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        chatgpt_app = apps_dir / "ChatGPT.app"
        chatgpt_app.mkdir(parents=True, exist_ok=True)

        os.environ["ICONREPLACE_TEST_APP_PATH"] = str(chatgpt_app)
        try:
            with self.assertRaises(SystemExit) as cm:
                run_auto_repair_delayed()

            self.assertEqual(cm.exception.code, 0)
            mock_patch.assert_called_once()
            self.assertEqual(mock_notify.call_count, 2)
            mock_notify.assert_has_calls([
                unittest.mock.call(
                    title="IconReplace ⚡",
                    message="Pesky ChatGPT update revert detected! Dark mode icon swap commencing in T-2 minutes. Hang tight!",
                ),
                unittest.mock.call(
                    title="IconReplace",
                    message="Codex updated — dark mode icon & branding re-applied successfully!",
                ),
            ])
        finally:
            os.environ.pop("ICONREPLACE_TEST_APP_PATH", None)


if __name__ == "__main__":
    unittest.main()
