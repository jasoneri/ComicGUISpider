# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
from uuid import uuid4

from PyQt5.QtCore import QObject, pyqtSignal

from ComicSpider.runtime import SpiderRuntimeThread
from GUI.thread import WorkThread
from utils.protocol import SpiderDownloadJob
from variables import SPIDERS


class DownloadRuntimeManager(QObject):
    """Manage SpiderRuntime + WorkThread lifecycle and process stage state."""

    process_stage_changed = pyqtSignal(str)

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.spider_runtime = None
        self.b_thread: WorkThread | None = None
        self.process_stage: str = ""
        self.active_job_id: str | None = None
        self.active_task_ids: set[str] = set()
        self.pending_job_id: str | None = None
        self.pending_task_ids: set[str] = set()
        self.binding_generation = 0

    def start_runtime(self, site_index: int):
        if self.spider_runtime and self.spider_runtime.is_alive():
            return
        self.spider_runtime = SpiderRuntimeThread()
        self.spider_runtime.daemon = True
        self.spider_runtime.start()
        self.spider_runtime.wait_ready()

    def submit_download(self, book):
        if not self.spider_runtime:
            self.start_runtime(self.gui.chooseBox.currentIndex())
        if self.active_job_id or self.pending_job_id:
            return
        site_index = self.gui.chooseBox.currentIndex()
        job = SpiderDownloadJob(
            job_id=uuid4().hex,
            spider_name=SPIDERS[site_index],
            site_index=site_index,
            payload=book,
            options={},
        )
        self.queue_job(job)
        self.ensure_work_thread()
        self.spider_runtime.submit_job(job)

    def flush_pending_rebind(self):
        self.binding_generation += 1
        if self.b_thread:
            self.b_thread.authority = self
            self.b_thread.suspend_dispatch()
            self._disconnect_worker_signals(self.b_thread)
            self.b_thread.rebind(self.gui)
            self._connect_worker_signals(self.b_thread)
            self.b_thread.resume_dispatch()

    def ensure_work_thread(self) -> WorkThread:
        if self.b_thread and self.b_thread.isRunning():
            self.b_thread.authority = self
            self.b_thread.suspend_dispatch()
            self._disconnect_worker_signals(self.b_thread)
            self.b_thread.rebind(self.gui)
            self._connect_worker_signals(self.b_thread)
            self.b_thread.resume_dispatch()
            return self.b_thread
        self.b_thread = WorkThread(self.gui, event_q=self.spider_runtime.event_q, authority=self)
        self._connect_worker_signals(self.b_thread)
        self.b_thread.start()
        if log := getattr(self.gui, "log", None):
            log.info("-*-*- Background thread & spider starting")
        return self.b_thread

    def stop_work_thread(self, wait_ms=800):
        worker = self.b_thread
        if worker is None:
            return
        worker.stop()
        worker.quit()
        worker.wait(wait_ms)
        self.b_thread = None

    def queue_job(self, job: SpiderDownloadJob):
        self.pending_job_id = job.job_id
        self.pending_task_ids = self._collect_task_ids(job.payload)

    def accept_job(self, job_id: str | None):
        if not job_id or job_id != self.pending_job_id:
            return
        self.active_job_id = job_id
        self.active_task_ids = set(self.pending_task_ids)
        self.pending_job_id = None
        self.pending_task_ids.clear()

    def reject_job(self, job_id: str | None):
        if not job_id or job_id != self.pending_job_id:
            return
        self.pending_job_id = None
        self.pending_task_ids.clear()

    def track_task(self, job_id: str | None, task_obj):
        if not job_id or job_id != self.active_job_id:
            return
        task_id = getattr(task_obj, "taskid", None)
        if task_id:
            self.active_task_ids.add(task_id)

    def finish_job(self, job_id: str | None):
        if not job_id or job_id != self.active_job_id:
            return
        self.active_job_id = None
        self.active_task_ids.clear()
        self.pending_job_id = None
        self.pending_task_ids.clear()
        self.process_stage = ""
        self.process_stage_changed.emit("")

    def has_active_download(self) -> bool:
        return bool(self.active_job_id or self.pending_job_id)

    def get_running_task_ids(self) -> set[str]:
        if self.active_task_ids:
            return set(self.active_task_ids)
        return set(self.pending_task_ids)

    @staticmethod
    def _collect_task_ids(book) -> set[str]:
        running_ids = set()
        episodes = list(getattr(book, "episodes", None) or [])
        if episodes:
            for episode in episodes:
                if hasattr(episode, "id_and_md5"):
                    running_ids.add(episode.id_and_md5()[1])
            return running_ids
        if hasattr(book, "id_and_md5"):
            running_ids.add(book.id_and_md5()[1])
        return running_ids

    @staticmethod
    def _disconnect_worker_signals(worker: WorkThread):
        for signal in (
            worker.print_signal,
            worker.item_count_signal,
            worker.tasks_signal,
            worker.process_state_signal,
            worker.worker_finished_signal,
        ):
            with contextlib.suppress(TypeError):
                signal.disconnect()

    def _connect_worker_signals(self, worker: WorkThread):
        signal_slot_pairs = (
            (worker.print_signal, self.on_worker_log),
            (worker.item_count_signal, self.on_progress_changed),
            (worker.tasks_signal, self.on_task_emitted),
            (worker.process_state_signal, self.on_process_stage_changed),
            (worker.worker_finished_signal, self.on_worker_finished),
        )
        for signal, slot in signal_slot_pairs:
            signal.connect(slot)

    def on_worker_log(self, generation: int, job_id: str | None, message: str):
        if generation != self.binding_generation:
            return
        if job_id and job_id != self.active_job_id:
            return
        self.gui.say(message)

    def on_progress_changed(self, generation: int, job_id: str | None, percent: int):
        if generation != self.binding_generation:
            return
        if not job_id or job_id != self.active_job_id:
            return
        self.gui.processbar_load(percent)

    def on_task_emitted(self, generation: int, job_id: str | None, task_obj):
        if generation != self.binding_generation:
            return
        if not job_id or job_id != self.active_job_id:
            return
        self.gui.task_mgr.handle(task_obj)

    def on_process_stage_changed(self, generation: int, job_id: str | None, stage: str):
        if generation != self.binding_generation:
            return
        if not job_id or job_id != self.active_job_id:
            return
        self.process_stage = stage or ""
        self.process_stage_changed.emit(self.process_stage)

    def on_worker_finished(self, generation: int, job_id: str | None, imgs_path: str, success: bool):
        if generation != self.binding_generation:
            return
        if not job_id or job_id != self.active_job_id:
            return
        self.gui._on_worker_finished(job_id, imgs_path, success)
        self.finish_job(job_id)

    def rebind(self, gui):
        self.gui = gui
        self.binding_generation += 1
        if self.b_thread:
            self.b_thread.authority = self
            self.b_thread.suspend_dispatch()
            self._disconnect_worker_signals(self.b_thread)
            self.b_thread.rebind(gui)
            self._connect_worker_signals(self.b_thread)
            self.b_thread.resume_dispatch()

    def close_runtime(self, stop_mgr=True, really_close=True):
        self.gui.clean_preview()
        if really_close:
            self.stop_work_thread()
        if self.spider_runtime and really_close:
            self.spider_runtime.shutdown()
            self.spider_runtime.join(timeout=3)
            self.spider_runtime = None
            self.active_job_id = None
            self.active_task_ids.clear()
            self.process_stage = ""
        if stop_mgr and getattr(self.gui, "mid_mgr", None):
            self.gui.mid_mgr.stop()
