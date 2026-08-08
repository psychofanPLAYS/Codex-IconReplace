"""
GUI module for IconReplace.

Provides an ultra-modern dark-mode liquid-glass interface built with CustomTkinter / Tkinter
for managing macOS application icons, status monitoring, auto-repair toggles, 1-click restoration,
launch agent startup configuration, and permission checks.

Auditing & Safety Notes:
- Non-blocking asynchronous threading for patch and restore actions to keep UI responsive.
- Clean system permission detection and direct System Settings URL routing.
- Handles custom icon selection (.png, .jpeg, .icns) and backup restoration securely.
"""

import logging
import os
import plistlib
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    HAS_CUSTOMTKINTER = True
except ImportError:
    import tkinter as ctk  # Fallback to standard tkinter if customtkinter missing
    from tkinter import filedialog, messagebox
    HAS_CUSTOMTKINTER = False

from app_watcher import AppUpdateWatcher, send_macos_notification
from backup_registry import BackupRegistry
from icon_engine import patch_app_icon
from launchd_manager import LaunchAgentManager

logger = logging.getLogger("IconReplace.GUI")

# LaunchAgent Configuration Constants
LAUNCH_AGENT_LABEL = "com.antigravity.iconreplace"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def open_app_management_settings() -> None:
    """Opens macOS System Settings directly to App Management privacy permissions."""
    try:
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AppManagement"],
            check=False,
        )
    except Exception as err:
        logger.error("Failed to open System Settings: %s", err)


def check_write_permission(target_dir: Path = Path("/Applications")) -> bool:
    """Checks if the process has write permissions to target directory."""
    try:
        if not target_dir.exists():
            return False
        test_file = target_dir / ".iconreplace_perm_check.tmp"
        test_file.touch()
        test_file.unlink()
        return True
    except Exception:
        return False


class HoverTooltip:
    """Floating borderless semi-transparent hover tooltip window."""

    def __init__(self, widget, text: str, delay: int = 250) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.timer_id = None

        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def schedule_show(self, event=None) -> None:
        self.unschedule()
        self.timer_id = self.widget.after(self.delay, self.show)

    def unschedule(self) -> None:
        if self.timer_id:
            try:
                self.widget.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None

    def show(self, event=None) -> None:
        if self.tooltip_window or not self.text:
            return

        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

            if HAS_CUSTOMTKINTER:
                tw = ctk.CTkToplevel(self.widget)
                tw.wm_overrideredirect(True)
                tw.wm_attributes("-topmost", True)
                try:
                    tw.wm_attributes("-alpha", 0.95)
                except Exception:
                    pass
                tw.geometry(f"+{x}+{y}")

                frame = ctk.CTkFrame(
                    tw,
                    fg_color="#1E2230",
                    border_color="#3B82F6",
                    border_width=1,
                    corner_radius=6,
                )
                frame.pack(fill="both", expand=True, ipadx=8, ipady=6)

                label = ctk.CTkLabel(
                    frame,
                    text=self.text,
                    font=ctk.CTkFont(size=12),
                    text_color="#F3F4F6",
                    wraplength=280,
                    justify="left",
                )
                label.pack()
            else:
                tw = ctk.Toplevel(self.widget)
                tw.wm_overrideredirect(True)
                tw.wm_attributes("-topmost", True)
                try:
                    tw.wm_attributes("-alpha", 0.95)
                except Exception:
                    pass
                tw.geometry(f"+{x}+{y}")

                label = ctk.Label(
                    tw,
                    text=self.text,
                    justify="left",
                    background="#1E2230",
                    foreground="#F3F4F6",
                    relief="solid",
                    borderwidth=1,
                    wraplength=280,
                    padx=8,
                    pady=6,
                )
                label.pack()

            self.tooltip_window = tw
        except Exception as err:
            logger.warning("Failed to show tooltip: %s", err)

    def hide(self, event=None) -> None:
        self.unschedule()
        if self.tooltip_window:
            try:
                self.tooltip_window.destroy()
            except Exception:
                pass
            self.tooltip_window = None


class IconReplaceGUI:
    """Main Application GUI Window for IconReplace."""

    def __init__(self, watcher: Optional[AppUpdateWatcher] = None) -> None:
        if HAS_CUSTOMTKINTER:
            ctk.set_appearance_mode("Dark")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = ctk.Tk()
            self.root.configure(bg="#0F1117")

        self.root.title("IconReplace — macOS App Icon & Branding Customizer")
        self.root.geometry("960x720")
        self.root.minsize(860, 620)

        self.backup_registry = BackupRegistry()
        self.watcher = watcher or AppUpdateWatcher(backup_registry=self.backup_registry)
        self.launch_agent_mgr = LaunchAgentManager()

        self.selected_icon_path: Optional[Path] = None
        self.views = {}
        self.nav_buttons = {}
        self.active_view = "overview"

        info_icon_file = Path("app/assets/icons/info.png")
        if not info_icon_file.exists():
            info_icon_file = Path(__file__).resolve().parent.parent / "assets" / "icons" / "info.png"
        if not info_icon_file.exists() and hasattr(sys, "_MEIPASS"):
            info_icon_file = Path(sys._MEIPASS) / "assets" / "icons" / "info.png"

        if HAS_CUSTOMTKINTER and HAS_PIL and info_icon_file.exists():
            self.info_icon_image = ctk.CTkImage(
                light_image=Image.open(info_icon_file),
                dark_image=Image.open(info_icon_file),
                size=(16, 16),
            )
        else:
            self.info_icon_image = None

        self._init_ui()

        # Connect watcher callback
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.refresh_status()

    def _on_close(self) -> None:
        """Pristine window hygiene: stops watcher threads and destroys all windows cleanly."""
        try:
            if hasattr(self, "watcher") and self.watcher:
                self.watcher.stop(timeout=1.0)
        except Exception as err:
            logger.warning("Error stopping watcher on window close: %s", err)
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _init_ui(self) -> None:
        """Constructs the 2-column liquid-glass UI layout with left sidebar navigation."""
        if HAS_CUSTOMTKINTER:
            # 2-Column Grid Setup: Column 0 = Sidebar (fixed), Column 1 = Content (expandable)
            self.root.grid_columnconfigure(0, weight=0)
            self.root.grid_columnconfigure(1, weight=1)
            self.root.grid_rowconfigure(0, weight=1)

            # Left Navigation Sidebar Frame
            self.sidebar_frame = ctk.CTkFrame(
                self.root,
                width=220,
                corner_radius=0,
                fg_color="#12151E",
                border_color="#1F2432",
                border_width=1,
            )
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
            self.sidebar_frame.grid_rowconfigure(5, weight=1)  # Spacer pushes footer to bottom

            # Right Main Content Area Container
            self.main_container = ctk.CTkFrame(
                self.root,
                fg_color="#0F1117",
                corner_radius=0,
            )
            self.main_container.grid(row=0, column=1, sticky="nsew")

            # 1. Build Left Sidebar Content
            self._build_sidebar()

            # 2. Build Right View Frames (standard CTkFrame without scrollbars)
            self.views["overview"] = ctk.CTkFrame(self.main_container, fg_color="#0F1117", corner_radius=0)
            self.views["settings"] = ctk.CTkFrame(self.main_container, fg_color="#0F1117", corner_radius=0)
            self.views["permissions"] = ctk.CTkFrame(self.main_container, fg_color="#0F1117", corner_radius=0)

            # Populate Views
            self._build_overview_view(self.views["overview"])
            self._build_settings_view(self.views["settings"])
            self._build_permissions_view(self.views["permissions"])

            # Default view
            self._show_view("overview")
        else:
            self.main_container = ctk.Frame(self.root, bg="#0F1117")
            self.main_container.pack(fill="both", expand=True, padx=20, pady=20)
            self._build_status_card(self.main_container)
            self._build_icon_drop_zone(self.main_container)
            self._build_action_buttons(self.main_container)
            self._build_settings_panel(self.main_container)
            self._build_permission_card(self.main_container)

    def _build_sidebar(self) -> None:
        """Constructs the left navigation sidebar with logo branding and view selector buttons."""
        if not HAS_CUSTOMTKINTER:
            return

        # Sidebar Title & Branding Header
        header_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(24, 20))

        lbl_logo = ctk.CTkLabel(
            header_frame,
            text="🎨 IconReplace",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#F3F4F6",
        )
        lbl_logo.pack(anchor="w")

        lbl_version = ctk.CTkLabel(
            header_frame,
            text="v0.1.015 • MacOS Edition.",
            font=ctk.CTkFont(size=11),
            text_color="#6B7280",
        )
        lbl_version.pack(anchor="w", pady=(2, 0))

        # Navigation Divider
        divider = ctk.CTkFrame(self.sidebar_frame, height=1, fg_color="#1F2432")
        divider.pack(fill="x", padx=16, pady=(0, 16))

        # Navigation Buttons
        nav_items = [
            ("overview", "📊  Overview"),
            ("settings", "⚙️  Settings"),
            ("permissions", "🔒  Permissions"),
        ]

        for view_key, label_text in nav_items:
            btn = ctk.CTkButton(
                self.sidebar_frame,
                text=label_text,
                anchor="w",
                height=38,
                corner_radius=8,
                font=ctk.CTkFont(size=13, weight="normal"),
                fg_color="transparent",
                hover_color="#1E2230",
                text_color="#9CA3AF",
                command=lambda k=view_key: self._show_view(k),
            )
            btn.pack(fill="x", padx=14, pady=3)
            self.nav_buttons[view_key] = btn

        # Bottom Footer / Status Indicator inside Sidebar
        footer_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#181B24", corner_radius=8, border_color="#2E344A", border_width=1)
        footer_frame.pack(side="bottom", fill="x", padx=14, pady=16)

        lbl_engine_status = ctk.CTkLabel(
            footer_frame,
            text="🟢 Engine Active",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10B981",
        )
        lbl_engine_status.pack(padx=10, pady=8)

    def _show_view(self, view_name: str) -> None:
        """Swaps the active view frame in the main container and updates navigation button state."""
        self.active_view = view_name
        for name, frame in self.views.items():
            frame.pack_forget()

        if view_name in self.views:
            self.views[view_name].pack(fill="both", expand=True, padx=24, pady=20)

        if HAS_CUSTOMTKINTER:
            for name, btn in self.nav_buttons.items():
                if name == view_name:
                    btn.configure(
                        fg_color="#6366F1",
                        hover_color="#4F46E5",
                        text_color="#FFFFFF",
                        font=ctk.CTkFont(size=13, weight="bold"),
                    )
                else:
                    btn.configure(
                        fg_color="transparent",
                        hover_color="#1E2230",
                        text_color="#9CA3AF",
                        font=ctk.CTkFont(size=13, weight="normal"),
                    )

    def _build_view_header(self, parent, title: str, subtitle: str) -> None:
        """Renders section header banner at top of view frame."""
        if HAS_CUSTOMTKINTER:
            header_frame = ctk.CTkFrame(parent, fg_color="transparent")
            header_frame.pack(fill="x", pady=(0, 20))

            lbl_title = ctk.CTkLabel(
                header_frame,
                text=title,
                font=ctk.CTkFont(size=22, weight="bold"),
                text_color="#F3F4F6",
            )
            lbl_title.pack(anchor="w")

            lbl_sub = ctk.CTkLabel(
                header_frame,
                text=subtitle,
                font=ctk.CTkFont(size=12),
                text_color="#9CA3AF",
            )
            lbl_sub.pack(anchor="w", pady=(2, 0))

    def _build_overview_view(self, parent) -> None:
        """Constructs the Overview view frame."""
        self._build_view_header(parent, "📊 Application Overview", "Manage target application status, custom icon selection, and branding patches.")
        self._build_status_card(parent)
        self._build_icon_drop_zone(parent)
        self._build_action_buttons(parent)

    def _build_settings_view(self, parent) -> None:
        """Constructs the Settings view frame."""
        self._build_view_header(parent, "⚙️ Preferences & Automation", "Configure auto-repair background behavior, startup LaunchAgent, and desktop alerts.")
        self._build_settings_panel(parent)

    def _build_permissions_view(self, parent) -> None:
        """Constructs the Permissions view frame."""
        self._build_view_header(parent, "🔒 System Permissions", "Verify macOS privacy entitlements and system application directory write access.")
        self._build_permission_card(parent)

    def _build_status_card(self, parent) -> None:
        """Status overview card for target application."""
        if HAS_CUSTOMTKINTER:
            self.status_card = ctk.CTkFrame(
                parent,
                fg_color="#181B24",
                border_color="#2E344A",
                border_width=1,
                corner_radius=12,
            )
        else:
            self.status_card = ctk.Frame(parent, bg="#181B24", bd=1, relief="solid")

        self.status_card.pack(fill="x", pady=(0, 15), ipadx=15, ipady=12)

        if HAS_CUSTOMTKINTER:
            lbl_title = ctk.CTkLabel(
                self.status_card,
                text="APPLICATION STATUS",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#6B7280",
            )
            lbl_title.pack(anchor="w", padx=15, pady=(10, 5))

            self.status_badge = ctk.CTkLabel(
                self.status_card,
                text="Checking status...",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color="#F3F4F6",
            )
            self.status_badge.pack(anchor="w", padx=15, pady=(0, 4))

            self.status_detail = ctk.CTkLabel(
                self.status_card,
                text="Path: Searching /Applications...",
                font=ctk.CTkFont(size=12),
                text_color="#9CA3AF",
            )
            self.status_detail.pack(anchor="w", padx=15, pady=(0, 10))

            btn_refresh = ctk.CTkButton(
                self.status_card,
                text="🔄 Refresh Status",
                width=120,
                height=28,
                fg_color="#2E344A",
                hover_color="#3D4461",
                text_color="#F3F4F6",
                command=self.refresh_status,
            )
            btn_refresh.pack(anchor="e", padx=15, pady=(0, 10))
        else:
            self.status_badge = ctk.Label(self.status_card, text="Checking...", fg="#F3F4F6", bg="#181B24")
            self.status_badge.pack(padx=10, pady=10)

    def _build_icon_drop_zone(self, parent) -> None:
        """Drag-and-Drop / File selection card with live visual icon preview."""
        if HAS_CUSTOMTKINTER:
            self.drop_frame = ctk.CTkFrame(
                parent,
                fg_color="#181B24",
                border_color="#2E344A",
                border_width=1,
                corner_radius=12,
            )
        else:
            self.drop_frame = ctk.Frame(parent, bg="#181B24", bd=1, relief="solid")

        self.drop_frame.pack(fill="x", pady=(0, 15), ipadx=15, ipady=15)

        if HAS_CUSTOMTKINTER:
            lbl_title = ctk.CTkLabel(
                self.drop_frame,
                text="CUSTOM REPLACEMENT ICON & PREVIEW",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#6B7280",
            )
            lbl_title.pack(anchor="w", padx=15, pady=(10, 5))

            self.preview_label = ctk.CTkLabel(
                self.drop_frame,
                text="",
                width=80,
                height=80,
            )
            self.preview_label.pack(pady=(5, 10))

            self.drop_label = ctk.CTkLabel(
                self.drop_frame,
                text="📁 Drag & Drop single .png, .jpeg, or .icns file here\nor click button below to choose file",
                font=ctk.CTkFont(size=13),
                text_color="#9CA3AF",
            )
            self.drop_label.pack(pady=5)

            self.icon_path_label = ctk.CTkLabel(
                self.drop_frame,
                text="Selected: Default System / Assets Icon",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#6366F1",
            )
            self.icon_path_label.pack(pady=(0, 10))

            btn_browse = ctk.CTkButton(
                self.drop_frame,
                text="Choose Custom Icon...",
                width=180,
                height=32,
                fg_color="#3B82F6",
                hover_color="#2563EB",
                command=self.select_icon_file,
            )
            btn_browse.pack(pady=(0, 10))
            self._update_icon_preview()

    def _build_action_buttons(self, parent) -> None:
        """Primary action buttons for applying patch and restoring backups."""
        if HAS_CUSTOMTKINTER:
            actions_frame = ctk.CTkFrame(parent, fg_color="transparent")
            actions_frame.pack(fill="x", pady=(0, 15))

            # Apply Button Row + Tooltip
            row_apply = ctk.CTkFrame(actions_frame, fg_color="transparent")
            row_apply.pack(fill="x", pady=(0, 8))

            self.btn_apply = ctk.CTkButton(
                row_apply,
                text="✨ Apply Dark Mode Icon",
                font=ctk.CTkFont(size=14, weight="bold"),
                height=42,
                fg_color="#6366F1",
                hover_color="#4F46E5",
                command=self.apply_dark_icon,
            )
            self.btn_apply.pack(side="left", fill="x", expand=True)

            info_apply = ctk.CTkLabel(
                row_apply,
                text="",
                image=self.info_icon_image,
                cursor="hand2",
            )
            info_apply.pack(side="left", padx=(8, 0))
            t_apply = "Replaces the application's icon and restarts the dock. A backup is automatically created."
            HoverTooltip(info_apply, t_apply)
            HoverTooltip(self.btn_apply, t_apply)

            # Restore Button Row + Tooltip
            row_restore = ctk.CTkFrame(actions_frame, fg_color="transparent")
            row_restore.pack(fill="x")

            self.btn_restore = ctk.CTkButton(
                row_restore,
                text="↺ Restore Original Backup (1-Click Undo)",
                font=ctk.CTkFont(size=13),
                height=36,
                fg_color="#2E344A",
                hover_color="#3D4461",
                text_color="#F3F4F6",
                command=self.restore_backup,
            )
            self.btn_restore.pack(side="left", fill="x", expand=True)

            info_restore = ctk.CTkLabel(
                row_restore,
                text="",
                image=self.info_icon_image,
                cursor="hand2",
            )
            info_restore.pack(side="left", padx=(8, 0))
            t_restore = "Reverts the icon to the original system default."
            HoverTooltip(info_restore, t_restore)
            HoverTooltip(self.btn_restore, t_restore)

    def _build_settings_panel(self, parent) -> None:
        """Settings switches for auto-repair, background startup, and notifications."""
        if HAS_CUSTOMTKINTER:
            self.settings_card = ctk.CTkFrame(
                parent,
                fg_color="#181B24",
                border_color="#2E344A",
                border_width=1,
                corner_radius=12,
            )
            self.settings_card.pack(fill="x", pady=(0, 15), ipadx=15, ipady=12)

            lbl_title = ctk.CTkLabel(
                self.settings_card,
                text="AUTOMATION & PREFERENCES",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#6B7280",
            )
            lbl_title.pack(anchor="w", padx=15, pady=(10, 10))

            # Auto-Repair Row
            row_auto = ctk.CTkFrame(self.settings_card, fg_color="transparent")
            row_auto.pack(anchor="w", padx=15, pady=(0, 8), fill="x")

            self.sw_auto_repair = ctk.CTkSwitch(
                row_auto,
                text="Auto-Repair when Codex updates (ChatGPT name detector)",
                font=ctk.CTkFont(size=13),
                command=self._on_toggle_auto_repair,
            )
            if self.launch_agent_mgr.is_agent_installed() or self.watcher.auto_repair_enabled:
                self.sw_auto_repair.select()
            self.sw_auto_repair.pack(side="left")

            info_auto = ctk.CTkLabel(
                row_auto,
                text="",
                image=self.info_icon_image,
                cursor="hand2",
            )
            info_auto.pack(side="left", padx=(8, 0))
            t_auto = "Runs silently in the background to automatically re-apply your custom icon if an app update overwrites it."
            HoverTooltip(info_auto, t_auto)
            HoverTooltip(self.sw_auto_repair, t_auto)

            # Startup Row
            row_startup = ctk.CTkFrame(self.settings_card, fg_color="transparent")
            row_startup.pack(anchor="w", padx=15, pady=(0, 8), fill="x")

            self.sw_startup = ctk.CTkSwitch(
                row_startup,
                text="Launch in background on system startup",
                font=ctk.CTkFont(size=13),
                command=self._on_toggle_startup,
            )
            if self.launch_agent_mgr.is_agent_installed():
                self.sw_startup.select()
            self.sw_startup.pack(side="left")

            info_startup = ctk.CTkLabel(
                row_startup,
                text="",
                image=self.info_icon_image,
                cursor="hand2",
            )
            info_startup.pack(side="left", padx=(8, 0))
            t_startup = "Ensures the Auto-Repair agent starts every time you turn on your Mac."
            HoverTooltip(info_startup, t_startup)
            HoverTooltip(self.sw_startup, t_startup)

            # Notifications Row
            row_notify = ctk.CTkFrame(self.settings_card, fg_color="transparent")
            row_notify.pack(anchor="w", padx=15, pady=(0, 10), fill="x")

            self.sw_notify = ctk.CTkSwitch(
                row_notify,
                text="macOS Desktop Banner Notifications",
                font=ctk.CTkFont(size=13),
                command=self._on_toggle_notifications,
            )
            if self.watcher.notifications_enabled:
                self.sw_notify.select()
            self.sw_notify.pack(side="left")

            info_notify = ctk.CTkLabel(
                row_notify,
                text="",
                image=self.info_icon_image,
                cursor="hand2",
            )
            info_notify.pack(side="left", padx=(8, 0))
            t_notify = "Displays macOS system banner notifications when icon changes or auto-repairs take place."
            HoverTooltip(info_notify, t_notify)
            HoverTooltip(self.sw_notify, t_notify)

            # Test Notification Button
            row_test_notify = ctk.CTkFrame(self.settings_card, fg_color="transparent")
            row_test_notify.pack(anchor="w", padx=15, pady=(0, 10), fill="x")

            self.btn_test_notify = ctk.CTkButton(
                row_test_notify,
                text="🔔 Test Notification",
                width=160,
                height=28,
                fg_color="#2E344A",
                hover_color="#3D4461",
                text_color="#F3F4F6",
                font=ctk.CTkFont(size=12),
                command=self._on_test_notification,
            )
            self.btn_test_notify.pack(side="left")
            t_test_notify = "Spawns a test macOS banner notification to verify system alert delivery."
            HoverTooltip(self.btn_test_notify, t_test_notify)

    def _build_permission_card(self, parent) -> None:
        """Permission status card and open System Settings helper."""
        if HAS_CUSTOMTKINTER:
            perm_card = ctk.CTkFrame(
                parent,
                fg_color="#181B24",
                border_color="#2E344A",
                border_width=1,
                corner_radius=12,
            )
            perm_card.pack(fill="x", pady=(0, 15), ipadx=15, ipady=12)

            has_write = check_write_permission()
            status_text = "🟢 App Management / /Applications Write Permission OK" if has_write else "⚠️ Restricted /Applications Write Access"
            status_color = "#10B981" if has_write else "#F59E0B"

            row_perm_title = ctk.CTkFrame(perm_card, fg_color="transparent")
            row_perm_title.pack(anchor="w", padx=15, pady=(10, 5), fill="x")

            lbl_title = ctk.CTkLabel(
                row_perm_title,
                text="SYSTEM PERMISSIONS",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#6B7280",
            )
            lbl_title.pack(side="left")

            info_perm = ctk.CTkLabel(
                row_perm_title,
                text="",
                image=self.info_icon_image,
                cursor="hand2",
            )
            info_perm.pack(side="left", padx=(8, 0))
            t_perm = "macOS requires explicit permission to modify files inside the secure /Applications folder."
            HoverTooltip(info_perm, t_perm)

            lbl_status = ctk.CTkLabel(
                perm_card,
                text=status_text,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=status_color,
            )
            lbl_status.pack(anchor="w", padx=15, pady=(0, 8))

            btn_perm = ctk.CTkButton(
                perm_card,
                text="⚙️ Open System Settings (App Management)",
                width=240,
                height=30,
                fg_color="#2E344A",
                hover_color="#3D4461",
                text_color="#F3F4F6",
                command=open_app_management_settings,
            )
            btn_perm.pack(anchor="w", padx=15, pady=(0, 10))
            HoverTooltip(btn_perm, t_perm)

    def _update_icon_preview(self) -> None:
        """Loads and renders the current replacement icon image in the GUI preview container."""
        if not HAS_CUSTOMTKINTER or not hasattr(self, "preview_label"):
            return

        icon_file = self.selected_icon_path or self.watcher.replacement_icon_path
        if icon_file is None or not icon_file.exists():
            asset_dir = Path(__file__).resolve().parent.parent / "assets"
            asset_png = asset_dir / "icon-codex-dark-color.png"
            if asset_png.exists():
                icon_file = asset_png
            else:
                icon_file = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")

        try:
            if icon_file.suffix.lower() == ".icns":
                self.preview_label.configure(text="[ .ICNS File ]", text_color="#6366F1")
            elif HAS_PIL:
                pil_img = Image.open(icon_file)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(72, 72))
                self.preview_label.configure(image=ctk_img, text="")
            else:
                self.preview_label.configure(text=f"[ {icon_file.name} ]", text_color="#6366F1")
        except Exception as err:
            logger.warning("Failed to render icon preview: %s", err)
            self.preview_label.configure(text="[ Image Icon ]", text_color="#6366F1")

    def select_icon_file(self) -> None:
        """Opens file dialog for user to choose custom image or .icns file with resolution check."""
        filetypes = [
            ("Supported Icon Files", "*.png *.jpg *.jpeg *.icns"),
            ("PNG Images", "*.png"),
            ("ICNS Icon Files", "*.icns"),
            ("JPEG Images", "*.jpg *.jpeg"),
            ("All Files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(
            title="Select Custom Application Icon",
            filetypes=filetypes,
        )
        if chosen:
            chosen_path = Path(chosen).resolve()
            # Resolution check for low quality images
            if HAS_PIL and chosen_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                try:
                    with Image.open(chosen_path) as img:
                        w, h = img.size
                        if w < 512 or h < 512:
                            use_low_res = messagebox.askyesno(
                                "Low Resolution Image Warning",
                                f"The image '{chosen_path.name}' is low resolution ({w}x{h} pixels).\n\n"
                                f"Icons smaller than 512x512 may look blurry or pixelated in Finder/Dock.\n\n"
                                f"Do you want to use it anyway?\n(Click No to keep default high-res dark icon)",
                            )
                            if not use_low_res:
                                return
                except Exception as err:
                    logger.warning("Failed to check image dimensions: %s", err)

            self.selected_icon_path = chosen_path
            if HAS_CUSTOMTKINTER:
                self.icon_path_label.configure(
                    text=f"Selected: {self.selected_icon_path.name}",
                    text_color="#10B981",
                )
            self.watcher.replacement_icon_path = self.selected_icon_path
            self._update_icon_preview()

    def refresh_status(self) -> None:
        """Refreshes status card display by querying AppUpdateWatcher."""
        status, app_path = self.watcher.check_now()
        self._update_status_display(status, app_path)

    def _update_status_display(self, status: str, app_path: Optional[Path]) -> None:
        """Updates GUI elements with current status information."""
        if not HAS_CUSTOMTKINTER:
            return

        if status == AppUpdateWatcher.STATUS_CODEX_INSTALLED:
            badge_text = "🟢 Installed as Codex.app"
            badge_color = "#10B981"
        elif status == AppUpdateWatcher.STATUS_NEEDS_PATCHING:
            badge_text = "🟡 ChatGPT.app Detected (Needs Patching)"
            badge_color = "#F59E0B"
        else:
            badge_text = "⚪ Codex / ChatGPT App Not Found in /Applications"
            badge_color = "#9CA3AF"

        path_text = f"Path: {app_path}" if app_path else "Path: Not found in /Applications"

        self.status_badge.configure(text=badge_text, text_color=badge_color)
        self.status_detail.configure(text=path_text)

    def _on_watcher_status_change(self, status: str, app_path: Optional[Path]) -> None:
        """Callback from watcher background thread when status changes."""
        self.root.after(0, lambda: self._update_status_display(status, app_path))

    def apply_dark_icon(self) -> None:
        """Applies dark mode icon patch in background thread."""
        status, app_path = self.watcher.get_codex_status()
        if not app_path or not app_path.exists():
            messagebox.showerror(
                "App Not Found",
                "Neither Codex.app nor ChatGPT.app was found in /Applications.",
            )
            return

        # Check if already patched to prevent redundant backups
        if status == AppUpdateWatcher.STATUS_CODEX_INSTALLED and self.selected_icon_path is None:
            repatch = messagebox.askyesno(
                "Already Patched",
                "Codex.app is already installed and running dark mode branding.\n\n"
                "Do you want to force re-patch the icon anyway?",
            )
            if not repatch:
                return

        # Check for dual-app conflict: ChatGPT.app and Codex.app both present
        parent_dir = app_path.parent
        chatgpt_app = parent_dir / "ChatGPT.app"
        codex_app = parent_dir / "Codex.app"
        if chatgpt_app.exists() and codex_app.exists():
            proceed = messagebox.askyesno(
                "App Conflict Detected",
                "Both ChatGPT.app and Codex.app were found in /Applications.\n\n"
                "Do you want to back up existing Codex.app to project root '_backups/' and proceed with dark mode icon patching?",
            )
            if not proceed:
                logger.info("User cancelled dark mode patching due to app conflict.")
                return

        icon_file = self.selected_icon_path or self.watcher.replacement_icon_path
        if icon_file is None or not icon_file.exists():
            # System icon fallback
            icon_file = Path("/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns")

        if HAS_CUSTOMTKINTER:
            self.btn_apply.configure(state="disabled", text="⏳ Applying Icon Patch...")

        def _worker():
            success = patch_app_icon(
                target_app_path=app_path,
                replacement_icon_path=icon_file,
                rename_to_codex=True,
                backup_registry=self.backup_registry,
                refresh_dock=True,
            )
            self.root.after(0, lambda: self._on_apply_complete(success))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_apply_complete(self, success: bool) -> None:
        """Callback when icon patch thread completes."""
        if HAS_CUSTOMTKINTER:
            self.btn_apply.configure(state="normal", text="✨ Apply Dark Mode Icon")
        self.refresh_status()

        if success:
            messagebox.showinfo("Success", "Codex icon & bundle branding patched successfully!")
        else:
            messagebox.showerror("Error", "Failed to patch app icon. Check permissions in System Settings.")

    def restore_backup(self) -> None:
        """Restores application bundle to original stock state from backup."""
        if HAS_CUSTOMTKINTER:
            self.btn_restore.configure(state="disabled", text="⏳ Restoring Backup...")

        def _worker():
            success = self.backup_registry.restore_latest_backup("Codex")
            self.root.after(0, lambda: self._on_restore_complete(success))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_restore_complete(self, success: bool) -> None:
        """Callback when backup restoration thread completes."""
        if HAS_CUSTOMTKINTER:
            self.btn_restore.configure(state="normal", text="↺ Restore Original Backup (1-Click Undo)")
        self.refresh_status()

        if success:
            messagebox.showinfo("Restored", "Successfully restored application bundle from backup!")
        else:
            messagebox.showwarning("Restore Failed", "No valid backups found to restore.")

    def _on_toggle_auto_repair(self) -> None:
        """Toggle auto-repair switch handler."""
        val = bool(self.sw_auto_repair.get())
        self.watcher.auto_repair_enabled = val
        if val:
            main_script = Path(__file__).resolve().parent / "main.py"
            self.launch_agent_mgr.install_agent(main_script)
        else:
            self.launch_agent_mgr.uninstall_agent()
        logger.info("Set auto-repair enabled: %s", val)

    def _on_toggle_startup(self) -> None:
        """Toggle startup LaunchAgent switch handler."""
        val = bool(self.sw_startup.get())
        if val:
            main_script = Path(__file__).resolve().parent / "main.py"
            self.launch_agent_mgr.install_agent(main_script)
        else:
            self.launch_agent_mgr.uninstall_agent()

    def _on_toggle_notifications(self) -> None:
        """Toggle notifications switch handler."""
        val = bool(self.sw_notify.get())
        self.watcher.notifications_enabled = val
        logger.info("Set notifications enabled: %s", val)

    def _on_test_notification(self) -> None:
        """Trigger a test macOS notification banner."""
        if not send_macos_notification("IconReplace", "Notification test successful!"):
            os.system("osascript -e 'display notification \"Notification test successful!\" with title \"IconReplace\"'")
        logger.info("Triggered test notification banner")

    def run(self) -> None:
        """Runs the main GUI event loop."""
        self.root.mainloop()
