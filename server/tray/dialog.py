from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget, Theme, setTheme

from server.tray.ui_common import ServerManageDialog, configure_tray_qt_fonts

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

    def show(self, tab_name: str = "Server") -> None:
        host = self.host
        if app := (host.qt_app or QApplication.instance()):
            configure_tray_qt_fonts(app)
        setTheme(Theme.AUTO, save=False)
        if self.dialog is not None:
            self.select(tab_name)
            self.refresh(rebuild_lists=True)
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
            return

        dialog = ServerManageDialog()
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
        self.select(tab_name)
        self.refresh(rebuild_lists=True)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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
