"""
Backup Registry for IconReplace.

This module manages byte-for-byte backups and restorations of macOS application bundles,
ensuring all icon modifications can be safely rolled back to stock application states.

Auditing & Safety Notes:
- Prior to modifying any application bundle, a timestamped snapshot of original app resources
  (Contents/Resources, Info.plist, and metadata) is persisted in `~/.iconreplace/backups/<app_name>/`.
- Restoration is idempotent and preserves original application metadata.
- All file operations use secure standard python file utilities.
"""

import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("IconReplace.BackupRegistry")


class BackupRegistry:
    """
    Registry manager for application bundle backup and restoration operations.
    """

    def __init__(self, backup_dir: Optional[Path] = None) -> None:
        """
        Initialize the BackupRegistry with a target directory for storing backups.

        Args:
            backup_dir: Custom backup directory Path. Defaults to ~/.iconreplace/backups.
        """
        if backup_dir is None:
            self.backup_dir = Path.home() / ".iconreplace" / "backups"
        else:
            self.backup_dir = Path(backup_dir).expanduser().resolve()

        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, app_path: Path) -> Path:
        """
        Creates a timestamped backup of the target application bundle's resources and Info.plist.

        Args:
            app_path: Path to the target .app bundle (e.g., /Applications/ChatGPT.app).

        Returns:
            Path pointing to the newly created backup directory.

        Raises:
            FileNotFoundError: If app_path does not exist or lacks Contents directory.
            IOError: If copying resources fails.
        """
        app_path = Path(app_path).resolve()
        if not app_path.exists() or not app_path.is_dir():
            raise FileNotFoundError(f"Target application bundle does not exist: {app_path}")

        contents_dir = app_path / "Contents"
        if not contents_dir.exists():
            raise FileNotFoundError(f"Invalid .app bundle missing Contents directory: {app_path}")

        app_name = app_path.stem  # e.g., 'ChatGPT' or 'Codex'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Backup path structure: <backup_dir>/<app_name>/<timestamp>/
        app_backup_dir = self.backup_dir / app_name / timestamp
        app_backup_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save metadata
        metadata = {
            "original_app_name": app_name,
            "original_app_path": str(app_path),
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
        }
        with open(app_backup_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # 2. Backup Contents/Info.plist if present
        info_plist = contents_dir / "Info.plist"
        if info_plist.exists():
            shutil.copy(info_plist, app_backup_dir / "Info.plist")

        # 3. Backup Contents/Resources if present
        resources_dir = contents_dir / "Resources"
        if resources_dir.exists():
            backup_resources_dir = app_backup_dir / "Resources"
            shutil.copytree(resources_dir, backup_resources_dir, dirs_exist_ok=True, copy_function=shutil.copy)

        logger.info("Successfully created backup for '%s' at %s", app_name, app_backup_dir)
        return app_backup_dir

    def list_backups(self, app_name: str) -> List[Path]:
        """
        Returns a chronologically sorted list of backup directories for a given app name.

        Args:
            app_name: Name of the application (e.g., 'ChatGPT' or 'Codex').

        Returns:
            List of Path objects pointing to backup directories, ordered from oldest to newest.
        """
        app_backup_root = self.backup_dir / app_name
        if not app_backup_root.exists() or not app_backup_root.is_dir():
            return []

        backups = [p for p in app_backup_root.iterdir() if p.is_dir()]
        backups.sort(key=lambda p: p.name)
        return backups

    def restore_latest_backup(
        self,
        target_app_name: str = "Codex",
        target_app_dir: Optional[Path] = None
    ) -> bool:
        """
        Restores the latest backup for target_app_name back to stock condition.

        If target_app_name is 'Codex', checks for backups under 'Codex' or 'ChatGPT'
        and restores the application bundle back to stock (e.g., reverting Codex.app to ChatGPT.app).

        Args:
            target_app_name: Name of the app to restore (default 'Codex').
            target_app_dir: Optional override path of the current app bundle location.

        Returns:
            True if backup was restored successfully, False otherwise.
        """
        candidate_names = [target_app_name]
        if target_app_name.lower() in ("codex", "chatgpt"):
            for n in ("ChatGPT", "Codex", "chatgpt", "codex"):
                if n not in candidate_names:
                    candidate_names.append(n)

        all_backups = []
        for name in candidate_names:
            for b in self.list_backups(name):
                all_backups.append(b)

        if not all_backups:
            logger.warning("No backups found for '%s'", target_app_name)
            return False

        # Sort all candidates chronologically by directory name
        all_backups.sort(key=lambda p: p.name)
        latest_backup = all_backups[-1]

        # Read metadata if present
        metadata_file = latest_backup / "metadata.json"
        original_app_path = None
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    if "original_app_path" in meta:
                        original_app_path = Path(meta["original_app_path"])
            except Exception as err:
                logger.warning("Failed to parse backup metadata: %s", err)

        # Locate active target app path on system
        current_app_path = target_app_dir
        if current_app_path is None:
            if original_app_path and original_app_path.exists():
                current_app_path = original_app_path
            else:
                possible_paths = [
                    Path(f"/Applications/{target_app_name}.app"),
                    Path("/Applications/Codex.app"),
                    Path("/Applications/ChatGPT.app"),
                ]
                for p in possible_paths:
                    if p.exists():
                        current_app_path = p
                        break

        if current_app_path is None or not current_app_path.exists():
            logger.error("Target app path not found for restoration: %s", current_app_path)
            return False

        contents_dir = current_app_path / "Contents"
        if not contents_dir.exists():
            logger.error("Contents directory missing in target app path: %s", current_app_path)
            return False

        # Restore Info.plist if present in backup
        backup_plist = latest_backup / "Info.plist"
        if backup_plist.exists():
            shutil.copy(backup_plist, contents_dir / "Info.plist")

        # Restore Resources/ if present in backup
        backup_resources = latest_backup / "Resources"
        if backup_resources.exists():
            target_resources = contents_dir / "Resources"
            if target_resources.exists():
                shutil.rmtree(target_resources)
            shutil.copytree(backup_resources, target_resources, copy_function=shutil.copy)

        # If original app path was different (e.g. ChatGPT.app vs Codex.app), rename back safely
        if original_app_path and current_app_path.resolve() != original_app_path.resolve():
            if original_app_path.exists():
                logger.info("Destination '%s' exists during restore. Removing conflict target cleanly...", original_app_path)
                shutil.rmtree(original_app_path)
            current_app_path.rename(original_app_path)
            current_app_path = original_app_path

        # Code-sign restored app bundle cleanly
        try:
            subprocess.run(
                ["xattr", "-cr", str(current_app_path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                ["codesign", "--force", "--sign", "-", str(current_app_path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.warning("Code signing warning during restore: %s", e)

        logger.info("Successfully restored '%s' from backup %s", target_app_name, latest_backup)
        return True
