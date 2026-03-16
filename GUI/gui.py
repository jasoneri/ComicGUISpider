import os
import re
import sys
import random
import traceback
import contextlib
from PyQt5.QtGui import QKeySequence, QGuiApplication
from PyQt5.QtCore import (
    QThread, Qt, QCoreApplication, QUrl, QRect,
    pyqtSignal
)
from GUI.core.timer import safe_single_shot
from PyQt5.QtWidgets import QMainWindow, QCompleter, QShortcut
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.uic.qfluent import (
    MonkeyPatch as FluentMonkeyPatch, CustomSplashScreen
)
from GUI.mainwindow import MitmMainWindow
from GUI.core.font import font_color
from GUI.core.theme import setupTheme
from GUI.core.anim import PopupAnimator
from GUI.conf_dialog import ConfDialog
from GUI.browser_window import BrowserWindow as BrowserWindowCls
from GUI.tools import ToolWindow, TextUtils
from GUI.manager import (
    TaskProgressManager, ClipGUIManager, AggrSearchManager, RVManager,
    CGSMidManagerGUI, PreviewMgr, UpdateNotifier, PublishDomainManager,
    SelectionFlowManager, DownloadRuntimeManager
)
from GUI.manager.preprocess import PreprocessManager
from GUI.types import GUIFlowStage
from utils.middleware.timeline import EventSource, TimelineStage
from variables import *
from assets import res
from utils import conf, p, curr_os, select, ori_path, bs_theme, temp_p
from utils.processed_class import (
    PreviewHtml, TmpFormatHtml
)
from utils.redViewer_tools import Handler as rVtools
from utils.website import spider_utils_map, InfoMinix, WnacgUtils
from utils.sql import SqlRecorder

_UNSET = object()


class SpiderGUI(QMainWindow, MitmMainWindow):
    res = res.GUI
    setup_finished = pyqtSignal()
    BrowserWindow: BrowserWindowCls = None
    toolWin = None
    web_is_r18 = False
    spiderUtils = None
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
        self.first_init = True
        self.setupUi(self)

    def setupUi(self, MainWindow):
        snapshot = None
        if not self.first_init and getattr(self, 'task_mgr', None):
            snapshot = self.task_mgr.capture_native_snapshot()
        super(SpiderGUI, self).setupUi(MainWindow)
        if self.first_init:
            self.splashScreen = CustomSplashScreen(self)
            self.setup_sleep_widget(self.bg_mgr.bg_f)
            self.show()
            res.set_language(conf.lang)
            self.apply_translations()
            self.task_init()
            self.task_mgr = TaskProgressManager(self)
            self.task_mgr.init_native_panel()
            setupTheme(self)
            safe_single_shot(10, self.setupUi_)
            self.first_init = False
        else:
            self.apply_translations()
            if getattr(self.bg_mgr, "bg_fs", []):
                self.setup_sleep_widget(random.choice(self.bg_mgr.bg_fs)[0])
            else:
                self.setup_sleep_widget(self.bg_mgr.bg_f)
            setupTheme(self)
            self.task_init()
            self.task_mgr.rebind_native_panel(snapshot)
            self.finish_setup()

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

        if getattr(self, 'sel_mgr', None):
            with contextlib.suppress(TypeError):
                self.sel_mgr.decision_made.disconnect()
            with contextlib.suppress(TypeError):
                self.sel_mgr.skip_notified.disconnect()
        if getattr(self, 'dl_mgr', None):
            with contextlib.suppress(TypeError):
                self.dl_mgr.process_stage_changed.disconnect()

        self.clip_mgr = ClipGUIManager(self)
        self.ags_mgr = AggrSearchManager(self)
        self.preview_mgr = PreviewMgr(self)
        self.publish_mgr = PublishDomainManager(self)
        if not getattr(self, 'dl_mgr', None):
            self.dl_mgr = DownloadRuntimeManager(self)
        else:
            self.dl_mgr.rebind(self)
        self.sel_mgr = SelectionFlowManager(self)
        if not getattr(self, 'mid_mgr', None):
            self.mid_mgr = CGSMidManagerGUI(self)
        else:
            self.mid_mgr.rebind(self)
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
        self.searchReady = False
        self.searchRunning = False
        self.previewInit = True
        self.previewSecondInit = False
        self.BrowserWindow = None
        self.bsm = None
        self.chooseBox.setEnabled(True)
        self.previewBtn.setVisible(True)
        self.mpreviewBtn.setVisible(False)

        self.preprocess_mgr = PreprocessManager(self)
        with contextlib.suppress(TypeError):
            self.chooseBox.currentIndexChanged.disconnect(self._chooseBox_changed_handle)
        self.chooseBox.currentIndexChanged.connect(self._chooseBox_changed_handle)
        self.searchReady = False
        self.searchRunning = False
        self.setup_finished.emit()

    def _chooseBox_changed_handle(self, index):
        if index not in SPIDERS.keys() and index != 0:
            self.mpreviewBtn.setVisible(False)
            self.previewBtn.setVisible(False)
            self.retrybtn.setEnabled(True)
            self.flow_stage = GUIFlowStage.IDLE
            self.preview_mgr.handle_choosebox_changed(index)
            self.preprocess_mgr.handle_choosebox_changed(index)
            return
        self.spiderUtils = spider_utils_map[index]
        self.rv_tools.ero = 0
        self.web_is_r18 = index in Spider.specials()
        self.mpreviewBtn.setVisible(index in SPIDERS and not self.web_is_r18)
        self.previewBtn.setVisible(self.web_is_r18)
        self.toolWin.rvInterface.set_sauce_visible(self.web_is_r18)
        self.mid_mgr.set_lane_hidden("EP", self.web_is_r18)
        if self.web_is_r18:
            self.sut = self.spiderUtils(conf)
            self.rv_tools.ero = 1
        self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", STATUS_TIP[index]))
        self.searchinput.setEnabled(True)
        FluentMonkeyPatch.rbutton_menu_lineEdit(self.searchinput)
        self.searchReady = False
        self.searchRunning = False
        if index and not self.dl_mgr.spider_runtime:
            self.chooseBox.setDisabled(True)
            try:
                self.dl_mgr.start_runtime(index)
            finally:
                self.chooseBox.setEnabled(True)
        self.retrybtn.setEnabled(True)
        self.chooseBox_changed_tips(index)
        if self.web_is_r18:
            self.sv_path = conf.sv_path.joinpath(res.SPIDER.ERO_BOOK_FOLDER)
        else:
            self.sv_path = conf.sv_path
        self.set_completer()
        self.flow_stage = GUIFlowStage.IDLE
        self.preview_mgr.handle_choosebox_changed(index)
        self.preprocess_mgr.handle_choosebox_changed(index)

    def chooseBox_changed_tips(self, index):
        match index:
            case 1:
                self.pageEdit.setStatusTip(self.pageEdit.statusTip() + f"  {self.res.copymaga_page_status_tip}")
                self.say(font_color(self.res.copymaga_tips, cls='theme-highlight'))
            case 3:
                if not conf.proxies:
                    self.say(font_color(self.res.wnacg_desc, cls='theme-highlight'), ignore_http=True)
            case 4:
                self.pageEdit.setDisabled(True)
                self.say(font_color(res.EHentai.GUIDE, cls='theme-highlight'))
            case _:
                self.say(font_color(getattr(self.res, f"{self.spiderUtils.name}_desc", ""), cls='theme-highlight'), ignore_http=True)
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
                with contextlib.suppress(TypeError):
                    shortcut.activated.disconnect()
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
        def _search_troggle(text):
            self.previewBtn.setEnabled(True)
        self.searchinput.textChanged.connect(_search_troggle)
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.confBtn.clicked.connect(self.conf_dia.show_self)
        self.conf_dia.acceptBtn.clicked.connect(self.set_completer)
        self.clipBtn.clicked.connect(self.clip_mgr.read_clip)
        self.aggrBtn.clicked.connect(self.showAggrWin)
        self.openPBtn.clicked.connect(lambda: curr_os.open_folder(self.sv_path))

        with contextlib.suppress(TypeError):
            self.mpreviewBtn.clicked.disconnect()
        self.mpreviewBtn.clicked.connect(self.show_preview)

        self.page_turn_frame()

    def mark_tip(self, ori_infos):
        """将self.books的各book加上
        1.已下载标记,from sql;
        2.（未做）非被指定标记"""
        def mark_tip(_infos):
            sql_utils = SqlRecorder()
            obj_to_md5 = {}
            md5s = []
            for obj in _infos:
                _, this_md5 = obj.id_and_md5()
                obj_to_md5[this_md5] = obj
                md5s.append(this_md5)
            downloaded_md5 = sql_utils.batch_check_dupe(md5s)
            for md5, obj in obj_to_md5.items():
                if md5 in downloaded_md5:
                    obj.mark_tip = "downloaded"
            sql_utils.close()
        infos = sorted(ori_infos.values(), key=lambda x: x.idx)
        if conf.isDeduplicate:
            mark_tip(infos)
        return infos

    def page_turn_frame(self):
        def page_turn(_p):
            if self.BrowserWindow and hasattr(self, 'preview_mgr'):
                self.preview_mgr.on_before_page_turn()

            if _p.startswith("next"):
                self.pageEdit.setValue(int(self.pageEdit.value()) + 1)
                self.preview_mgr.navigate_to(int(self.pageEdit.value()))
            elif _p.startswith("previous"):
                self.pageEdit.setValue(max(1, int(self.pageEdit.value()) - 1))
                self.preview_mgr.navigate_to(int(self.pageEdit.value()))
            else:
                self.preview_mgr.navigate_to(int(self.pageEdit.value()))

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
        self.BrowserWindow.setMinimumWidth(self.BrowserWindow.minimumWidth() + 30)
        self.BrowserWindow.setMinimumHeight(self.BrowserWindow.minimumHeight() + 30)
        # button group
        self.previewBtn.setEnabled(True)
        self.previewBtn.setFocus()

    def present_browser(
        self, *,
        ensure_handler=_UNSET,
        close_handler=None,
        enable_page_frame=False,
        reload_tf=False,
        rect=None,
    ):
        """Unified BrowserWindow init ceremony + animated presentation."""
        if self.previewInit or not self.BrowserWindow:
            self.set_preview(rect)
            self.previewInit = False
        elif self.previewSecondInit:
            self.BrowserWindow.second_init()
            self.previewSecondInit = False
        elif reload_tf:
            self.BrowserWindow.home_url = QUrl.fromLocalFile(self.tf)
            self.BrowserWindow.load_home()

        if ensure_handler is not _UNSET:
            self.BrowserWindow.set_ensure_handler(ensure_handler)
        if close_handler:
            self.BrowserWindow.set_close_handler(close_handler)
        if enable_page_frame:
            self.pageFrame.setEnabled(True)
            self.pageFrame.setStyleSheet("QToolButton { background-color: rgb(255, 255, 255); }")
        final_rect = self.BrowserWindow.geometry()
        PopupAnimator.show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")
        return self.BrowserWindow

    def show_preview(self):
        if not self.searchReady:
            self.start_and_search()
        elif self.searchRunning:
            InfoBar.info(title='', content='searching', isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=2000, parent=self.textBrowser)
        else:
            return self.preview_mgr._active.show_cached()

    def clean_preview(self):
        self.clean_temp_file()
        if self.BrowserWindow:
            self.BrowserWindow.destroy()

    def clean_temp_file(self):
        """when: 1. preview BrowserWindow destroy; 2. pageTurn btn group clicked"""
        if getattr(self, "tf") and p.Path(self.tf).exists():
            os.remove(self.tf)

    def retry_schedule(self):
        if hasattr(self, 'preprocess_mgr'):
            self.preprocess_mgr.cleanup()

        def retry_all():
            try:
                if getattr(self, "preview_mgr", None):
                    self.preview_mgr.shutdown()
            except Exception:
                self.log.error(str(traceback.format_exc()))
            self.log = conf.cLog(name="GUI")
            self.clean_preview()
            self.BrowserWindow = None
            self.setupUi(self)

        self.say(font_color(f"{self.res.reboot_tip}", cls='theme-highlight', size=4))
        safe_single_shot(50, retry_all)
        self.retrybtn.setDisabled(True)
        self.log.info('===--→ retry_schedule end\n')

    def disable_start(self):
        self.searchinput.setDisabled(True)
        self.clipBtn.setDisabled(True)

    def _on_worker_finished(self, imgs_path: str, success: bool):
        pass

    def start_and_search(self, keyword=None, site_index=None):
        self.log.info('===--→ -*- searching')
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
        self.searchReady = True
        self.searchRunning = True
        self.searchinput.setEnabled(False)
        site = self.chooseBox.currentIndex()
        self.log.debug(f'[search] site :[{site}], keyword [{kw}] ')
        self.preview_mgr.on_spreview_clicked(keyword=kw)

    def next(self):
        self.log.info('===--→ nexting')

        mgr = None
        if self.clip_mgr.is_triggered:
            mgr = self.clip_mgr
        elif hasattr(self, "ags_mgr") and self.ags_mgr.is_triggered:
            mgr = self.ags_mgr

        if mgr:
            selected_list = mgr.create_selected_list(self.BrowserWindow.output)
            if selected_list and len(selected_list) > 20 and int(conf.concurr_num) > 10:
                conf.update(concurr_num=8)
                self.say(res.SPIDER.reduce_concurrency_tip % 8)
            self.sel_mgr.submit_decision(
                "BOOK",
                selected_list,
                flow_stage=self.flow_stage,
            )
            return
        idxes = f"{str(self.BrowserWindow.output)}"
        cache = getattr(self.preview_mgr, "books_cache", {})
        selected_books = select(idxes, {int(k): v for k, v in cache.items()})
        self.sel_mgr.submit_decision(
            "BOOK", selected_books,
            flow_stage=self.flow_stage,
        )

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
        self.progressBar.setCustomBarColor(light="#00ff00", dark="#00cc00")
        self.retrybtn.setEnabled(True)
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
        cursor = self.textBrowser.textCursor()
        self.textBrowser.moveCursor(cursor.End)  # move cursor to the end for show dynamicly

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
        cache_file = temp_p.joinpath(f"{self.spiderUtils.name}_domain.txt")
        cached = cache_file.read_text(encoding='utf-8').strip() if cache_file.exists() else ""
        self.tf = TmpFormatHtml.created_temp_html("publish",
            bs_theme=bs_theme(), publish_url=self.spiderUtils.publish_url,
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
