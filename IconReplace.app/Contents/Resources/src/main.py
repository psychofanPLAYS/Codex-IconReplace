"""
Main entry point for IconReplace application.

Provides CLI options for GUI mode, non-interactive CLI patching/restoration,
and background LaunchAgent daemon execution.

Usage:
    python3 src/main.py                  # Launch full GUI
    python3 src/main.py --background     # Run background watcher daemon
    python3 src/main.py --patch          # Non-interactive CLI icon patch
    python3 src/main.py --restore        # Non-interactive CLI backup restore
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add src/ directory to sys.path
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app_watcher import AppUpdateWatcher, is_process_running, send_macos_notification
from backup_registry import BackupRegistry
from gui import IconReplaceGUI
from icon_engine import patch_app_icon


def setup_logging(verbose: bool = False) -> None:
    """Configures application-wide logging formats and log levels."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=log_level, format=log_format)


def run_auto_repair_delayed() -> None:
    """Executes 2-minute delayed auto-repair mechanism when triggered by launchd WatchPaths."""
    logging.info("Executing 2-minute delayed auto-repair mechanism...")
    
    # Edgy/quirky one-time notification when T-2min countdown starts
    send_macos_notification(
        title="IconReplace ⚡",
        message="Pesky ChatGPT update revert detected! Dark mode icon swap commencing in T-2 minutes. Hang tight!",
    )

    delay = 0.1 if os.environ.get("ICONREPLACE_TESTING") == "1" else 120
    time.sleep(delay)

    target_processes = ["ChatGPT", "Codex", "chatgpt", "codex"]
    if is_process_running(target_processes):
        send_macos_notification(
            title="IconReplace",
            message="Codex is currently open. Dark mode icon & rename will apply automatically once the app is closed.",
        )
        sleep_interval = 0.05 if os.environ.get("ICONREPLACE_TESTING") == "1" else 2
        while is_process_running(target_processes):
            time.sleep(sleep_interval)

    env_app = os.environ.get("ICONREPLACE_TEST_APP_PATH")
    chatgpt_app = Path("/Applications/ChatGPT.app")
    user_chatgpt_app = Path.home() / "Applications" / "ChatGPT.app"

    target_app = None
    if env_app and Path(env_app).exists():
        target_app = Path(env_app)
    elif chatgpt_app.exists() and chatgpt_app.is_dir():
        target_app = chatgpt_app
    elif user_chatgpt_app.exists() and user_chatgpt_app.is_dir():
        target_app = user_chatgpt_app

    if target_app:
        sys_icon = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")
        patch_app_icon(
            target_app_path=target_app,
            replacement_icon_path=sys_icon,
            rename_to_codex=True,
        )
        send_macos_notification(
            title="IconReplace",
            message="Codex updated — dark mode icon & branding re-applied successfully!",
        )
    sys.exit(0)



def run_background_daemon() -> None:
    """Runs the AppUpdateWatcher indefinitely in background daemon mode."""
    logging.info("Starting IconReplace background daemon mode...")
    watcher = AppUpdateWatcher(poll_interval=3.0, auto_repair_enabled=True)
    watcher.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logging.info("Received termination signal. Stopping background daemon...")
        watcher.stop()


def run_cli_patch(icon_path: str) -> None:
    """Executes a single non-interactive CLI patch command."""
    logging.info("Executing CLI patch operation...")
    watcher = AppUpdateWatcher(auto_repair_enabled=False)
    status, app_path = watcher.get_codex_status()

    if not app_path or not app_path.exists():
        logging.error("Neither Codex.app nor ChatGPT.app was found in /Applications.")
        sys.exit(1)

    target_icon = Path(icon_path).resolve() if icon_path else None
    if not target_icon or not target_icon.exists():
        target_icon = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")

    registry = BackupRegistry()
    success = patch_app_icon(
        target_app_path=app_path,
        replacement_icon_path=target_icon,
        rename_to_codex=True,
        backup_registry=registry,
    )

    if success:
        logging.info("Successfully patched app icon via CLI.")
        sys.exit(0)
    else:
        logging.error("Failed to patch app icon via CLI.")
        sys.exit(1)


def run_cli_restore() -> None:
    """Executes a single non-interactive CLI restore operation."""
    logging.info("Executing CLI restore operation...")
    registry = BackupRegistry()
    success = registry.restore_latest_backup("Codex")
    if success:
        logging.info("Successfully restored original backup via CLI.")
        sys.exit(0)
    else:
        logging.error("Failed to restore backup via CLI.")
        sys.exit(1)


def main() -> None:
    """Main CLI parser and mode dispatcher."""
    parser = argparse.ArgumentParser(
        description="IconReplace — macOS App Icon & Branding Customizer",
    )
    parser.add_argument(
        "--auto-repair-delayed",
        action="store_true",
        help="Execute 2-minute delayed auto-repair mechanism",
    )
    parser.add_argument(
        "-b", "--background",
        action="store_true",
        help="Run in background daemon mode watching for app updates",
    )
    parser.add_argument(
        "-p", "--patch",
        action="store_true",
        help="Execute non-interactive icon patch",
    )
    parser.add_argument(
        "-r", "--restore",
        action="store_true",
        help="Execute non-interactive backup restore",
    )
    parser.add_argument(
        "-i", "--icon",
        type=str,
        default="",
        help="Path to replacement icon file for CLI patch operation",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging output",
    )

    parser.add_argument(
        "-g", "--gui",
        action="store_true",
        help="Launch graphical control panel interface",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    if args.auto_repair_delayed:
        run_auto_repair_delayed()
    elif args.background:
        run_background_daemon()
    elif args.patch:
        run_cli_patch(args.icon)
    elif args.restore:
        run_cli_restore()
    else:
        # Default: Launch GUI main menu control panel
        logging.info("Launching IconReplace GUI main menu...")
        app = IconReplaceGUI()
        app.run()


if __name__ == "__main__":
    main()
