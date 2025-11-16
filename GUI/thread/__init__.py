import traceback
import asyncio
from copy import deepcopy
from multiprocessing import Process
from PyQt5.QtCore import QThread, pyqtSignal
from utils import conf, get_loop, QueuesManager, code_env
from utils.website.info import InfoMinix, BookInfo, Episode
from utils.processed_class import GuiQueuesManger, QueueHandler
from assets import res
from deploy.update import Proj
from GUI.core.font import font_color

from .ags import AggrSearchThread


class ClipTasksThread(QThread):
    info_signal = pyqtSignal(InfoMinix)
    total_signal = pyqtSignal(dict)

    def __init__(self, gui, tasks):
        super(ClipTasksThread, self).__init__(gui)  # 设置GUI为parent，确保正确的线程上下文
        self.gui = gui
        self.tasks = tasks

    def run(self):
        self.msleep(500)  # 延时，否则子线程太快导致主界面没跟上
        loop = get_loop()
        total = loop.run_until_complete(self._async_run())
        self.handle_total(total)

    async def _async_run(self):
        async with self.gui.spiderUtils.get_cli(conf, is_async=True) as cli:
            total = {}
            async def fetch_single(idx, url):
                _idx = idx + 1
                try:
                    resp = await cli.get(url, follow_redirects=True, timeout=6)
                    book = self.gui.spiderUtils.parse_book(resp.text)
                    self.msleep(50)
                    book.idx = _idx
                    book.url = url
                    self.info_signal.emit(book)
                    return _idx, book
                except Exception as e:
                    err_msg = rf"{res.GUI.Clip.get_info_error}({url}): [{type(e).__name__}] {str(e)}"
                    self.gui.log.exception(e)
                    self.gui.say(font_color(err_msg + '<br>', cls='theme-err'), ignore_http=True)
                    return _idx, None
            # 并发执行所有任务
            tasks = [fetch_single(idx, url) for idx, url in enumerate(self.tasks)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    continue
                if result[1] is not None:
                    total[result[0]] = result[1]
            return total

    def check_condition_and_run_js(self):
        if self.iterations >= self.max_iterations:
            print("[clip tasks loop]❌over max_iterations, fail.")
            self.total_signal.emit(self.total)
            return
        self.iterations += 1
        self.gui.BrowserWindow.js_execute("checkDoneTasks();", self.handle_js_result)

    def handle_js_result(self, num):
        if num and num >= len(self.total):
            print("[clip tasks loop]✅finsh.")
            self.total_signal.emit(self.total)
            return
        self.msleep(250)
        self.check_condition_and_run_js()

    def handle_total(self, total):
        self.max_iterations = 7 * len(self.tasks)
        self.iterations = 0
        self.total = total
        if not total:
            self.total_signal.emit({})
            self.gui.say(font_color(res.GUI.Clip.all_fail, cls='theme-err'), ignore_http=True)
            self.gui.say(font_color(rf"<br>{res.GUI.Clip.view_log} [{conf.log_path}\GUI.log]", cls='theme-err', size=5))
        else:
            self.msleep(1200 if len(self.total) == 1 else 350)
            self.check_condition_and_run_js()


class QueueInitThread(QThread):
    init_completed = pyqtSignal(object, object, int)

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui

    def run(self):
        guiQueuesManger = GuiQueuesManger()
        queue_port = guiQueuesManger.find_free_port()
        p_qm = Process(target=guiQueuesManger.create_server_manager)
        p_qm.daemon = False
        p_qm.start()
        manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue', 'TasksQueue',
            address=('127.0.0.1', queue_port), authkey=b'abracadabra'
        )
        manager.connect()
        Q = QueueHandler(manager)
        self.gui.p_qm = p_qm
        self.gui.guiQueuesManger = guiQueuesManger
        self.init_completed.emit(manager, Q, queue_port)


class WorkThread(QThread):
    """only for monitor signals"""
    item_count_signal = pyqtSignal(int)
    print_signal = pyqtSignal(str)
    finish_signal = pyqtSignal(str)
    tasks_signal = pyqtSignal(object)
    active = True

    def __init__(self, gui):
        super(WorkThread, self).__init__(gui)
        self.gui = gui
        self.flag = 1

    def run(self):
        manager = self.gui.manager
        TextBrowser = manager.TextBrowserQueue()
        Bar = manager.BarQueue()
        _Tasks = manager.TasksQueue()
        while self.active:
            self.msleep(5)
            try:
                if not TextBrowser.empty():
                    _ = TextBrowser.get().text
                    if isinstance(_, dict) and all(tuple(isinstance(v, BookInfo) for v in _.values())):
                        self.gui.books = deepcopy(_)
                    elif isinstance(_, dict) and all(tuple(isinstance(v, Episode) for v in _.values())):
                        self.gui.eps = deepcopy(_)
                    elif "PreviewBookInfoEnd" in _:
                        self.gui.preprocess_preview(_)
                    elif "[ShowKeepBooks]" == _:
                        self.gui.show_keep_books()
                    elif '[httpok]' in _:
                        self.print_signal.emit('[httpok]' + _.replace('[httpok]', ''))
                    else:
                        self.print_signal.emit(_)
                    self.msleep(2)
                if not Bar.empty():
                    self.item_count_signal.emit(Bar.get())
                    # self.msleep(5)
                if not _Tasks.empty():
                    self.tasks_signal.emit(_Tasks.get())
                if res.GUI.WorkThread_finish_flag in self.gui.textBrowser.toPlainText():
                    self.item_count_signal.emit(100)
                    break
                elif res.GUI.WorkThread_empty_flag in self.gui.textBrowser.toPlainText():
                    break
            except ConnectionResetError:
                self.active = False
        if self.active:
            self.finish_signal.emit(str(conf.sv_path))

    # def __del__(self):
    #     self.wait()

    def stop(self):
        self.flag = 0


class ProjUpdateThread(QThread):
    checked_signal = pyqtSignal(object)
    update_signal = pyqtSignal()
    toupdate_signal = pyqtSignal(object)
    debug_signal = pyqtSignal(str)

    def __init__(self, conf_dia):
        self.proj = None
        super(ProjUpdateThread, self).__init__(conf_dia)
        self.conf_dia = conf_dia
        self.is_update_requested = False
        self.log = conf.cLog(name="GUI")
        self.debug_signal.connect(self.conf_dia.gui.say)

    def run(self):
        try:
            self.proj = Proj(debug_signal=self.debug_signal)
            self.proj.check()
            self.checked_signal.emit(self.proj)
            while not self.is_update_requested and not self.isInterruptionRequested():
                self.msleep(100)  # 休眠100毫秒，减少CPU使用
            if self.is_update_requested and not self.isInterruptionRequested():
                self.run_update()
        except Exception as e:
            self.log.exception(f"ProjCheckError: {e}")
            self.checked_signal.emit(traceback.format_exc())

    def request_update(self):
        self.is_update_requested = True

    def run_update(self):
        self.toupdate_signal.emit(self.proj)
