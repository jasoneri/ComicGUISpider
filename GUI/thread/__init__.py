from PyQt5.QtCore import QThread, pyqtSignal
from utils import font_color, conf
from assets import res


class ClipTasksThread(QThread):
    info_signal = pyqtSignal(tuple)
    total_signal = pyqtSignal(dict)

    def __init__(self, gui, tasks):
        super(ClipTasksThread, self).__init__()
        self.gui = gui
        self.tasks = tasks

    def run(self):
        self.msleep(1200)  # 延后1s，否则子线程太快导致主界面没跟上
        cli = self.gui.spiderUtils.get_cli(conf)
        total = {}
        for idx, url in enumerate(self.tasks):
            try:
                resp = cli.get(url, follow_redirects=True, timeout=3)
                info = self.gui.spiderUtils.parse_book(resp.text)
                self.msleep(50)
                self.info_signal.emit((idx + 1, url, *info[1:]))
                total[idx + 1] = [info[2], info[0]]
            except Exception as e:
                err_msg = rf"获取信息失败({url}): [{type(e).__name__}] {str(e)}"
                self.gui.log.exception(e)
                self.gui.say(font_color(err_msg + '<br>', color='red'), ignore_http=True)
        self.handle_total(total)

    def check_condition_and_run_js(self):
        if self.iterations >= self.max_iterations:
            print("[clip tasks loop]❌over max_iterations, fail.")
            self.total_signal.emit(self.total)
            return
        else:
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
        self.max_iterations = 7 * len(self.tasks)  # 一个任务约给1.5秒
        self.iterations = 0  # 当前循环次数
        self.total = total
        if not total:
            self.total_signal.emit({})
            self.gui.say(
                font_color(r"没有一个成功的任务，如http错误请更新配置如代理/cookies后重新运行此功能，若总是失败提issue",
                           color='red'),
                ignore_http=True)
            self.gui.say(
                font_color(rf"<br>在日志文件查看详细报错堆栈 [{conf.log_path}\GUI.log]", color='red', size=5))
        else:
            self.msleep(1200 if len(self.total) == 1 else 350)
            self.check_condition_and_run_js()


class WorkThread(QThread):
    """only for monitor signals"""
    item_count_signal = pyqtSignal(int)
    print_signal = pyqtSignal(str)
    finish_signal = pyqtSignal(str)
    tasks_signal = pyqtSignal(object)
    active = True

    def __init__(self, gui):
        super(WorkThread, self).__init__()
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
                    _ = str(TextBrowser.get().text)
                    if "__temp" in _:
                        self.gui.tf = _  # REMARK(2024-08-18): QWebEngineView 只允许在 SpiderGUI 自己进程/线程初始化
                        self.gui.previewBtn.setEnabled(True)
                    else:
                        self.print_signal.emit(_)
                    self.msleep(5)
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
