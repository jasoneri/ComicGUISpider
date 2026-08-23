from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget, qconfig

from GUI.core.theme import theme_mgr
from server.tray.style import apply_manage_dialog_theme
from server.tray.ui_common import ServerManageDialog, configure_tray_qt_fonts
from utils.config import qconfig_dir
from utils.config.qc import cgs_cfg

if TYPE_CHECKING:
    from server.tray.host import ServerTrayHost


class ManageDialogController:
    def __init__(self, host: "ServerTrayHost") -> None:
        self.host = host
        self.dialog: ServerManageDialog | None = None
        self.events_dialog: ServerManageDialog | None = None
        self._tab_segment: SegmentedWidget | None = None
        self._tab_stack: QStackedWidget | None = None
        self._tab_widgets: dict[str, QWidget] = {}
        self._theme_subscribed = False

    def show(self, tab_name: str = "Server") -> None:
        host = self.host
        if app := (host.qt_app or QApplication.instance()):
            configure_tray_qt_fonts(app)
        # Tray is a separate process from the main GUI: always re-read qc.json so
        # dialog day/night follows conf_dialog.darkTheme (cgs_cfg.themeMode), not OS AUTO.
        self._sync_theme_from_config()
        if self.dialog is not None:
            self.apply_theme()
            self.select(tab_name)
            self.refresh(rebuild_lists=True)
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
            return

        dialog = ServerManageDialog()
        dialog.setObjectName("ServerManageDialog")
        dialog.setWindowTitle(self._title())
        dialog.setWindowIcon(QIcon(":/CGS-logo.png"))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        self._tab_segment = SegmentedWidget(dialog)
        self._tab_stack = QStackedWidget(dialog)
        self._tab_widgets = {}
        for title, widget in (
            ("Schedule", host.schedule_panel.build_tab(dialog)),
            ("Server", host.server_panel.build_tab(dialog)),
            ("MCP", host.mcp_panel.build_tab(dialog)),
        ):
            self._tab_segment.addItem(title, title, onClick=lambda _checked=False, item=title: self.select(item))
            self._tab_stack.addWidget(widget)
            self._tab_widgets[title] = widget

        layout.addWidget(self._tab_segment)
        layout.addWidget(self._tab_stack, 1)
        dialog.setMinimumSize(960, 520)
        self.dialog = dialog
        self.events_dialog = dialog
        self._ensure_theme_subscription()
        self.apply_theme()
        self.select(tab_name)
        self.refresh(rebuild_lists=True)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _sync_theme_from_config(self) -> None:
        qconfig.load(qconfig_dir.joinpath("qc.json"), cgs_cfg)
        theme_mgr.set_theme_mode(cgs_cfg.themeMode.value, save=False)
        if app := (self.host.qt_app or QApplication.instance()):
            theme_mgr.apply_to_app(app)

    def apply_theme(self, _theme=None) -> None:
        if self.dialog is None:
            return
        from GUI.core.theme.qss_template import load_templated_qss_document

        load_templated_qss_document.cache_clear()
        apply_manage_dialog_theme(self.dialog)
        if self.is_visible():
            self.refresh(rebuild_lists=True)

    def _ensure_theme_subscription(self) -> None:
        if self._theme_subscribed:
            return
        theme_mgr.subscribe(self.apply_theme)
        self._theme_subscribed = True
        if self.dialog is not None and not getattr(self.dialog, "_cgs_tray_theme_cleanup", False):
            def _cleanup(_obj=None):
                theme_mgr.unsubscribe(self.apply_theme)
                self._theme_subscribed = False

            self.dialog.destroyed.connect(_cleanup)
            setattr(self.dialog, "_cgs_tray_theme_cleanup", True)

    def select(self, tab_name: str) -> None:
        if self._tab_stack is None or self._tab_segment is None:
            return
        widget = self._tab_widgets.get(tab_name) or self._tab_widgets["Server"]
        self._tab_stack.setCurrentWidget(widget)
        self._tab_segment.setCurrentItem(tab_name if tab_name in self._tab_widgets else "Server")
        if tab_name == "Schedule" and self.is_visible():
            self.host.schedule_panel.refresh(full=True)

    def refresh(self, *, rebuild_lists: bool = False, schedule_full: bool | None = None) -> None:
        host = self.host
        if schedule_full is None:
            schedule_full = rebuild_lists
        host.schedule_panel.refresh(full=schedule_full)
        host.server_panel.refresh()
        host.mcp_panel.refresh(rebuild_lists=rebuild_lists)

    def is_visible(self) -> bool:
        return self.dialog is not None and self.dialog.isVisible()

    def refresh_title(self) -> None:
        if self.dialog is not None:
            self.dialog.setWindowTitle(self._title())

    def _title(self) -> str:
        host = self.host
        return f"CGS Server · {host.version_label()} · pid {host.record.pid}"
