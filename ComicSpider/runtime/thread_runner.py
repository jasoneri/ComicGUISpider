"""Spider runtime thread — 在后台线程中运行 Twisted reactor + CrawlerRunner"""
import queue
import threading
import logging

from ComicSpider.runtime.protocol import (
    SpiderDownloadJob, SubmitJobCommand, CancelJobCommand, ShutdownCommand,
    JobAcceptedEvent, JobFinishedEvent, ErrorEvent, RuntimeState,
)
from variables import SPIDERS

logger = logging.getLogger(__name__)


class RuntimeEventQueue(queue.Queue):
    def __init__(self):
        super().__init__()
        self._seq = 0
        self._seq_lock = threading.Lock()

    def _stamp(self, event):
        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        setattr(event, "_event_seq", seq)
        return event

    def put(self, item, block=True, timeout=None):
        super().put(self._stamp(item), block=block, timeout=timeout)

    def put_nowait(self, item):
        self.put(item, block=False)

    def last_sequence(self) -> int:
        with self._seq_lock:
            return self._seq


class SpiderRuntimeThread(threading.Thread):
    """常驻后台线程：持有 Twisted reactor + CrawlerRunner。

    通信通道：
    - command_q: GUI -> Spider（SubmitJobCommand / ShutdownCommand）
    - event_q: Spider -> GUI（各种 SpiderEvent）
    - state: 共享 RuntimeState（线程安全）
    """
    daemon = True

    def __init__(self):
        super().__init__(name="SpiderRuntime")
        self.command_q = queue.Queue()
        self.event_q = RuntimeEventQueue()
        self.state = RuntimeState()
        self._ready = threading.Event()
        self._runner = None
        self._reactor = None
        self._settings = None

    def run(self):
        # 延迟导入 Scrapy/Twisted 避免阻塞主线程
        from scrapy.crawler import CrawlerRunner
        from scrapy.utils.log import configure_logging
        from scrapy.utils.project import get_project_settings
        from twisted.internet import reactor
        self._reactor = reactor

        s = get_project_settings()
        s.setmodule("ComicSpider.settings")
        installed_reactor = f"{reactor.__class__.__module__}.{reactor.__class__.__name__}"
        s.set("TWISTED_REACTOR", installed_reactor, priority="cmdline")
        configure_logging(s)
        self._runner = CrawlerRunner(s)
        self._settings = s
        self._ready.set()

        # 使用 callWhenRunning 确保 reactor 启动后才调度命令轮询
        reactor.callWhenRunning(self._schedule_command_poll)
        reactor.run(installSignalHandlers=False)
        logger.info("SpiderRuntimeThread reactor stopped")

    def wait_ready(self, timeout=10):
        """阻塞等待 reactor 就绪"""
        self._ready.wait(timeout)

    def _schedule_command_poll(self):
        """在 reactor 线程中定期检查 command_q"""
        try:
            while True:
                cmd = self.command_q.get_nowait()
                self._handle_command(cmd)
        except queue.Empty:
            pass
        # 只要 reactor 存在就继续调度（callWhenRunning 保证首次调用时 reactor 已运行）
        if self._reactor:
            self._reactor.callLater(0.1, self._schedule_command_poll)

    def _handle_command(self, cmd):
        if isinstance(cmd, SubmitJobCommand):
            self._start_crawl(cmd.job)
        elif isinstance(cmd, ShutdownCommand):
            self._reactor.stop()
        elif isinstance(cmd, CancelJobCommand):
            logger.warning(f"CancelJob not yet implemented: {cmd.job_id}")

    def _start_crawl(self, job: SpiderDownloadJob):
        spider_cls_name = SPIDERS.get(job.site_index)
        if not spider_cls_name:
            self.event_q.put(ErrorEvent(job_id=job.job_id, error=f"Unknown site_index: {job.site_index}"))
            return
        self.state.update(stage="crawling", active_job_id=job.job_id, error=None)
        self.event_q.put(JobAcceptedEvent(job_id=job.job_id))

        d = self._runner.crawl(
            spider_cls_name,
            runtime_thread=self,
            job=job,
        )
        d.addCallback(lambda _: self._on_crawl_finished(job))
        d.addErrback(lambda f: self._on_crawl_error(job, f))

    def _on_crawl_finished(self, job):
        self.state.update(stage="idle", active_job_id=None, progress=0.0)
        self.event_q.put(JobFinishedEvent(job_id=job.job_id, success=True))
        logger.info(f"Job {job.job_id} finished")

    def _on_crawl_error(self, job, failure):
        error_msg = str(failure.value) if hasattr(failure, 'value') else str(failure)
        self.state.update(stage="error", error=error_msg)
        self.event_q.put(ErrorEvent(job_id=job.job_id, error=error_msg))
        self.event_q.put(JobFinishedEvent(job_id=job.job_id, success=False))
        logger.error(f"Job {job.job_id} failed: {error_msg}")

    def submit_job(self, job: SpiderDownloadJob):
        """从 GUI 线程调用：安全地提交 job"""
        self.command_q.put(SubmitJobCommand(job=job))

    def shutdown(self):
        """从 GUI 线程调用：安全地停止 reactor"""
        self.command_q.put(ShutdownCommand())
