# -*- coding: utf-8 -*-
"""Existing subscription window with subscription and WebDAV pages."""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
)
from qfluentwidgets import InfoBar, InfoBarPosition, Pivot, ScrollArea, TransparentToolButton
from qframelesswindow import FramelessWindow
from qframelesswindow.utils import startSystemMove

from GUI.core.anim import PopupAnimator
from GUI.core.theme import CustTheme, theme_mgr
from GUI.core.theme.qss_template import render_templated_qss_section
from utils import ori_path
from utils.config.qc import cgs_cfg
from utils.subscription import SubscriptionStore
from utils.website.preprocess import site_db_path
from GUI.tools.addons.interface import AddonsInterface
from GUI.tools.rv.interface import RvInterface
from GUI.tools.subscribe.interface import SubscribeInterface

SUBSCRIBE_QSS_PATH = ori_path.joinpath("GUI/core/theme/subscribe.qss")
# hitomiTool 页的挂载门：与预处理下载目标同源（utils.website.preprocess.site_db_path）
HITOMI_DB_PATH = site_db_path("hitomi")

# pivot 项固定位次（与页面何时挂入无关）：rvTool / aggrSearch / hitomiTool / midTool / 订阅 / WebDAV / addons。
# hitomiTool 与 midTool 是懒构造页（db 门 / 无生产入口），挂载时机不定，顺序由本表决定。
PIVOT_ORDER = (
    "rvInterface", "asInterface", "htInterface", "midInterface",
    "subscribeInterface", "webdavInterface", "addonsInterface",
)

# 竖版窗口基准（宽 > 高）：最小宽 620、默认宽 660（仅首开用，之后以记忆几何为准）、默认高占屏幕 0.85 量级；最小高按 rv 表 10 行可见反推（10×38 行高 + 206 chrome ≈ 586 → 600 留余量）。
PORTRAIT_MIN_WIDTH = 620
PORTRAIT_DEFAULT_WIDTH = 660
PORTRAIT_MIN_HEIGHT = 600


class ToolWorkspaceWindow(FramelessWindow):
    # 构造期 super().__init__ 内 qframelesswindow 就会触发 move/resize 事件，此时实例属性
    # 尚未建立；用类级默认值兜底，_persist_ready 到 __init__ 末尾才放开几何落盘排程。
    _geometry_persist_timer: QTimer | None = None
    _persist_ready = False
    _first_show = True

    def __init__(self, parent=None, *, store: SubscriptionStore | None = None, share_api_factory=None, worker_client_factory=None):
        super().__init__()
        self.gui = parent
        self._closing = False
        self._theme_callback = self._apply_subscribe_qss
        self.setObjectName("ToolWorkspaceWindow")
        self.setWindowTitle("订阅管理")
        # ScriptWindow 同款生命周期：关闭即销毁、重开走全新构造——qfw 的边框样式/DWM 阴影
        # 只在构造期对新句柄施加一次，单例复用旧实例重开后会失去它们（不可拉伸+直角）。
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()
        self._restore_window_geometry()

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
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
        self.content_scroll.setObjectName("ToolWorkspaceScroll")
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
        self.rv_interface = RvInterface(self.gui, self.stackedWidget, host_window=self)
        # addons 页常驻：页壳无 DB/扫描不吃启动，cell 懒构造在页内（首次 show 才建）。
        self.addons_interface = AddonsInterface(self.gui, self.stackedWidget, host_window=self)
        for page, title in (
            (self.subscribe_interface, "订阅"),
            (self.webdav_interface, "webdav"),
            (self.rv_interface, "rvTool"),
            (self.addons_interface, "addons"),
        ):
            self._add_pivot_page(page, title)
        # aggrSearch / hitomiTool 非常驻：由 preprocess 按站点条件登记（gui.request_tool_page）后挂页——站点选择不建窗，页在建窗时或窗已在位时补挂（见 ensure_pending_pages），而非退化为「点按钮才建」。
        self.as_interface = None
        self.hitomi_interface = None  # 挂页门 = hitomi.db 存在（sqlite 查询不进窗开启路径）
        self.mid_interface = None  # 懒构造：首次 show_page("midInterface") 才建（无生产按钮，入口即 show_page 本身）
        self.stackedWidget.currentChanged.connect(self._on_page_changed)
        # 默认落 rvTool 页：与 pivot 首位一致，不经订阅页中转。
        # setCurrentWidget 触发 currentChanged → _on_page_changed 同步 pivot，避免两处各设一遍。
        self.stackedWidget.setCurrentWidget(self.rv_interface)
        theme_mgr.subscribe(self._theme_callback)
        self.destroyed.connect(self._unsubscribe_theme)
        self._apply_subscribe_qss(theme_mgr.get_theme())
        if sys.platform == "win32":
            import ctypes
            preference = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 33, ctypes.byref(preference), ctypes.sizeof(preference))
        self._persist_ready = True

    def _add_pivot_page(self, page: QWidget, title: str) -> None:
        """挂页 + 按 PIVOT_ORDER 把 pivot 项插到固定位次。

        插入位次 = 已在位且排在本页之前的项数，因此懒挂载页（hitomiTool / midTool）何时
        构造都不改变顺序；未登记进 PIVOT_ORDER 的 objectName 会直接 ValueError。
        """
        route_key = page.objectName()
        order = PIVOT_ORDER.index(route_key)
        index = sum(1 for key in self.pivot.items if PIVOT_ORDER.index(key) < order)
        self.stackedWidget.addWidget(page)
        self.pivot.insertItem(index, routeKey=route_key, text=title,
            onClick=lambda _checked=False, widget=page: self.stackedWidget.setCurrentWidget(widget))

    def infobar_surface(self):
        """本窗的提示承载面：当前 interface（见 async_task.resolve_infobar_host）。

        落点须为子 frame 而非窗本身——InfoBar 按 parent 的 rect 定位、按 parent().width()
        定换行，挂窗上会压住 pivot 头；挂当前页则与页内提示（如 addons 页 parent=self）同源。
        """
        return self.stackedWidget.currentWidget()

    def show_page(self, route_key: str) -> None:
        """显示子页统一入口：常驻页（rv / 订阅 / WebDAV）与懒挂载页（aggrSearch / hitomiTool / midTool）。

        各页前置差异（页对象 / 挂页门 / 懒构造）在 match 分支内处理；公共尾部（切页 + 展示窗）统一执行。
        常驻页在尾部额外同步 rv 上下文（sync_context）。
        hitomi 挂页门未过（db 缺失）提示后返回、不入页；未知 route_key 直接 ValueError。
        """
        sync_context = False
        match route_key:
            case "rvInterface":
                page = self.rv_interface
                sync_context = True
            case "subscribeInterface":
                page = self.subscribe_interface
                sync_context = True
            case "webdavInterface":
                page = self.webdav_interface
                sync_context = True
            case "asInterface":
                self.ensure_ags_page()
                page = self.as_interface
            case "htInterface":
                if not self.ensure_hitomi_page():
                    InfoBar.warning(
                        title="", content=f"未找到 hitomi 数据库 ({HITOMI_DB_PATH})",
                        position=InfoBarPosition.TOP, duration=3000, parent=self)
                    return
                page = self.hitomi_interface
            case "midInterface":
                if self.mid_interface is None:
                    from GUI.tools.mid_tool import MidToolInterface
                    self.mid_interface = MidToolInterface(self.gui)
                    self.mid_interface.setObjectName("midInterface")
                    self._add_pivot_page(self.mid_interface, "midTool")
                page = self.mid_interface
            case _:
                raise ValueError(f"unknown tool page {route_key!r}")
        self.stackedWidget.setCurrentWidget(page)
        self.show()
        self.raise_()
        self.activateWindow()
        if sync_context:
            self.gui.rv_mgr.sync_context()

    def ensure_ags_page(self) -> None:
        """挂 aggrSearch 页（只挂不显示窗），供 preprocess 与按钮入口共用。"""
        if self.as_interface is not None:
            return
        from GUI.tools.ags import AggrSearchView
        self.as_interface = AggrSearchView(self.gui, host_window=self)
        self.as_interface.setObjectName("asInterface")
        # aggrSearch 页自带 9px 内缩，挂进本窗时归零，与其他页对齐。
        self.as_interface.main_layout.setContentsMargins(0, 0, 0, 0)
        self._add_pivot_page(self.as_interface, "aggrSearch")

    def ensure_hitomi_page(self) -> bool:
        """挂 hitomiTool 页（只挂不显示窗）；db 门未过返回 False。

        与 preprocess 同门同源：db 缺失即不挂页。挂页与显示窗分离。
        """
        if self.hitomi_interface is not None:
            return True
        if not HITOMI_DB_PATH.exists():
            return False
        from GUI.tools.hitomi.interface import HitomiInterface
        self.hitomi_interface = HitomiInterface(self.gui, self.stackedWidget, host_window=self)
        self._add_pivot_page(self.hitomi_interface, "hitomiTool")
        return True

    def ensure_pending_pages(self, page_keys) -> None:
        """补挂站点预处理登记过的页（工作区窗首次建窗 / preprocess 时窗已在位）。"""
        for key in page_keys:
            if key == "htInterface":
                self.ensure_hitomi_page()
            elif key == "asInterface":
                self.ensure_ags_page()
            else:
                raise ValueError(f"unknown pending tool page {key!r}")

    def _on_page_changed(self, index: int) -> None:
        self.pivot.setCurrentItem(self.stackedWidget.widget(index).objectName())
        self.gui.rv_mgr.sync_context()

    def receive_pushed_books(self, books: list) -> None:
        self.show_page("subscribeInterface")
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
        if self._first_show:
            self._first_show = False
            # 工作区窗贴 SpiderGUI 右侧落位，故自右滑入。
            PopupAnimator.show(self, self.geometry(), duration_ms=220, direction="left")

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
            if self.hitomi_interface is not None:
                self.hitomi_interface.dispose()
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
        proposed = QRect(int(x), int(y), max(PORTRAIT_MIN_WIDTH, int(width)), max(PORTRAIT_MIN_HEIGHT, int(height)))
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
        self.setMinimumSize(min(PORTRAIT_MIN_WIDTH, fitted.width()), min(PORTRAIT_MIN_HEIGHT, fitted.height()))
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
            window_width = PORTRAIT_DEFAULT_WIDTH
            window_height = max(PORTRAIT_MIN_HEIGHT, int(screen_geo.height() * 0.85))
            anchor = self._gui_anchor()
            if anchor is None:
                x = screen_geo.x() + (screen_geo.width() - window_width) // 2
                y = screen_geo.y() + (screen_geo.height() - window_height) // 2
            else:
                x, y = anchor[0] - window_width, anchor[1] - window_height // 2
            self._apply_window_geometry(QRect(x, y, window_width, window_height))
        else:
            self._apply_window_geometry(QRect(0, 0, 660, 760))

    def _gui_anchor(self) -> tuple[int, int] | None:
        """初次落位锚点：(右边缘全局 x, 纵向中心全局 y)。

        右边缘对齐 SpiderGUI 气泡 svg（bubbleLabel）右边线，纵向中心对齐 SpiderGUI 中心；
        gui 不是 SpiderGUI（probe 裸 QWidget）或气泡未布局时返回 None，退回屏幕居中。
        """
        gui = self.gui
        bubble = getattr(gui, "bubbleLabel", None)
        if bubble is None or not isinstance(gui, QWidget) or not isinstance(bubble, QWidget):
            return None
        bubble_rect = bubble.rect()
        if bubble_rect.isEmpty() or gui.height() <= 0:
            return None
        return (
            bubble.mapToGlobal(QPoint(bubble_rect.right(), 0)).x(),
            gui.mapToGlobal(QPoint(0, gui.height() // 2)).y(),
        )

    def _persist_window_geometry(self) -> None:
        geometry = self._normalized_window_rect(self.x(), self.y(), self.width(), self.height())
        cgs_cfg.toolWorkspaceWinRect.value = [geometry.x(), geometry.y(), geometry.width(), geometry.height()]
        cgs_cfg.save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_geometry_persist()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._schedule_geometry_persist()

    def _schedule_geometry_persist(self) -> None:
        """拖拽/缩放停止 600ms 后落盘几何：托盘退出等路径不触发 closeEvent，仅靠关窗落盘会丢。"""
        if not self._persist_ready:
            return
        if self._geometry_persist_timer is None:
            self._geometry_persist_timer = QTimer(self)
            self._geometry_persist_timer.setSingleShot(True)
            self._geometry_persist_timer.timeout.connect(self._persist_window_geometry)
        self._geometry_persist_timer.start(600)
