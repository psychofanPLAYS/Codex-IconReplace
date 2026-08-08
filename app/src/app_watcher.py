"""
App Update Watcher for IconReplace.

Monitors /Applications and ~/Applications for ChatGPT.app appearances or modifications
(indicating Codex updated itself and reset its bundle name and icon). When detected,
automatically applies dark mode icon patching and sends native macOS notifications.

Auditing & Safety Notes:
- Uses event-driven file system watching via watchdog (FSEventsObserver on macOS).
- Receives native OS kernel notifications on /Applications events instead of polling.
- Zero CPU usage when /Applications is quiet.
- Uses native osascript notification banners for user updates.
- Fully configurable with auto-repair toggles and customizable target search paths.
"""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

try:
    from watchdog.observers.fsevents import FSEventsObserver as Observer
except ImportError:
    from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backup_registry import BackupRegistry
from icon_engine import patch_app_icon
from launchd_manager import LaunchAgentManager

logger = logging.getLogger("IconReplace.AppWatcher")


import json


def send_macos_notification(title: str, message: str) -> bool:
    """
    Sends a native macOS desktop banner notification using osascript safely formatted via JSON.

    Args:
        title: Title of the banner notification.
        message: Content body message of the notification.

    Returns:
        True if osascript executed successfully, False otherwise.
    """
    safe_title = json.dumps(title)
    safe_message = json.dumps(message)
    script = f"display notification {safe_message} with title {safe_title}"
    cmd = ["osascript", "-e", script]

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            logger.info("Sent macOS notification: %s - %s", title, message)
            return True
        logger.warning("osascript notification returned code %d: %s", res.returncode, res.stderr)
    except Exception as err:
        logger.warning("Failed to dispatch osascript notification: %s", err)
    return False


def is_process_running(process_names: Optional[List[str]] = None) -> bool:
    """
    Checks if ChatGPT.app (com.openai.chat) is currently active on macOS.

    If ICONREPLACE_TESTING=1, returns True if ICONREPLACE_TEST_PROCESS_RUNNING environment
    variable is set to "1", "true", or "yes".
    """
    if os.environ.get("ICONREPLACE_TESTING") == "1":
        val = os.environ.get("ICONREPLACE_TEST_PROCESS_RUNNING", "0").lower()
        return val in ("1", "true", "yes")

    # 1. Check using lsappinfo for bundle ID com.openai.chat
    try:
        res = subprocess.run(
            ["lsappinfo", "list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode == 0 and "com.openai.chat" in res.stdout:
            return True
    except Exception as err:
        logger.debug("lsappinfo check failed: %s", err)

    # 2. Check using pgrep for ChatGPT binary
    target_names = process_names or ["ChatGPT", "chatgpt"]
    for name in target_names:
        try:
            res = subprocess.run(
                ["pgrep", "-x", name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if res.returncode == 0 and res.stdout.strip():
                return True
        except Exception as err:
            logger.debug("pgrep check failed for process %s: %s", name, err)

    return False



class _AppUpdateEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler that triggers check_now on AppUpdateWatcher whenever
    filesystem events occur in watched directories.
    """

    def __init__(self, watcher: "AppUpdateWatcher") -> None:
        super().__init__()
        self.watcher = watcher

    def on_any_event(self, event) -> None:
        try:
            self.watcher.check_now()
        except Exception as err:
            logger.error("Error handling watchdog filesystem event: %s", err)


class AppUpdateWatcher:
    """
    Background directory monitor that watches for ChatGPT.app appearances or updates
    via kernel filesystem events and automatically restores Codex icon & bundle branding.
    """

    STATUS_CODEX_INSTALLED = "Codex.app Installed"
    STATUS_NEEDS_PATCHING = "ChatGPT.app Detected (Needs Patching)"
    STATUS_NOT_FOUND = "Not Found in /Applications"

    def __init__(
        self,
        watch_dirs: Optional[List[Path]] = None,
        replacement_icon_path: Optional[Path] = None,
        auto_repair_enabled: bool = True,
        notifications_enabled: bool = True,
        poll_interval: float = 3.0,
        backup_registry: Optional[BackupRegistry] = None,
        on_status_change: Optional[Callable[[str, Optional[Path]], None]] = None,
    ) -> None:
        """
        Initializes the AppUpdateWatcher.

        Args:
            watch_dirs: Custom directories to monitor. Defaults to [/Applications, ~/Applications].
            replacement_icon_path: Path to custom .png / .icns file for auto-repair.
            auto_repair_enabled: If True, automatically patches app when ChatGPT.app is detected.
            notifications_enabled: If True, dispatches macOS banner notifications on repair.
            poll_interval: Kept for backwards-compatible API signature.
            backup_registry: Optional BackupRegistry instance.
            on_status_change: Optional callback function triggered when app status changes.
        """
        if watch_dirs is None:
            self.watch_dirs = [
                Path("/Applications"),
                Path.home() / "Applications",
            ]
        else:
            self.watch_dirs = [Path(d).expanduser().resolve() for d in watch_dirs]

        self.replacement_icon_path = (
            Path(replacement_icon_path).resolve()
            if replacement_icon_path
            else None
        )
        self.auto_repair_enabled = auto_repair_enabled
        self.notifications_enabled = notifications_enabled
        self.poll_interval = poll_interval
        self.backup_registry = backup_registry or BackupRegistry()
        self.on_status_change = on_status_change

        self._observer: Optional[Observer] = None
        self._event_handler: Optional[_AppUpdateEventHandler] = None
        self._lock = threading.Lock()
        self._last_seen_mtime: float = 0.0
        self._last_status: str = ""

    @property
    def is_running(self) -> bool:
        """Returns True if the watchdog background observer is currently active."""
        return self._observer is not None and self._observer.is_alive()

    def start(self) -> None:
        """Starts the watchdog filesystem observer if not already running."""
        if self.is_running:
            logger.info("AppUpdateWatcher is already running.")
            return

        self._observer = Observer()
        self._event_handler = _AppUpdateEventHandler(self)

        scheduled_count = 0
        for search_dir in self.watch_dirs:
            if search_dir.exists() and search_dir.is_dir():
                self._observer.schedule(self._event_handler, str(search_dir), recursive=False)
                scheduled_count += 1

        self._observer.start()
        logger.info("AppUpdateWatcher watchdog event-driven observer started watching %d directories.", scheduled_count)

        # Immediate initial status check & auto-repair trigger upon start
        self.check_now()

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stops the background watchdog observer.

        Args:
            timeout: Maximum seconds to wait for observer thread termination.
        """
        if not self.is_running:
            return

        logger.info("Stopping AppUpdateWatcher watchdog observer...")
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=timeout)
            self._observer = None
        logger.info("AppUpdateWatcher watchdog observer stopped.")

    def get_codex_status(self) -> Tuple[str, Optional[Path]]:
        """
        Scans monitored directories to determine current Codex / ChatGPT app status.

        Returns:
            Tuple of (status_string, active_app_path).
        """
        # 1. Check for ChatGPT.app (needs patching)
        for search_dir in self.watch_dirs:
            if not search_dir.exists():
                continue
            chatgpt_app = search_dir / "ChatGPT.app"
            if chatgpt_app.exists() and chatgpt_app.is_dir():
                return (self.STATUS_NEEDS_PATCHING, chatgpt_app)

        # 2. Check for Codex.app (already patched / installed)
        for search_dir in self.watch_dirs:
            if not search_dir.exists():
                continue
            codex_app = search_dir / "Codex.app"
            if codex_app.exists() and codex_app.is_dir():
                return (self.STATUS_CODEX_INSTALLED, codex_app)

        # 3. Not found
        return (self.STATUS_NOT_FOUND, None)

    def check_now(self) -> Tuple[str, Optional[Path]]:
        """
        Performs an immediate check and triggers auto-repair if ChatGPT.app is detected
        and auto_repair_enabled is True.

        Returns:
            Tuple of (current_status, active_app_path).
        """
        with self._lock:
            status, app_path = self.get_codex_status()

            if status != self._last_status:
                self._last_status = status
                if self.on_status_change:
                    try:
                        self.on_status_change(status, app_path)
                    except Exception as err:
                        logger.error("Error in on_status_change callback: %s", err)

            if status == self.STATUS_NEEDS_PATCHING and app_path and self.auto_repair_enabled:
                # Check if this bundle was modified since last repair
                try:
                    info_plist = app_path / "Contents" / "Info.plist"
                    mtime = info_plist.stat().st_mtime if info_plist.exists() else app_path.stat().st_mtime
                except Exception:
                    mtime = time.time()

                if mtime > self._last_seen_mtime:
                    self._last_seen_mtime = mtime
                    logger.info("ChatGPT.app detected at %s. Triggering auto-repair...", app_path)
                    self._execute_repair(app_path)
                    # Re-check status after repair
                    status, app_path = self.get_codex_status()
                    self._last_status = status
                    if self.on_status_change:
                        try:
                            self.on_status_change(status, app_path)
                        except Exception as err:
                            logger.error("Error in on_status_change callback: %s", err)

            return (status, app_path)

    def _execute_repair(self, target_app_path: Path) -> bool:
        """
        Executes icon repair on target ChatGPT.app bundle and triggers desktop notification.

        Args:
            target_app_path: Path to ChatGPT.app.

        Returns:
            True on successful repair, False otherwise.
        """
        # Use provided replacement icon or system icon default fallback
        icon_to_use = self.replacement_icon_path
        if icon_to_use is None or not icon_to_use.exists():
            # Fallback to system application icon or asset
            icon_to_use = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")

        success = patch_app_icon(
            target_app_path=target_app_path,
            replacement_icon_path=icon_to_use,
            rename_to_codex=True,
            backup_registry=self.backup_registry,
        )

        if success:
            logger.info("Auto-repair completed for %s", target_app_path)
            if self.notifications_enabled:
                send_macos_notification(
                    title="IconReplace",
                    message="Codex updated — dark icon auto-applied!",
                )
            return True

        logger.error("Auto-repair failed for %s", target_app_path)
        return False

