from pathlib import Path
import typing as t

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, FluentIcon as FIF, InfoBar, InfoBarPosition, PrimaryToolButton, StrongBodyLabel, 
    SubtitleLabel, TabBar, TabCloseButtonDisplayMode, ToolButton, TransparentToolButton
    )

from deploy import curr_os
from GUI.browser_window import BrowserWindow
from GUI.core.browser import BrowserChallengeCoordinator, BrowserChallengeSpec, BrowserRequestCaptureConfig
from GUI.core.theme import theme_mgr
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components import CountBadge
from utils.config.qc import danbooru_cfg, cgs_cfg
from utils.script.image.danbooru.constants import DANBOORU_BASE_URL, DANBOORU_SQL_TABLE
from utils.script.image.danbooru.http import DanbooruChallengeRequired, DanbooruResponseInspector
from utils.script.image.danbooru.models import DanbooruRuntimeConfig, DanbooruSearchQuery
from utils.script.image.danbooru.session import DanbooruBrowserSession, danbooru_browser_session_store
from utils.sql import SqlRecorder

from .core import DanbooruDownloadController, DanbooruSearchController, DanbooruTabState
from .detail_preview import DanbooruDetailPreviewController
from .style import (
    CARD_ZOOM_METRICS, DEFAULT_CARD_ZOOM_INDEX, DEFAULT_TAB_STATUS_CLASS, DEFAULT_TAB_STATUS_TEXT, DanbooruCardMetrics, DanbooruUiPalette, 
    build_interface_stylesheet, build_network_label_stylesheet, build_tip_line_stylesheet, build_title_label_stylesheet,
    format_tip_rich_text as _format_tip_rich_text, qcolor_from_css, reload_danbooru_qss,
)
from .tab import DanbooruTabWidget
from .viewer import DanbooruImageViewer

class DanbooruInterface(QFrame):
    download_result_signal = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("DanbooruInterface")
        self.task_mgr = AsyncTaskManager(self)
        self.tab_counter = 0
        self.tabs: dict[str, DanbooruTabWidget] = {}
        self.tab_states: dict[str, DanbooruTabState] = {}
        self._tab_tips: dict[str, tuple[str, str]] = {}
        self.sql_recorder = SqlRecorder(table=DANBOORU_SQL_TABLE)
        self.image_viewer = DanbooruImageViewer(parent)
        self.detail_preview_controller = DanbooruDetailPreviewController(self, self.image_viewer)
        self.search_controller = DanbooruSearchController(self)
        self.download_controller = DanbooruDownloadController(self)
        self._card_zoom_index = DEFAULT_CARD_ZOOM_INDEX
        self._runtime_config = DanbooruRuntimeConfig.from_conf()
        self._browser_challenge = BrowserChallengeCoordinator(
            window_factory=lambda: BrowserWindow(self._host_gui(), skip_env_mode=True),
            on_success=self._handle_verification_confirmed,
            on_missing=self._handle_verification_missing,
            parent=self,
        )
        self.download_result_signal.connect(self.download_controller.on_download_result)
        self.image_viewer.tag_clicked.connect(self._open_tag_jump_tab)
        self.image_viewer.download_requested.connect(self.download_controller.submit_single)
        self.image_viewer.previous_requested.connect(lambda: self.detail_preview_controller.open_adjacent(-1))
        self.image_viewer.next_requested.connect(lambda: self.detail_preview_controller.open_adjacent(1))
        self.image_viewer.closed.connect(self.detail_preview_controller.clear_context)
        theme_mgr.subscribe(self._apply_theme)
        self.setupUi()
        self._apply_theme()
        self.create_tab()

    def setupUi(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 14)
        self.main_layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 20, 0)
        title_row.setSpacing(4)
        self.title_block = QWidget(self)
        self.title_block.setObjectName("DanbooruTitleBlock")
        title_block_layout = QHBoxLayout(self.title_block)
        title_block_layout.setContentsMargins(16, 12, 16, 12)
        title_block_layout.setSpacing(16)
        self.title_label = SubtitleLabel("Danbooru", self)
        self.tip_line = StrongBodyLabel("", self)
        self.tip_line.setTextFormat(Qt.RichText)
        self.tip_line.setObjectName("DanbooruTipLine")
        self.network_label = BodyLabel("", self)
        self.network_label.setObjectName("DanbooruNetworkLabel")
        title_block_layout.addWidget(self.title_label)
        title_block_layout.addWidget(self.tip_line, 1)
        # title_block_layout.addWidget(self.network_label)  # 当前 doh 没恢复时禁止恢复注释
        zoomBtnGroup = QVBoxLayout()
        zoomBtnGroup.setContentsMargins(2,0,2,0)
        zoomBtnGroup.setSpacing(0)
        self.zoomIn = ToolButton(QIcon(':/script/zoomin.svg'))
        self.zoomIn.setToolTip("放大卡片")
        self.zoomIn.setMaximumHeight(22)
        self.zoomOut = ToolButton(QIcon(':/script/zoomout.svg'))
        self.zoomOut.setToolTip("缩小卡片")
        self.zoomOut.setMaximumHeight(22)
        self.zoomIn.clicked.connect(self._zoom_in_cards)
        self.zoomOut.clicked.connect(self._zoom_out_cards)
        zoomBtnGroup.addWidget(self.zoomIn)
        zoomBtnGroup.addWidget(self.zoomOut)
        self.openBtn = ToolButton(FIF.FOLDER)
        self.openBtn.setToolTip("打开下载目录")
        self.openBtn.setMinimumHeight(50)
        self.openBtn.clicked.connect(self._open_save_path)
        self.batch_download_btn = PrimaryToolButton(FIF.DOWNLOAD, self)
        self.batch_download_btn.setMinimumHeight(50)
        self.batch_download_btn.setMinimumWidth(80)
        self.batch_download_btn.setIconSize(QtCore.QSize(20, 20))
        self.batch_download_btn.setDisabled(True)
        self.batch_download_btn.clicked.connect(self.download_controller.submit_selected)
        self.batch_download_badge = CountBadge(parent=self, target=self.batch_download_btn)
        self.batch_download_badge.hide()
        title_row.addWidget(self.title_block, 1)
        title_row.addLayout(zoomBtnGroup)
        title_row.addWidget(self.openBtn)
        title_row.addWidget(self.batch_download_btn)
        self.main_layout.addLayout(title_row)

        self.pivot_shell = QFrame(self)
        self.pivot_shell.setObjectName("DanbooruPivotShell")
        self.pivot_shell.setMinimumHeight(34)
        pivot_shell_layout = QHBoxLayout(self.pivot_shell)
        pivot_shell_layout.setContentsMargins(14, 2, 14, 2)
        pivot_shell_layout.setSpacing(8)
        self.pivot_back_btn = TransparentToolButton(FIF.LEFT_ARROW, self.pivot_shell)
        self.pivot_back_btn.setObjectName("DanbooruPivotScrollButton")
        self.pivot_back_btn.setFixedSize(18, 18)
        self.pivot_back_btn.setIconSize(QtCore.QSize(14, 14))
        self.pivot_back_btn.setToolTip("向左滚动标签")
        self.pivot_back_btn.clicked.connect(lambda: self._scroll_pivot_tabs(-1))
        pivot_shell_layout.addWidget(self.pivot_back_btn, 0, Qt.AlignVCenter)
        self.tab_bar = TabBar(self.pivot_shell)
        self.tab_bar.setObjectName("DanbooruPivotScrollArea")
        self.tab_bar.view.setObjectName("DanbooruPivotTabBarView")
        self.tab_bar.setAddButtonVisible(False)
        self.tab_bar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.ON_HOVER)
        self.tab_bar.setTabShadowEnabled(False)
        self.tab_bar.setTabMaximumWidth(148)
        self.tab_bar.setTabMinimumWidth(96)
        self.tab_bar.enableTransparentBackground()
        self.tab_bar.itemLayout.setContentsMargins(0, 5, 0, 5)
        self.tab_bar.itemLayout.setSpacing(6)
        self.pivot_scroll = self.tab_bar
        self.tab_bar.currentChanged.connect(self._on_tabbar_index_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        pivot_shell_layout.addWidget(self.tab_bar, 1)
        self.pivot_forward_btn = TransparentToolButton(FIF.RIGHT_ARROW, self.pivot_shell)
        self.pivot_forward_btn.setObjectName("DanbooruPivotScrollButton")
        self.pivot_forward_btn.setFixedSize(18, 18)
        self.pivot_forward_btn.setIconSize(QtCore.QSize(14, 14))
        self.pivot_forward_btn.setToolTip("向右滚动标签")
        self.pivot_forward_btn.clicked.connect(lambda: self._scroll_pivot_tabs(1))
        pivot_shell_layout.addWidget(self.pivot_forward_btn, 0, Qt.AlignVCenter)
        pivot_scroll_bar = self.pivot_scroll.horizontalScrollBar()
        pivot_scroll_bar.rangeChanged.connect(lambda *_args: self._sync_pivot_scroll_controls())
        pivot_scroll_bar.valueChanged.connect(lambda *_args: self._sync_pivot_scroll_controls())
        self.main_layout.addWidget(self.pivot_shell)

        self.content_shell = QFrame(self)
        self.content_shell.setObjectName("DanbooruContentShell")
        content_shell_layout = QVBoxLayout(self.content_shell)
        content_shell_layout.setContentsMargins(12, 12, 12, 12)
        content_shell_layout.setSpacing(0)
        self.stacked_widget = QStackedWidget(self.content_shell)
        self.stacked_widget.currentChanged.connect(self._on_current_tab_changed)
        content_shell_layout.addWidget(self.stacked_widget)
        self.main_layout.addWidget(self.content_shell, 1)

    def _apply_theme(self, *_args):
        palette = DanbooruUiPalette.current()
        self.setStyleSheet(build_interface_stylesheet(palette))
        self.title_label.setStyleSheet(build_title_label_stylesheet(palette))
        self.tip_line.setStyleSheet(build_tip_line_stylesheet(palette))
        self.network_label.setStyleSheet(build_network_label_stylesheet(palette))
        self.tab_bar.setTabShadowEnabled(False)
        selected_color = qcolor_from_css(palette.pivot_selected)
        self.tab_bar.setTabSelectedBackgroundColor(selected_color, selected_color)
        self.image_viewer.apply_theme()
        for tab in self.tabs.values():
            tab.apply_theme()
        self._update_tab_chrome()
        self._sync_tip_line()
        self.refresh_runtime_settings()
        self._update_zoom_buttons()
        self._sync_tab_bar_width()

    def create_tab(self, initial_query: str = "", auto_search: bool = False):
        self.tab_counter += 1
        tab_id = f"danbooru-tab-{self.tab_counter}"
        state = DanbooruTabState(
            tab_id=tab_id,
            title=self._display_title_for_query(initial_query, self.tab_counter),
            query=DanbooruSearchQuery.normalize(initial_query),
        )
        tab = DanbooruTabWidget(state, self)
        tab.setObjectName(tab_id)
        tab.set_card_metrics(self._current_card_metrics())
        tab.request_search.connect(lambda query, tid=tab_id: self.search_controller.start_search(tid, query))
        tab.request_conversion.connect(lambda tid=tab_id: self.search_controller.convert_term(tid))
        tab.request_single_download.connect(lambda post, tid=tab_id: self.download_controller.submit_single(post, tid))
        tab.request_tag_jump.connect(self._open_tag_jump_tab)
        tab.request_next_page.connect(lambda tid=tab_id: self.search_controller.load_next_page(tid))
        tab.detail_opened.connect(lambda post, tid=tab_id: self.detail_preview_controller.open_viewer(tid, post))
        tab.selection_count_changed.connect(lambda _count, tid=tab_id: self._update_batch_button(tid))
        tab.search_edit.textChanged.connect(lambda _text, current_tab=tab: self._update_favorite_button_state(current_tab))
        self.tabs[tab_id] = tab
        self.tab_states[tab_id] = state
        self._tab_tips[tab_id] = (DEFAULT_TAB_STATUS_TEXT, DEFAULT_TAB_STATUS_CLASS)
        self.stacked_widget.addWidget(tab)
        self.tab_bar.addTab(routeKey=tab_id, text=state.title)
        self._sync_tab_bar_width()
        self._set_current_tab(tab_id)
        self._update_tab_chrome()
        self._refresh_completer(tab)
        if state.query:
            tab.search_edit.setText(state.query)
            if auto_search:
                self.search_controller.start_search(tab_id, state.query)
        if self._active_tab_id() == tab_id:
            self._sync_tip_line(tab_id)
        return tab_id

    def close_current_tab(self):
        self._close_tab_by_id(self._active_tab_id())

    def _close_tab_by_id(self, tab_id: t.Optional[str]):
        if len(self.tabs) <= 1:
            return
        if not tab_id:
            return
        tab = self.tabs.pop(tab_id, None)
        self.tab_states.pop(tab_id, None)
        self._tab_tips.pop(tab_id, None)
        if tab is None:
            return
        if self.detail_preview_controller.current_tab_id == tab_id and self.image_viewer.isVisible():
            self.image_viewer.hide()
            self.detail_preview_controller.clear_context()
        self.tab_bar.removeTabByKey(tab_id)
        self.stacked_widget.removeWidget(tab)
        tab.deleteLater()
        if self.stacked_widget.count():
            self._set_current_tab(self.stacked_widget.widget(0).objectName())
        self._update_tab_chrome()
        self._sync_tab_bar_width()

    def _set_current_tab(self, tab_id: str):
        tab = self.tabs.get(tab_id)
        if tab is None:
            return
        self.stacked_widget.setCurrentWidget(tab)
        self.tab_bar.setCurrentTab(tab_id)
        self._update_batch_button(tab_id)

    def _on_current_tab_changed(self, _index: int):
        widget = self.stacked_widget.currentWidget()
        if widget is None:
            return
        self.tab_bar.setCurrentTab(widget.objectName())
        self._update_batch_button(widget.objectName())
        self._update_tab_chrome()
        self._sync_tip_line(widget.objectName())

    def _on_tabbar_index_changed(self, index: int):
        tab_id = self._tab_id_at(index)
        if tab_id:
            self._set_current_tab(tab_id)

    def _on_tab_close_requested(self, index: int):
        self._close_tab_by_id(self._tab_id_at(index))

    def _tab_id_at(self, index: int) -> t.Optional[str]:
        if not 0 <= index < self.tab_bar.count():
            return None
        return self.tab_bar.tabItem(index).routeKey()

    def _tab_index(self, tab_id: str) -> int:
        item = self.tab_bar.tab(tab_id)
        return self.tab_bar.items.index(item) if item is not None else -1

    @staticmethod
    def _display_title_for_query(query: str, tab_index: int) -> str:
        canonical = DanbooruSearchQuery.normalize(query)
        if not canonical:
            return f"工作区 {tab_index}"
        if len(canonical) <= 18:
            return canonical
        return canonical[:16].rstrip() + ".."

    def _update_tab_title(self, tab_id: str, query: str):
        state = self.tab_states.get(tab_id)
        if state is None:
            return
        title = self._display_title_for_query(query, int(tab_id.rsplit("-", 1)[-1]))
        if title == state.title:
            return
        state.title = title
        index = self._tab_index(tab_id)
        if index >= 0:
            self.tab_bar.setTabText(index, state.title)
        self._update_tab_chrome()
        self._sync_tab_bar_width()

    def _update_tab_chrome(self):
        palette = DanbooruUiPalette.current()
        current_tab_id = self._active_tab_id()
        active_text_color = qcolor_from_css(palette.text)
        inactive_text_color = qcolor_from_css(palette.muted_text)
        self.tab_bar.setTabsClosable(len(self.tabs) > 1)
        for index in range(self.tab_bar.count()):
            item = self.tab_bar.tabItem(index)
            if item is None:
                continue
            tab_id = item.routeKey()
            state = self.tab_states.get(tab_id)
            item.setBorderRadius(12)
            self.tab_bar.setTabToolTip(index, state.title if state is not None else item.text())
            self.tab_bar.setTabTextColor(
                index,
                active_text_color if tab_id == current_tab_id else inactive_text_color,
            )

    def _active_tab_id(self) -> t.Optional[str]:
        widget = self.stacked_widget.currentWidget()
        return widget.objectName() if widget is not None else None

    def _set_tab_tip(self, tab_id: str, text: str, cls: str = DEFAULT_TAB_STATUS_CLASS):
        self._tab_tips[tab_id] = (text, cls or DEFAULT_TAB_STATUS_CLASS)
        if self._active_tab_id() == tab_id:
            self.tip_line.setText(_format_tip_rich_text(*self._tab_tips[tab_id]))

    def _sync_tip_line(self, tab_id: t.Optional[str] = None):
        effective_tab_id = tab_id or self._active_tab_id()
        text, cls = self._tab_tips.get(effective_tab_id, (DEFAULT_TAB_STATUS_TEXT, DEFAULT_TAB_STATUS_CLASS))
        self.tip_line.setText(_format_tip_rich_text(text, cls))

    def _current_card_metrics(self) -> DanbooruCardMetrics:
        return CARD_ZOOM_METRICS[self._card_zoom_index]

    def _apply_card_metrics(self):
        metrics = self._current_card_metrics()
        for tab in self.tabs.values():
            tab.set_card_metrics(metrics)
        self._update_zoom_buttons()

    def _zoom_in_cards(self):
        if self._card_zoom_index >= len(CARD_ZOOM_METRICS) - 1:
            return
        self._card_zoom_index += 1
        self._apply_card_metrics()

    def _zoom_out_cards(self):
        if self._card_zoom_index <= 0:
            return
        self._card_zoom_index -= 1
        self._apply_card_metrics()

    def _update_zoom_buttons(self):
        self.zoomIn.setEnabled(self._card_zoom_index < len(CARD_ZOOM_METRICS) - 1)
        self.zoomOut.setEnabled(self._card_zoom_index > 0)

    def _scroll_pivot_tabs(self, direction: int):
        bar = self.pivot_scroll.horizontalScrollBar()
        if bar.maximum() <= bar.minimum():
            return
        step = max(72, int(self.pivot_scroll.viewport().width() * 0.72))
        bar.setValue(bar.value() + direction * step)

    def _sync_pivot_scroll_controls(self):
        if not hasattr(self, "pivot_scroll"):
            return
        bar = self.pivot_scroll.horizontalScrollBar()
        has_overflow = bar.maximum() > bar.minimum()
        self.pivot_back_btn.setEnabled(has_overflow and bar.value() > bar.minimum())
        self.pivot_forward_btn.setEnabled(has_overflow and bar.value() < bar.maximum())

    def _sync_tab_bar_width(self):
        if not hasattr(self, "tab_bar"):
            return
        self.tab_bar.view.adjustSize()
        self.tab_bar.updateGeometry()
        QtCore.QTimer.singleShot(0, self._sync_pivot_scroll_controls)

    def _open_save_path(self):
        curr_os.open_folder(Path(self._runtime_config.save_path))

    def _update_batch_button(self, tab_id: str):
        if self._active_tab_id() != tab_id:
            return
        state = self.tab_states.get(tab_id)
        count = len(state.selected_md5_set) if state else 0
        self.batch_download_btn.setDisabled(count == 0)
        if count <= 0:
            self.batch_download_badge.hide()
            return
        self.batch_download_badge.set_count(count)
        self.batch_download_badge.show()

    def apply_downloaded_post(self, md5_value: str):
        for tab in self.tabs.values():
            tab.apply_downloaded_state(md5_value)
        if self.detail_preview_controller.matches(md5=md5_value):
            self.image_viewer.set_download_state(True)
        self.detail_preview_controller.sync_navigation()

    def _gui_logger(self):
        return getattr(getattr(self.parent_window, "gui", None), "log", None)

    def _host_gui(self):
        return getattr(self.parent_window, "gui", None) or self.parent_window

    def _show_task_error(self, prefix: str, error: str, duration: int = 6000):
        logger = self._gui_logger()
        if logger is not None:
            logger.error(error)
        summary = (error.splitlines() or ["unknown error"])[0]
        self._show_info(InfoBar.error, f"{prefix}: {summary}", duration)

    def _log_search_request(self, tab_id: str, query: str, order: str, page: int, limit: int):
        logger = self._gui_logger()
        if logger is None:
            return
        params = DanbooruSearchQuery(query, order).params(page=page, limit=limit)
        stub_endpoint = self._runtime_config.stub_dns_endpoint() or "disabled"
        logger.info(
            f"[Danbooru] GET /posts.json tab={tab_id} params={params} dns={self._runtime_config.request_dns_summary()} stub={stub_endpoint}"
        )

    def refresh_runtime_settings(self):
        self._runtime_config = DanbooruRuntimeConfig.from_conf()
        # self.network_label.setText(self._runtime_config.network_label())
        # self.network_label.setToolTip(self._runtime_config.network_tooltip())

    def _update_favorite_button_state(self, tab: DanbooruTabWidget, term: t.Optional[str] = None):
        canonical_term = DanbooruSearchQuery.normalize(term if term is not None else tab.search_edit.text())
        is_favorited = bool(canonical_term and canonical_term in danbooru_cfg.get_favorites())
        tab.favorite_btn.setToolTip("取消收藏搜索词" if is_favorited else "收藏搜索词")

    def _refresh_completer(self, tab: DanbooruTabWidget):
        history = danbooru_cfg.get_history()
        favorites = sorted(danbooru_cfg.get_favorites() - set(history))
        tab.update_completer(history + favorites)
        try:
            tab.favorite_btn.clicked.disconnect()
        except TypeError:
            pass
        tab.favorite_btn.clicked.connect(lambda _=False, tid=tab.state.tab_id: self._toggle_favorite(tid))
        self._update_favorite_button_state(tab)

    def _show_info(self, factory, content: str, duration: int = 3000):
        factory(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=self,
        )

    def handle_danbooru_challenge(
        self,
        tab_id: str,
        challenge: DanbooruChallengeRequired,
        retry_callback: t.Callable[[], None],
        *,
        reason: str,
        retry_key: str,
    ):
        normalized_reason = str(reason or "请求").strip() or "请求"
        self._set_tab_tip(tab_id, f"Danbooru {normalized_reason}需要网页验证，完成后会自动重试", cls="theme-tip")
        self._browser_challenge.submit(
            self._build_verification_spec(challenge),
            tab_id=tab_id,
            retry_key=str(retry_key or f"{tab_id}:{normalized_reason}"),
            retry_callback=retry_callback,
        )

    def _build_verification_spec(self, challenge: DanbooruChallengeRequired) -> BrowserChallengeSpec:
        return BrowserChallengeSpec(
            challenge.verify_url,
            domain_filter="danbooru.donmai.us",
            source_url=challenge.verify_url,
            doh_url=cgs_cfg.get_doh_url(),
            window_size=QtCore.QSize(980, 760),
            window_title="Danbooru Verification",
            completion_detector=DanbooruResponseInspector.is_verification_completion_url,
            request_capture=BrowserRequestCaptureConfig(host_filter="danbooru.donmai.us"),
        )

    def _handle_verification_missing(self, result, tab_ids: list[str]):
        logger = self._gui_logger()
        if logger is not None:
            logger.warning(
                f"[Danbooru] browser verification transfer missing trigger={result.trigger} "
                f"current_url={result.current_url or '<unknown>'}"
            )
        for tab_id in tab_ids:
            self._set_tab_tip(tab_id, "验证页已返回，但没有采集到可回灌的请求头或 Cookie", cls="theme-err")
        self._show_info(InfoBar.warning, "Danbooru 验证页已返回，但没有采集到可回灌的请求头或 Cookie", 5000)

    def _handle_verification_confirmed(
        self,
        result,
        retry_callbacks: list[t.Callable[[], None]],
        tab_ids: list[str],
    ):
        merged_cookies = DanbooruBrowserSession.merge_cookies(
            list(result.live_cookies),
            list(result.snapshot_cookies),
        )
        headers = dict(result.headers or {})
        effective_source_url = result.source_url or result.current_url or DANBOORU_BASE_URL
        if effective_source_url and "referer" not in {name.casefold() for name in headers}:
            headers["Referer"] = effective_source_url
        session = danbooru_browser_session_store.update(
            cookies=merged_cookies,
            user_agent=result.user_agent,
            headers=headers,
            source_url=effective_source_url,
        )
        logger = self._gui_logger()
        if logger is not None:
            logger.info(
                f"[Danbooru] browser verification session synced cookies={len(session.cookies)} "
                f"headers={len(session.headers)} retries={len(retry_callbacks)} "
                f"current_url={result.current_url or '<unknown>'}"
            )
        for tab_id in tab_ids:
            cookie_text = f"{len(session.cookies)} 个 Cookie" if session.cookies else "0 个 Cookie"
            header_text = f"{len(session.headers)} 个 Header"
            self._set_tab_tip(tab_id, f"已同步浏览器验证态({cookie_text}, {header_text})，正在重试", cls="theme-success")
        self._show_info(InfoBar.success, "Danbooru 浏览器验证态已同步，正在重试请求", 4000)
        for retry_callback in retry_callbacks:
            retry_callback()

    def _toggle_favorite(self, tab_id: str):
        tab = self.tabs.get(tab_id)
        if tab is None:
            return
        term = DanbooruSearchQuery.normalize(tab.search_edit.text())
        if not term:
            self._update_favorite_button_state(tab, term)
            return
        is_favorited = danbooru_cfg.toggle_favorite(term)
        self._refresh_completer(tab)
        self._update_favorite_button_state(tab, term)
        self._show_info(InfoBar.success if is_favorited else InfoBar.warning, f"{'已收藏' if is_favorited else '已取消收藏'}搜索词: {term}")

    def _open_tag_jump_tab(self, tag: str):
        self.image_viewer.hide()
        self.detail_preview_controller.clear_context()
        canonical_tag = DanbooruSearchQuery.normalize(tag)
        if not canonical_tag:
            return
        for tab_id, state in self.tab_states.items():
            if DanbooruSearchQuery.normalize(state.query) == canonical_tag:
                self._set_current_tab(tab_id)
                tab = self.tabs.get(tab_id)
                if tab is not None and not state.result_list and not state.loading:
                    self.search_controller.start_search(tab_id, canonical_tag)
                return
        active_tab_id = self._active_tab_id()
        active_state = self.tab_states.get(active_tab_id) if active_tab_id else None
        if active_tab_id and active_state and not active_state.query and not active_state.result_list and not active_state.loading:
            active_state.query = canonical_tag
            self.tabs[active_tab_id].search_edit.setText(canonical_tag)
            self.search_controller.start_search(active_tab_id, canonical_tag)
            return
        self.create_tab(initial_query=canonical_tag, auto_search=True)

    def notify_download_result(self, md5_value: str, success: bool):
        self.download_result_signal.emit(md5_value, success)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_tab_bar_width()

    def closeEvent(self, event):
        try:
            theme_mgr.unsubscribe(self._apply_theme)
            self.image_viewer.hide()
            self.sql_recorder.close()
        finally:
            super().closeEvent(event)
