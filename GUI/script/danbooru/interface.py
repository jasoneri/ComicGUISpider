import gc
import shutil
import typing as t
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QStackedWidget, QTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action, ComboBox, FluentIcon as FIF, InfoBar, InfoBarPosition, PrimaryToolButton, ProgressBar, RoundMenu,
    StrongBodyLabel, SubtitleLabel, TabBar, TabCloseButtonDisplayMode, TeachingTipTailPosition, ToolButton,
    TransparentToolButton
    )

from deploy import curr_os
from GUI.core.theme import theme_mgr
from GUI.manager.async_task import AsyncTaskManager, summarize_error_message
from GUI.uic.qfluent.components import CountBadge, CustomInfoBar, CustomTeachingTip
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.script.image.danbooru.client import DanbooruClient
from utils.config.qc import danbooru_cfg
from utils.script.image.danbooru.constants import DANBOORU_SAVE_TYPE_SEARCH_TAG, DANBOORU_SQL_TABLE
from utils.script.image.danbooru.models import DanbooruRuntimeConfig, DanbooruSearchQuery
from utils.script import folder_sub
from utils.sql import SqlRecorder

from .challenge import DanbooruChallengeController
from .core import DanbooruDownloadController, DanbooruSearchController, DanbooruTabState
from .detail_preview import DetailPreviewController
from .favorite_groups import build_favorite_groups_state
from .favorites import DanbooruFavoriteManagerDialog
from .style import (
    CARD_ZOOM_METRICS, DEFAULT_TAB_STATUS_CLASS, DanbooruCardMetrics, DanbooruUiPalette, default_tab_status_text,
    build_interface_stylesheet, build_tip_line_stylesheet, build_title_label_stylesheet,
    format_tip_rich_text as _format_tip_rich_text, qcolor_from_css,
)
from .tab import DanbooruTabWidget
from .video_proxy import VideoProxy
from .viewer import DanbooruImageViewer


class DanbooruFuncs:
    def __init__(self, parentInterface: "DanbooruInterface"):
        self.parentInterface = parentInterface
        self.func_menu = None
        self._merge_floder_tip = None

    def open_menu(self):
        func_menu = RoundMenu(parent=self.parentInterface.funcBtn)
        merge_floder_action = Action(CgsIcon.SCRIPT_MERGE_FLODER.icon(), text='整合目录')
        merge_floder_action.triggered.connect(lambda *_: self.merge_floder())
        func_menu.addAction(merge_floder_action)
        self.func_menu = func_menu
        func_menu.exec(self.parentInterface.funcBtn.mapToGlobal(self.parentInterface.funcBtn.rect().bottomLeft()))

    def merge_floder(self):
        merge_floder_queue = self._build_merge_floder_queue()
        if not merge_floder_queue:
            return
        progress_bar = ProgressBar(self.parentInterface)
        progress_bar.setRange(0, len(merge_floder_queue))
        progress_bar.setValue(0)
        if self._merge_floder_tip is not None:
            self._merge_floder_tip.close()
        tip = CustomTeachingTip.create(
            [progress_bar], target=self.parentInterface.funcBtn, parent=self.parentInterface, tailPosition=TeachingTipTailPosition.RIGHT
        )
        self._merge_floder_tip = tip
        tip.destroyed.connect(lambda *_args, current_tip=tip: self._clear_merge_floder_tip(current_tip))

        def update_progress(value: str):
            done = int(value)
            progress_bar.setValue(done)
            if done >= progress_bar.maximum():
                progress_bar.setCustomBarColor(light="#00ff00", dark="#00cc00")

        self.parentInterface.task_mgr.execute_simple_task(
            self._process_merge_floder_queue,
            progress_callback=update_progress, show_success_info=False, show_error_info=True, show_tooltip=False,
            task_id="danbooru-merge-floder", merge_floder_queue=merge_floder_queue,
        )

    def _clear_merge_floder_tip(self, tip):
        if self._merge_floder_tip is tip:
            self._merge_floder_tip = None

    def _build_merge_floder_queue(self) -> list[tuple[Path, Path]]:
        base_path = Path(self.parentInterface._runtime_config.save_path)
        search_extras = [
            folder_sub.sub("-", danbooru_cfg.canonicalize_term(extra))
            for extra in danbooru_cfg.get_search_extra()
            if danbooru_cfg.canonicalize_term(extra)
        ]
        suffixes = sorted({f" {extra}" for extra in search_extras if extra}, key=len, reverse=True)
        merge_floder_queue = []
        for source_path in base_path.iterdir():
            if not source_path.is_dir():
                continue
            for suffix in suffixes:
                if source_path.name.endswith(suffix):
                    target_name = source_path.name[:-len(suffix)]
                    if target_name:
                        merge_floder_queue.append((source_path, base_path.joinpath(target_name)))
                    break
        return merge_floder_queue

    def _process_merge_floder_queue(self, merge_floder_queue: list[tuple[Path, Path]], progress_callback=None) -> int:
        done = 0
        target_locks = {target_path: Lock() for _, target_path in merge_floder_queue}

        def merge_one(source_path: Path, target_path: Path) -> None:
            with target_locks[target_path]:
                self._merge_one_floder(source_path, target_path)

        with ThreadPoolExecutor(max_workers=min(8, len(merge_floder_queue))) as executor:
            futures = [
                executor.submit(merge_one, source_path, target_path)
                for source_path, target_path in merge_floder_queue
            ]
            for future in as_completed(futures):
                future.result()
                done += 1
                if progress_callback is not None:
                    progress_callback(str(done))
        return done

    @staticmethod
    def _merge_one_floder(source_path: Path, target_path: Path) -> None:
        target_path.mkdir(parents=True, exist_ok=True)
        for child in list(source_path.iterdir()):
            target_child = target_path.joinpath(child.name)
            if target_child.exists():
                if target_child.is_dir():
                    shutil.rmtree(target_child)
                else:
                    target_child.unlink()
            shutil.move(str(child), str(target_child))
        source_path.rmdir()


class DanbooruInterface(QFrame):
    download_result_signal = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.gui = parent.gui
        self.setObjectName("DanbooruInterface")
        self.task_mgr = AsyncTaskManager(self.gui, self)
        self.funcs = DanbooruFuncs(self)
        self.tabs: dict[str, DanbooruTabWidget] = {}
        self.tab_states: dict[str, DanbooruTabState] = {}
        self._runtime_config = DanbooruRuntimeConfig.from_conf()
        self.request_client = DanbooruClient(runtime_config=self._runtime_config)
        self.sql_recorder = SqlRecorder(table=DANBOORU_SQL_TABLE)
        self.video_proxy = VideoProxy(self.request_client, self)
        self.image_viewer = DanbooruImageViewer(parent)
        self.detail_preview_controller = DetailPreviewController(self, self.image_viewer)
        self.search_controller = DanbooruSearchController(self)
        self.download_controller = DanbooruDownloadController(self)
        self.challenge_controller = DanbooruChallengeController(self)
        self.zoom_mgr = self._ZoomMgr(self)
        self.tab_mgr = self._TabMgr(self)
        self._infobars_by_key = {}
        self.download_result_signal.connect(self.download_controller.on_download_result)
        self.image_viewer.tag_clicked.connect(self._open_tag_jump_tab)
        self.image_viewer.download_requested.connect(self.download_controller.submit_single)
        self.image_viewer.previous_requested.connect(lambda: self.detail_preview_controller.open_adjacent(-1))
        self.image_viewer.next_requested.connect(lambda: self.detail_preview_controller.open_adjacent(1))
        self.image_viewer.closed.connect(self.detail_preview_controller.clear_context)
        self._install_key_event_filter()
        theme_mgr.subscribe(self._apply_theme)
        self.setupUi()
        self._apply_theme()
        self.tab_mgr.create()

    def server_mode_switch_blockers(self) -> list[str]:
        if self.task_mgr.get_running_tasks():
            return ["danbooru script"]
        return []

    def _install_key_event_filter(self):
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

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
        title_block_layout.addWidget(self.title_label)
        title_block_layout.addWidget(self.tip_line, 1)
        zoomBtnGroup = QVBoxLayout()
        zoomBtnGroup.setContentsMargins(2,0,2,0)
        zoomBtnGroup.setSpacing(0)
        self.zoomIn = ToolButton(QIcon(':/script/zoomin.svg'))
        self.zoomIn.setMaximumHeight(22)
        self.zoomOut = ToolButton(QIcon(':/script/zoomout.svg'))
        self.zoomOut.setMaximumHeight(22)
        zoomBtnGroup.addWidget(self.zoomIn)
        zoomBtnGroup.addWidget(self.zoomOut)
        self.funcBtn = ToolButton(CgsIcon.SCRIPT_FUNC, self)
        self.funcBtn.setIconSize(QSize(20, 20))
        self.funcBtn.setMinimumHeight(50)
        self.favMgrBtn = ToolButton(CgsIcon.SCRIPT_FAV_MGR, self)
        self.favMgrBtn.setObjectName("FavMgrBtn")
        self.favMgrBtn.setIconSize(QSize(20, 20))
        self.favMgrBtn.setMinimumHeight(50)
        self.openBtn = ToolButton(FIF.FOLDER)
        self.openBtn.setMinimumHeight(50)
        self.batch_download_btn = PrimaryToolButton(FIF.DOWNLOAD, self)
        self.batch_download_btn.setMinimumHeight(50)
        self.batch_download_btn.setMinimumWidth(80)
        self.batch_download_btn.setIconSize(QtCore.QSize(20, 20))
        self.batch_download_btn.setDisabled(True)
        self.batch_download_badge = CountBadge(parent=self, target=self.batch_download_btn)
        self.batch_download_badge.hide()
        title_row.addWidget(self.title_block, 1)
        title_row.addLayout(zoomBtnGroup)
        title_row.addWidget(self.funcBtn)
        title_row.addWidget(self.favMgrBtn)
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
        pivot_shell_layout.addWidget(self.tab_bar, 1)
        self.pivot_forward_btn = TransparentToolButton(FIF.RIGHT_ARROW, self.pivot_shell)
        self.pivot_forward_btn.setObjectName("DanbooruPivotScrollButton")
        self.pivot_forward_btn.setFixedSize(18, 18)
        self.pivot_forward_btn.setIconSize(QtCore.QSize(14, 14))
        pivot_shell_layout.addWidget(self.pivot_forward_btn, 0, Qt.AlignVCenter)
        pivot_scroll_bar = self.pivot_scroll.horizontalScrollBar()

        self.content_shell = QFrame(self)
        self.content_shell.setObjectName("DanbooruContentShell")
        content_shell_layout = QVBoxLayout(self.content_shell)
        content_shell_layout.setContentsMargins(12, 12, 12, 12)
        content_shell_layout.setSpacing(0)
        self.stacked_widget = QStackedWidget(self.content_shell)
        content_shell_layout.addWidget(self.stacked_widget)
        # binding
        self.zoomIn.clicked.connect(self.zoom_mgr.zoom_in)
        self.zoomOut.clicked.connect(self.zoom_mgr.zoom_out)
        self.funcBtn.clicked.connect(self.funcs.open_menu)
        self.favMgrBtn.clicked.connect(self._open_favorite_manager)
        self.openBtn.clicked.connect(self._open_save_path)
        self.batch_download_btn.clicked.connect(self.download_controller.submit_selected)
        self.tab_bar.currentChanged.connect(self.tab_mgr.on_tabbar_index_changed)
        self.pivot_back_btn.clicked.connect(lambda: self.tab_mgr.scroll_tabs(-1))
        self.pivot_forward_btn.clicked.connect(lambda: self.tab_mgr.scroll_tabs(1))
        self.tab_bar.tabCloseRequested.connect(self.tab_mgr.on_tab_close_requested)
        pivot_scroll_bar.rangeChanged.connect(lambda *_args: self.tab_mgr.sync_scroll_controls())
        pivot_scroll_bar.valueChanged.connect(lambda *_args: self.tab_mgr.sync_scroll_controls())
        self.stacked_widget.currentChanged.connect(self.tab_mgr.on_current_tab_changed)
        
        self.main_layout.addWidget(self.pivot_shell)
        self.main_layout.addWidget(self.content_shell, 1)

    def _apply_theme(self, *_args):
        palette = DanbooruUiPalette.current()
        self.setStyleSheet(build_interface_stylesheet(palette))
        self.title_label.setStyleSheet(build_title_label_stylesheet(palette))
        self.tip_line.setStyleSheet(build_tip_line_stylesheet(palette))
        self.tab_bar.setTabShadowEnabled(False)
        selected_color = qcolor_from_css(palette.pivot_selected)
        self.tab_bar.setTabSelectedBackgroundColor(selected_color, selected_color)
        self.image_viewer.apply_theme()
        for tab in self.tabs.values():
            tab.apply_theme()
        self.tab_mgr.update_chrome()
        self.tab_mgr.sync_tip_line()
        self.refresh_runtime_settings()
        self.zoom_mgr.sync_buttons()
        self.tab_mgr.sync_bar_width()

    def eventFilter(self, obj, event):
        if self._handle_interface_key_press(obj, event):
            return True
        return super().eventFilter(obj, event)

    def _handle_interface_key_press(self, obj, event) -> bool:
        if event.type() != QtCore.QEvent.KeyPress:
            return False
        if not self._is_active_interface_key_target():
            return False
        if self._is_editable_key_target(obj):
            return False
        if not event.modifiers() & Qt.KeypadModifier:
            return False
        active_tab = self._active_tab_widget()
        if active_tab is None:
            return False
        key = event.key()
        if key in (Qt.Key_4, Qt.Key_Left):
            active_tab.apply_first_extra_search()
        elif key in self._keypad_num5_keys():
            if active_tab.favorite_btn.isEnabled():
                active_tab.favorite_btn.click()
        elif key in (Qt.Key_6, Qt.Key_Right):
            active_tab.apply_score_sort_search()
        else:
            return False
        event.accept()
        return True

    def _is_active_interface_key_target(self) -> bool:
        if not self.isVisible():
            return False
        active_window = QApplication.activeWindow()
        return active_window is not None and active_window is self.window()

    @staticmethod
    def _is_editable_key_target(obj) -> bool:
        editable_widgets = (QLineEdit, QTextEdit, QPlainTextEdit)
        focus_widget = QApplication.focusWidget()
        return isinstance(focus_widget, editable_widgets) or isinstance(obj, editable_widgets)

    def _active_tab_widget(self) -> t.Optional[DanbooruTabWidget]:
        tab_id = self.tab_mgr.active_tab_id()
        return self.tabs.get(tab_id) if tab_id else None

    @staticmethod
    def _keypad_num5_keys() -> set:
        keys = {Qt.Key_5}
        key_clear = getattr(Qt, "Key_Clear", None)
        if key_clear is not None:
            keys.add(key_clear)
        return keys

    class _ZoomMgr:
        def __init__(self, interface: "DanbooruInterface"):
            self.interface = interface
            self.zoom_index = int(danbooru_cfg.zoom_index.value)
            self.generation = 0

        def current_metrics(self) -> DanbooruCardMetrics:
            return CARD_ZOOM_METRICS[self.zoom_index]

        def zoom_in(self):
            if self.zoom_index >= len(CARD_ZOOM_METRICS) - 1:
                return
            self.zoom_index += 1
            danbooru_cfg.zoom_index.value = self.zoom_index
            danbooru_cfg.save()
            self.apply_current()
            self.sync_buttons()

        def zoom_out(self):
            if self.zoom_index <= 0:
                return
            self.zoom_index -= 1
            danbooru_cfg.zoom_index.value = self.zoom_index
            danbooru_cfg.save()
            self.apply_current()
            self.sync_buttons()

        def sync_buttons(self):
            self.interface.zoomIn.setEnabled(self.zoom_index < len(CARD_ZOOM_METRICS) - 1)
            self.interface.zoomOut.setEnabled(self.zoom_index > 0)

        def apply_current(self, *, active_tab_id: t.Optional[str] = None):
            self.generation += 1
            metrics = self.current_metrics()
            active_tab_id = self.interface.tab_mgr.active_tab_id() if active_tab_id is None else active_tab_id
            for tab_id, tab in self.interface.tabs.items():
                if tab_id == active_tab_id:
                    tab.zoom_mgr.apply_active(metrics=metrics)
                else:
                    tab.zoom_mgr.mark_hidden_target(metrics=metrics)

        def sync_tab(self, tab_id: str):
            tab = self.interface.tabs.get(tab_id)
            if tab is None:
                return
            tab.zoom_mgr.sync_to(metrics=self.current_metrics())

        def forget(self, tab_id: str):
            return

        def shutdown(self):
            return

    class _TabMgr:
        def __init__(self, interface: "DanbooruInterface"):
            self.interface = interface
            self.counter = 0
            self.tips: dict[str, tuple[str, str]] = {}
            self.httpx_status: dict[str, str] = {}
            self.activation_order: list[str] = []
            self._zoom_sync_generation = 0

        def create(self, initial_query: str = "", auto_search: bool = False) -> str:
            self.counter += 1
            tab_id = f"danbooru-tab-{self.counter}"
            state = DanbooruTabState(
                tab_id=tab_id, title=self.display_title_for_query(initial_query, self.counter),
                query=DanbooruSearchQuery.normalize(initial_query),
            )
            tab = DanbooruTabWidget(state, self.interface)
            tab.setObjectName(tab_id)
            tab.zoom_mgr.apply_immediate(metrics=self.interface.zoom_mgr.current_metrics(), refresh_preview=True)
            tab.request_search.connect(lambda query, tid=tab_id: self.interface.search_controller.start_search(tid, query))
            tab.request_conversion.connect(lambda tid=tab_id: self.interface.search_controller.convert_term(tid))
            tab.request_single_download.connect(lambda post, tid=tab_id: self.interface.download_controller.submit_single(post, tid))
            tab.request_tag_jump.connect(self.interface._open_tag_jump_tab)
            tab.request_next_page.connect(lambda tid=tab_id: self.interface.search_controller.load_next_page(tid))
            tab.request_close.connect(self.close_current)
            tab.request_extra_search.connect(lambda term, tid=tab_id: self.interface._on_extra_search(tid, term))
            tab.detail_opened.connect(lambda post, tid=tab_id: self.interface.detail_preview_controller.open_viewer(tid, post))
            tab.selection_count_changed.connect(lambda _count, tid=tab_id: self.interface._update_batch_button(tid))
            tab.favorite_btn.clicked.connect(lambda _=False, tid=tab_id: self.interface._toggle_favorite(tid))
            self.interface.tabs[tab_id] = tab
            self.interface.tab_states[tab_id] = state
            self.tips[tab_id] = (default_tab_status_text(), DEFAULT_TAB_STATUS_CLASS)
            self.httpx_status[tab_id] = ""
            self.interface.stacked_widget.addWidget(tab)
            self.interface.tab_bar.addTab(routeKey=tab_id, text=state.title)
            self.sync_bar_width()
            self.set_current(tab_id)
            self.update_chrome()
            self.interface._refresh_completer(tab)
            if state.query:
                tab.search_edit.setText(state.query)
                if auto_search:
                    self.interface.search_controller.start_search(tab_id, state.query)
            if self.active_tab_id() == tab_id:
                self.sync_tip_line(tab_id)
            return tab_id

        def close_current(self):
            self.close_by_id(self.active_tab_id())

        def close_by_id(self, tab_id: t.Optional[str]):
            if len(self.interface.tabs) <= 1 or not tab_id:
                return
            is_active_tab = self.active_tab_id() == tab_id
            next_tab_id = self.previous_live_tab_id(tab_id) if is_active_tab else None
            tab = self.interface.tabs.pop(tab_id, None)
            self.interface.tab_states.pop(tab_id, None)
            self.tips.pop(tab_id, None)
            self.httpx_status.pop(tab_id, None)
            self.drop_activation(tab_id)
            self.interface.zoom_mgr.forget(tab_id)
            if tab is None:
                return
            if self.interface.detail_preview_controller.current_tab_id == tab_id and self.interface.image_viewer.isVisible():
                self.interface.image_viewer.hide()
                self.interface.detail_preview_controller.clear_context()
            self.interface.tab_bar.removeTabByKey(tab_id)
            self.interface.stacked_widget.removeWidget(tab)
            tab.deleteLater()
            gc.collect()
            if is_active_tab and next_tab_id:
                self.set_current(next_tab_id)
            elif self.interface.stacked_widget.count():
                fallback_widget = self.interface.stacked_widget.currentWidget() or self.interface.stacked_widget.widget(0)
                if fallback_widget is not None:
                    self.set_current(fallback_widget.objectName())
            self.update_chrome()
            self.sync_bar_width()

        def set_current(self, tab_id: str):
            tab = self.interface.tabs.get(tab_id)
            if tab is None:
                return
            previous_widget = self.interface.stacked_widget.currentWidget()
            previous_tab_id = previous_widget.objectName() if previous_widget is not None else None
            if previous_tab_id and previous_tab_id != tab_id:
                previous_tab = self.interface.tabs.get(previous_tab_id)
                if previous_tab is not None:
                    previous_tab.zoom_mgr.suspend_hidden()
            self.interface.stacked_widget.setCurrentWidget(tab)
            self.interface.tab_bar.setCurrentTab(tab_id)
            self.record_activation(tab_id)
            self.interface._update_batch_button(tab_id)

        def record_activation(self, tab_id: str):
            if tab_id in self.activation_order:
                self.activation_order.remove(tab_id)
            self.activation_order.append(tab_id)

        def drop_activation(self, tab_id: str):
            if tab_id in self.activation_order:
                self.activation_order.remove(tab_id)

        def previous_live_tab_id(self, closing_tab_id: str) -> t.Optional[str]:
            for candidate in reversed(self.activation_order):
                if candidate != closing_tab_id and candidate in self.interface.tabs:
                    return candidate
            return None

        def on_current_tab_changed(self, _index: int):
            widget = self.interface.stacked_widget.currentWidget()
            if widget is None:
                return
            tab_id = widget.objectName()
            current_tab = self.interface.tab_bar.currentTab()
            if current_tab is None or current_tab.routeKey() != tab_id:
                self.interface.tab_bar.setCurrentTab(tab_id)
            self.interface._update_batch_button(tab_id)
            self.update_chrome()
            self.sync_tip_line(tab_id)
            self.schedule_zoom_sync(tab_id)

        def schedule_zoom_sync(self, tab_id: str):
            self._zoom_sync_generation += 1
            generation = self._zoom_sync_generation
            QtCore.QTimer.singleShot(0, lambda tid=tab_id, gen=generation: self._run_deferred_zoom_sync(tid, gen))

        def _run_deferred_zoom_sync(self, tab_id: str, generation: int):
            if generation != self._zoom_sync_generation or self.active_tab_id() != tab_id:
                return
            self.interface.zoom_mgr.sync_tab(tab_id)

        def on_tabbar_index_changed(self, index: int):
            tab_id = self.tab_id_at(index)
            if tab_id:
                self.set_current(tab_id)

        def on_tab_close_requested(self, index: int):
            self.close_by_id(self.tab_id_at(index))

        def tab_id_at(self, index: int) -> t.Optional[str]:
            if not 0 <= index < self.interface.tab_bar.count():
                return None
            return self.interface.tab_bar.tabItem(index).routeKey()

        def tab_index(self, tab_id: str) -> int:
            item = self.interface.tab_bar.tab(tab_id)
            return self.interface.tab_bar.items.index(item) if item is not None else -1

        @staticmethod
        def display_title_for_query(query: str, tab_index: int) -> str:
            canonical = DanbooruSearchQuery.normalize(query)
            if not canonical:
                return f"工作区 {tab_index}"
            if len(canonical) <= 18:
                return canonical
            return canonical[:16].rstrip() + ".."

        def update_title(self, tab_id: str, query: str):
            state = self.interface.tab_states.get(tab_id)
            if state is None:
                return
            title = self.display_title_for_query(query, int(tab_id.rsplit("-", 1)[-1]))
            if title == state.title:
                return
            state.title = title
            index = self.tab_index(tab_id)
            if index >= 0:
                self.interface.tab_bar.setTabText(index, state.title)
            self.update_chrome()
            self.sync_bar_width()

        def update_chrome(self):
            palette = DanbooruUiPalette.current()
            current_tab_id = self.active_tab_id()
            active_text_color = qcolor_from_css(palette.text)
            inactive_text_color = qcolor_from_css(palette.muted_text)
            self.interface.tab_bar.setTabsClosable(len(self.interface.tabs) > 1)
            for index in range(self.interface.tab_bar.count()):
                item = self.interface.tab_bar.tabItem(index)
                if item is None:
                    continue
                tab_id = item.routeKey()
                item.setBorderRadius(12)
                self.interface.tab_bar.setTabTextColor(index, active_text_color if tab_id == current_tab_id else inactive_text_color)

        def active_tab_id(self) -> t.Optional[str]:
            widget = self.interface.stacked_widget.currentWidget()
            return widget.objectName() if widget is not None else None

        def set_tip(self, tab_id: str, text: str, cls: str = DEFAULT_TAB_STATUS_CLASS):
            self.tips[tab_id] = (text, cls or DEFAULT_TAB_STATUS_CLASS)
            if self.active_tab_id() == tab_id:
                self.interface.tip_line.setText(_format_tip_rich_text(*self.tips[tab_id]))

        def set_httpx_status(self, tab_id: str, status: str, cls: str = DEFAULT_TAB_STATUS_CLASS):
            self.httpx_status[tab_id] = str(status or "")
            self.set_tip(tab_id, self.httpx_status[tab_id], cls=cls)

        def sync_tip_line(self, tab_id: t.Optional[str] = None):
            effective_tab_id = tab_id or self.active_tab_id()
            text, cls = self.tips.get(effective_tab_id, (default_tab_status_text(), DEFAULT_TAB_STATUS_CLASS))
            self.interface.tip_line.setText(_format_tip_rich_text(text, cls))

        def scroll_tabs(self, direction: int):
            bar = self.interface.pivot_scroll.horizontalScrollBar()
            if bar.maximum() <= bar.minimum():
                return
            step = max(72, int(self.interface.pivot_scroll.viewport().width() * 0.72))
            bar.setValue(bar.value() + direction * step)

        def sync_scroll_controls(self):
            bar = self.interface.pivot_scroll.horizontalScrollBar()
            has_overflow = bar.maximum() > bar.minimum()
            self.interface.pivot_back_btn.setEnabled(has_overflow and bar.value() > bar.minimum())
            self.interface.pivot_forward_btn.setEnabled(has_overflow and bar.value() < bar.maximum())

        def sync_bar_width(self):
            self.interface.tab_bar.view.adjustSize()
            self.interface.tab_bar.updateGeometry()
            QtCore.QTimer.singleShot(0, self.sync_scroll_controls)

    def _open_save_path(self):
        base_path = Path(self._runtime_config.save_path)
        tab_id = self.tab_mgr.active_tab_id()
        state = self.tab_states.get(tab_id) if tab_id else None
        open_path = base_path
        if state is not None and self._runtime_config.save_type == DANBOORU_SAVE_TYPE_SEARCH_TAG:
            folder_term = DanbooruSearchQuery(state.query).folder_term
            if folder_term:
                tab_save_path = base_path.joinpath(folder_sub.sub("-", folder_term))
                if tab_save_path.exists():
                    open_path = tab_save_path
        curr_os.open_folder(open_path)

    def _update_batch_button(self, tab_id: str):
        if self.tab_mgr.active_tab_id() != tab_id:
            return
        state = self.tab_states.get(tab_id)
        count = len(state.selected_post_ids) if state else 0
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

    def _show_task_error(self, error: str, duration: int = 6000):
        self.gui.log.error(error)
        summary = summarize_error_message(error)
        self._show_info(InfoBar.error, f"✕ {summary}", duration)

    def _log_search_request(self, tab_id: str, query: str, order: str, page: int, limit: int):
        params = DanbooruSearchQuery(query, order).params(page=page, limit=limit)
        stub_endpoint = self._runtime_config.stub_dns_endpoint() or "disabled"
        dns_summary = f"DoH={self._runtime_config.doh_url}" if self._runtime_config.is_doh_enabled() else "system"
        self.gui.log.info(f"[Danbooru] GET /posts.json tab={tab_id} params={params} dns={dns_summary} stub={stub_endpoint}")

    def refresh_runtime_settings(self):
        self._runtime_config = DanbooruRuntimeConfig.from_conf()
        self.request_client.set_runtime_config(self._runtime_config)

    def _favorite_groups_state(self):
        return build_favorite_groups_state(danbooru_cfg.searchFavorites.value, canonicalize_term=danbooru_cfg.canonicalize_term)

    @staticmethod
    def _save_favorite_groups_state(groups_state):
        danbooru_cfg.fav.save_payload(groups_state.to_payload())

    def _refresh_completer(self, tab: DanbooruTabWidget):
        history = danbooru_cfg.get_history()
        favorites_state = self._favorite_groups_state()
        favorites = sorted(favorites_state.all_terms() - set(history))
        tab.update_completer(history + favorites)

    def _show_info(self, factory, content: str, duration: int = 3000):
        key = (getattr(factory, "__name__", repr(factory)), str(content or ""))
        existing = self._infobars_by_key.get(key)
        if existing is not None:
            return existing
        infobar = factory(
            title="", content=content, orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=duration, parent=self,
        )
        if infobar is None:
            return None
        self._infobars_by_key[key] = infobar
        infobar.closedSignal.connect(lambda bar=infobar, current_key=key: self._forget_infobar(current_key, bar))
        return infobar

    def _forget_infobar(self, key, infobar):
        if self._infobars_by_key.get(key) is infobar:
            self._infobars_by_key.pop(key, None)

    def _on_extra_search(self, tab_id: str, extra_term: str):
        tab = self.tabs.get(tab_id)
        if tab is None:
            return
        current = DanbooruSearchQuery.normalize(tab.search_edit.text())
        combined = f"{current} {extra_term}".strip() if current else extra_term
        tab.search_edit.setText(combined)
        self.search_controller.start_search(tab_id, combined)

    def _toggle_favorite(self, tab_id: str):
        tab = self.tabs.get(tab_id)
        if tab is None:
            return
        term = DanbooruSearchQuery.normalize(tab.search_edit.text())
        if not term:
            tab.sync_favorite_button_state()
            return
        favorites_state = self._favorite_groups_state()
        is_favorited = favorites_state.toggle(term)
        self._save_favorite_groups_state(favorites_state)
        self._refresh_all_favorites_ui()
        content = f"★ {term}" if is_favorited else f"☆ {term}"
        if not is_favorited:
            return self._show_info(InfoBar.error, content)
        custom_groups = favorites_state.custom_groups
        if not custom_groups:
            return self._show_info(InfoBar.success, content)
        tmpFavMgrBtn = PrimaryToolButton(CgsIcon.SCRIPT_FAV_MGR)
        first_ib = CustomInfoBar.show_custom(
            title="", content=content, parent=self, _type="SUCCESS",
            ib_pos=InfoBarPosition.TOP, duration=3000, widgets=[tmpFavMgrBtn],
        )
        def _open_group_picker():
            first_ib.close()
            combo = ComboBox()
            combo.addItems([group.name for group in custom_groups])
            combo.setMinimumWidth(100)
            accept_btn = PrimaryToolButton(FIF.ACCEPT)
            picker_ib = CustomInfoBar.show_custom(
                title="", content="move to:", parent=self, _type="INFORMATION",
                ib_pos=InfoBarPosition.TOP, duration=-1, widgets=[combo, accept_btn],
            )
            def _move_tag():
                group_name = combo.currentText()
                move_state = self._favorite_groups_state()
                move_state.move_to_group(term, group_name)
                self._save_favorite_groups_state(move_state)
                self._refresh_all_favorites_ui()
                picker_ib.close()
                self._show_info(InfoBar.success, f"moved to「{group_name}」")
            accept_btn.clicked.connect(_move_tag)
        tmpFavMgrBtn.clicked.connect(_open_group_picker)

    def _refresh_all_favorites_ui(self):
        for tab in self.tabs.values():
            tab.set_search_menu()
            self._refresh_completer(tab)
            tab.sync_favorite_button_state()

    def _open_favorite_manager(self):
        dialog = DanbooruFavoriteManagerDialog(self._favorite_groups_state(), self)
        if dialog.exec():
            self._save_favorite_groups_state(dialog.groups_state)
            self._refresh_all_favorites_ui()

    def _open_tag_jump_tab(self, tag: str):
        self.image_viewer.hide()
        self.detail_preview_controller.clear_context()
        canonical_tag = DanbooruSearchQuery.normalize(tag)
        if not canonical_tag:
            return
        for tab_id, state in self.tab_states.items():
            if DanbooruSearchQuery.normalize(state.query) == canonical_tag:
                self.tab_mgr.set_current(tab_id)
                tab = self.tabs.get(tab_id)
                if tab is not None and not state.result_list and not state.loading:
                    self.search_controller.start_search(tab_id, canonical_tag)
                return
        active_tab_id = self.tab_mgr.active_tab_id()
        active_state = self.tab_states.get(active_tab_id) if active_tab_id else None
        if active_tab_id and active_state and not active_state.query and not active_state.result_list and not active_state.loading:
            active_state.query = canonical_tag
            self.tabs[active_tab_id].search_edit.setText(canonical_tag)
            self.search_controller.start_search(active_tab_id, canonical_tag)
            return
        self.tab_mgr.create(initial_query=canonical_tag, auto_search=True)

    def notify_download_result(self, md5_value: str, success: bool):
        self.download_result_signal.emit(md5_value, success)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.tab_mgr.sync_bar_width()

    def closeEvent(self, event):
        try:
            theme_mgr.unsubscribe(self._apply_theme)
            self.image_viewer.hide()
            self.video_proxy.close()
            self.sql_recorder.close()
            self.zoom_mgr.shutdown()
        finally:
            super().closeEvent(event)
