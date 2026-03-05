import os
import re
import sys
import random
import traceback
import contextlib
from multiprocessing import Process
import multiprocessing.managers as m
from PyQt5.QtGui import QKeySequence, QGuiApplication
from PyQt5.QtCore import (
    QThread, Qt, QCoreApplication, QUrl, QRect, QTimer,
    pyqtSignal
)
from PyQt5.QtWidgets import QMainWindow, QCompleter, QShortcut

from GUI.uic.qfluent import (
    MonkeyPatch as FluentMonkeyPatch, CustomSplashScreen
)
from GUI.mainwindow import MitmMainWindow
from GUI.core.font import font_color
from GUI.core.theme import setupTheme
from GUI.core.anim import animate_popup_show
from GUI.conf_dialog import ConfDialog
from GUI.browser_window import BrowserWindow as BrowserWindowCls
from GUI.thread import WorkThread, QueueInitThread
from GUI.tools import ToolWindow, TextUtils
from GUI.manager import (
    TaskProgressManager, ClipGUIManager, AggrSearchManager, RVManager,
    CGSMidManagerGUI, MangaPreviewManager, UpdateNotifier, PublishDomainManager
)
from GUI.manager.preprocess import PreprocessManager
from utils.middleware.timeline import EventSource, TimelineStage
from variables import *
from assets import res
from utils import Queues, QueuesManager, conf, p, curr_os, select, ori_path, bs_theme, temp_p
from utils.processed_class import (
    InputFieldState, TextBrowserState, ProcessState,
    GuiQueuesManger, refresh_state, crawl_what,
    PreviewHtml, TmpFormatHtml
)
from utils.redViewer_tools import Handler as rVtools
from utils.website import spider_utils_map, InfoMinix, WnacgUtils
from utils.sql import SqlRecorder


class SpiderGUI(QMainWindow, MitmMainWindow):
    res = res.GUI
    setup_finished = pyqtSignal()
    input_state: InputFieldState = None
    text_browser_state: TextBrowserState = None
    process_state: ProcessState = None
    queues: Queues = None
    book_choose: list = []
    book_num: int = 0
    nextclickCnt = 0
    pageFrameClickCnt = 0
    BrowserWindow: BrowserWindowCls = None
    toolWin = None
    books = {}
    keep_books = []
    eps = []
    web_is_r18 = False
    spiderUtils = None
    sut = None
    bsm: dict = None  # books show max

    p_crawler: Process = None
    p_qm: Process = None
    queue_port: int = None
    bThread: WorkThread = None
    manager: QueuesManager = None
    guiQueuesManger: GuiQueuesManger = None
    Q = None
    s: m.Server = None
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
            QTimer.singleShot(10, self.setupUi_)
            self.first_init = False
        else:
            self.apply_translations()
            self.chooseBox.setDisabled(True)
            if getattr(self.bg_mgr, "bg_fs", []):
                self.setup_sleep_widget(random.choice(self.bg_mgr.bg_fs)[0])
            else:
                self.setup_sleep_widget(self.bg_mgr.bg_f)
            setupTheme(self)
            self.task_init()
            self.task_mgr.rebind_native_panel(snapshot)
            self.on_queue_init_completed(self.manager, self.Q, self.queue_port)

    def setupUi_(self):
        """启动队列初始化线程"""
        self.queue_init_thread = QueueInitThread(self)
        self.queue_init_thread.init_completed.connect(self.on_queue_init_completed)
        self.queue_init_thread.start()
        
        self.rv_tools = rVtools()
        self.rv_mgr = RVManager(self)
        self.rv_mgr.start_scan(show_progress=False)
        self.browser_zoom_factor = 1.0  # WebEngine 用户缩放率，生命周期同 SpiderGUI

    def on_queue_init_completed(self, manager, Q, queue_port):
        self.manager = manager
        self.Q = Q
        self.queue_port = queue_port
        self.textBrowser.clear()
        self.chooseBox.setEnabled(True)
        self.finish_setup()

    def finish_setup(self):
        self.books = {}
        self.keep_books = []
        self.eps = []
        self.conf_dia = ConfDialog(self)
        self.textBrowser.append(TextUtils.description())
        self.input_state = InputFieldState(keyword='', bookSelected=0, indexes='', pageTurn='')
        # 按钮组
        self.clip_mgr = ClipGUIManager(self)
        self.ags_mgr = AggrSearchManager(self)
        self.mid_mgr = CGSMidManagerGUI(self)
        self.manga_mgr = MangaPreviewManager(self)
        self.publish_mgr = PublishDomainManager(self)
        self.nextclickCnt = 0
        self.pageFrameClickCnt = 0
        self.sv_path = conf.sv_path
        self.btn_logic_bind()
        self.set_shortcut()
        self.set_tool_win()
        # 预览
        self.tf = None
        self.previewInit = True
        self.previewSecondInit = False
        self.BrowserWindow = None
        self.bsm = None
        self.previewBtn.setVisible(True)
        self.mpreviewBtn.setVisible(False)

        def chooseBox_changed_handle(index):
            if index not in SPIDERS.keys() and index != 0:
                self.mpreviewBtn.setVisible(False)
                self.previewBtn.setVisible(False)
                self.retrybtn.setEnabled(True)
                self.manga_mgr.handle_choosebox_changed(index)
                self.preprocess_mgr.handle_choosebox_changed(index)
                return
            self.spiderUtils = spider_utils_map[index]
            rmt_s2c = True
            self.rv_tools.ero = 0
            self.web_is_r18 = index in SPECIAL_WEBSITES_IDXES
            is_normal_spider = index in SPIDERS and not self.web_is_r18
            self.mpreviewBtn.setVisible(is_normal_spider)
            self.previewBtn.setVisible(self.web_is_r18)
            self.toolWin.rvInterface.set_sauce_visible(self.web_is_r18)
            if self.web_is_r18:
                self.sut = self.spiderUtils(conf)
                rmt_s2c = False
                self.rv_tools.ero = 1
                self.mid_mgr.set_lane_hidden("EP", self.web_is_r18)
            # FluentMonkeyPatch.rbutton_menu_textBrowser(self.textBrowser, index, rmt_s2c)
            self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", STATUS_TIP[index]))
            self.searchinput.setEnabled(True)
            FluentMonkeyPatch.rbutton_menu_lineEdit(self.searchinput)
            if index and not getattr(self, 'p_crawler'):
                # optimize backend scrapy start speed
                self.p_crawler = Process(target=crawl_what, args=(index, self.queue_port))
                self.p_crawler.start()
                self.chooseBox.setDisabled(True)
                self.retrybtn.setEnabled(True)
            self.chooseBox_changed_tips(index)
            if self.web_is_r18:
                self.sv_path = conf.sv_path.joinpath(res.SPIDER.ERO_BOOK_FOLDER)
            # 输入框联想补全
            self.set_completer()
            # 预处理管理器处理
            self.manga_mgr.handle_choosebox_changed(index)
            self.preprocess_mgr.handle_choosebox_changed(index)
        self.chooseBox.currentIndexChanged.connect(chooseBox_changed_handle)

        self.first_tmp_sv_flag = True
        self.preprocess_mgr = PreprocessManager(self)
        self.rv_tools = rVtools()

        if hasattr(self, 'splashScreen'):
            self.splashScreen.finish()

        self.update_notifier = UpdateNotifier(self)
        self.update_notifier.check_on_startup()
        self.is_setup_finished = True
        self.setup_finished.emit()

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

    def set_shortcut(self):
        self.previousPageShort = QShortcut(QKeySequence("Ctrl+,"), self)
        self.previousPageShort.setContext(Qt.ApplicationShortcut)
        self.previousPageShort.activated.connect(self.previousPageBtn.click)
        self.nextPageShort = QShortcut(QKeySequence("Ctrl+."), self)
        self.nextPageShort.setContext(Qt.ApplicationShortcut)
        self.nextPageShort.activated.connect(self.nextPageBtn.click)

    def set_tool_win(self):
        self.toolWin = ToolWindow(self)
        self.toolWin.addMidTool()

        def show_toolWin():
            t = self.toolWin
            h = self.height()
            abs_y = self.y() + h
            screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
            target_y = screen_height - t.height() if abs_y + t.height() > screen_height else abs_y
            target_rect = QRect(self.x(), target_y, t.width(), t.height())
            animate_popup_show(t, target_rect, duration_ms=220, direction="down")
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
            # TODO[0](2026-03-02):  # 处理 previewBtn Enable
            ...
        self.searchinput.textChanged.connect(_search_troggle)
        self.previewBtn.setDisabled(True)
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.confBtn.clicked.connect(self.conf_dia.show_self)
        self.conf_dia.acceptBtn.clicked.connect(self.set_completer)
        self.clipBtn.clicked.connect(self.clip_mgr.read_clip)
        self.openPBtn.clicked.connect(lambda: curr_os.open_folder(self.sv_path))

        with contextlib.suppress(TypeError):
            self.mpreviewBtn.clicked.disconnect()
        self.mpreviewBtn.clicked.connect(self.manga_mgr.on_spreview_clicked)

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
        def refresh_view(_prev_tf):
            # 只有 R18 预览模式才使用 tf 变化判定
            if (
                not self.BrowserWindow
                or not self.BrowserWindow.isVisible()
                or not self.web_is_r18  # 非R18模式由 MangaPreviewManager 管理，不需要等待 tf 变化
            ):
                return
            i = 0
            while i < 1000:  # i * 4ms = 极限等待4s
                if self.tf != _prev_tf:
                    self.BrowserWindow.second_init()
                    self.previewSecondInit = False
                    break
                i += 1
                QThread.msleep(4)
                # 每次循环后处理事件队列，避免阻塞
                QCoreApplication.processEvents()
            # 超时不再强制关闭窗口，仅标记状态
            if self.tf == _prev_tf:
                self.previewSecondInit = True

        def page_turn(_p):
            _prev_tf = self.tf
            self.previewSecondInit = True
            self.pageFrameClickCnt += 1
            self.clean_temp_file()
            if self.BrowserWindow and self.BrowserWindow.output:
                idxes = f"[combine]{str(self.BrowserWindow.output)}"
                self.BrowserWindow.output = []
            else:
                idxes = ""
            __ = select(idxes, self.books)
            self.keep_books.extend(__)
            self.books = {}
            if _p.startswith("next"):
                self.pageEdit.setValue(int(self.pageEdit.value()) + 1)
            elif _p.startswith("previous"):
                self.pageEdit.setValue(int(self.pageEdit.value()) - 1)
            self.input_state.pageTurn = _p
            self.q_InputFieldQueue_send(self.input_state)
            refresh_view(_prev_tf)

        _ = lambda arg: self.BrowserWindow.page(lambda: page_turn(arg)) if self.BrowserWindow else page_turn(arg)
        self.nextPageBtn.clicked.connect(lambda: _(f"next{self.pageFrameClickCnt}"))
        self.previousPageBtn.clicked.connect(lambda: _(f"previous{self.pageFrameClickCnt}"))
        self.pageJumpBtn.clicked.connect(lambda: _(str(self.pageEdit.value())))

        def page_edit(_):
            self.pageJumpBtn.setEnabled(True)

        self.pageEdit.valueChanged.connect(page_edit)
    
    def show_keep_books(self):
        if self.keep_books:
            elected_titles = tuple(x.name for x in self.keep_books)
            self.say(font_color(f"<br>{res.SPIDER.choice_list_before_turn_page}<br>"
                    f"{'<br>'.join(elected_titles)}", cls='theme-success'))

    def preprocess_preview(self, url_str):
        url = url_str.replace("[PreviewBookInfoEnd]", "")
        
        if not self.web_is_r18:
            return
        self.previewBtn.setEnabled(True)
        books = self.mark_tip(self.books)
        self.preview = PreviewHtml(url, books)
        self.preview.duel_contents()
        self.tf = self.preview.created_temp_html

    def set_preview(self, rect=None):
        sb = self.BrowserWindow = BrowserWindowCls(self)
        preview_y = self.y() + self.funcGroupBox.y() - sb.height() + 25
        if rect:
            self.BrowserWindow.setGeometry(rect)
        else:
            self.BrowserWindow.move(self.x(), preview_y if preview_y > 0 else 200) 
        # button group
        self.previewBtn.setEnabled(True)
        self.previewBtn.setFocus()

    def show_preview(self):
        """prevent PreviewWindow is None when init"""
        if self.previewInit:
            self.set_preview()
            self.previewInit = False
        elif self.previewSecondInit:
            self.BrowserWindow.second_init()
            self.previewSecondInit = False
        self.BrowserWindow.set_ensure_handler()
        final_rect = self.BrowserWindow.geometry()
        animate_popup_show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")

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
        if getattr(self, 'p_crawler', None):

            with contextlib.suppress(ConnectionResetError):
                # refresh_state 会发生阻塞，使用原生 Queues.recv
                process_queue = self.Q('ProcessQueue')
                state = Queues.recv(process_queue.queue)  # 直接调用底层方法
                if state:
                    self.process_state = state
                    self.log.info(f'===--→ step: {state.process}， now retrying…… ')
                else:
                    self.log.info('===--→ now retrying (process state unavailable)…… ')
            self.log.info(f'===--→ step: {getattr(self.process_state, "process", "unknown")}， now retrying…… ')

        def retry_all():
            try:
                self.close_process(stop_mgr=False)
            except (FileNotFoundError, m.RemoteError, ConnectionRefusedError, ValueError, BrokenPipeError) as e:
                self.log.error(str(traceback.format_exc()))
            if getattr(self, "mid_mgr", None):
                self.mid_mgr.stop()
            self.log = conf.cLog(name="GUI")
            self.BrowserWindow = None
            def safe_setup():
                if hasattr(self, 'p_crawler') and self.p_crawler and self.p_crawler.is_alive():
                    QTimer.singleShot(70, safe_setup)
                else:
                    self.Q('InputFieldQueue').clear()
                    self.setupUi(self)
            QTimer.singleShot(10, safe_setup)

        self.say(font_color(f"{self.res.reboot_tip}", cls='theme-highlight', size=4))
        QTimer.singleShot(50, retry_all)
        self.retrybtn.setDisabled(True)
        self.log.info('===--→ retry_schedule end\n')

    def disable_start(self):
        self.searchinput.setDisabled(True)
        self.clipBtn.setDisabled(True)

    # --- WorkThread lifecycle API (FR-2) ---

    def ensure_work_thread(self) -> WorkThread:
        if self.bThread and self.bThread.isRunning():
            return self.bThread
        self.bThread = WorkThread(self)
        self._connect_worker_signals(self.bThread)
        mgr = getattr(self, "mid_mgr", None)
        if mgr:
            mgr.attach_worker(self.bThread)
        self.bThread.start()
        self.log.info("-*-*- Background thread & spider starting")
        return self.bThread

    def stop_work_thread(self, wait_ms=800):
        worker = self.bThread
        if worker is None:
            return
        if mgr:= getattr(self, "mid_mgr", None):
            mgr.detach_worker(worker)
        worker.stop()
        worker.quit()
        worker.wait(wait_ms)
        self.bThread = None

    def _connect_worker_signals(self, worker: WorkThread):
        signal_slot_pairs = (
            (worker.print_signal, self.say),
            (worker.item_count_signal, self.processbar_load),
            (worker.tasks_signal, self.task_mgr.handle),
            (worker.worker_finished_signal, self._on_worker_finished),
            (worker.books_ready_signal, self._on_books_ready),
            (worker.eps_ready_signal, self._on_eps_ready),
            (worker.show_max_signal, self.say_show_max),
            (worker.preview_signal, self.preprocess_preview),
            (worker.keep_books_signal, self.show_keep_books),
            (worker.process_state_signal, self._on_process_state_changed),
        )
        for signal, slot in signal_slot_pairs:
            signal.connect(slot)

    def _on_books_ready(self, books: dict):
        self.books = books

    def _on_eps_ready(self, eps: dict):
        self.eps = eps

    def _on_process_state_changed(self, state):
        self.process_state = state

    def _on_worker_finished(self, imgs_path: str):
        self.bThread = None
        self.crawl_end(imgs_path)

    def submit_decision(self, lane: str, indexes, *, page_turn: str = ""):
        """Unified decision pipeline (FR-1).

        Both manual UI operations and mid_mgr automation funnel through here
        to ensure GUI state (book_choose / keep_books / book_num) stays consistent.
        """
        self.input_state.pageTurn = page_turn
        if lane == "BOOK":
            if isinstance(indexes, list):
                self.keep_books.extend(indexes)
            self.input_state.indexes = self.keep_books
            if self.nextclickCnt == 1:
                self.book_choose = self.input_state.indexes
                self.book_num = len(self.book_choose)
        else:
            self.input_state.indexes = indexes

        self.q_InputFieldQueue_send(self.input_state)

        mgr = getattr(self, "mid_mgr", None)
        if mgr and mgr.enabled:
            stage_map = {"BOOK": TimelineStage.BOOK_SENT, "EP": TimelineStage.EP_SENT}
            if stage := stage_map.get(lane):
                mgr.dispatch_stage(stage, EventSource.UI, {"lane": lane})

    def next_schedule(self, keyword=None, site_index=None):
        # TODO[0](2026-03-02): 删掉了next_btn 重做
        def start_and_search():
            self.log.info('===--→ -*- searching')

            self.input_state.keyword = keyword if keyword is not None else self.searchinput.text().strip()
            self.input_state.bookSelected = site_index if site_index is not None else self.chooseBox.currentIndex()

            if self.nextclickCnt == 0:          # 从section步 回parse步 的话以免重开
                self.ensure_work_thread()

            # 将GUI的网站序号结合搜索关键字 →→ 开多线程or进程后台处理scrapy，线程检测spider发送的信号
            self.q_InputFieldQueue_send(self.input_state)

            self.log.debug(
                f'website_index:[{self.input_state.bookSelected}], keyword [{self.input_state.keyword}] success ')

        if self.next_btn.text() != self.res.Uic.next_btnDefaultText:
            self._next()
        else:
            start_and_search()

        self.nextclickCnt += 1
        self.searchinput.setEnabled(False)
        self.pageFrame.setEnabled(True)

        refresh_state(self, 'process_state', 'ProcessQueue')
        self.log.info(f"===--→ next_schedule end (now step: {self.process_state.process})\n")

    def _next(self):
        # TODO[0](2026-03-02): 删掉了next_btn 重做
        self.log.info('===--→ nexting')
        self.pageFrame.setEnabled(False)
        if self.BrowserWindow:
            self.BrowserWindow.ensureBtn.setDisabled(True)

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
            self.ensure_work_thread()

            self.input_state.indexes = selected_list
            self.input_state.pageTurn = ""
            self.q_InputFieldQueue_send(self.input_state)
            refresh_state(self, 'process_state', 'ProcessQueue')
            self.clipBtn.setDisabled(True)
            return
        if self.BrowserWindow and self.BrowserWindow.output:
            idxes = f"[combine]{str(self.BrowserWindow.output)}"
        __ = select(idxes, self.books)
        self.books = {}
        self.submit_decision("BOOK", __)

    def crawl(self, episodes=None):
        # TODO[0](2026-03-02): 删掉了 crawl_btn 重做
        if episodes is None:
            episodes = select("123456465465464", self.eps)
        if not episodes:
            self.say(font_color(r'selected idxes error!!!', cls='theme-err', size=5))
            return
        book = episodes[0].from_book
        book.episodes = episodes

        QThread.msleep(10)
        self.submit_decision("EP", book)

        self.eps = []  # 在复数本选择下，清空 eps 确保 eps 不会同序号不同book
        self.log.debug(f'book_num remain: {self.book_num}')
        self.log.info(f"===--→ crawl finish (now step: {self.process_state.process})\n")

    def q_InputFieldQueue_send(self, input_state, *args):
        """format input"""
        _input_idx = input_state.indexes
        if (not _input_idx or
            isinstance(_input_idx, InfoMinix) or  # 支持单个Selected对象
            isinstance(_input_idx, list) and all(isinstance(s, InfoMinix) for s in _input_idx) or  # 支持Selected列表
            isinstance(_input_idx, str) and (
                _input_idx.startswith("[combine]") or _input_idx == "0" or
                bool(re.match(r'^-\d+$', _input_idx)) or bool(re.match(r'^\d+[0-9\+\-]*$', _input_idx))
            )):
            self.Q('InputFieldQueue').send(input_state)
        else:
            raise ValueError(self.res.input_format_err)

    def crawl_end(self, imgs_path):
        self.progressBar.setCustomBarColor(light="#00ff00", dark="#00cc00")
        self.retrybtn.setEnabled(True)

        if self.BrowserWindow:
            if self.BrowserWindow.topHintBox.isChecked():
                self.BrowserWindow.topHintBox.click()
            self.BrowserWindow.hide()
            self.show()

        self.process_state.process = 'fin'
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
        if self.first_tmp_sv_flag and self.BrowserWindow:
            self.first_tmp_sv_flag = False
            self.BrowserWindow.tmp_sv_local()

    def close_process(self, stop_mgr=True):
        self.clean_preview()
        self.stop_work_thread()
        targets = ('p_qm', 'p_crawler',) if stop_mgr else ('p_crawler',)
        for _ in targets:
            _p = getattr(self, _)
            if _p is not None:
                _p.kill()
                _p.join()
                _p.close()
                delattr(self, _)
        if stop_mgr and getattr(self, "mid_mgr", None):
            self.mid_mgr.stop()

    def closeEvent(self, event):
        if hasattr(self, 'rv_mgr'):
            self.rv_mgr.stop_scan()
        if hasattr(self, 'task_mgr'):
            self.task_mgr.close()
        if hasattr(self, 'preprocess_mgr'):
            self.preprocess_mgr.cleanup()
        event.accept()
        self.destroy()  # 窗口关闭销毁
        self.close_process()
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
        animate_popup_show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")


    def open_url_by_browser(self, url, callback=None):
        screen_height = QGuiApplication.primaryScreen().availableGeometry().height()
        rect = QRect(self.x(), int(screen_height*0.05),
            self.width(), int(screen_height*0.9))
        if not getattr(self, 'BrowserWindow'):
            self.set_preview(rect)
        else:
            self.BrowserWindow.setGeometry(rect)
        final_rect = self.BrowserWindow.geometry()
        animate_popup_show(self.BrowserWindow, final_rect, duration_ms=220, direction="right")
        self.BrowserWindow.view.load(QUrl(url))
        if callback:
            callback()

    def say_show_max(self):
        self.bsm = self.bsm or self.rv_tools.show_max()
        bc_name = self.book_choose[0].name
        bookShow = self.bsm.get(bc_name) or self.bsm.get(self.searchinput.text().strip())
        if bookShow:
            self.say(font_color(bookShow.show, cls='theme-tip', size=4), ignore_http=True)

# ---
