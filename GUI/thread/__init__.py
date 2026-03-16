import traceback
import asyncio
import queue
import threading
from PyQt5.QtCore import QThread, pyqtSignal
from utils import conf, get_loop, code_env
from utils.website.info import InfoMinix
from assets import res
from deploy.update import Proj
from GUI.core.font import font_color
from utils.protocol import JobAcceptedEvent, LogEvent, ProcessStateEvent, TasksObjEvent, BarProgressEvent, JobFinishedEvent, ErrorEvent

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
                    self.msleep(30)
                    book.idx = _idx
                    book.preview_url = book.url = url
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
            self.gui.say(font_color(rf"<br>{res.GUI.Clip.view_log} [{conf.log_path}\GUI.log]", cls='theme-err', size=3))
        else:
            self.msleep(1200 if len(self.total) == 1 else 350)
            self.check_condition_and_run_js()


class WorkThread(QThread):
    """Consume runtime events and forward only the active job to current GUI bindings."""
    item_count_signal = pyqtSignal(int, object, int)
    print_signal = pyqtSignal(int, object, str)
    tasks_signal = pyqtSignal(int, object, object)
    process_state_signal = pyqtSignal(int, object, str)
    worker_finished_signal = pyqtSignal(int, object, str, bool)

    def __init__(self, gui, event_q: queue.Queue, authority=None):
        super(WorkThread, self).__init__(gui)
        self.gui = gui
        self.event_q = event_q
        self.authority = authority
        self.active = True
        self._bind_lock = threading.Lock()
        self._bind_generation = 0
        self._dispatch_enabled = True
        self._dispatching = False
        self._rebind_cutoff_seq = 0

    def rebind(self, gui):
        with self._bind_lock:
            self.gui = gui
            self._bind_generation += 1
            self._rebind_cutoff_seq = getattr(self.event_q, "last_sequence", lambda: 0)()
        self.setParent(gui)

    def suspend_dispatch(self):
        while True:
            with self._bind_lock:
                self._dispatch_enabled = False
                if not self._dispatching:
                    return
            self.msleep(1)

    def resume_dispatch(self):
        with self._bind_lock:
            self._dispatch_enabled = True

    def _capture_binding(self):
        with self._bind_lock:
            return self._bind_generation, self.gui

    def _is_current_binding(self, generation: int) -> bool:
        with self._bind_lock:
            return generation == self._bind_generation

    def _is_dispatch_enabled(self) -> bool:
        with self._bind_lock:
            return self._dispatch_enabled

    def _begin_dispatch(self, event, generation: int) -> bool:
        with self._bind_lock:
            if not self._dispatch_enabled:
                return False
            if generation != self._bind_generation:
                return False
            if isinstance(event, JobAcceptedEvent):
                if self.authority is not None:
                    event_job_id = getattr(event, "job_id", None)
                    is_pending = getattr(self.authority, "is_job_pending", None)
                    if callable(is_pending):
                        if not is_pending(event_job_id):
                            return False
            event_seq = getattr(event, "_event_seq", 0)
            if self._rebind_cutoff_seq and event_seq and event_seq <= self._rebind_cutoff_seq:
                return False
            self._dispatching = True
            return True

    def _end_dispatch(self):
        with self._bind_lock:
            self._dispatching = False

    def run(self):
        while self.active:
            try:
                event = self.event_q.get(timeout=0.05)
            except queue.Empty:
                continue

            generation, gui = self._capture_binding()

            if not self._begin_dispatch(event, generation):
                continue
            try:
                if isinstance(event, JobAcceptedEvent):
                    if self.authority is not None:
                        self.authority.accept_job(event.job_id)
                elif isinstance(event, LogEvent):
                    msg = event.message if isinstance(event.message, str) else str(event.message)
                    self.print_signal.emit(generation, event.job_id, msg)
                elif isinstance(event, ProcessStateEvent):
                    self.process_state_signal.emit(generation, event.job_id, event.process)
                elif isinstance(event, TasksObjEvent):
                    if self.authority is not None and event.is_new:
                        self.authority.track_task(event.job_id, event.task_obj)
                    self.tasks_signal.emit(generation, event.job_id, event.task_obj)
                elif isinstance(event, BarProgressEvent):
                    self.item_count_signal.emit(generation, event.job_id, event.percent)
                elif isinstance(event, JobFinishedEvent):
                    imgs_path = str(getattr(gui, "sv_path", conf.sv_path))
                    self.worker_finished_signal.emit(generation, event.job_id, imgs_path, event.success)
                elif isinstance(event, ErrorEvent):
                    if self.authority is not None:
                        self.authority.reject_job(event.job_id)
                    self.print_signal.emit(generation, event.job_id, font_color(f"[Error] {event.error}", cls='theme-err'))
            finally:
                self._end_dispatch()

    def stop(self):
        self.active = False


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


class RvThread(QThread):
    scan_completed = pyqtSignal(int)
    scan_progress = pyqtSignal(str)
    
    def __init__(self, gui, show_progress: bool = False):
        super().__init__(gui)
        self.gui = gui
        self.show_progress = show_progress
        
    def run(self):
        try:
            if self.show_progress:
                self.scan_progress.emit("backend scaning local...")
            self.gui.log.info(f"RvThread started, show_progress={self.show_progress}")
            total = self.gui.rv_tools.scan(conf, init=False)
            self.gui.log.info(f"RvThread completed: scanned {total} books/episodes")
            if self.show_progress:
                self.scan_completed.emit(total)
        except Exception as e:
            self.gui.log.exception(f"RvThread error: {e}")
            self.gui.say(f"scan err: {str(e)}")
