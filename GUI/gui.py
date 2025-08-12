import os
import re
import sys
import traceback
from multiprocessing import Process
import multiprocessing.managers as m
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import QThread, Qt, QCoreApplication, QRect, QTimer
from PyQt5.QtWidgets import QMainWindow, QCompleter, QShortcut

from GUI.uic.qfluent import (
    MonkeyPatch as FluentMonkeyPatch, CustomSplashScreen
)
from GUI.mainwindow import MitmMainWindow
from GUI.core.font import font_color
from GUI.core.theme import setupTheme
from GUI.conf_dialog import ConfDialog
from GUI.browser_window import BrowserWindow as BrowserWindowCls
from GUI.thread import WorkThread, QueueInitThread
from GUI.tools import ToolWindow, TextUtils
from GUI.manager import TaskProgressManager, ClipGUIManager
from GUI.manager.preprocess import PreprocessManager
from variables import *
from assets import res
from utils import (
    Queues, QueuesManager, conf, p, curr_os
)
from utils.processed_class import (
    InputFieldState, TextBrowserState, ProcessState,
    GuiQueuesManger, refresh_state, crawl_what,
    PreviewHtml, Selected
)
from utils.website import spider_utils_map


class SpiderGUI(QMainWindow, MitmMainWindow):
    res = res.GUI
    input_state: InputFieldState = None
    text_browser_state: TextBrowserState = None
    process_state: ProcessState = None
    queues: Queues = None
    book_choose: list = []
    book_num: int = 0
    nextclickCnt = 0
    pageFrameClickCnt = 0
    checkisopenCnt = 0
    BrowserWindow: BrowserWindowCls = None
    toolWin = None
    webs_status = []

    p_crawler: Process = None
    p_qm: Process = None
    queue_port: int = None
    bThread: WorkThread = None
    manager: QueuesManager = None
    guiQueuesManger: GuiQueuesManger = None
    Q = None
    s: m.Server = None
    sv_path = None

    def __init__(self, parent=None):
        super(SpiderGUI, self).__init__(parent)
        self.log = conf.cLog(name="GUI")
        # self.log.debug(f'-*- 主进程id {os.getpid()}')
        # self.log.debug(f'-*- 主线程id {threading.currentThread().ident}')
        self.first_init = True
        self.setupUi(self)

    def init_queue(self):
        self.guiQueuesManger = GuiQueuesManger()
        self.queue_port = self.guiQueuesManger.find_free_port()
        self.p_qm = Process(target=self.guiQueuesManger.create_server_manager)
        self.p_qm.start()

    def setupUi(self, MainWindow):
        super(SpiderGUI, self).setupUi(MainWindow)
        if self.first_init:
            self.splashScreen = CustomSplashScreen(self)
            self.show()
            setupTheme(self)
            QTimer.singleShot(10, self.setupUi_)
            self.first_init = False
        else:
            self.say(font_color(f"<br>{self.res.reboot_tip2}", cls='theme-highlight', size=4))
            self.chooseBox.setDisabled(True)
            if getattr(self, 'bg_mgr', None):
                self.textBrowser.set_fixed_image(self.bg_mgr.bg_f)
            self.setupUi_()

    def setupUi_(self):
        """启动队列初始化线程"""
        self.queue_init_thread = QueueInitThread(self)
        self.queue_init_thread.init_completed.connect(self.on_queue_init_completed)
        self.queue_init_thread.start()

    def on_queue_init_completed(self, manager, Q, queue_port):
        self.manager = manager
        self.Q = Q
        self.queue_port = queue_port
        self.textBrowser.clear()
        self.chooseBox.setEnabled(True)
        self.finish_setup()

    def finish_setup(self):
        self.conf_dia = ConfDialog(self)
        self.textBrowser.setOpenExternalLinks(True)
        self.textBrowser.append(TextUtils.description())
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk {background-color: #0cc7ff; width: 3px;}')
        self.input_state = InputFieldState(keyword='', bookSelected=0, indexes='', pageTurn='')
        # 按钮组
        self.clip_mgr = ClipGUIManager(self)
        self.nextclickCnt = 0
        self.pageFrameClickCnt = 0
        self.checkisopenCnt = 0
        self.sv_path = conf.sv_path
        self.btn_logic_bind()
        self.set_shortcut()
        self.set_tool_win()
        # 预览
        self.tf = None
        self.previewInit = True
        self.previewSecondInit = False
        self.BrowserWindow = None

        def chooseBox_changed_handle(index):
            if index not in SPIDERS.keys() and index != 0:
                self.retrybtn.setEnabled(True)
                self.preprocess_mgr.handle_choosebox_changed(index)
                return
            self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", STATUS_TIP[index]))
            self.searchinput.setEnabled(True)
            FluentMonkeyPatch.rbutton_menu_lineEdit(self.searchinput)
            FluentMonkeyPatch.rbutton_menu_lineEdit(self.chooseinput)
            if index and not getattr(self, 'p_crawler'):
                # optimize backend scrapy start speed
                self.p_crawler = Process(target=crawl_what, args=(index, self.queue_port))
                self.p_crawler.start()
                self.chooseBox.setDisabled(True)
                self.retrybtn.setEnabled(True)
            self.chooseBox_changed_tips(index)
            match index:
                case 2 | 3:
                    self.toolWin.addDomainTool()
                case 6:
                    self.toolWin.addHitomiTool()
            if index in SPECIAL_WEBSITES_IDXES:
                self.clipBtn.setEnabled(1)
                self.sv_path = conf.sv_path.joinpath(rf"{res.SPIDER.ERO_BOOK_FOLDER}/web")
            # 输入框联想补全
            self.set_completer()
            # 预处理管理器处理
            self.preprocess_mgr.handle_choosebox_changed(index)
        self.chooseBox.currentIndexChanged.connect(chooseBox_changed_handle)

        self.setup_chooseinput_number_keypad()

        self.first_tmp_sv_flag = True
        self.task_mgr = TaskProgressManager(self)
        self.preprocess_mgr = PreprocessManager(self)

        if hasattr(self, 'splashScreen'):
            self.splashScreen.finish()

    def setup_chooseinput_number_keypad(self):
        if not hasattr(self.chooseinput, 'objectName') or not self.chooseinput.objectName():
            self.chooseinput.setObjectName('chooseinput')

    def chooseBox_changed_tips(self, index):
        self.spiderUtils = spider_utils_map[index]
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
        self.rvBtn.clicked.connect(self.toolWin.show)

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
        _completer = QCompleter(list(map(lambda x: f" {x}", ['1', '-1', '-3', '0'])))
        _completer.setCompletionMode(QCompleter.PopupCompletion)
        self.chooseinput.setCompleter(_completer)
        _completer.activated.connect(lambda :
            self.chooseinput.setCursorPosition(len(self.chooseinput.text())))

    def btn_logic_bind(self):
        def search_btn(text):
            self.next_btn.setEnabled(len(text.strip()) > 0 and self.chooseBox.currentIndex() != 0)  # else None
        self.searchinput.textChanged.connect(search_btn)
        self.next_btn.setDisabled(True)
        self.previewBtn.setDisabled(True)
        self.crawl_btn.clicked.connect(self.crawl)
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.next_btn.clicked.connect(self.next_schedule)
        self.confBtn.clicked.connect(self.conf_dia.show_self)
        self.conf_dia.acceptBtn.clicked.connect(self.set_completer)
        self.clipBtn.clicked.connect(self.clip_mgr.read_clip)

        def checkisopen_btn():
            if self.checkisopenCnt > 0:
                curr_os.open_folder(self.sv_path)
            self.checkisopen.setText(self.res.checkisopen_text_change)
            self.checkisopen.setStatusTip(self.res.checkisopen_status_tip)
            self.checkisopenCnt += 1

        self.checkisopen.clicked.connect(checkisopen_btn)

        self.page_turn_frame()

    def tip_duplication(self):
        def trigger_mark_downloads():
            page = self.BrowserWindow.view.page() if self.BrowserWindow else None
            if page and page.contentsSize().width() > 0:
                PreviewHtml.tip_duplication(SPIDERS[self.chooseBox.currentIndex()], self.tf, page)
                page.contentsSizeChanged.disconnect(trigger_mark_downloads)
        self.BrowserWindow.view.page().contentsSizeChanged.connect(trigger_mark_downloads)

    def page_turn_frame(self):
        def refresh_view(_prev_tf):
            if self.BrowserWindow and self.BrowserWindow.isVisible():
                i = 0
                while i < 1000:  # i * 3ms = 极限等待3s
                    if self.tf != _prev_tf:
                        self.BrowserWindow.second_init()
                        if conf.isDeduplicate:
                            self.tip_duplication()
                        self.previewSecondInit = False
                        break
                    i += 1
                    QThread.msleep(4)
                if self.tf == _prev_tf:
                    self.previewSecondInit = True
                    self.BrowserWindow.close()

        def page_turn(_p):
            _prev_tf = self.tf
            self.previewSecondInit = True
            self.pageFrameClickCnt += 1
            self.clean_temp_file()
            if self.BrowserWindow and self.BrowserWindow.output:
                idxes = f"[combine]{str(self.BrowserWindow.output)} and {self.chooseinput.text().strip()}"
                self.input_state.indexes = idxes
                self.BrowserWindow.output = []
            elif self.chooseinput.text().strip():
                self.input_state.indexes = self.chooseinput.text().strip()
            else:
                self.input_state.indexes = ""
            if _p.startswith("next"):
                self.pageEdit.setValue(int(self.pageEdit.value()) + 1)
            elif _p.startswith("previous"):
                self.pageEdit.setValue(int(self.pageEdit.value()) - 1)
            self.input_state.pageTurn = _p
            self.q_InputFieldQueue_send(self.input_state)
            refresh_view(_prev_tf)
            self.chooseinput.clear()

        _ = lambda arg: self.BrowserWindow.page(lambda: page_turn(arg)) if self.BrowserWindow else page_turn(arg)
        self.nextPageBtn.clicked.connect(lambda: _(f"next{self.pageFrameClickCnt}"))
        self.previousPageBtn.clicked.connect(lambda: _(f"previous{self.pageFrameClickCnt}"))
        self.pageJumpBtn.clicked.connect(lambda: _(str(self.pageEdit.value())))

        def page_edit(_):
            self.pageJumpBtn.setEnabled(True)

        self.pageEdit.valueChanged.connect(page_edit)

    def set_preview(self):
        self.BrowserWindow = BrowserWindowCls(self)
        preview_y = self.y() + self.funcGroupBox.y() - self.BrowserWindow.height() - 28
        self.BrowserWindow.setGeometry(QRect(
            self.x() + self.funcGroupBox.x(),
            preview_y if preview_y > 0 else 200,
            self.BrowserWindow.width(), self.BrowserWindow.height()
        ))
        # button group
        self.previewBtn.setEnabled(True)
        self.previewBtn.setFocus()
        # webEngine / page
        if conf.isDeduplicate and not self.clip_mgr.is_triggered:
            self.tip_duplication()

    def show_preview(self):
        """prevent PreviewWindow is None when init"""
        if self.previewInit:
            self.set_preview()
            self.previewInit = False
        elif self.previewSecondInit:
            self.BrowserWindow.second_init()
            self.previewSecondInit = False
        self.BrowserWindow.show()

    def clean_preview(self):
        if self.BrowserWindow:
            self.clean_temp_file()
            self.BrowserWindow.destroy()

    def clean_temp_file(self):
        """when: 1. preview BrowserWindow destroy; 2. pageTurn btn group clicked"""
        if self.tf and p.Path(self.tf).exists():
            os.remove(self.tf)

    def retry_schedule(self):
        if getattr(self, 'p_crawler', None):
            try:
                refresh_state(self, 'process_state', 'ProcessQueue')
            except ConnectionResetError:
                ...
            self.log.info(f'===--→ step: {self.process_state.process}， now retrying…… ')

        def retry_all():
            try:
                self.close_process()  # 考虑重开应该是可以减少重新实例化的数量
            except (FileNotFoundError, m.RemoteError, ConnectionRefusedError, ValueError, BrokenPipeError) as e:
                self.log.error(str(traceback.format_exc()))
            self.log = conf.cLog(name="GUI")
            self.BrowserWindow = None
            self.guiQueuesManger = None
            self.Q = None
            QTimer.singleShot(10, lambda : self.setupUi(self))

        self.say(font_color(f"{self.res.reboot_tip}", cls='theme-highlight', size=4))
        QTimer.singleShot(50, retry_all)
        self.retrybtn.setDisabled(True)
        self.log.info('===--→ retry_schedule end\n')

    def disable_start(self):
        self.searchinput.setDisabled(True)
        self.next_btn.setDisabled(True)
        self.clipBtn.setDisabled(True)

    def next_schedule(self):
        def start_and_search():
            self.log.info('===--→ -*- searching')
            self.next_btn.setText('Next')

            self.input_state.keyword = self.searchinput.text().strip()
            self.input_state.bookSelected = self.chooseBox.currentIndex()
            # 将GUI的网站序号结合搜索关键字 →→ 开多线程or进程后台处理scrapy，线程检测spider发送的信号
            self.q_InputFieldQueue_send(self.input_state)

            if self.nextclickCnt == 0:          # 从section步 回parse步 的话以免重开
                self.bThread = WorkThread(self)

                def crawl_btn(text):
                    if len(text.strip()) > 0:
                        refresh_state(self, 'process_state', 'ProcessQueue')
                        self.crawl_btn.setEnabled(self.process_state.process == 'parse section')
                        self.next_btn.setDisabled(self.crawl_btn.isEnabled())
                self.chooseinput.textChanged.connect(crawl_btn)

                self.bThread.print_signal.connect(self.say)
                self.bThread.item_count_signal.connect(self.processbar_load)
                self.bThread.tasks_signal.connect(self.task_mgr.handle)
                self.bThread.finish_signal.connect(self.crawl_end)
                self.bThread.start()
                self.log.info(f'-*-*- Background thread & spider starting')

            self.log.debug(
                f'website_index:[{self.input_state.bookSelected}], keyword [{self.input_state.keyword}] success ')

        if self.next_btn.text() != self.res.Uic.next_btnDefaultText:
            self._next()
        else:
            start_and_search()

        self.nextclickCnt += 1
        self.searchinput.setEnabled(False)
        self.pageFrame.setEnabled(True)
        # self.next_btn.setEnabled(False)
        self.chooseinput.setFocusPolicy(Qt.StrongFocus)

        refresh_state(self, 'process_state', 'ProcessQueue')
        self.log.info(f"===--→ next_schedule end (now step: {self.process_state.process})\n")

    def _next(self):
        self.log.info('===--→ nexting')
        self.pageFrame.setEnabled(False)
        if self.BrowserWindow:
            self.BrowserWindow.ensureBtn.setDisabled(True)
        if self.clip_mgr.is_triggered:  # 剪贴板支线走向
            self.bThread = WorkThread(self)
            self.bThread.print_signal.connect(self.say)
            self.bThread.item_count_signal.connect(self.processbar_load)
            self.bThread.tasks_signal.connect(self.task_mgr.handle)
            self.bThread.finish_signal.connect(self.crawl_end)
            self.bThread.start()

            selected_list = self.clip_mgr.create_selected_list(self.BrowserWindow.output)
            self.input_state.indexes = selected_list
            self.input_state.pageTurn = ""
            self.q_InputFieldQueue_send(self.input_state)
            refresh_state(self, 'process_state', 'ProcessQueue')
            self.clipBtn.setDisabled(True)
            return
        idxes = self.chooseinput.text().strip()
        if self.BrowserWindow and self.BrowserWindow.output:
            idxes = f"[combine]{str(self.BrowserWindow.output)} and {idxes}"
        self.input_state.indexes = idxes
        self.input_state.pageTurn = ""
        if self.nextclickCnt == 1:
            self.book_choose = self.input_state.indexes if self.input_state.indexes != "0" else \
                [_ for _ in range(1, 11)]  # 选0的话这里要爬虫返回书本数量数据，还要加个Queue
            self.book_num = len(self.book_choose)
            if self.book_num > 1:
                self.log.info('book_num > 1')
        self.chooseinput.clear()
        # choose逻辑 交由crawl, next,retry3个btn的schedule控制
        self.q_InputFieldQueue_send(self.input_state)
        self.log.debug(f'send choose: {self.input_state.indexes} success')

    def crawl(self):
        self.input_state.indexes = self.chooseinput.text().strip()
        self.log.debug(f'===--→ click down crawl_btn')

        QThread.msleep(10)
        self.q_InputFieldQueue_send(self.input_state)
        self.log.debug(f'send choose success')

        if self.book_num == 0:
            self.crawl_btn.setDisabled(True)
        else:
            self.chooseinput.clear()
        self.log.debug(f'book_num remain: {self.book_num}')
        self.log.info(f"===--→ crawl finish (now step: {self.process_state.process})\n")

    def q_InputFieldQueue_send(self, input_state, *args):
        """format input"""
        _input_idx = input_state.indexes
        if (not _input_idx or
            isinstance(_input_idx, Selected) or  # 支持单个Selected对象
            isinstance(_input_idx, list) and all(isinstance(s, Selected) for s in _input_idx) or  # 支持Selected列表
            isinstance(_input_idx, str) and (
                _input_idx.startswith("[combine]") or _input_idx == "0" or
                bool(re.match(r'^-\d+$', _input_idx)) or bool(re.match(r'^\d+[0-9\+\-]*$', _input_idx))
            )):
            self.Q('InputFieldQueue').send(input_state)
        else:
            raise ValueError(self.res.input_format_err)

    def crawl_end(self, imgs_path):
        del self.manager
        del self.guiQueuesManger
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk { background-color: #00ff00;}')
        self.chooseinput.setDisabled(True)
        self.next_btn.setDisabled(True)
        self.retrybtn.setEnabled(True)

        if self.BrowserWindow:
            if self.BrowserWindow.topHintBox.isChecked():
                self.BrowserWindow.topHintBox.click()
            self.BrowserWindow.hide()
            self.show()

        self.process_state.process = 'fin'
        self.say(font_color("…… (*￣▽￣)(￣▽:;.…::;.:.:::;..::;.:..."))
        if self.checkisopen.isChecked():
            curr_os.open_folder(self.sv_path)
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

    def say(self, string, ignore_http=False):
        fin_s = ""
        if isinstance(string, str) and string.startswith('[httpok]'):
            string = string[len('[httpok]'):]
            ignore_http = True
        if not ignore_http and 'http' in string:
            if self.chooseBox.currentIndex() in SPECIAL_WEBSITES_IDXES:
                fin_s = self.res.textbrowser_load_if_http % string
        else:
            fin_s = string
        if fin_s:
            self.textBrowser.append(fin_s)
        cursor = self.textBrowser.textCursor()
        self.textBrowser.moveCursor(cursor.End)  # move cursor to the end for show dynamicly

    def processbar_load(self, i):
        self.progressBar.setValue(i)
        if self.first_tmp_sv_flag:
            self.first_tmp_sv_flag = False
            self.BrowserWindow.tmp_sv_local()

    def close_process(self):
        self.clean_preview()
        if self.bThread is not None:  # 线程停止
            self.bThread.stop()
        for _ in ['p_qm', 'p_crawler']:
            _p = getattr(self, _)
            if _p is not None:  # 进程停止
                _p.kill()
                _p.join()
                _p.close()
                delattr(self, _)

    def closeEvent(self, event):
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
        self.say(font_color(rf"<br>{self.res.global_err_hook} <br>[{conf.log_path}\GUI.log]<br>", cls='theme-err', size=5))
