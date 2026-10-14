import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from qfluentwidgets import InfoBar, InfoBarPosition

from utils import conf
from utils.redViewer_tools import ScanContext, ScanSnapshot
from GUI.thread import RvThread


class RVManager(QObject):
    context_changed = Signal(object)
    snapshot_changed = Signal(object)
    busy_changed = Signal(bool)
    scan_failed = Signal(str)
    pos = InfoBarPosition.TOP_RIGHT

    # CGS016: 延后到这段延迟之后才开跑,等首次启动的导入/构建风暴过去。
    # 扫描与主线程同抢 GIL(QThread 不豁免),重叠会把 setupUi_ 拖出秒级卡顿。
    STARTUP_SCAN_DELAY_MS = 2000
    # 扫描体感上无需打扰用户的时长上限;超过才值得弹一次结果
    QUIET_SCAN_DURATION_MS = 1500

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.scan_thread = None
        self._started_at = 0.0
        self._last_total = None
        self._deferred_timer = None
        self.context: ScanContext | None = None
        self.snapshot: ScanSnapshot | None = None
        self.busy = False
        self.error = ""
        self._show_kws = {}
        self._stopped = False

    def schedule_startup_scan(self, delay_ms: int = None, **show_kws):
        """启动路径专用:延后发起扫描,避开启动关键路径的导入风暴。"""
        if delay_ms is None:
            delay_ms = self.STARTUP_SCAN_DELAY_MS
        self._deferred_timer = QTimer(self)
        self._deferred_timer.setSingleShot(True)
        self._deferred_timer.timeout.connect(lambda: self.start_scan(show_progress=False, **show_kws))
        self._deferred_timer.start(delay_ms)

    def sync_context(self):
        self._set_context(ScanContext.capture(conf, self.gui.rv_tools.ero))

    def _set_context(self, context: ScanContext):
        if context != self.context:
            self.context = context
            self.snapshot = None
            self.error = ""
            self.context_changed.emit(context)
            self.snapshot_changed.emit(None)

    def start_scan(self, show_progress: bool = False, **show_kws):
        if self._deferred_timer is not None:
            self._deferred_timer.stop()
        context = ScanContext.capture(conf, self.gui.rv_tools.ero)
        self._stopped = False
        self._set_context(context)
        if self.scan_thread is not None:
            return

        self._started_at = time.monotonic()
        self._show_kws = {**show_kws, "pos": show_kws.get("pos", self.pos), "force_notify": show_progress}
        self.error = ""
        self.scan_thread = RvThread(self.gui, show_progress=show_progress, context=context)
        self.scan_thread.scan_progress.connect(self._show_scan_progress)
        self.scan_thread.finished.connect(self._on_scan_finished)
        if not self.busy:
            self.busy = True
            self.busy_changed.emit(True)
        self.scan_thread.start()

    @Slot()
    def _on_scan_finished(self):
        worker = self.scan_thread
        current = ScanContext.capture(conf, self.gui.rv_tools.ero)
        if not self._stopped:
            self._set_context(current)
        if worker.error:
            self.gui.log.error(worker.error)
        if not self._stopped and worker.context == current:
            if worker.error:
                self.error = worker.error
                self.scan_failed.emit(worker.error)
                self.gui.say(f"scan err: {worker.error}")
            else:
                self.snapshot = worker.snapshot
                self.snapshot_changed.emit(self.snapshot)
                self._on_scan_completed(worker.total, **self._show_kws)
        self.scan_thread = None
        worker.deleteLater()
        self.busy = False
        self.busy_changed.emit(False)

    @Slot(str)
    def _show_scan_progress(self, message: str):
        show_kws = self._show_kws
        if self._stopped or not show_kws.get("force_notify"):
            return
        parent = show_kws.get("parent_widget", self.gui.showArea)
        InfoBar.info(title='', content=message, position=show_kws['pos'], duration=2000, parent=parent)

    def _on_scan_completed(self, total: int, **show_kws):
        self.gui.bsm = None
        # 数量变化说明本地库有增删,值得告知一次
        library_changed = self._last_total is not None and total != self._last_total
        self._last_total = total

        elapsed_ms = (time.monotonic() - self._started_at) * 1000 if self._started_at else 0.0
        slow_scan = elapsed_ms >= self.QUIET_SCAN_DURATION_MS
        if not (show_kws.get("force_notify") or slow_scan or library_changed):
            self.gui.log.info(f"Scanned {total} books/episodes in {elapsed_ms:.0f}ms (quiet, no notification)")
            return

        self.gui.log.info(f"Scanned: {total} episodes")
        parent = show_kws.get("parent_widget", self.gui.showArea)
        info_what = InfoBar.success if total else InfoBar.warning
        info_what(title='', content=f'Scanned: {total} books/episodes', position=show_kws['pos'], duration=3000, parent=parent)

    def stop_scan(self):
        self._stopped = True
        if self._deferred_timer is not None:
            self._deferred_timer.stop()
            self._deferred_timer = None
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait(1000)
