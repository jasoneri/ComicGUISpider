import json
import os
import re
import sys
import time
import traceback
from multiprocessing import Process
import multiprocessing.managers as m
from PyQt5.QtCore import QThread, Qt, QCoreApplication, QRect, QTimer
from PyQt5.QtWidgets import QMainWindow, QMenu, QAction, QMessageBox, QCompleter

from GUI.uic.ui_mainwindow import Ui_MainWindow
from GUI.conf_dialog import ConfDialog
from GUI.browser_window import BrowserWindow
from GUI.thread import WorkThread, ClipTasksThread

from variables import *
from assets import res
from utils import (
    font_color, Queues, QueuesManager, conf, p, ori_path
)
from utils.processed_class import (
    InputFieldState, TextBrowserState, ProcessState,
    GuiQueuesManger, QueueHandler, refresh_state, crawl_what, ClipManager,
    PreviewHtml, TaskObj, TasksObj, CopyUnfinished
)
from utils.website import spider_utils_map
from utils.comic_viewer_tools import combine_then_mv, show_max
from utils.sql import SqlUtils
from deploy import curr_os


class TaskProgressManager:
    def __init__(self, gui):
        self.gui = gui
        self._tasks = {}
        self.init_flag = True
        self.sql_handler = SqlUtils()

    def init(self, add_task):
        """初始化相关"""
        self.init_flag = False
        if not self.gui.BrowserWindow and self.gui.previewInit:
            self.gui.tf = self.gui.tf or PreviewHtml().created_temp_html
            self.gui.previewInit = False
            self.gui.set_preview()
        self.gui.BrowserWindow.init_task_panel(add_task)

    def add_task(self, task_info: tuple):
        """新增任务"""
        if self.init_flag:
            self.init(lambda: self._real_add_task(task_info))
        else:
            self._real_add_task(task_info)

    def _real_add_task(self, task_info: tuple):
        """实际新增任务"""
        obj = TasksObj(*task_info)
        self._tasks[task_info[0]] = obj
        self.gui.BrowserWindow.add_task(obj)

    def update_progress(self, task_obj: TaskObj):
        """更新指定任务进度"""
        taskid = task_obj.taskid
        progress_completed = False
        if taskid in self._tasks:
            _tasks = self._tasks[taskid]
            _tasks.downloaded.append(task_obj)
            curr_progress = int(len(_tasks.downloaded) / _tasks.tasks_count * 100)
            if conf.isDeduplicate and curr_progress >= 100:
                progress_completed = True
            self.gui.BrowserWindow.update_progress(taskid, curr_progress,
                                                   lambda: self.gui.BrowserWindow.tmp_sv_local() if progress_completed else lambda: None
            )

    @property
    def unfinished_tasks(self):
        _tasks_key = list(self._tasks.keys())
        downloaded_taskids = self.sql_handler.batch_check_dupe(_tasks_key)
        un_taskids = set(_tasks_key) - set(downloaded_taskids)
        return [self._tasks[taskid] for taskid in un_taskids]
        
    def close(self):
        self.sql_handler.close()


class ToolMenu(QMenu):
    res = res.GUI.ToolMenu

    def __init__(self, gui, *args, **kwargs):
        super(ToolMenu, self).__init__(*args, **kwargs)
        self.gui = gui
        self.init_actions()
        gui.toolButton.setMenu(self)

    def init_actions(self):
        action_show_max = QAction(self.res.action1, self.gui)
        self.action_show_max = action_show_max
        action_show_max.setObjectName("action_show_max")
        self.addAction(action_show_max)
        action_show_max.triggered.connect(self.show_max)

        action_combine_then_mv = QAction(self.res.action2, self.gui)
        self.action_combine_then_mv = action_combine_then_mv
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

    def switch_ero(self):
        self.removeAction(self.action_show_max)
        self.removeAction(self.action_combine_then_mv)

        action_read_clip = QAction(self.res.action_ero1, self.gui)
        action_read_clip.setObjectName("action_read_clip")
        self.addAction(action_read_clip)
        action_read_clip.triggered.connect(self.read_clip)

    def read_clip(self):
        if self.gui.next_btn.text() != '搜索':
            QMessageBox.information(self.gui, 'Warning', self.res.clip_process_warning)
        else:
            clip = ClipManager(conf.clip_db, f"{conf.clip_sql} limit {conf.clip_read_num}",
                               getattr(self.gui.spiderUtils, "book_url_regex"))
            tf, match_items = clip.main()
            if not match_items:
                self.gui.say(f"无匹配任务，先进行复制再运行此功能，当前匹配规则：{self.gui.spiderUtils.book_url_regex}",
                             ignore_http=True)
            else:
                self.gui.init_clip_handle(tf, match_items)


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
        self.textBrowser.setOpenExternalLinks(True)
        self.textBrowser.append(TextUtils.description)
        self.progressBar.setStyleSheet(r'QProgressBar {text-align: center; border-color: #0000ff;}'
                                       r'QProgressBar::chunk {background-color: #0cc7ff; width: 3px;}')
        # 初始化通信管道相关
        self.input_state = InputFieldState(keyword='', bookSelected=0, indexes='', pageTurn='')
        self.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue', 'TasksQueue',
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
        # 预览
        self.tf = None
        self.previewInit = True
        self.previewSecondInit = False
        self.BrowserWindow = None
        # 剪贴板
        self.clip_is_triggered = False

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

        self.first_tmp_sv_flag = True
        self.task_mgr = TaskProgressManager(self)

        self.show()

    def chooseBox_changed_tips(self, index):
        self.spiderUtils = spider_utils_map[index]
        if index in SPECIAL_WEBSITES_IDXES:
            self.tool_menu.switch_ero()
        if index == 1:
            self.pageEdit.setStatusTip(self.pageEdit.statusTip() + f"  {self.res.copymaga_page_status_tip}")
            self.say(font_color(self.res.copymaga_tips, color='purple'))
        elif index == 2:
            self.say(font_color(self.res.jm_bookid_support, color='blue'))
        elif index == 3 and not conf.proxies:
            self.say(font_color(self.res.wnacg_run_slow_in_cn_tip, color='purple'), ignore_http=True)
        elif index == 4:
            self.pageEdit.setDisabled(True)
            self.say(font_color(res.EHentai.GUIDE, color='purple'))
        elif index == 5:
            self.say(font_color(self.res.mangabz_desc, color='purple'))

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
            if self.BrowserWindow and self.BrowserWindow.output:
                idxes = f"[combine]{str(self.BrowserWindow.output)} and {self.chooseinput.text()[5:].strip()}"
                self.input_state.indexes = idxes
                self.BrowserWindow.output = []
            elif self.chooseinput.text()[5:].strip():
                self.input_state.indexes = self.chooseinput.text()[5:].strip()
            else:
                self.input_state.indexes = ""
            self.input_state.pageTurn = _p
            self.q_InputFieldQueue_send(self.input_state)
            refresh_view(_prev_tf)
            self.chooseinput.clear()

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
        # button group
        self.previewBtn.setEnabled(True)
        self.previewBtn.setFocus()
        self.BrowserWindow.ensureBtn.clicked.connect(lambda : self.BrowserWindow.ensure(self._next))
        def copyUnfinishedTasks():
            _ = CopyUnfinished(self.task_mgr.unfinished_tasks)
            _.to_clip()
            QMessageBox.information(self.BrowserWindow, 'Tip', self.res.copied_tip % _.length)
        self.BrowserWindow.copyBtn.clicked.connect(copyUnfinishedTasks)
        # webEngine / page
        if conf.isDeduplicate and not self.clip_is_triggered:
            PreviewHtml.tip_duplication(SPIDERS[self.chooseBox.currentIndex()], self.tf)

    def show_preview(self):
        """prevent PreviewWindow is None when init"""
        if self.previewInit:
            self.set_preview()
            self.previewInit = False
        elif self.previewSecondInit:
            self.BrowserWindow.second_init(self.tf)
            self.previewSecondInit = False
        self.BrowserWindow.show()

    def clean_preview(self):
        if self.BrowserWindow:
            self.clean_temp_file()
            self.BrowserWindow.destroy()

    def init_clip_handle(self, tf, match_urls):
        self.searchinput.setDisabled(True)
        self.previewInit = False
        self.clip_is_triggered = True
        self.tf = tf
        self.clip_tasks = match_urls
        self.set_preview()
        self.BrowserWindow.resize(self.BrowserWindow.width(), 860)
        self.BrowserWindow.show()
        self.page = self.BrowserWindow.view.page()
        self.clipTasksThread = ClipTasksThread(self, match_urls)
        self.clipTasksThread.info_signal.connect(self.single_clip_tasks_data)
        self.clipTasksThread.total_signal.connect(self.all_clip_tasks_data)
        self.clipTasksThread.start()

    def single_clip_tasks_data(self, info):
        idx, url, img_src, title, author, pages, tags = info
        js_code = rf'addEL({idx}, "{url}", "{img_src}", "{title}", "{author}","{pages}",{tags})'
        self.BrowserWindow.js_execute_by_page(self.page, js_code, lambda _: None)

    def all_clip_tasks_data(self, infos):
        def refresh_tf(html):
            if html:
                with open(self.tf, 'w', encoding='utf-8') as f:
                    # 实在搞不懂怎么跨端正常关掉已经打开的模态框，只能硬改标签属性了
                    html = re.sub(r"<body.*?>", "<body>", html)
                    html = re.sub(r"""aria-labelledby="exampleModalLabel".*?>""",
                                  """aria-labelledby="exampleModalLabel">""", html)
                    html = html.replace(r"""<div class="modal-backdrop fade show"></div>""", "")
                    f.write(html)
                if conf.isDeduplicate:
                    PreviewHtml.tip_duplication(SPIDERS[self.chooseBox.currentIndex()], self.tf)
                    self.BrowserWindow.refreshBtn.click()
                # self.BrowserWindow.second_init(self.tf)
                if self.BrowserWindow.topHintBox.isChecked():
                    self.BrowserWindow.topHintBox.click()
                if len(infos) < len(self.clip_tasks):
                    self.activateWindow()
                    self.say("===部分失败，但仍可继续处理任务窗口的任务")
                self.clip_infos = infos
            else:
                print("没有内容？？？")
        if not infos:
            self.BrowserWindow.hide()
        else:
            self.BrowserWindow.js_execute("finishTasks();", refresh_tf)

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
                self.close_process()  # 考虑重开应该是可以减少重新实例化的数量
            except (FileNotFoundError, m.RemoteError, ConnectionRefusedError, ValueError, BrokenPipeError) as e:
                self.log.error(str(traceback.format_exc()))
            self.log = conf.cLog(name="GUI")
            self.BrowserWindow = None
            self.setupUi(self)

        self.say(font_color(f"<br>(・∀・(・∀・(・∀・*)(・∀・(・∀・*) {self.res.reboot_tip}", color='purple', size=5))
        QTimer.singleShot(200, retry_all)
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
            self.q_InputFieldQueue_send(self.input_state)

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
                self.bThread.tasks_signal.connect(self.task_handle)
                self.bThread.finish_signal.connect(self.crawl_end)
                self.bThread.start()
                self.log.info(f'-*-*- Background thread & spider starting')

            self.log.debug(
                f'website_index:[{self.input_state.bookSelected}], keyword [{self.input_state.keyword}] success ')

        if self.next_btn.text() != '搜索':
            self._next()
        else:
            if self.chooseBox.currentIndex() == 4:
                self.say(f"{self.res.check_ehetai}<br>")
                if not BrowserWindow.check_ehentai(self):
                    return
            elif self.chooseBox.currentIndex() == 5:
                self.say(f"{self.res.check_mangabz}<br>")
                obj = self.spiderUtils(conf)
                if not obj.test_index():
                    QMessageBox.warning(self, 'Warning', f"{self.res.ACCESS_FAIL} {obj.index}")
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
        if self.BrowserWindow:
            self.BrowserWindow.ensureBtn.setDisabled(True)
        if self.clip_is_triggered:  # 剪贴板支线走向
            self.bThread = WorkThread(self)
            self.bThread.print_signal.connect(self.say)
            self.bThread.item_count_signal.connect(self.processbar_load)
            self.bThread.tasks_signal.connect(self.task_handle)
            self.bThread.finish_signal.connect(self.crawl_end)
            self.bThread.start()
            results = [self.clip_infos[i] for i in self.BrowserWindow.output]
            self.input_state.indexes = "[clip]" + json.dumps(results)
            self.input_state.pageTurn = ""
            self.q_InputFieldQueue_send(self.input_state)
            refresh_state(self, 'process_state', 'ProcessQueue')
            self.toolButton.setDisabled(True)
            return
        idxes = self.chooseinput.text()[5:].strip()
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
        self.input_state.indexes = self.chooseinput.text()[5:].strip()
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
        """规范输入"""
        _input_idx = input_state.indexes
        if not _input_idx or isinstance(_input_idx, str) and (
                _input_idx.startswith("[clip]") or _input_idx.startswith("[combine]") or _input_idx == "0" or 
                bool(re.match(r'^-\d+$', _input_idx)) or bool(re.match(r'^\d+[0-9\+\-]*$', _input_idx))
            ):
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
        curr_os.open_folder(imgs_path) if self.checkisopen.isChecked() else None
        self.log.info(f"-*-*- crawl_end finish, spider closed \n")

    def say(self, string, ignore_http=False):
        if 'http' in string and not ignore_http:
            if self.chooseBox.currentIndex() in SPECIAL_WEBSITES_IDXES:
                self.textBrowser.append(self.res.textbrowser_load_if_http % string)
        elif "</p>" in string:
            self.textBrowser.append(string.replace('<p>', '<p style="color: black;">'))
        else:
            self.textBrowser.append(r'<p style="color: black;">%s</p>' % string)
        cursor = self.textBrowser.textCursor()
        self.textBrowser.moveCursor(cursor.End)  # 光标移到最后，这样就会自动显示出来

    def processbar_load(self, i):
        # 发送item目前信号>更新进度条
        self.progressBar.setValue(i)
        if self.first_tmp_sv_flag:
            self.first_tmp_sv_flag = False
            self.BrowserWindow.tmp_sv_local()

    def task_handle(self, task):
        if isinstance(task, tuple):
            self.task_mgr.add_task(task)
        else:
            self.task_mgr.update_progress(task)

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
        if hasattr(self, 'task_mgr'):
            self.task_mgr.close()
        event.accept()
        self.destroy()  # 窗口关闭销毁
        self.close_process()
        sys.exit(0)

    def hook_exception(self, exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc_value, exc_traceback)
        exception = str("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        self.log.error(exception)
        self.say(font_color(rf"{type(exc_value)}{exc_value}", color='red', size=4), ignore_http=True)
        self.say(font_color(rf"<br>{self.res.global_err_hook} <br>[{conf.log_path}\GUI.log]<br>", color='red', size=5))


class TextUtils:
    description = r"""<style>* {margin: 1px;padding: 1px;}</style><div>
    <div style="text-align: center;align-items: center;height: 75px">
        <img alt="描述" src="%s" height="60"><span style="font-weight: bold;font-size: 40px">CGS</span>
    </div>
    <div style="color: blue">
        <p>%s</p>
        <p>%s<span style="color: white"> %s</span></p>
        <hr><p style="color: green">%s</p><hr><p></p>
    </div>
</div>""" % (rf'file:///{ori_path.joinpath("assets/icon.png")}',
             res.GUI.DESC1, res.GUI.DESC2, res.GUI.DESC_ELSE, res.GUI.DESC_NEW)

    @staticmethod
    def warning_(text):
        return font_color(text, color='orange', size=4)
