# -*- coding: utf-8 -*-
"""Existing subscription window with subscription and WebDAV pages."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QAbstractButton, QApplication, QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout
from qfluentwidgets import InfoBar, InfoBarPosition, Pivot, ScrollArea, TransparentToolButton
from qframelesswindow import FramelessWindow
from qframelesswindow.utils import startSystemMove

from GUI.core.theme import CustTheme, theme_mgr
from GUI.core.theme.qss_template import render_templated_qss_section
from utils import ori_path
from utils.config.qc import cgs_cfg
from utils.subscription import SubscriptionStore
from GUI.tools.subscribe.interface import SubscribeInterface

SUBSCRIBE_QSS_PATH = ori_path.joinpath("GUI/core/theme/subscribe.qss")


class ToolWorkspaceWindow(FramelessWindow):
    def __init__(self, parent=None, *, store: SubscriptionStore | None = None, share_api_factory=None, worker_client_factory=None):
        super().__init__()
        self.gui = parent
        self._closing = False
        self._theme_callback = self._apply_subscribe_qss
        self.setObjectName("ToolWorkspaceWindow")
        self.setWindowTitle("订阅管理")
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        self._restore_window_geometry()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 14)
        root.setSpacing(8)
        self.header_shell = QFrame(self)
        self.header_shell.setObjectName("SubscribeHeaderShell")
        self.header_shell.installEventFilter(self)
        header = QHBoxLayout(self.header_shell)
        header.setContentsMargins(14, 6, 8, 6)
        self.pivot = Pivot(self.header_shell)
        header.addWidget(self.pivot)
        header.addStretch(1)
        self.close_button = TransparentToolButton(self.header_shell)
        self.close_button.setIcon(QIcon(":/close.svg"))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setAccessibleName("关闭")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        root.addWidget(self.header_shell)
        self.content_scroll = ScrollArea(self)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.stackedWidget = QStackedWidget(self.content_scroll)
        self.content_scroll.setWidget(self.stackedWidget)
        root.addWidget(self.content_scroll, 1)

        from GUI.tools.webdav.interface import WebdavInterface
        self.subscribe_interface = SubscribeInterface(
            self.gui, self.stackedWidget, store=store, share_api_factory=share_api_factory, worker_client_factory=worker_client_factory)
        self.webdav_interface = WebdavInterface(self.gui, self.stackedWidget)
        self.webdav_interface.setObjectName("webdavInterface")
        for page, title in ((self.subscribe_interface, "订阅"), (self.webdav_interface, "WebDAV")):
            self.stackedWidget.addWidget(page)
            self.pivot.addItem(routeKey=page.objectName(), text=title,
                onClick=lambda _checked=False, widget=page: self.stackedWidget.setCurrentWidget(widget))
        self.stackedWidget.currentChanged.connect(self._on_page_changed)
        self.pivot.setCurrentItem(self.subscribe_interface.objectName())
        theme_mgr.subscribe(self._theme_callback)
        self.destroyed.connect(self._unsubscribe_theme)
        self._apply_subscribe_qss(theme_mgr.get_theme())

    def show_subscribe(self) -> None:
        self.stackedWidget.setCurrentWidget(self.subscribe_interface)
        self.show()
        self.raise_()
        self.activateWindow()
        self.gui.rv_mgr.sync_context()

    def show_webdav(self) -> None:
        self.stackedWidget.setCurrentWidget(self.webdav_interface)
        self.show()
        self.raise_()
        self.activateWindow()
        self.gui.rv_mgr.sync_context()

    def _on_page_changed(self, index: int) -> None:
        self.pivot.setCurrentItem(self.stackedWidget.widget(index).objectName())
        self.gui.rv_mgr.sync_context()

    def receive_pushed_books(self, books: list) -> None:
        self.show_subscribe()
        self.subscribe_interface.receive_pushed_books(books)

    def refresh_library(self) -> None:
        self.subscribe_interface.refresh_library()

    def has_active_work(self) -> bool:
        return self.subscribe_interface.has_active_work() or self.webdav_interface.has_active_work()

    def server_mode_switch_blockers(self) -> list[str]:
        return self.subscribe_interface.server_mode_switch_blockers() + self.webdav_interface.server_mode_switch_blockers()

    def showEvent(self, event) -> None:
        self._closing = False
        self._apply_window_geometry(self.geometry())
        super().showEvent(event)

    def closeEvent(self, event) -> None:
        if self.has_active_work():
            InfoBar.warning(title="", content="请先等待当前任务完成", position=InfoBarPosition.TOP, duration=3000, parent=self)
            event.ignore()
            return
        if not self._closing:
            self._closing = True
            self._persist_window_geometry()
            self.subscribe_interface.shutdown()
            self.webdav_interface.shutdown()
        super().closeEvent(event)

    def _unsubscribe_theme(self, *_args) -> None:
        theme_mgr.unsubscribe(self._theme_callback)

    def _apply_subscribe_qss(self, theme=None) -> None:
        current = theme if theme is not None else theme_mgr.get_theme()
        theme_name = current.value if isinstance(current, CustTheme) else "light"
        self.setStyleSheet(render_templated_qss_section(SUBSCRIBE_QSS_PATH, theme_name, "window"))

    def eventFilter(self, obj, event):
        if obj is self.header_shell and event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            hit = self.header_shell.childAt(event.position().toPoint())
            while hit is not None and hit is not self.header_shell:
                if isinstance(hit, QAbstractButton):
                    return super().eventFilter(obj, event)
                hit = hit.parentWidget()
            startSystemMove(self, event.globalPosition().toPoint())
            return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _normalized_window_rect(x: int, y: int, width: int, height: int) -> QRect:
        """Fit restored geometry into its current screen's logical work area."""
        proposed = QRect(int(x), int(y), max(900, int(width)), max(560, int(height)))
        screens = QApplication.screens()
        if not screens:
            return proposed

        def overlap_area(screen):
            intersection = screen.availableGeometry().intersected(proposed)
            return intersection.width() * intersection.height()

        screen = max(screens, key=overlap_area)
        if overlap_area(screen) == 0:
            screen = QApplication.primaryScreen() or screen
            proposed.moveCenter(screen.availableGeometry().center())
        available = screen.availableGeometry()
        width = min(proposed.width(), available.width())
        height = min(proposed.height(), available.height())
        x = max(available.x(), min(proposed.x(), available.right() - width + 1))
        y = max(available.y(), min(proposed.y(), available.bottom() - height + 1))
        return QRect(x, y, width, height)

    def _apply_window_geometry(self, rect: QRect) -> None:
        fitted = self._normalized_window_rect(rect.x(), rect.y(), rect.width(), rect.height())
        self.setMinimumSize(min(900, fitted.width()), min(560, fitted.height()))
        self.setGeometry(fitted)

    def _restore_window_geometry(self) -> None:
        saved_rect = cgs_cfg.toolWorkspaceWinRect.value
        if not saved_rect:
            # One-time migration: inherit the deprecated legacy key, then persist under the new key.
            legacy_rect = cgs_cfg.subscribeWinRect.value
            if legacy_rect:
                saved_rect = legacy_rect
                cgs_cfg.toolWorkspaceWinRect.value = saved_rect
                cgs_cfg.save()
        if saved_rect and len(saved_rect) >= 4:
            x, y, width, height = (int(value) for value in saved_rect[:4])
            self._apply_window_geometry(QRect(x, y, width, height))
            return
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.availableGeometry() if screen is not None else None
        if screen_geo is not None:
            window_width = max(980, int(screen_geo.width() * 0.82))
            window_height = max(640, int(screen_geo.height() * 0.82))
            self._apply_window_geometry(QRect(
                screen_geo.x() + (screen_geo.width() - window_width) // 2,
                screen_geo.y() + (screen_geo.height() - window_height) // 2, window_width, window_height))
        else:
            self._apply_window_geometry(QRect(0, 0, 1100, 720))

    def _persist_window_geometry(self) -> None:
        geometry = self._normalized_window_rect(self.x(), self.y(), self.width(), self.height())
        cgs_cfg.toolWorkspaceWinRect.value = [geometry.x(), geometry.y(), geometry.width(), geometry.height()]
        cgs_cfg.save()
