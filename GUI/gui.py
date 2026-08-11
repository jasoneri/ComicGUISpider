import os
import sys
import time
import random
import threading
import traceback
import contextlib
import warnings
from PySide6.QtGui import QKeySequence, QGuiApplication, QShortcut, QTextCursor
from PySide6.QtCore import (
    QThread, Qt, QCoreApplication, QUrl, QRect, QTimer,
    Signal,
)
from GUI.core.timer import safe_single_shot
from PySide6.QtWidgets import QApplication, QMainWindow, QCompleter
from qfluentwidgets import Action, FluentIcon as FIF, InfoBar, InfoBarPosition
from qfluentwidgets.components.widgets.line_edit import CompleterMenu

from GUI.uic.qfluent import (
    MonkeyPatch as FluentMonkeyPatch, CustomSplashScreen
)
from GUI.mainwindow import MitmMainWindow
from GUI.core.font import font_color
from GUI.core.theme import setupTheme
from GUI.core.anim import PopupAnimator
from GUI.types import GUIFlowStage, PreviewRequestState, SearchLifecycleState, SearchUiState
from utils.config.qc import cgs_cfg
from variables import *
from assets import res
from utils import conf, p, curr_os, select, bs_theme
_UNSET = object()

def _safe_disconnect(signal, slot=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with contextlib.suppress(TypeError, RuntimeError):
            if slot is None:
                signal.disconnect()
            else:
                signal.disconnect(slot)


class SpiderGUI(QMainWindow, MitmMainWindow):
    res = res.GUI
    setup_finished = Signal()
    exception_feedback_requested = Signal(str, str)
    # Background fetch → main-thread publish (must be QueuedConnection; QTimer from
    # worker threads does not reliably schedule on the GUI thread).
    online_favorites_ready = Signal(str, int, object)  # provider_name, site_index, books
    BrowserWindow = None  # CGS001 browser init/show flow
    toolWin = None
    conf_dia = None  # CGS006: construct on demand (P4)
    web_is_r18 = False
    gui_site_runtime = None  # CGS001 choose-box site flow
    dl_mgr = None
    sut = None
    bsm: dict = None  # books show max
    flow_stage: GUIFlowStage = GUIFlowStage.IDLE
    sv_path = None
    rv_tools = None
    splashWait = 3

    def __init__(self, parent=None):
        self.st = time.time()
        super(SpiderGUI, self).__init__(parent)
        self.log = conf.cLog(name="GUI")
        self.log.debug(f"{conf.settings=}")
        self.log.debug(f"{cgs_cfg.doh.get_url()=}")
        self._preview_warmup_pending = False
        self._post_first_paint_setup_requested = False
        self._post_first_paint_setup_started = False
        self._server_mode_switch_requested = False
        self._closing = False
        self.script_window = None
        self.timeline_tip_mgr = None
        self._pending_rv_sauce_visible = False  # CGS006: apply when toolWin is ensured
        self._conf_accept_bound = False
        # self.log.debug(f'-*- 主进程id {os.getpid()}')
        self.setupUi(self)
        self.exception_feedback_requested.connect(self._show_exception_feedback, Qt.QueuedConnection)
        self.online_favorites_ready.connect(self._on_online_favorites_ready, Qt.QueuedConnection)

    def _pick_sleep_widget_image(self, *, allow_random: bool) -> str | None:
        if allow_random and getattr(self.bg_mgr, "bg_fs", []):
            return random.choice(self.bg_mgr.bg_fs)[0]
        return self.bg_mgr.bg_f

    def setupUi(self, MainWindow):
        conf.sv_path.mkdir(parents=True, exist_ok=True)
        super(SpiderGUI, self).setupUi(MainWindow)
        self.splashScreen = CustomSplashScreen(self)
        self.setup_sleep_widget(self._pick_sleep_widget_image(allow_random=False))
        self.show()
        res.set_language(conf.lang)
        self.apply_translations()
        setupTheme(self)

    def start_post_first_paint_setup(self):
        if self._post_first_paint_setup_requested or self._post_first_paint_setup_started:
            return
        self._post_first_paint_setup_requested = True
        safe_single_shot(10, self.setupUi_)

    def setupUi_(self):
        if self._post_first_paint_setup_started:
            return
        self._post_first_paint_setup_started = True
        # CGS006: import only the submodules needed for P2 — not GUI.manager barrel.
        from utils.redViewer_tools import Handler as rVtools
        from GUI.manager.task_progress import TaskProgressManager
        from GUI.manager.rv import RVManager
        self.task_init()
        self.task_mgr = TaskProgressManager(self)
        self.task_mgr.init_native_panel()
        self.rv_tools = rVtools()
        self.rv_mgr = RVManager(self)
        self.rv_mgr.start_scan(show_progress=False)
        self.browser_zoom_factor = 1.0  # WebEngine 用户缩放率，生命周期同 SpiderGUI
        self.textBrowser.clear()
        self.finish_setup()

    def finish_setup(self):
        self.generation_bind()
        if not getattr(self, "_startup_completed", False):
            # Start while splash still covers the window so chooseBox first-use
            # does not race an empty warmup (was gated on splash finish).
            self._start_import_warmup()
            self.startup_only()
            self._startup_completed = True

    def _restore_feedback_panel(self):
        from GUI.tools.chore import TextUtils
        self.textBrowser.clear()
        self.textBrowser.append(TextUtils.description())
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)

    def startup_only(self):
        from GUI.manager import UpdateNotifier
        from GUI.manager.timeline_tip import TimelineTipManager
        self.update_notifier = UpdateNotifier(self)
        self.update_notifier.check_on_startup()
        self.timeline_tip_mgr = TimelineTipManager(self)
        self.timeline_tip_mgr.check_on_startup()
        past = time.time() - self.st
        delay_ms = int((0 if past >= self.splashWait else self.splashWait - past) * 1000)
        safe_single_shot(delay_ms, self.splashScreen.finish)

    def _start_import_warmup(self):
        """Background-import what startup deferred (providers + scrapy stack)."""
        from GUI.core.warmup import ImportWarmupThread

        self.warmup_thread = ImportWarmupThread(self)
        self.warmup_thread.start()

    def generation_bind(self):
        # CGS006 P2: interactive-minimum only — ConfDialog/ToolWindow are P4.
        from utils.sql.download_state import DownloadStateStore
        from GUI.tools.chore import TextUtils
        from GUI.manager.clip import ClipGUIManager
        from GUI.manager.ags import AggrSearchManager
        from GUI.manager.mid import CGSMidManagerGUI
        from GUI.manager.preview import PreviewMgr
        from GUI.manager.publish import PublishDomainManager
        from GUI.manager.selection import SelectionFlowManager
        from GUI.manager.download import DownloadRuntimeManager
        from GUI.manager.share import Shares
        from GUI.manager.preprocess import PreprocessManager
        from GUI.manager.login import LoginManager
        self.flow_stage = GUIFlowStage.IDLE
        self.pageFrameClickCnt = 0
        self.conf_dia = None
        self.textBrowser.append(TextUtils.description())

        self.clip_mgr = ClipGUIManager(self)
        self.ags_mgr = AggrSearchManager(self)
        self.preview_mgr = PreviewMgr(self)
        self.publish_mgr = PublishDomainManager(self)
        self.shares = Shares(self)
        self.download_state = DownloadStateStore()
        self.dl_mgr = DownloadRuntimeManager(self)
        self.sel_mgr = SelectionFlowManager(self)
        self.mid_mgr = CGSMidManagerGUI(self)
        self.login_mgr = LoginManager(self)
        self.dl_mgr.process_stage_changed.connect(self.mid_mgr.on_process_stage)
        if self.dl_mgr.process_stage:
            self.mid_mgr.on_process_stage(self.dl_mgr.process_stage)
        self.sel_mgr.decision_made.connect(self._on_decision_made)
        self.sel_mgr.skip_notified.connect(self._show_skip_info)

        self.sv_path = conf.sv_path
        self.btn_logic_bind()
        self.set_shortcut()
        self.set_tool_win()
        self.tf = None
        self.gui_site_runtime = None
        self.BrowserWindow = None
        self.bsm = None
        self.search_ui_state = SearchUiState()

        self.preprocess_mgr = PreprocessManager(self)
        _safe_disconnect(self.chooseBox.currentIndexChanged, self._chooseBox_changed_handle)
        self.chooseBox.currentIndexChanged.connect(self._chooseBox_changed_handle)
        self.refresh_lifecycle_state()
        self.setup_finished.emit()

    def ensure_conf_dialog(self):
        """CGS006 P4: build ConfDialog only when configuration UI is needed."""
        if self.conf_dia is None:
            from GUI.conf_dialog import ConfDialog
            self.conf_dia = ConfDialog(self)
            if not self._conf_accept_bound:
                self.conf_dia.acceptBtn.clicked.connect(self.set_completer)
                self._conf_accept_bound = True
            update_notifier = getattr(self, "update_notifier", None)
            if update_notifier is not None:
                update_notifier.refresh_badges()
        return self.conf_dia

    def ensure_tool_win(self):
        """CGS006 P4: build ToolWindow on first tool open / rv sauce need."""
        if self.toolWin is None:
            from GUI.tools import ToolWindow
            self.toolWin = ToolWindow(self)
            if hasattr(self.toolWin, "rvInterface"):
                self.toolWin.rvInterface.set_sauce_visible(self._pending_rv_sauce_visible)
        return self.toolWin

    def update_search_ui(self, *, session=_UNSET, request=_UNSET, controls_blocked=_UNSET):
        if session is not _UNSET:
            self.search_ui_state.session = session
        if request is not _UNSET:
            self.search_ui_state.request = request
        if controls_blocked is not _UNSET:
            self.search_ui_state.controls_blocked = bool(controls_blocked)
            self.clipBtn.setDisabled(self.search_ui_state.controls_blocked)
        self._apply_lifecycle_state()

    def refresh_lifecycle_state(self):
        self._apply_lifecycle_state()

    def _apply_lifecycle_state(self):
        has_selected_site = self.chooseBox.currentIndex() > 0
        has_search_site = self.chooseBox.currentIndex() in SPIDERS
        ui_state = self.search_ui_state
        request_running = ui_state.request is PreviewRequestState.Running
        choose_enabled = not has_selected_site
        search_enabled = (
            has_search_site
            and ui_state.session is SearchLifecycleState.Unlocked
            and not ui_state.controls_blocked
        )
        preview_enabled = has_search_site and not request_running and not ui_state.controls_blocked
        retry_enabled = has_selected_site
        if not has_search_site:
            show_ero = False
            show_manga = False
        else:
            show_ero = self.web_is_r18
            show_manga = not self.web_is_r18
        page_enabled = (
            has_search_site
            and self.flow_stage is GUIFlowStage.SEARCHED
            and getattr(self, "preview_mgr", None)
            and self.preview_mgr.is_pageable
            and not request_running
        )

        self.chooseBox.setEnabled(choose_enabled)
        self.searchinput.setEnabled(search_enabled)
        self.previewBtn.setVisible(show_ero)
        self.mpreviewBtn.setVisible(show_manga)
        self.retrybtn.setEnabled(retry_enabled)
        self.confBtn.setEnabled(True)
        self._set_page_frame_enabled(bool(page_enabled))

    def _set_page_frame_enabled(self, enabled: bool):
        self.pageFrame.setEnabled(enabled)
        color = "rgb(255, 255, 255)" if enabled else "rgb(127, 127, 127)"
        self.pageFrame.setStyleSheet(f"QToolButton {{ background-color: {color}; }}")

    def _create_gui_site_runtime(self, site_index: int):
        from utils.website.registry import create_gui_site_runtime
        if site_index in SPIDERS:
            return create_gui_site_runtime(site_index, conf_state=conf, default_doh_url=cgs_cfg.doh.get_url())

    def _destroy_browser_window(self):
        browser = self.BrowserWindow
        if not browser:
            return
        browser.set_close_handler(None)
        browser.close()
        browser.deleteLater()
        self.BrowserWindow = None

    def _chooseBox_changed_handle(self, index):
        if index <= 0:
            self.search_ui_state = SearchUiState()
            self.web_is_r18 = False
            self.flow_stage = GUIFlowStage.IDLE
            self.login_mgr.on_site_changed(0)
            self.preview_mgr.handle_choosebox_changed(index, None)
            self.refresh_lifecycle_state()
            return

        self.gui_site_runtime = self._create_gui_site_runtime(index)
        self.search_ui_state = SearchUiState()
        self.rv_tools.ero = 0
        self.web_is_r18 = index in Spider.specials()
        self._pending_rv_sauce_visible = self.web_is_r18
        if self.toolWin is not None and hasattr(self.toolWin, "rvInterface"):
            self.toolWin.rvInterface.set_sauce_visible(self.web_is_r18)
        self.mid_mgr.set_lane_hidden("EP", self.web_is_r18)
        self.sut = None
        if index in (Spider.JM, Spider.WNACG) and not conf.proxies:
            self.domainBtn.setVisible(True)
        self.login_mgr.on_site_changed(index)
        if self.web_is_r18:
            self.rv_tools.ero = 1
        self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", STATUS_TIP.get(index) or ""))
        self._set_search_context_menu()
        if index in SPIDERS and not self.dl_mgr.spider_runtime:
            self.dl_mgr.start_runtime(index)
        self.chooseBox_changed_tips(index)
        if self.web_is_r18:
            self.sv_path = conf.sv_path.joinpath(res.SPIDER.ERO_BOOK_FOLDER)
        else:
            self.sv_path = conf.sv_path
        self.set_completer()
        self.flow_stage = GUIFlowStage.IDLE
        self.preprocess_mgr.handle_choosebox_changed(index, self.gui_site_runtime)
        self.refresh_lifecycle_state()

    def chooseBox_changed_tips(self, index):
        self.pageEdit.setEnabled(index != Spider.EHENTAI)
        match index:
            case 1:
                self.pageEdit.setStatusTip(self.pageEdit.statusTip() + f"  {self.res.copymaga_page_status_tip}")
                self.say(font_color(self.res.copymaga_tips, cls='theme-highlight'))
            case 3:
                if not conf.proxies:
                    self.say(font_color(self.res.wnacg_desc, cls='theme-highlight'), ignore_http=True)
            case 4:
                self.say(font_color(res.EHentai.GUIDE, cls='theme-highlight'))
            case _:
                if self.gui_site_runtime is not None:
                    desc = getattr(self.res, f"{self.gui_site_runtime.name}_desc", None)
                    if isinstance(desc, str) and desc:
                        self.say(font_color(desc, cls='theme-highlight'), ignore_http=True)
        if index in Spider.mangas():
            self.say(font_color(self.res.manga_fav_tip, cls='theme-tip'))

    def set_shortcut(self):
        shortcut_pairs = (
            ("previousPageShort", "Ctrl+,", self.previousPageBtn.click),
            ("nextPageShort", "Ctrl+.", self.nextPageBtn.click),
        )
        for attr_name, key, slot in shortcut_pairs:
            shortcut = getattr(self, attr_name, None)
            if shortcut is None:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.setContext(Qt.ApplicationShortcut)
                setattr(self, attr_name, shortcut)
            else:
                _safe_disconnect(shortcut.activated)
            shortcut.activated.connect(slot)

    def show_toolWin(self, win_type):
        _map = {"ags": "asInterface", "hitomi": "htInterface", "subscribe": "subscribeInterface"}
        self.rvBtn.click()

        def _jump():
            tool_window = self.ensure_tool_win()
            if win_type == "subscribe":
                tool_window.ensure_subscribe_interface()
            target_widget = getattr(tool_window, _map[win_type], None)
            if target_widget is not None:
                tool_window.stackedWidget.setCurrentWidget(target_widget)

        safe_single_shot(10, _jump)

    def open_scriptWin(self, *, pure_only: bool = False, script_entry_state: dict | None = None):
        from GUI.script import ScriptWindow
        if self.toolWin is not None and self.toolWin.isVisible():
            self.toolWin.close()
        # Keep main window visible until ScriptWindow is ready: import/construct can block the
        # GUI thread for seconds; hide-first looks like a total freeze with only a taskbar ghost.
        self.script_window = ScriptWindow(
            self,
            script_entry_state=script_entry_state,
            feedback_dispatcher=self.exception_feedback_dispatcher,
        )
        self.script_window.destroyed.connect(lambda *_args: setattr(self, "script_window", None))
        if pure_only:
            self.script_window.apply_pure_entry_mode()
        if self.script_window.kemonoInterface is not None:
            setupTheme(self.script_window.kemonoInterface)
        self.script_window.show()
        self.script_window.raise_()
        self.script_window.activateWindow()
        self.hide()
        self.log.info(
            f"[ScriptWindow] shown geometry=[{self.script_window.x()}, {self.script_window.y()}, "
            f"{self.script_window.width()}, {self.script_window.height()}] "
            f"mounted={sorted(self.script_window._mounted_keys)}"
        )

    @property
    def server_mode_switch_requested(self) -> bool:
        return self._server_mode_switch_requested

    def request_server_mode_switch(self, conf_dialog):
        blockers = self.server_mode_switch_blockers()
        if blockers:
            InfoBar.warning(
                title="", content=f"请先停止或完成当前任务：{', '.join(blockers)}",
                isClosable=True, position=InfoBarPosition.TOP, duration=5000, parent=conf_dialog,
            )
            return False
        conf_dialog.save_conf(raise_on_invalid=True)
        self._server_mode_switch_requested = True
        conf_dialog.hide()
        self.close()
        return True

    def server_mode_switch_blockers(self) -> list[str]:
        blockers = []
        if self.dl_mgr.has_active_download():
            blockers.append("download")
        if self.search_ui_state.request is PreviewRequestState.Running:
            blockers.append("preview/search")
        blockers.extend(self.preprocess_mgr.server_mode_switch_blockers())
        blockers.extend(self.shares.server_mode_switch_blockers())
        if self.toolWin is not None:
            blockers.extend(self.toolWin.server_mode_switch_blockers())
        if self.script_window is not None:
            blockers.extend(self.script_window.server_mode_switch_blockers())
        blockers.extend(self.publish_mgr.server_mode_switch_blockers())
        blockers.extend(self.clip_mgr.server_mode_switch_blockers())
        blockers.extend(self.ags_mgr.server_mode_switch_blockers())
        return list(dict.fromkeys(blockers))

    def set_tool_win(self):
        # CGS006: only wire the open hook on P2; ToolWindow builds on first click (P4).
        self.toolWin = None

        def _show_toolWin():
            tool_window = self.ensure_tool_win()
            abs_y = self.y() + self.height()
            screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
            target_y = screen_height - tool_window.height() if abs_y + tool_window.height() > screen_height else abs_y
            target_rect = QRect(self.x(), target_y, tool_window.width(), tool_window.height())
            PopupAnimator.show(tool_window, target_rect, duration_ms=220, direction="down")

        self.rvBtn.clicked.connect(_show_toolWin)

    def _set_search_context_menu(self):
        def show_preset_completer():
            if not self.searchinput.text().strip():
                self.searchinput.setText(" ")
            self.searchinput._showCompleterMenu()

        def show_history_completer():
            history_terms = cgs_cfg.search.get_history()
            if not history_terms:
                return
            history_menu = CompleterMenu(self.searchinput)
            history_menu.setItems(history_terms)
            history_menu.setMaxVisibleItems(max(len(history_terms), 10))
            history_menu.activated.connect(
                lambda selected_text: self.searchinput.setCursorPosition(len(selected_text or ""))
            )
            self.searchinput.setFocus(Qt.OtherFocusReason)
            history_menu.popup()

        preset_action = Action(
            FIF.ALIGNMENT,
            text=self.searchinput.tr(self.res.Uic.menu_show_completer),
            triggered=show_preset_completer,
        )
        history_terms = cgs_cfg.search.get_history()
        history_action = Action(
            FIF.HISTORY,
            text=self.searchinput.tr(self.res.Uic.menu_show_history),
            triggered=show_history_completer,
        )
        history_action.setEnabled(bool(history_terms))
        online_fav_action = Action(
            FIF.HEART,
            text=self.searchinput.tr(self.res.menu_fetch_online_fav),
            triggered=lambda: self._fetch_online_favorites(),
        )
        FluentMonkeyPatch.rbutton_menu_lineEdit(
            self.searchinput,
            extra_actions=[preset_action, history_action, online_fav_action],
        )

    def _fetch_online_favorites(self):
        """登录态拉取当前站点收藏列表 → 正式预览网格 (与搜索/本地收藏同交互)。

        产品入口: 搜索框右键「拉取线上收藏」/ completer online_fav。
        成功路径必须: run_fetch_favorites → (QueuedConnection 回主线程) →
        preview publish → present_browser 打开并加载 gui.tf。禁止平行 Dialog。

        线程约束: 网络在后台线程; UI 只经 online_favorites_ready 信号进主线程。
        禁止在 worker 里 QTimer.singleShot(GUI) — 那不会可靠调度到 GUI 线程,
        表现为菜单点了没反应 / browser 不弹 (用户实测根因)。
        """
        if self.gui_site_runtime is None:
            self.say(font_color("请先选择站点并等待预处理完成", cls="theme-warning"), ignore_http=True)
            return
        provider_name = self.gui_site_runtime.name
        site_index = self.chooseBox.currentIndex()
        from utils.website.account import resolve_favorites_spec, run_fetch_favorites

        if resolve_favorites_spec(provider_name) is None:
            self.say(font_color("当前站点不支持拉取线上收藏", cls="theme-warning"), ignore_http=True)
            return
        if not conf.cookies.get(provider_name):
            self.say(font_color("请先点击登录按钮保存该站点 cookies", cls="theme-warning"), ignore_http=True)
            return

        # Same chrome loader path as search_initial (open browser shell + loading bar).
        from GUI.manager.preview.loading import PreviewLoadingReason

        self.preview_mgr.loading.begin(PreviewLoadingReason.SEARCH_INITIAL)
        self.say(font_color(f"正在拉取 {provider_name} 线上收藏…", cls="theme-highlight"), ignore_http=True)

        def worker():
            try:
                books = run_fetch_favorites(provider_name)
            except Exception:
                self.log.exception("fetch online favorites failed")
                books = []
            # Cross-thread: QueuedConnection delivers on GUI thread.
            self.online_favorites_ready.emit(provider_name, int(site_index), books or [])

        threading.Thread(target=worker, daemon=True, name=f"online-fav-{provider_name}").start()

    def _on_online_favorites_ready(self, provider_name: str, site_index: int, books):
        """Main-thread slot: publish online favorites into formal preview browser."""
        from GUI.manager.preview.loading import PreviewLoadingReason

        runtime = self.gui_site_runtime
        if runtime is None or runtime.name != provider_name:
            self.preview_mgr.loading.end(PreviewLoadingReason.SEARCH_INITIAL)
            self.say(font_color("站点已切换，已丢弃线上收藏结果", cls="theme-warning"), ignore_http=True)
            return
        if self.chooseBox.currentIndex() != site_index:
            self.preview_mgr.loading.end(PreviewLoadingReason.SEARCH_INITIAL)
            self.say(font_color("站点已切换，已丢弃线上收藏结果", cls="theme-warning"), ignore_http=True)
            return
        if not books:
            self.preview_mgr.loading.end(PreviewLoadingReason.SEARCH_INITIAL)
            self.say(
                font_color(
                    "未拉取到线上收藏（登录态失效 / CF 拦截 / 收藏为空）",
                    cls="theme-warning",
                ),
                ignore_http=True,
            )
            return
        try:
            self.preview_mgr.show_online_favorites(books)
            active = self.preview_mgr._active
            if hasattr(active, "_ensure_online_fav_completer"):
                active._ensure_online_fav_completer()
        finally:
            self.preview_mgr.loading.end(PreviewLoadingReason.SEARCH_INITIAL)
        browser = getattr(self, "BrowserWindow", None)
        tf_path = getattr(self, "tf", None)
        if browser is None or not tf_path:
            self.log.error(
                "online favorites publish did not open browser: browser=%s tf=%s",
                browser is not None,
                bool(tf_path),
            )
            self.say(
                font_color("线上收藏已解析但预览窗口未打开，请看日志", cls="theme-err"),
                ignore_http=True,
            )
            return
        if not browser.isVisible():
            browser.show()
            browser.raise_()
            browser.activateWindow()
        with_cover = sum(1 for book in books if getattr(book, "img_preview", None))
        self.say(
            font_color(
                f"线上收藏已打开预览（{len(books)} 本，封面 {with_cover}）",
                cls="theme-success",
            ),
            ignore_http=True,
        )

    def set_completer(self):
        idx = self.chooseBox.currentIndex()
        if idx == 0:
            return
        this_completer = conf.completer[idx] if idx in conf.completer else DEFAULT_COMPLETER[idx]
        completer = QCompleter(list(map(lambda x: f" {x}", this_completer)))
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.searchinput.setCompleter(completer)
        completer.activated.connect(lambda: self.searchinput.setCursorPosition(len(self.searchinput.text())))

    def btn_logic_bind(self):
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.confBtn.clicked.connect(lambda: self.ensure_conf_dialog().show_self())
        self.clipBtn.clicked.connect(self.clip_mgr.read_clip)
        self.aggrBtn.clicked.connect(lambda: self.show_toolWin("ags"))
        self.htBtn.clicked.connect(lambda: self.show_toolWin("hitomi"))
        self.openPBtn.clicked.connect(lambda: curr_os.open_folder(self.sv_path))
        self.shareBtn.clicked.connect(self.shares.upload)
        self.shares.changed.connect(self._sync_share_btn_visible)
        self._sync_share_btn_visible()
        self.domainBtn.clicked.connect(self.do_publish)
        self.login_mgr.bind()

        _safe_disconnect(self.mpreviewBtn.clicked)
        self.mpreviewBtn.clicked.connect(self.show_preview)

        self.page_turn_frame()

    def _sync_share_btn_visible(self):
        self.shareBtn.setVisible(not self.shares.is_empty())

    def page_turn_frame(self):
        def page_turn(_p):
            if not hasattr(self, "preview_mgr"):
                return
            current = self.preview_mgr._current_page
            if _p.startswith("next"):
                target = current + 1
            elif _p.startswith("previous"):
                target = max(1, current - 1)
            else:
                target = int(self.pageEdit.value())
            self.preview_mgr.navigate_to(target)

        _ = lambda arg: self.BrowserWindow.page(lambda: page_turn(arg)) if self.BrowserWindow else page_turn(arg)
        self.nextPageBtn.clicked.connect(lambda: _(f"next{self.pageFrameClickCnt}"))
        self.previousPageBtn.clicked.connect(lambda: _(f"previous{self.pageFrameClickCnt}"))
        self.pageJumpBtn.clicked.connect(lambda: _(str(self.pageEdit.value())))

        def page_edit(_):
            self.pageJumpBtn.setEnabled(True)

        self.pageEdit.valueChanged.connect(page_edit)
    
    def set_preview(self, rect=None, *, skip_env_mode: bool = False):
        from GUI.browser_window import BrowserWindow as BrowserWindowCls
        if self.BrowserWindow:
            self._destroy_browser_window()
        sb = self.BrowserWindow = BrowserWindowCls(self, skip_env_mode=skip_env_mode)
        preview_y = self.y() + self.funcGroupBox.y() - sb.height() + 25
        if rect:
            self.BrowserWindow.setGeometry(rect)
        else:
            self.BrowserWindow.move(self.x()+100, preview_y if preview_y > 0 else 200)
        if self.chooseBox.currentIndex() in Spider.mangas():
            self.BrowserWindow.setMinimumWidth(self.BrowserWindow.minimumWidth() + 30)
            self.BrowserWindow.setMinimumHeight(self.BrowserWindow.minimumHeight() + 30)
            self.BrowserWindow.move(self.BrowserWindow.x(), max(0,self.BrowserWindow.y() - 20))
        self.refresh_lifecycle_state()

    def schedule_preview_warmup(self):
        if self._preview_warmup_pending or self.BrowserWindow:
            return
        if self.chooseBox.currentIndex() not in SPIDERS:
            return
        self._preview_warmup_pending = True

        def _warmup():
            self._preview_warmup_pending = False
            if self.BrowserWindow or self.chooseBox.currentIndex() not in SPIDERS:
                return
            gui_site_runtime = self.gui_site_runtime
            skip_env_mode = not bool(
                gui_site_runtime and (
                    gui_site_runtime.peek_cached_domain()
                    or getattr(gui_site_runtime.provider_cls, "domain", None)
                )
            )
            self.log.debug(f"[preview.perf] warmup BrowserWindow start skip_env_mode={skip_env_mode}")
            self.set_preview(skip_env_mode=skip_env_mode)
            self.log.debug("[preview.perf] warmup BrowserWindow done")

        safe_single_shot(0, _warmup)

    def present_browser(
        self, *,
        ensure_handler=_UNSET,
        ensure_result_kind="checked_ids",
        close_handler=None,
        enable_page_frame=False,
        reload_tf=False,
        rect=None,
    ):
        """Unified BrowserWindow init ceremony + animated presentation.

        When ``reload_tf`` is true (search / online-fav / local-fav publish path),
        always bind ``gui.tf`` into ``home_url`` and load it. Warmup may have
        already constructed BrowserWindow on about:blank; without this branch the
        new HTML never becomes the visible page even though books_cache is filled.
        """
        browser = self.BrowserWindow
        browser_created = False
        if not browser:
            self.set_preview(rect)
            browser = self.BrowserWindow
            browser_created = True

        preview_file = getattr(self, "tf", None)
        if reload_tf and preview_file:
            browser.home_url = QUrl.fromLocalFile(str(preview_file))
            # Warmup / prior show may have already consumed _first_show; always load.
            browser._first_show = False
            browser.load_home()
        elif browser_created and preview_file:
            # Fresh window: showEvent would load home_url, but re-bind in case set_preview
            # raced before gui.tf was assigned (callers should set tf first).
            browser.home_url = QUrl.fromLocalFile(str(preview_file))

        if ensure_handler is not _UNSET:
            browser.set_ensure_handler(ensure_handler, result_kind=ensure_result_kind)
        if close_handler:
            browser.set_close_handler(close_handler)
        final_rect = browser.geometry()
        if enable_page_frame:
            self.refresh_lifecycle_state()
        # Always present when caller asked to reload preview HTML, or window not visible.
        if browser_created or reload_tf or not browser.isVisible():
            PopupAnimator.show(browser, final_rect, duration_ms=220, direction="right")
            if not browser.isVisible():
                browser.show()
                browser.raise_()
                browser.activateWindow()
        return browser

    def show_preview(self):
        def _has_cached_preview():
            if self.flow_stage is GUIFlowStage.SEARCHED:
                return True
            preview_file = getattr(self, "tf", None)
            if not preview_file or not p.Path(preview_file).exists():
                return False
            return any(bool(mgr.is_triggered and mgr.infos) for mgr in (self.clip_mgr, self.ags_mgr))
    
        if self.search_ui_state.request is PreviewRequestState.Running:
            return
        if not _has_cached_preview():
            self.start_and_search()
            return
        return self.preview_mgr._active.show_cached()

    def clean_preview(self):
        self.clean_temp_file()
        self._destroy_browser_window()

    def clean_temp_file(self):
        """when: 1. preview BrowserWindow destroy; 2. pageTurn btn group clicked"""
        if getattr(self, "tf") and p.Path(self.tf).exists():
            os.remove(self.tf)

    def retry_schedule(self):
        image = self._pick_sleep_widget_image(allow_random=True)
        self.reset_search_context()
        self.setup_sleep_widget(image)

    def reset_search_context(self):
        reset_tip = font_color(f"{self.res.reboot_tip}", cls='theme-highlight', size=4)
        self.textBrowser.append(reset_tip)
        if hasattr(self, 'preprocess_mgr'):
            self.preprocess_mgr.cleanup()
        if getattr(self, "preview_mgr", None):
            self.preview_mgr.shutdown()
        if self.timeline_tip_mgr is not None:
            self.timeline_tip_mgr.close()
            self.preview_mgr.handle_choosebox_changed(0, None)
        self.clean_temp_file()
        self._destroy_browser_window()
        from GUI.browser_window import BrowserWindow as BrowserWindowCls
        BrowserWindowCls.clear_proxies()
        self.clip_mgr.reset()
        self.ags_mgr.reset()
        # self.tf = None
        # self.sut = None
        # self.web_is_r18 = False
        self.gui_site_runtime = None
        self.domainBtn.setVisible(False)
        self.loginBtn.setVisible(False)
        self.rv_tools.ero = 0
        self.bsm = None
        self.sv_path = conf.sv_path
        self.flow_stage = GUIFlowStage.IDLE
        self.search_ui_state = SearchUiState()
        self.searchinput.clear()
        self.searchinput.setStatusTip("")
        self.pageEdit.setEnabled(True)
        self.pageEdit.setValue(1)
        self.chooseBox.blockSignals(True)
        self.chooseBox.setCurrentIndex(0)
        self.chooseBox.blockSignals(False)
        self.aggrBtn.setVisible(False)
        self.htBtn.setVisible(False)
        self.clipBtn.setVisible(False)
        self.refresh_lifecycle_state()
        self._restore_feedback_panel()
        self.log.info('===--→ reset_search_context end\n')

    def disable_start(self):
        self.update_search_ui(controls_blocked=True)

    def start_and_search(self, keyword=None, site_index=None):
        self.log.info('===--→ -*- searching')
        if self.search_ui_state.request is PreviewRequestState.Running:
            return
        if site_index is not None:
            self.chooseBox.setCurrentIndex(site_index)
        if keyword:
            self.searchinput.setText(keyword)
        kw = self.searchinput.text().strip()
        if kw.startswith("dc:"):
            share_id = kw[3:].strip()
            self.shares.download(share_id)
            return
        if not kw:
            return InfoBar.info(
                title='', content='先输入搜索词吧', isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=2000, parent=self.textBrowser,
            )
        site = self.chooseBox.currentIndex()
        if site not in SPIDERS or not getattr(self.preview_mgr, "worker", None):
            self.refresh_lifecycle_state()
            return
        cgs_cfg.search.add_history(kw)
        self._set_search_context_menu()
        self.log.debug(f'[search] site :[{site}], keyword [{kw}] ')
        self.preview_mgr.on_spreview_clicked(keyword=kw)

    def next(self):
        self.log.info('===--→ nexting')
        if self.clip_mgr.is_triggered:
            self.clip_mgr.submit_browser_selection()
            return
        if hasattr(self, "ags_mgr") and self.ags_mgr.is_triggered:
            self.ags_mgr.submit_browser_selection()
            return
        self.preview_mgr.submit_browser_selection()

    def crawl(self, episodes=None):
        if episodes is None:
            all_eps = {}
            for book_key, book_eps in getattr(self.preview_mgr, "episodes_cache", {}).items():
                for ep in book_eps or []:
                    all_eps[f"{book_key}-{getattr(ep, 'idx', len(all_eps))}"] = ep
            episodes = select("123456465465464", all_eps)
        if not episodes:
            self.say(font_color(r'selected idxes error!!!', cls='theme-err', size=5))
            return
        book = episodes[0].from_book
        book.episodes = episodes

        QThread.msleep(10)
        self.sel_mgr.submit_decision("EP", book)

        self.log.debug(f'book_num remain: {self.sel_mgr.book_num}')
        self.log.info("===--→ crawl finish\n")

    def crawl_end(self, imgs_path):
        self.refresh_lifecycle_state()
        self.say(font_color("…… (*￣▽￣)(￣▽:;.…::;.:.:::;..::;.:..."))
        self.log.info("-*-*- crawl_end finish, spider closed \n")

    def say(self, string, ignore_http=False):
        fin_s = ""
        if isinstance(string, str) and string.startswith('[httpok]'):
            string = string[len('[httpok]'):]
            ignore_http = True
        if not ignore_http and 'http' in string:
            if self.web_is_r18:
                fin_s = self.res.textbrowser_load_if_http % string
        else:
            fin_s = string
        if fin_s:
            self.textBrowser.append(fin_s)
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)

    def _show_exception_feedback(self, headline: str, guidance: str):
        self.say(headline, ignore_http=True)
        self.say(guidance)

    def processbar_load(self, i):
        self.progressBar.setValue(i)

    def closeEvent(self, event):
        self._closing = True
        if self.script_window is not None:
            self.script_window.close()
        if self.toolWin is not None:
            self.toolWin.close()
        if hasattr(self, 'rv_mgr'):
            self.rv_mgr.stop_scan()
        if hasattr(self, 'task_mgr'):
            self.task_mgr.close()
        if hasattr(self, 'preprocess_mgr'):
            self.preprocess_mgr.cleanup()
        if getattr(self, "preview_mgr", None):
            self.preview_mgr.shutdown()
        event.accept()
        self.destroy()  # 窗口关闭销毁
        if self.dl_mgr is not None:
            self.dl_mgr.close_runtime()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def hook_exception(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        exception = str("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        self.log.error(exception)
        headline = font_color(rf"{type(exc_value)}{exc_value}", cls='theme-err', size=4)
        guidance = font_color(rf"<br>{self.res.global_err_hook} <br>[{conf.log_path}\GUI.log]<br>", cls='theme-err', size=3)
        if QThread.currentThread() is self.thread():
            self._show_exception_feedback(headline, guidance)
            return
        self.exception_feedback_requested.emit(headline, guidance)

    def do_publish(self):
        from utils.processed_class import TmpFormatHtml
        gui_site_runtime = self.gui_site_runtime
        if gui_site_runtime is None:
            raise RuntimeError("gui_site_runtime unavailable for publish flow")
        cached = gui_site_runtime.peek_cached_domain() or ""
        publish_url = getattr(gui_site_runtime.provider_cls, "publish_url", "")
        self.tf = TmpFormatHtml.created_temp_html("publish", bs_theme=bs_theme(), publish_url=publish_url, __cached_domain__=cached)
        provider_domain = getattr(gui_site_runtime.provider_cls, "domain", None)
        self.set_preview(skip_env_mode=not bool(cached or provider_domain))
        self.publish_mgr.setup_channel(self.BrowserWindow.view.page())
        screen_width = QGuiApplication.primaryScreen().availableGeometry().width()
        o_h = self.BrowserWindow.height()
        o_w = int(screen_width * 0.75) if self.BrowserWindow.width() < screen_width * 0.75 else self.BrowserWindow.width()
        self.BrowserWindow.resize(o_w, o_h+150)
        final_rect = self.BrowserWindow.geometry()
        PopupAnimator.show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")

    def open_url_by_browser(self, url, callback=None):
        screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
        rect = QRect(self.x(), int(screen_height*0.05), self.width(), int(screen_height*0.9))
        if not getattr(self, 'BrowserWindow'):
            site_index = (
                self.gui_site_runtime.site_index
                if self.gui_site_runtime is not None
                else self.chooseBox.currentIndex()
            )
            skip_env_mode = self.gui_site_runtime is None or site_index not in SPIDERS
            self.set_preview(rect, skip_env_mode=skip_env_mode)
        else:
            self.BrowserWindow.setGeometry(rect)
            # 复用浏览器时刷新当前站点环境 (cookies/referer/proxy):
            # 否则 conf.cookies 变化 (登录保存/清除) 不会反映到浏览器
            if self.gui_site_runtime is not None:
                self.BrowserWindow.apply_standard_environment()
        final_rect = self.BrowserWindow.geometry()
        PopupAnimator.show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")
        self.BrowserWindow.view.load(QUrl(url))
        if callback:
            callback()

    def say_show_max(self):
        """.discard()"""

    def _on_decision_made(self, lane: str, indexes: list):
        from utils.middleware.timeline import EventSource, TimelineStage
        mgr = getattr(self, "mid_mgr", None)
        if mgr and mgr.enabled:
            stage_map = {"BOOK": TimelineStage.BOOK_SENT, "EP": TimelineStage.EP_SENT}
            if stage := stage_map.get(lane):
                mgr.dispatch_stage(stage, EventSource.UI, {"lane": lane})

    def _show_skip_info(self, skip_info: dict):
        tips = []
        if skip_info.get("running"):
            tips.append(f"进行中 {skip_info['running']}")
        if skip_info.get("downloaded"):
            tips.append(f"已下载 {skip_info['downloaded']}")
        if tips:
            self.say(font_color(f"已跳过：{'，'.join(tips)}", cls='theme-tip'), ignore_http=True)

    def publish_share_books(self, books):
        self.preview_mgr.publish_share_books(books)

# ---
