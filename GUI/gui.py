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
from GUI.preview_window import PreviewWindow

from variables import *
from utils import (
    transfer_input, font_color, Queues, QueuesManager,
    conf, p)
from utils.processed_class import (
    InputFieldState, TextBrowserState, ProcessState,
    GuiQueuesManger, QueueHandler, refresh_state, crawl_what
)
from utils.comic_viewer_tools import combine_then_mv, show_max


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
                    if "AppData" in _:  # C:/Users/xxxxx/AppData/Local/Temp/xxx.html
                        self.gui.tf = _  # REMARK(2024-08-18): QWebEngineView 只允许在 SpiderGUI 自己内部初始化
                        self.gui.previewBtn.setEnabled(True)
                    else:
                        self.print_signal.emit(_)
                    self.msleep(10)
                if not Bar.empty():
                    self.item_count_signal.emit(Bar.get())
                    self.msleep(10)
                if '完成任务' in self.gui.textBrowser.toPlainText():
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
    def __init__(self, gui, *args, **kwargs):
        super(ToolMenu, self).__init__(*args, **kwargs)
        self.gui = gui
        self.init_actions()
        gui.toolButton.setMenu(self)

    def init_actions(self):
        action_show_max = QAction("显示已阅最新话数记录", self.gui)
        action_show_max.setObjectName("action_show_max")
        self.addAction(action_show_max)
        action_show_max.triggered.connect(self.show_max)

        action_combine_then_mv = QAction("整合章节并移至web目录", self.gui)
        action_combine_then_mv.setObjectName("action_combine_then_mv")
        self.addAction(action_combine_then_mv)
        action_combine_then_mv.triggered.connect(self.combine_then_mv)

    def show_max(self):
        record_txt = conf.sv_path.joinpath("web_handle/record.txt")
        if record_txt.exists():
            QMessageBox.information(self.gui, 'show_max', show_max(record_txt), QMessageBox.Ok)
        else:
            QMessageBox.information(self.gui, 'show_max',
                                    f"未配合[comic_viewer]项目产生记录文件[{str(record_txt)}]，\n功能无法正常使用",
                                    QMessageBox.Ok)

    def combine_then_mv(self):
        done = combine_then_mv(conf.sv_path, conf.sv_path.joinpath("web"))
        QMessageBox.information(self.gui, 'combine_then_mv',
                                f"已将{done}整合章节并转换至[{conf.sv_path.joinpath("web")}]", QMessageBox.Ok)


class SpiderGUI(QMainWindow, Ui_MainWindow):
    input_state: InputFieldState = None
    text_browser_state: TextBrowserState = None
    process_state: ProcessState = None
    queues: Queues = None
    book_choose: list = []
    book_num: int = 0
    nextclickCnt = 0
    checkisopenCnt = 0
    PreviewWindow: PreviewWindow = None

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
        self.input_state = InputFieldState(keyword='', bookSelected=0, indexes='')
        self.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue',
            address=('127.0.0.1', self.queue_port), authkey=b'abracadabra'
        )
        self.manager.connect()
        self.Q = QueueHandler(self.manager)
        # 按钮组
        self.tool_menu = ToolMenu(self)
        self.nextclickCnt = 0
        self.checkisopenCnt = 0
        self.btn_logic_bind()

        self.tf = None
        self.previewInit = True

        def chooseBox_changed_handle(index):
            text = {0: None,
                    1: '拷贝漫画：（1）输入【搜索词】返回搜索结果（2）按空格即可选择预设（2.1）规则补充：排名+日/周/月/总+轻小说/男/女，例如"排名轻小说月"',
                    2: 'jm：（1）输入【搜索词】返回搜索结果（2）按空格即可选择预设（2.1）规则补充：时间维度可选 日/周/月/总，例如"收藏总"（3）翻页：最后加上"&page=2" 等页数',
                    3: 'wnacg：（1）输入【搜索词】返回搜索结果（2）按空格即可选择预设（3）翻页：搜索词翻页加入"&p=2" 例如 "C104&p=2" 固定页面如更新页则使用映射'}
            self.searchinput.setStatusTip(QCoreApplication.translate("MainWindow", text[index]))
            if index and not getattr(self, 'p_crawler'):
                # optimize backend scrapy start speed
                self.p_crawler = Process(target=crawl_what, args=(index, self.queue_port))
                self.p_crawler.start()
                self.chooseBox.setDisabled(True)
                self.retrybtn.setEnabled(True)
            if index in SPECIAL_WEBSITES_IDXES:
                self.toolButton.setDisabled(True)
                self.textBrowser.append(TextUtils.warning_(f'<br>{"*" * 10} 仅当常规漫画网站能使用工具箱功能<br>'))
            if index == 3 and not conf.proxies:
                self.textbrowser_load(font_color(
                    "wancg 国内源有点慢哦，半分钟没出列表时，看看 `scripts/log/scrapy.log` 是不是报错了 <br>" +
                    "网络问题一般重启就好了，数次均无效的话 加群反映/提issue<br>", color='purple'))
            # 输入框联想补全
            self.set_completer()

        self.chooseBox.currentIndexChanged.connect(chooseBox_changed_handle)
        self.show()

    def set_completer(self):
        idx = self.chooseBox.currentIndex()
        if idx == 0:
            return
        completer = QCompleter(list(map(lambda x: f"输入关键字：{x}", conf.completer[idx])))
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
        self.previewBtn.clicked.connect(self.show_preview)
        self.conf_dia.buttonBox.accepted.connect(self.set_completer)

        def checkisopen_btn():
            if self.checkisopenCnt > 0:
                os.startfile(conf.sv_path)
            self.checkisopen.setText("现在点击立刻打开存储目录")
            self.checkisopen.setStatusTip('勾选状态下完成后也会自动打开目录的')
            self.checkisopenCnt += 1

        self.checkisopen.clicked.connect(checkisopen_btn)

    def set_preview(self):
        proxies = None if self.chooseBox.currentIndex() != 3 else \
            (conf.proxies or [None])[0]  # only wnacg need proxies presently
        if proxies:
            PreviewWindow.set_proxies(proxies)
        self.PreviewWindow = PreviewWindow(self.tf)
        preview_y = self.y() + self.funcGroupBox.y() - self.PreviewWindow.height() + 50
        self.PreviewWindow.setGeometry(QRect(
            self.x() + self.funcGroupBox.x(),
            preview_y if preview_y > 0 else 200,
            self.PreviewWindow.width(), self.PreviewWindow.height()
        ))
        self.previewBtn.setEnabled(True)
        self.previewBtn.setFocus()
        self.PreviewWindow.ensureBtn.clicked.connect(self.ensure_preview)

    def show_preview(self):
        """prevent PreviewWindow is None when init"""
        if self.previewInit:
            self.set_preview()
            self.previewInit = False
        self.PreviewWindow.show()

    def ensure_preview(self):
        def callback():
            self.previewBtn.setDisabled(True)
            self._next()
        self.PreviewWindow.ensure(callback)

    def clean_preview(self):
        if self.PreviewWindow:
            if self.tf and p.Path(self.tf).exists():
                os.remove(self.tf)
            self.PreviewWindow.destroy()

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
            self.setupUi(self)

        # retry_do_what = {'fin': retry_all}
        # QThread.msleep(5)
        # retry_do_what[self.process_state.process]()
        retry_all()
        self.retrybtn.setDisabled(True)
        self.confBtn.setDisabled(False)
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

                self.bThread.start()
                self.log.info(f'-*-*- Background thread & spider starting')

            self.log.debug(
                f'website_index:[{self.input_state.bookSelected}], keyword [{self.input_state.keyword}] success ')

        if self.next_btn.text() != '搜索':
            self._next()
        else:
            start_and_search()

        self.nextclickCnt += 1
        self.searchinput.setEnabled(False)
        # self.next_btn.setEnabled(False)
        self.chooseinput.setFocusPolicy(Qt.StrongFocus)

        refresh_state(self, 'process_state', 'ProcessQueue')
        self.log.debug(f"===--→ next_schedule end (now step: {self.process_state.process})\n")

    def _next(self):
        self.log.debug('===--→ nexting')
        idxes = transfer_input(self.chooseinput.text()[5:].strip())
        if self.PreviewWindow and self.PreviewWindow.output:
            idxes = list(set(self.PreviewWindow.output) | set(idxes))
        self.input_state.indexes = idxes
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
            self.textbrowser_load(font_color(">>>>> 说明按钮内容已更新，去点下看看吧<br>", color='purple'))
            self.crawl_btn.setDisabled(True)
            self.input_field.setDisabled(True)
        else:
            self.chooseinput.clear()
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
        self.input_field.setEnabled(True)

        self.process_state.process = 'fin'
        self.textbrowser_load(
            font_color("…… (*￣▽￣)(￣▽:;.…::;.:.:::;..::;.:..."))
        os.startfile(imgs_path) if self.checkisopen.isChecked() else None
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

    def textbrowser_load(self, string):
        if 'http' in string:
            self.textBrowser.setOpenExternalLinks(True)
            if self.chooseBox.currentIndex() in SPECIAL_WEBSITES_IDXES:
                string = (u'<b><font size="5"><br>  内置预览：点击右下 "点我预览" </font></b> 或者 '
                          u'<a href="%s" ><b style="font-size:20px;">浏览器查看结果</b></a>') % string
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


class TextUtils:
    description = (
            f"{'message':-^110}<br>" +
            font_color(
                " 首次使用: 1、打开`README.md`(绿色安装包的话打开`使用说明.html`)，内有配置/GUI视频使用指南等说明<br>",
                color='blue', size=5) +
            font_color(" 2、右下说明更新不及时，尽量参考视频使用指南", color='blue', size=5) +
            font_color(' 有任何问题到群反映<br>', color='white') +
            f"{'仅供学习使用':-^105}")

    @staticmethod
    def warning_(text):
        return font_color(text, color='orange', size=4)
