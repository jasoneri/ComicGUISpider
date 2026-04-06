import os
import re
import sys
import random
import traceback
import contextlib
import warnings
from PySide6.QtGui import QKeySequence, QGuiApplication, QShortcut, QTextCursor
from PySide6.QtCore import (
    QThread, Qt, QCoreApplication, QUrl, QRect,
    Signal,
)
from GUI.core.timer import safe_single_shot
from PySide6.QtWidgets import QMainWindow, QCompleter
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox

from GUI.uic.qfluent import (
    MonkeyPatch as FluentMonkeyPatch, CustomSplashScreen
)
from GUI.mainwindow import MitmMainWindow
from GUI.core.font import font_color
from GUI.core.theme import setupTheme
from GUI.core.anim import PopupAnimator
from GUI.core.browser.browser_environment import peek_snapshot_domain
from utils.sql.download_state import DownloadStateStore
from GUI.conf_dialog import ConfDialog
from GUI.browser_window import BrowserWindow as BrowserWindowCls
from GUI.tools import ToolWindow, TextUtils
from GUI.manager import (
    TaskProgressManager, ClipGUIManager, AggrSearchManager, RVManager,
    CGSMidManagerGUI, PreviewMgr, UpdateNotifier, PublishDomainManager,
    SelectionFlowManager, DownloadRuntimeManager
)
from utils.config.qc import cgs_cfg
from GUI.manager.preprocess import PreprocessManager
from GUI.types import GUIFlowStage, PreviewRequestState, SearchContextSnapshot, SearchLifecycleState, SearchUiState
from utils.middleware.timeline import EventSource, TimelineStage
from variables import *
from assets import res
from utils import conf, p, curr_os, select, ori_path, bs_theme
from utils.processed_class import (
    PreviewHtml, TmpFormatHtml
)
from utils.redViewer_tools import Handler as rVtools
from utils.website import InfoMinix, WnacgUtils
from utils.website.registry import resolve_site_gateway, resolve_spider_adapter
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
    BrowserWindow: BrowserWindowCls = None
    toolWin = None
    web_is_r18 = False
    site_gateway = None
    spider_adapter = None
    sut = None
    bsm: dict = None  # books show max
    flow_stage: GUIFlowStage = GUIFlowStage.IDLE
    sv_path = None
    rv_tools: rVtools = None

    def __init__(self, parent=None):
        super(SpiderGUI, self).__init__(parent)
        self.log = conf.cLog(name="GUI")
        # self.log.debug(f'-*- 主进程id {os.getpid()}')
        # self.log.debug(f'-*- 主线程id {threading.currentThread().ident}')
        self.setupUi(self)

    def _pick_sleep_widget_image(self, *, allow_random: bool) -> str | None:
        if allow_random and getattr(self.bg_mgr, "bg_fs", []):
            return random.choice(self.bg_mgr.bg_fs)[0]
        return self.bg_mgr.bg_f

    def setupUi(self, MainWindow):
        super(SpiderGUI, self).setupUi(MainWindow)
        self.splashScreen = CustomSplashScreen(self)
        self.setup_sleep_widget(self._pick_sleep_widget_image(allow_random=False))
        self.show()
        res.set_language(conf.lang)
        self.apply_translations()
        self.task_init()
        self.task_mgr = TaskProgressManager(self)
        self.task_mgr.init_native_panel()
        setupTheme(self)
        safe_single_shot(10, self.setupUi_)

    def setupUi_(self):
        self.rv_tools = rVtools()
        self.rv_mgr = RVManager(self)
        self.rv_mgr.start_scan(show_progress=False)
        self.browser_zoom_factor = 1.0  # WebEngine 用户缩放率，生命周期同 SpiderGUI
        self.textBrowser.clear()
        self.finish_setup()

    def finish_setup(self):
        self.generation_bind()
        if not getattr(self, "_startup_completed", False):
            self.startup_only()
            self._startup_completed = True

    def _restore_feedback_panel(self):
        self.textBrowser.clear()
        self.textBrowser.append(TextUtils.description())
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)

    def startup_only(self):
        self.update_notifier = UpdateNotifier(self)
        self.update_notifier.check_on_startup()
        if hasattr(self, 'splashScreen'):
            self.splashScreen.finish()

    def generation_bind(self):
        self.flow_stage = GUIFlowStage.IDLE
        self.pageFrameClickCnt = 0
        self.conf_dia = ConfDialog(self)
        self.textBrowser.append(TextUtils.description())

        self.clip_mgr = ClipGUIManager(self)
        self.ags_mgr = AggrSearchManager(self)
        self.preview_mgr = PreviewMgr(self)
        self.publish_mgr = PublishDomainManager(self)
        self.download_state = DownloadStateStore()
        self.dl_mgr = DownloadRuntimeManager(self)
        self.sel_mgr = SelectionFlowManager(self)
        self.mid_mgr = CGSMidManagerGUI(self)
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
        self._search_context = None
        self.BrowserWindow = None
        self.bsm = None
        self.search_ui_state = SearchUiState()

        self.preprocess_mgr = PreprocessManager(self)
        _safe_disconnect(self.chooseBox.currentIndexChanged, self._chooseBox_changed_handle)
        self.chooseBox.currentIndexChanged.connect(self._chooseBox_changed_handle)
        self.refresh_lifecycle_state()
        self.setup_finished.emit()

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

    def _snapshot_cookies(self, site_index: int) -> dict[str, dict]:
        if site_index == Spider.JM:
            if cookies := conf.cookies.get("jm"):
                return {"jm": dict(cookies)}
        elif site_index == Spider.EHENTAI:
            if cookies := conf.cookies.get("ehentai"):
                return {"ehentai": dict(cookies)}
        return {}

    def _build_search_context_snapshot(self, site_index: int) -> SearchContextSnapshot:
        domains = {}
        try:
            site_gateway = resolve_site_gateway(site_index)
        except ValueError:
            site_gateway = None
        if site_index == Spider.JM and site_gateway is not None:
            if domain := peek_snapshot_domain(site_gateway):
                domains["jm"] = domain
        elif site_index == Spider.WNACG and site_gateway is not None:
            if domain := peek_snapshot_domain(site_gateway):
                domains["wnacg"] = domain
        elif site_index == Spider.EHENTAI and site_gateway is not None:
            domains["ehentai"] = site_gateway.domain
        return SearchContextSnapshot(
            site_index=site_index,
            proxies=list(conf.proxies or []),
            cookies=self._snapshot_cookies(site_index),
            domains=domains,
            custom_map=dict(conf.custom_map or {}),
            doh_url=cgs_cfg.get_doh_url(),
        )

    @property
    def search_context(self) -> SearchContextSnapshot | None:
        return self._search_context

    def update_search_context(self, snapshot: SearchContextSnapshot):
        if snapshot.site_index != self.chooseBox.currentIndex():
            return
        self._search_context = snapshot
        if getattr(self, "preview_mgr", None):
            self.preview_mgr.update_search_context(snapshot)
        if getattr(self, "BrowserWindow", None):
            self.BrowserWindow.apply_standard_environment()

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
            self._search_context = None
            self.search_ui_state = SearchUiState()
            self.web_is_r18 = False
            self.site_gateway = None
            self.spider_adapter = None
            self.flow_stage = GUIFlowStage.IDLE
            self.preview_mgr.handle_choosebox_changed(index, None)
            self.refresh_lifecycle_state()
            return

        self._search_context = self._build_search_context_snapshot(index)
        self.search_ui_state = SearchUiState()
        try:
            self.site_gateway = resolve_site_gateway(index)
        except ValueError:
            self.site_gateway = None
        try:
            self.spider_adapter = resolve_spider_adapter(index)
        except ValueError:
            self.spider_adapter = None
        self.rv_tools.ero = 0
        self.web_is_r18 = index in Spider.specials()
        self.toolWin.rvInterface.set_sauce_visible(self.web_is_r18)
        self.mid_mgr.set_lane_hidden("EP", self.web_is_r18)
        self.sut = None
        if index in (2,3) and not conf.proxies:
            self.domainBtn.setVisible(True)
        if self.web_is_r18 and self.site_gateway is not None:
            self.rv_tools.ero = 1
        self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", STATUS_TIP.get(index) or ""))
        FluentMonkeyPatch.rbutton_menu_lineEdit(self.searchinput)
        if index in SPIDERS and not self.dl_mgr.spider_runtime:
            self.dl_mgr.start_runtime(index)
        self.chooseBox_changed_tips(index)
        if self.web_is_r18:
            self.sv_path = conf.sv_path.joinpath(res.SPIDER.ERO_BOOK_FOLDER)
        else:
            self.sv_path = conf.sv_path
        self.set_completer()
        self.flow_stage = GUIFlowStage.IDLE
        self.preview_mgr.handle_choosebox_changed(index, self._search_context)
        self.preprocess_mgr.handle_choosebox_changed(index, self._search_context)
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
                if self.site_gateway:
                    self.say(font_color(getattr(self.res, f"{self.site_gateway.name}_desc", ""), cls='theme-highlight'), ignore_http=True)
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

    def showAggrWin(self):
        self.rvBtn.click()
        def _jump():
            self.toolWin.stackedWidget.setCurrentWidget(self.toolWin.asInterface)
        safe_single_shot(10, _jump)

    def set_tool_win(self):
        # if getattr(self, "toolWin", None):
        #     self.toolWin.close()
        self.toolWin = ToolWindow(self)
        # self.toolWin.addMidTool()  # TODO[2](2026-03-07): 下个稳定版本恢复

        def show_toolWin():
            t = self.toolWin
            h = self.height()
            abs_y = self.y() + h
            screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
            target_y = screen_height - t.height() if abs_y + t.height() > screen_height else abs_y
            target_rect = QRect(self.x(), target_y, t.width(), t.height())
            PopupAnimator.show(t, target_rect, duration_ms=220, direction="down")
        self.rvBtn.clicked.connect(show_toolWin)

    def set_completer(self):
        idx = self.chooseBox.currentIndex()
        if idx == 0:
            return
        this_completer = conf.completer[idx] if idx in conf.completer else DEFAULT_COMPLETER[idx]
        completer = QCompleter(list(map(lambda x: f" {x}", this_completer)))
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.searchinput.setCompleter(completer)
        completer.activated.connect(lambda :
            self.searchinput.setCursorPosition(len(self.searchinput.text())))

    def btn_logic_bind(self):
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.confBtn.clicked.connect(self.conf_dia.show_self)
        self.conf_dia.acceptBtn.clicked.connect(self.set_completer)
        self.clipBtn.clicked.connect(self.clip_mgr.read_clip)
        self.aggrBtn.clicked.connect(self.showAggrWin)
        self.openPBtn.clicked.connect(lambda: curr_os.open_folder(self.sv_path))
        self.domainBtn.clicked.connect(self.do_publish)

        _safe_disconnect(self.mpreviewBtn.clicked)
        self.mpreviewBtn.clicked.connect(self.show_preview)

        self.page_turn_frame()

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
    
    def set_preview(self, rect=None):
        sb = self.BrowserWindow = BrowserWindowCls(self)
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

    def present_browser(
        self, *,
        ensure_handler=_UNSET,
        ensure_result_kind="checked_ids",
        close_handler=None,
        enable_page_frame=False,
        reload_tf=False,
        rect=None,
    ):
        """Unified BrowserWindow init ceremony + animated presentation."""
        browser_created = False
        if not self.BrowserWindow:
            self.set_preview(rect)
            browser_created = True
        elif reload_tf:
            self.BrowserWindow.home_url = QUrl.fromLocalFile(str(self.tf)) if self.tf else QUrl("about:blank")
            self.BrowserWindow.load_home()

        if ensure_handler is not _UNSET:
            self.BrowserWindow.set_ensure_handler(ensure_handler, result_kind=ensure_result_kind)
        if close_handler:
            self.BrowserWindow.set_close_handler(close_handler)
        final_rect = self.BrowserWindow.geometry()
        if enable_page_frame:
            self.refresh_lifecycle_state()
        if browser_created or not reload_tf:
            PopupAnimator.show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")
        return self.BrowserWindow

    def show_preview(self):
        def _has_cached_preview():
            if self.flow_stage is GUIFlowStage.SEARCHED:
                return True
            preview_file = getattr(self, "tf", None)
            if not preview_file or not p.Path(preview_file).exists():
                return False
            return any(bool(mgr.is_triggered and mgr.infos) for mgr in (self.clip_mgr, self.ags_mgr))
    
        if self.search_ui_state.request is PreviewRequestState.Running:
            InfoBar.info(title='', content='searching', isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=2000, parent=self.textBrowser)
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
            self.preview_mgr.handle_choosebox_changed(0, None)
        self.clean_temp_file()
        self._destroy_browser_window()
        BrowserWindowCls.clear_proxies()
        self.clip_mgr.reset()
        self.ags_mgr.reset()
        # self.tf = None
        # self.sut = None
        # self.web_is_r18 = False
        self.site_gateway = None
        self.spider_adapter = None
        self.domainBtn.setVisible(False)
        self.rv_tools.ero = 0
        self.bsm = None
        self.sv_path = conf.sv_path
        self.flow_stage = GUIFlowStage.IDLE
        self._search_context = None
        self.search_ui_state = SearchUiState()
        self.searchinput.clear()
        self.searchinput.setStatusTip("")
        self.pageEdit.setEnabled(True)
        self.pageEdit.setValue(1)
        self.chooseBox.blockSignals(True)
        self.chooseBox.setCurrentIndex(0)
        self.chooseBox.blockSignals(False)
        self.aggrBtn.setVisible(False)
        self.clipBtn.setVisible(False)
        self.refresh_lifecycle_state()
        self._restore_feedback_panel()
        self.log.info('===--→ reset_search_context end\n')

    def disable_start(self):
        self.update_search_ui(controls_blocked=True)

    def start_and_search(self, keyword=None, site_index=None):
        self.log.info('===--→ -*- searching')
        if self.search_ui_state.request is PreviewRequestState.Running:
            InfoBar.info(title='', content='searching', isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=2000, parent=self.textBrowser)
            return
        if site_index is not None:
            self.chooseBox.setCurrentIndex(site_index)
        if keyword:
            self.searchinput.setText(keyword)
        kw = self.searchinput.text().strip()
        if not kw:
            InfoBar.info(
                title='', content='先输入搜索词吧', isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=2000,
                parent=self.textBrowser
            )
            return
        site = self.chooseBox.currentIndex()
        if site not in SPIDERS or not getattr(self.preview_mgr, "worker", None):
            self.refresh_lifecycle_state()
            return
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
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

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

    def processbar_load(self, i):
        self.progressBar.setValue(i)

    def closeEvent(self, event):
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
        if getattr(self, "dl_mgr", None):
            self.dl_mgr.close_runtime()
        sys.exit(0)

    def hook_exception(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        exception = str("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        self.log.error(exception)
        self.say(font_color(rf"{type(exc_value)}{exc_value}", cls='theme-err', size=4), ignore_http=True)
        self.say(font_color(rf"<br>{self.res.global_err_hook} <br>[{conf.log_path}\GUI.log]<br>", cls='theme-err', size=3))

    def do_publish(self):
        gateway = self.site_gateway
        if gateway is None:
            raise RuntimeError("site gateway unavailable for publish flow")
        cache_file = gateway.cache_path()
        cached = cache_file.read_text(encoding='utf-8').strip() if cache_file.exists() else ""
        self.tf = TmpFormatHtml.created_temp_html("publish",
            bs_theme=bs_theme(), publish_url=gateway.publish_url,
            wnacg_publish=WnacgUtils.publish_domain, __cached_domain__=cached
        )
        self.set_preview()
        self.publish_mgr.setup_channel(self.BrowserWindow.view.page())
        screen_width = QGuiApplication.primaryScreen().availableGeometry().width()
        o_h = self.BrowserWindow.height()
        o_w = int(screen_width * 0.75) if self.BrowserWindow.width() < screen_width * 0.75 else self.BrowserWindow.width()
        self.BrowserWindow.resize(o_w, o_h+150)
        final_rect = self.BrowserWindow.geometry()
        PopupAnimator.show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")

    def open_url_by_browser(self, url, callback=None):
        screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
        rect = QRect(self.x(), int(screen_height*0.05),
            self.width(), int(screen_height*0.9))
        if not getattr(self, 'BrowserWindow'):
            self.set_preview(rect)
        else:
            self.BrowserWindow.setGeometry(rect)
        final_rect = self.BrowserWindow.geometry()
        PopupAnimator.show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")
        self.BrowserWindow.view.load(QUrl(url))
        if callback:
            callback()

    def say_show_max(self):
        """.discard()"""

    def _on_decision_made(self, lane: str, indexes: list):
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

# ---
