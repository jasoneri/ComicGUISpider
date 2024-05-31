import os
import sys
import time
from multiprocessing import Process, freeze_support
import multiprocessing.managers as m
from PyQt5.QtCore import QThread, Qt, pyqtSignal, QCoreApplication
from PyQt5.QtWidgets import QDialog, QMainWindow
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
import traceback
from loguru import logger

from GUI.ui_mainwindow import Ui_MainWindow
from GUI.ui_ensure_dia import Ui_FinEnsureDialog
from GUI.ui_helplabel import Ui_HelpLabel
from utils import transfer_input, font_color, Queues, State, QueuesManager, conf
from utils.processed_class import (
    InputFieldState, TextBrowserState, ProcessState,
    GuiQueuesManger, QueueHandler, refresh_state
)


class FinEnsureDialog(QDialog, Ui_FinEnsureDialog):

    def __init__(self, parent=None):
        super(FinEnsureDialog, self).__init__(parent)
        self.setupUi(self)

    def setupUi(self, ensureDialog):
        super(FinEnsureDialog, self).setupUi(ensureDialog)


class WorkThread(QThread):
    """only for monitor signals"""
    item_count_signal = pyqtSignal(int)
    print_signal = pyqtSignal(str)
    finishSignal = pyqtSignal(str)
    active = True

    def __init__(self, gui):
        super(WorkThread, self).__init__()
        self.gui = gui
        self.flag = 1

    def run(self):
        m = self.gui.manager
        TextBrowser = m.TextBrowserQueue()
        Bar = m.BarQueue()
        while self.active:
            self.msleep(8)
            if not TextBrowser.empty():
                self.print_signal.emit(str(TextBrowser.get().text))
            if not Bar.empty():
                self.item_count_signal.emit(Bar.get())
            if '完成任务' in self.gui.textBrowser.toPlainText():
                self.item_count_signal.emit(100)
                self.msleep(20)
                break
        if self.active:
            from ComicSpider.settings import IMAGES_STORE
            self.finishSignal.emit(IMAGES_STORE)

    # def __del__(self):
    #     self.wait()

    def stop(self):
        self.flag = 0


class SpiderGUI(QMainWindow, Ui_MainWindow):
    input_state: InputFieldState = None
    text_browser_state: TextBrowserState = None
    process_state: ProcessState = None
    queues: Queues = None
    book_choose: list = []
    book_num: int = 0
    helpclickCnt = 0
    nextclickCnt = 0

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
        self.dia = FinEnsureDialog()
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
        self.helpbtn.setFocus()
        self.textBrowser.setText(''.join(TextUtils.description))
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk {background-color: #0cc7ff; width: 3px;}')
        self.helplabel = Ui_HelpLabel(self.centralwidget)
        self.helpclickCnt = 0
        self.nextclickCnt = 0
        # 初始化通信管道相关
        self.input_state = InputFieldState(keyword='', bookSelected=0, indexes='')
        self.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue',
            address=('127.0.0.1', self.queue_port), authkey=b'abracadabra'
        )
        QThread.msleep(2000)
        self.manager.connect()
        self.Q = QueueHandler(self.manager)
        self.btn_logic_bind()

        def status_tip(index):
            text = {0: None,
                    1: '90MH网：（1）输入【搜索词】返回搜索结果（2）可输入【更新】【排名】..字如其名',
                    2: 'kukuM网：（1）输入【搜索词】返回搜索结果（2）可输入【更新】【推荐】..字如其名',
                    3: 'wnacg网：（1）输入【搜索词】返回搜索结果（2）可输入【更新】【汉化】..字如其名'}
            self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", text[index]))
        self.chooseBox.currentIndexChanged.connect(status_tip)
        self.show()

    def btn_logic_bind(self):
        def search_btn(text):
            self.next_btn.setEnabled(len(text) > 6)  # if self.chooseBox.currentIndex() in [1, 2, 3] else None
        self.searchinput.textChanged.connect(search_btn)
        # self.next_btn.setEnabled(True)
        self.crawl_btn.clicked.connect(self.crawl)
        self.retrybtn.setDisabled(1)
        self.retrybtn.clicked.connect(self.retry_schedule)
        self.next_btn.clicked.connect(self.next_schedule)

    def show_help(self):
        self.helplabel.hide() if self.helpclickCnt%2 else self.helplabel.show()
        self.helpclickCnt += 1

    def retry_schedule(self):  # 烂逻辑
        refresh_state(self, 'process_state', 'ProcessQueue')
        self.log.info(f'===--→ step: {self.process_state.process}， now retrying…… ')

        def retry_all():
            self.textBrowser.setStyleSheet('background-color: red;')
            self.textbrowser_load(font_color('…………重启爬虫中，会卡个几秒', size=6))
            self.retrybtn.setToolTip(QCoreApplication.translate("MainWindow", "retry重启时会卡几秒，等等"))
            QThread.msleep(200)
            try:
                time.sleep(0.8)
                self.close_process()
            except (FileNotFoundError, m.RemoteError, ConnectionRefusedError, ValueError, BrokenPipeError) as e:
                self.log.error(str(traceback.format_exc()))
            self.setupUi(self)

        retry_do_what = {'fin': retry_all}
        QThread.msleep(5)
        retry_do_what[self.process_state.process]()
        self.retrybtn.setDisabled(True)
        self.log.debug('===--→ retry_schedule end\n')

    def next_schedule(self):
        def start_and_search():
            self.log.debug('===--→ -*- searching')
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

                self.bThread.print_signal.connect(self.textbrowser_load)
                self.bThread.item_count_signal.connect(self.processbar_load)
                self.bThread.finishSignal.connect(self.crawl_end)

                self.p_crawler = Process(target=crawl_what, args=(self.input_state.bookSelected, self.queue_port))
                self.p_crawler.start()
                self.bThread.start()
                self.log.info(f'-*-*- Background thread & spider starting')

            self.chooseBox.setDisabled(True)
            self.log.debug(
                f'website_index:[{self.input_state.bookSelected}], keyword [{self.input_state.keyword}] success ')

        def _next():
            self.log.debug('===--→ nexting')
            self.input_state.indexes = transfer_input(self.chooseinput.text()[5:].strip())
            if self.nextclickCnt == 1:
                self.book_choose = self.input_state.indexes if self.input_state.indexes != [0] else [_ for _ in range(1,
                                                                                                                      11)]  # 选0的话这里要爬虫返回书本数量数据，还要加个Queue
                self.book_num = len(self.book_choose)
                if self.book_num > 1:
                    self.log.info('book_num > 1')
                    self.textBrowser.append(TextUtils.warning_(f'<br>{"*" * 20}警告！！多选书本时不要随意使用 retry<br>'))
            self.chooseinput.clear()
            # choose逻辑 交由crawl, next,retry3个btn的schedule控制
            self.Q('InputFieldQueue').send(self.input_state)
            self.log.debug(f'send choose: {self.input_state.indexes} success')

        if self.next_btn.text()!='搜索':
            _next()
        else:
            start_and_search()

        self.nextclickCnt += 1
        self.searchinput.setEnabled(False)
        # self.next_btn.setEnabled(False)
        self.chooseinput.setFocusPolicy(Qt.StrongFocus)

        refresh_state(self, 'process_state', 'ProcessQueue')
        self.log.debug(f"===--→ next_schedule end (now step: {self.process_state.process})\n")

    def crawl(self):
        def dia_text(_str):
            self.dia.textEdit.append(TextUtils.warning_(_str) if 'notice' in _str else _str)

        self.input_state.indexes = transfer_input(self.chooseinput.text()[5:].strip())
        self.log.debug(f'===--→ click down crawl_btn')
        self.dia.textEdit.clear()
        self.bThread.print_signal.disconnect(self.textbrowser_load)
        self.bThread.print_signal.connect(dia_text)

        QThread.msleep(10)
        self.Q('InputFieldQueue').send(self.input_state)
        self.log.debug(f'send choose success')

        if self.dia.exec_() == QDialog.Accepted:    # important dia窗口确认为最后把关
            self.book_num -= 1
        else:
            ...
        self.bThread.print_signal.connect(self.textbrowser_load)

        if self.book_num == 0:
            self.helplabel.re_pic()
            self.textbrowser_load(font_color(">>>>> 说明按钮内容已更新，去点下看看吧<br>", color='purple'))
            self.crawl_btn.setDisabled(True)
            self.input_yield.setDisabled(True)
        else:
            self.chooseinput.clear()
        self.bThread.print_signal.disconnect(dia_text)
        self.log.debug(f'book_num remain: {self.book_num}')
        self.log.debug(f"===--→ crawl finish (now step: {self.process_state.process})\n")

    def crawl_end(self, imgs_path):
        del self.manager
        del self.guiQueuesManger
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk { background-color: #00ff00;}')
        self.chooseinput.setDisabled(True)
        self.next_btn.setDisabled(True)
        self.retrybtn.setEnabled(True)
        self.input_yield.setEnabled(True)

        self.process_state.process = 'fin'
        self.helplabel.re_pic()
        self.textbrowser_load(
            font_color(">>>>> 重申，说明按钮内容已更新，去点下看看吧<br>", color='purple') + font_color(
                "…… (*￣▽￣)(￣▽:;.…::;.:.:::;..::;.:..."))
        os.startfile(imgs_path) if self.checkisopen.isChecked() else None
        self.checkisopen.clicked.connect(lambda: os.startfile(imgs_path))
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

    def textbrowser_load(self, string):
        # todo: v1.4 - (1)、每组图预览，图片缓存 (2)、勾选选项（改写choose逻辑）放textbrowser？
        if 'http' in string:
            self.textBrowser.setOpenExternalLinks(True)
            string = u'<a href="%s" ><b style="font-size:20px;"><br> 点击查看搜索结果</b></a><b><s><font color="WhiteSmoke"  size="4"> 懒得做预览图功能</font></s></b>' % string
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


class TextUtils:
    description = (f"{'message':-^95}<br>" +
                   font_color(" 不懂的： 1、右下点说明跟着走，2、首次使用去打开【运行必读.txt】看下", color='blue', size=5) +
                   font_color('别老问怎么错<br>', color='white') +
                   f"{'仅为学习使用':-^90}")

    @staticmethod
    def warning_(text):
        return font_color(text)


def crawl_what(what, queue_port):
    spider_what = {1: 'comic90mh',
                   2: 'comickukudm',
                   3: 'wnacg'}
    freeze_support()
    process = CrawlerProcess(get_project_settings())
    process.crawl(spider_what[what], queue_port=queue_port)
    # process.crawl(spider_what[3])
    process.start()
    process.join()
    process.stop()

