import os
import sys
import time
from multiprocessing import Process
import multiprocessing.managers as m
from PyQt5.QtCore import QThread, Qt, pyqtSignal, QCoreApplication, QRect
from PyQt5.QtWidgets import QMainWindow, QMenu, QAction, QMessageBox, QCompleter
import traceback

from GUI.uic.ui_mainwindow import Ui_MainWindow
from GUI.conf_dialog import ConfDialog
from GUI.fin_ensure_dialog import FinEnsureDialog
from GUI.browser_window import BrowserWindow

from variables import *
from assets import res
from utils import (
    transfer_input, font_color, Queues, QueuesManager,
    conf, p)
from utils.processed_class import (
    InputFieldState, TextBrowserState, ProcessState,
    GuiQueuesManger, QueueHandler, refresh_state, crawl_what
)
from utils.special import MangabzUtils
from utils.comic_viewer_tools import combine_then_mv, show_max
from deploy import curr_os


class WorkThread(QThread):
    """only for monitor signals"""
    item_count_signal = pyqtSignal(int)
    print_signal = pyqtSignal(str)
    finishSignal = pyqtSignal(str)
    active = True

    def __init__(self, gui):
        super(WorkThread, self).__init__()
        self.gui: SpiderGUI = gui
        self.flag = 1

    def run(self):
        manager = self.gui.manager
        TextBrowser = manager.TextBrowserQueue()
        Bar = manager.BarQueue()
        while self.active:
            self.msleep(5)
            try:
                if not TextBrowser.empty():
                    _ = str(TextBrowser.get().text)
                    if "__temp" in _:
                        self.gui.tf = _  # REMARK(2024-08-18): QWebEngineView 只允许在 SpiderGUI 自己进程/线程初始化
                        self.gui.previewBtn.setEnabled(True)
                    else:
                        self.print_signal.emit(_)
                    self.msleep(5)
                if not Bar.empty():
                    self.item_count_signal.emit(Bar.get())
                    self.msleep(10)
                if res.GUI.WorkThread_finish_flag in self.gui.textBrowser.toPlainText():
                    self.item_count_signal.emit(100)
                    self.msleep(10)
                    break
            except ConnectionResetError:
                self.active = False
        if self.active:
            self.finishSignal.emit(str(conf.sv_path))

    # def __del__(self):
    #     self.wait()

    def stop(self):
        self.flag = 0


class ToolMenu(QMenu):
    res = res.GUI.ToolMenu

    def __init__(self, gui, *args, **kwargs):
        super(ToolMenu, self).__init__(*args, **kwargs)
        self.gui = gui
        self.init_actions()
        gui.toolButton.setMenu(self)

    def init_actions(self):
        action_show_max = QAction(self.res.action1, self.gui)
        action_show_max.setObjectName("action_show_max")
        self.addAction(action_show_max)
        action_show_max.triggered.connect(self.show_max)

        action_combine_then_mv = QAction(self.res.action2, self.gui)
        action_combine_then_mv.setObjectName("action_combine_then_mv")
        self.addAction(action_combine_then_mv)
        action_combine_then_mv.triggered.connect(self.combine_then_mv)

    def show_max(self):
        record_txt = conf.sv_path.joinpath("web_handle/record.txt")
        if record_txt.exists():
            QMessageBox.information(self.gui, 'show_max', show_max(record_txt), QMessageBox.Ok)
        else:
            QMessageBox.information(self.gui, 'show_max', self.res.action2_warning % record_txt, QMessageBox.Ok)

    def combine_then_mv(self):
        done = combine_then_mv(conf.sv_path, conf.sv_path.joinpath("web"))
        QMessageBox.information(self.gui, 'combine_then_mv',
                                f"已将{done}整合章节并转换至[{conf.sv_path.joinpath("web")}]", QMessageBox.Ok)


class SpiderGUI(QMainWindow, Ui_MainWindow):
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
    BrowserWindow: BrowserWindow = None

    p_crawler: Process = None
    p_qm: Process = None
    queue_port: int = None
    bThread: WorkThread = None
    manager: QueuesManager = None
    guiQueuesManger: GuiQueuesManger = None
    Q = None
    s: m.Server = None

    def __init__(self, parent=None):
        super(SpiderGUI, self).__init__(parent)
        self.ensure_dia = FinEnsureDialog()
        self.conf_dia = ConfDialog()
        self.log = conf.cLog(name="GUI")
        # self.log.debug(f'-*- 主进程id {os.getpid()}')
        # self.log.debug(f'-*- 主线程id {threading.currentThread().ident}')
        self.setupUi(self)

    def init_queue(self):
        self.guiQueuesManger = GuiQueuesManger()
        self.queue_port = self.guiQueuesManger.find_free_port()
        self.p_qm = Process(target=self.guiQueuesManger.create_server_manager)
        self.p_qm.start()

    def setupUi(self, MainWindow):
        self.init_queue()
        super(SpiderGUI, self).setupUi(MainWindow)
        self.textBrowser.setText(''.join(TextUtils.description))
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk {background-color: #0cc7ff; width: 3px;}')
        # 初始化通信管道相关
        self.input_state = InputFieldState(keyword='', bookSelected=0, indexes='', pageTurn='')
        self.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue',
            address=('127.0.0.1', self.queue_port), authkey=b'abracadabra'
        )
        self.manager.connect()
        self.Q = QueueHandler(self.manager)
        # 按钮组
        self.tool_menu = ToolMenu(self)
        self.nextclickCnt = 0
        self.pageFrameClickCnt = 0
        self.checkisopenCnt = 0
        self.btn_logic_bind()

        self.tf = None
        self.previewInit = True
        self.previewSecondInit = False

        def chooseBox_changed_handle(index):
            self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", STATUS_TIP[index]))
            self.searchinput.setEnabled(True)
            if index and not getattr(self, 'p_crawler'):
                # optimize backend scrapy start speed
                self.p_crawler = Process(target=crawl_what, args=(index, self.queue_port))
                self.p_crawler.start()
                self.chooseBox.setDisabled(True)
                self.retrybtn.setEnabled(True)
            self.chooseBox_changed_tips(index)
            # 输入框联想补全
            self.set_completer()

        self.chooseBox.currentIndexChanged.connect(chooseBox_changed_handle)
        self.show()

    def chooseBox_changed_tips(self, index):
        if index in SPECIAL_WEBSITES_IDXES:
            self.toolButton.setDisabled(True)
            self.say(TextUtils.warning_(f'<br>{"*" * 10} {self.res.toolBox_warning}<br>'))
        if index == 1:
            self.pageEdit.setStatusTip(self.pageEdit.statusTip() + f"  {self.res.copymaga_page_status_tip}")
        elif index == 2:
            self.say(font_color(self.res.jm_bookid_support, color='blue'))
        elif index == 3 and not conf.proxies:
            self.say(font_color(self.res.wnacg_run_slow_in_cn_tip, color='purple'))
        elif index == 4:
            self.pageEdit.setDisabled(True)
            self.say(font_color(res.EHentai.GUIDE, color='purple'))
        elif index == 5:
            self.say(font_color('<br>' + self.res.mangabz_desc, color='purple'))

    def set_completer(self):
        idx = self.chooseBox.currentIndex()
        if idx == 0:
            return
        this_completer = conf.completer[idx] if idx in conf.completer else DEFAULT_COMPLETER[idx]
        completer = QCompleter(list(map(lambda x: f"输入关键字：{x}", this_completer)))
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.searchinput.setCompleter(completer)

    def btn_logic_bind(self):
        def search_btn(text):
            self.next_btn.setEnabled(len(text) > 6 and self.chooseBox.currentIndex() != 0)  # else None
        self.searchinput.textChanged.connect(search_btn)
        self.next_btn.setDisabled(True)
        self.previewBtn.setDisabled(True)
        self.crawl_btn.clicked.connect(self.crawl)
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.next_btn.clicked.connect(self.next_schedule)
        self.confBtn.clicked.connect(self.conf_dia.show_self)
        self.conf_dia.buttonBox.accepted.connect(self.set_completer)

        def checkisopen_btn():
            if self.checkisopenCnt > 0:
                curr_os.open_folder(conf.sv_path)
            self.checkisopen.setText(self.res.checkisopen_text_change)
            self.checkisopen.setStatusTip(self.res.checkisopen_status_tip)
            self.checkisopenCnt += 1

        self.checkisopen.clicked.connect(checkisopen_btn)

        self.page_turn_frame()

    def page_turn_frame(self):
        def refresh_view(_prev_tf):
            if self.BrowserWindow and self.BrowserWindow.isVisible():
                i = 0
                while i < 1000:  # i * 3ms = 极限等待3s
                    if self.tf != _prev_tf:
                        self.BrowserWindow.second_init(self.tf)
                        self.previewSecondInit = False
                        break
                    i += 1
                    QThread.msleep(3)
                if self.tf == _prev_tf:
                    self.BrowserWindow.close()

        def page_turn(_p):
            _prev_tf = self.tf
            self.previewSecondInit = True
            self.pageFrameClickCnt += 1
            self.clean_temp_file()
            if self.BrowserWindow and self.BrowserWindow.isRetain.isChecked():
                idxes = self.BrowserWindow.output
                self.input_state.indexes = idxes
            self.input_state.pageTurn = _p
            self.Q('InputFieldQueue').send(self.input_state)
            refresh_view(_prev_tf)

        _ = lambda arg: self.BrowserWindow.page(lambda: page_turn(arg)) if self.BrowserWindow else page_turn(arg)
        self.nextPageBtn.clicked.connect(lambda: _(f"next{self.pageFrameClickCnt}"))
        self.previousPageBtn.clicked.connect(lambda: _(f"previous{self.pageFrameClickCnt}"))
        self.pageJumpBtn.clicked.connect(lambda: _(self.pageEdit.text()))

        def page_edit(text):
            self.pageEdit.setText(text.strip())
            self.pageEdit.setCursorPosition(len(text))
            self.pageJumpBtn.setEnabled(len(text) > 0)

        self.pageEdit.textChanged.connect(page_edit)

    def set_preview(self):
        proxies = None if self.chooseBox.currentIndex() not in SPIDERS_NEED_PROXIES_IDXES else \
            (conf.proxies or [None])[0]  # only wnacg need proxies presently
        if proxies:
            BrowserWindow.set_proxies(proxies)
        self.BrowserWindow = BrowserWindow(self.tf)
        if self.chooseBox.currentIndex() == 4:  # e-hentai
            self.BrowserWindow.set_ehentai()
        preview_y = self.y() + self.funcGroupBox.y() - self.BrowserWindow.height() - 28
        self.BrowserWindow.setGeometry(QRect(
            self.x() + self.funcGroupBox.x(),
            preview_y if preview_y > 0 else 200,
            self.BrowserWindow.width(), self.BrowserWindow.height()
        ))
        self.previewBtn.setEnabled(True)
        self.previewBtn.setFocus()
        self.BrowserWindow.ensureBtn.clicked.connect(self.ensure_preview)

    def show_preview(self):
        """prevent PreviewWindow is None when init"""
        if self.previewInit:
            self.set_preview()
            self.previewInit = False
        elif self.previewSecondInit:
            self.BrowserWindow.second_init(self.tf)
            self.previewSecondInit = False
        self.BrowserWindow.show()

    def ensure_preview(self):
        def callback():
            self.BrowserWindow.ensureBtn.setDisabled(True)
            self._next()

        self.BrowserWindow.ensure(callback)

    def clean_preview(self):
        if self.BrowserWindow:
            self.clean_temp_file()
            self.BrowserWindow.destroy()

    def clean_temp_file(self):
        """when: 1. preview BrowserWindow destroy; 2. pageTurn btn group clicked"""
        if self.tf and p.Path(self.tf).exists():
            os.remove(self.tf)

    def retry_schedule(self):  # 烂逻辑
        if getattr(self, 'p_crawler', None):
            refresh_state(self, 'process_state', 'ProcessQueue')
            self.log.info(f'===--→ step: {self.process_state.process}， now retrying…… ')

        def retry_all():
            try:
                time.sleep(1)
                self.close_process()  # 考虑重开应该是可以减少重新实例化的数量
            except (FileNotFoundError, m.RemoteError, ConnectionRefusedError, ValueError, BrokenPipeError) as e:
                self.log.error(str(traceback.format_exc()))
            self.log = conf.cLog(name="GUI")
            self.setupUi(self)

        # retry_do_what = {'fin': retry_all}
        # QThread.msleep(5)
        # retry_do_what[self.process_state.process]()
        retry_all()
        self.retrybtn.setDisabled(True)
        self.confBtn.setDisabled(False)
        self.log.info('===--→ retry_schedule end\n')

    def next_schedule(self):
        def start_and_search():
            self.log.info('===--→ -*- searching')
            self.next_btn.setText('Next')

            self.input_state.keyword = self.searchinput.text()[6:].strip()
            self.input_state.bookSelected = self.chooseBox.currentIndex()
            # 将GUI的网站序号结合搜索关键字 →→ 开多线程or进程后台处理scrapy，线程检测spider发送的信号
            self.Q('InputFieldQueue').send(self.input_state)

            if self.nextclickCnt == 0:          # 从section步 回parse步 的话以免重开
                self.bThread = WorkThread(self)

                def crawl_btn(text):
                    if len(text) > 5:
                        refresh_state(self, 'process_state', 'ProcessQueue')
                        self.crawl_btn.setEnabled(self.process_state.process == 'parse section')
                        self.next_btn.setDisabled(self.crawl_btn.isEnabled())
                self.chooseinput.textChanged.connect(crawl_btn)

                self.bThread.print_signal.connect(self.say)
                self.bThread.item_count_signal.connect(self.processbar_load)
                self.bThread.finishSignal.connect(self.crawl_end)

                self.bThread.start()
                self.log.info(f'-*-*- Background thread & spider starting')

            self.log.debug(
                f'website_index:[{self.input_state.bookSelected}], keyword [{self.input_state.keyword}] success ')

        if self.next_btn.text() != '搜索':
            self._next()
        else:
            if self.chooseBox.currentIndex() == 4:
                self.say(self.res.check_ehetai)
                if not BrowserWindow.check_ehentai(self):
                    return
            elif self.chooseBox.currentIndex() == 5:
                self.say("<br>" + self.res.check_mangabz)
                obj = MangabzUtils(conf.proxies)
                if not obj.test_index():
                    QMessageBox.information(self, 'Warning', f"{self.res.ACCESS_FAIL} {obj.index}")
                    return
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
        idxes = transfer_input(self.chooseinput.text()[5:].strip())
        if self.BrowserWindow and self.BrowserWindow.output:
            idxes = list(set(self.BrowserWindow.output) | set(idxes))
        self.input_state.indexes = idxes
        self.input_state.pageTurn = ""
        if self.nextclickCnt == 1:
            self.book_choose = self.input_state.indexes if self.input_state.indexes != [0] else \
                [_ for _ in range(1, 11)]  # 选0的话这里要爬虫返回书本数量数据，还要加个Queue
            self.book_num = len(self.book_choose)
            if self.book_num > 1:
                self.log.info('book_num > 1')
        self.chooseinput.clear()
        # choose逻辑 交由crawl, next,retry3个btn的schedule控制
        self.Q('InputFieldQueue').send(self.input_state)
        self.log.debug(f'send choose: {self.input_state.indexes} success')

    def crawl(self):
        self.input_state.indexes = transfer_input(self.chooseinput.text()[5:].strip())
        self.log.debug(f'===--→ click down crawl_btn')

        QThread.msleep(10)
        self.Q('InputFieldQueue').send(self.input_state)
        self.log.debug(f'send choose success')

        if self.book_num == 0:
            self.crawl_btn.setDisabled(True)
        else:
            self.chooseinput.clear()
        self.log.debug(f'book_num remain: {self.book_num}')
        self.log.info(f"===--→ crawl finish (now step: {self.process_state.process})\n")

    def crawl_end(self, imgs_path):
        del self.manager
        del self.guiQueuesManger
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk { background-color: #00ff00;}')
        self.chooseinput.setDisabled(True)
        self.next_btn.setDisabled(True)
        self.retrybtn.setEnabled(True)

        self.process_state.process = 'fin'
        self.say(font_color("…… (*￣▽￣)(￣▽:;.…::;.:.:::;..::;.:..."))
        curr_os.open_folder(imgs_path) if self.checkisopen.isChecked() else None
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

    def say(self, string):
        if 'http' in string:
            self.textBrowser.setOpenExternalLinks(True)
            if self.chooseBox.currentIndex() in SPECIAL_WEBSITES_IDXES:
                string = self.res.textbrowser_load_if_http % string
                self.textBrowser.append(string)
        else:
            string = r'<p>%s</p>' % string
            self.textBrowser.append(string)

        cursor = self.textBrowser.textCursor()
        self.textBrowser.moveCursor(cursor.End)  # 光标移到最后，这样就会自动显示出来

    def processbar_load(self, i):
        # 发送item目前信号>更新进度条
        self.progressBar.setValue(i)

    def enterEvent(self, QEvent):
        self.textBrowser.setStyleSheet('background-color: white;')

    def leaveEvent(self, QEvent):
        self.textBrowser.setStyleSheet('background-color: pink;')

    def close_process(self):
        self.clean_preview()
        if self.bThread is not None:  # 线程停止
            self.bThread.stop()
        for _ in ['p_qm', 'p_crawler']:
            p = getattr(self, _)
            if p is not None:  # 进程停止
                p.kill()
                p.join()
                p.close()
                delattr(self, _)

    def closeEvent(self, event):
        event.accept()
        self.destroy()  # 窗口关闭销毁
        self.close_process()
        sys.exit(0)

    def hook_exception(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        exception = str("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        self.log.error(exception)
        self.say(font_color(rf"<br>{self.res.global_err_hook} <br>[{conf.log_path}\GUI.log]<br>", color='red', size=5))


class TextUtils:
    description = (
            f"{'message':-^110}<br>" +
            font_color(res.GUI.DESC1, color='blue', size=5) +
            font_color(res.GUI.DESC2, color='blue', size=5) +
            font_color(res.GUI.DESC3, color='blue', size=5) +
            font_color(res.GUI.DESC4, color='white') +
            f"{'仅供学习使用/proj only for study':-^105}")

    @staticmethod
    def warning_(text):
        return font_color(text, color='orange', size=4)
