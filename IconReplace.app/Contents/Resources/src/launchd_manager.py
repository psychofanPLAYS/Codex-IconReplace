"""
LaunchAgent Manager for IconReplace auto-repair mechanism.

Manages installation, uninstallation, and status of macOS launchd user agent plists.
"""

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("IconReplace.LaunchAgentManager")

DEFAULT_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.antigravity.iconreplace.plist"


class LaunchAgentManager:
    """
    Manages launchd LaunchAgent for 2-minute delayed auto-repair of Codex / ChatGPT.app icons.
    """

    def __init__(self, plist_path: Optional[Path] = None) -> None:
        """
        Initializes LaunchAgentManager.

        Args:
            plist_path: Custom plist location (defaults to ~/Library/LaunchAgents/com.antigravity.iconreplace.plist).
        """
        self.plist_path = Path(plist_path).expanduser().resolve() if plist_path else DEFAULT_PLIST_PATH

    @property
    def is_testing(self) -> bool:
        """Returns True if test isolation mode ICONREPLACE_TESTING=1 is enabled."""
        return os.environ.get("ICONREPLACE_TESTING") == "1"

    def install_agent(self, app_executable_path: Optional[Path] = None) -> bool:
        """
        Writes LaunchAgent plist with WatchPaths pointing to ChatGPT.app locations and
        loads it into launchd using launchctl load.

        Args:
            app_executable_path: Executable or script path to invoke. Defaults to sys.executable.

        Returns:
            True on successful installation, False on failure.
        """
        try:
            if app_executable_path is None:
                app_executable_path = Path(sys.executable)
            else:
                app_executable_path = Path(app_executable_path).resolve()

            # Format ProgramArguments
            if app_executable_path.suffix == ".py":
                prog_args = [sys.executable, str(app_executable_path), "--auto-repair-delayed"]
            else:
                prog_args = [str(app_executable_path), "--auto-repair-delayed"]

            watch_paths = [
                "/Applications/ChatGPT.app",
                str(Path.home() / "Applications" / "ChatGPT.app"),
            ]

            plist_data = {
                "Label": "com.antigravity.iconreplace",
                "ProgramArguments": prog_args,
                "WatchPaths": watch_paths,
            }

            self.plist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.plist_path, "wb") as f:
                plistlib.dump(plist_data, f, fmt=plistlib.FMT_XML)

            logger.info("Wrote LaunchAgent plist to %s", self.plist_path)

            if self.is_testing:
                logger.info("[TESTING MODE] Mocking out launchctl load")
                return True

            res = subprocess.run(
                ["launchctl", "load", str(self.plist_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if res.returncode == 0:
                logger.info("Loaded launchd agent successfully")
                return True
            else:
                logger.error("launchctl load failed with exit code %d: %s", res.returncode, res.stderr)
                return False
        except Exception as err:
            logger.error("Failed to install launch agent: %s", err)
            return False

    def uninstall_agent(self) -> bool:
        """
        Unloads LaunchAgent via launchctl unload and deletes the plist file.

        Returns:
            True on success, False otherwise.
        """
        try:
            if not self.is_testing and self.plist_path.exists():
                subprocess.run(
                    ["launchctl", "unload", str(self.plist_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                logger.info("Unloaded launchd agent %s", self.plist_path)

            if self.plist_path.exists():
                self.plist_path.unlink()
                logger.info("Removed LaunchAgent plist %s", self.plist_path)

            return True
        except Exception as err:
            logger.error("Failed to uninstall launch agent: %s", err)
            return False

    def is_agent_installed(self) -> bool:
        """
        Checks if plist exists and is loaded in launchd.

        Returns:
            True if plist exists and is loaded, False otherwise.
        """
        if not self.plist_path.exists():
            return False

        if self.is_testing:
            return True

        try:
            res = subprocess.run(
                ["launchctl", "list", "com.antigravity.iconreplace"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return res.returncode == 0
        except Exception as err:
            logger.warning("Error checking launchctl list: %s", err)
            return False
