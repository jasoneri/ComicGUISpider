# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
# from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from ComicSpider.runtime import SpiderRuntimeThread
from GUI.thread import WorkThread
from utils.protocol import SpiderDownloadJob
from variables import SPIDERS


class DownloadRuntimeManager(QObject):
    """Manage SpiderRuntime + WorkThread lifecycle and process stage state."""

    process_stage_changed = Signal(str)
    all_jobs_finished = Signal()

    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.spider_runtime = None
        self.b_thread: WorkThread | None = None
        self.process_stage: str = ""
        self.running_job_ids: set[str] = set()
        self.binding_generation = 0
        self.session_job_ids: set[str] = set()
        self.session_job_task_ids: set[str] = set()
        self.pending_job_ids: set[str] = set()
        self._job_task_ids: dict[str, set[str]] = {}

    def start_runtime(self, site_index: int):
        if self.spider_runtime and self.spider_runtime.is_alive():
            return
        self.spider_runtime = SpiderRuntimeThread()
        self.spider_runtime.daemon = True
        self.spider_runtime.start()
        self.spider_runtime.wait_ready()

    def submit_download(self, task_info, tasks_obj=None):
        if not self.spider_runtime:
            self.start_runtime(self.gui.chooseBox.currentIndex())

        site_index = self.gui.chooseBox.currentIndex()
        tasks_obj = tasks_obj or task_info.to_tasks_obj()
        job_id = tasks_obj.taskid
        if job_id in self.pending_job_ids or job_id in self.running_job_ids:
            raise ValueError(f"duplicate runtime submission detected for task {job_id}")

        job = SpiderDownloadJob(
            job_id=job_id,
            spider_name=SPIDERS[site_index],
            site_index=site_index,
            payload=task_info,
            options={},
            tasks_obj=tasks_obj,
        )

        self.session_job_ids.add(job_id)
        self.pending_job_ids.add(job_id)
        self._job_task_ids[job_id] = {tasks_obj.taskid}
        self.session_job_task_ids.add(tasks_obj.taskid)
        self.gui.task_mgr.handle(tasks_obj)
        self.ensure_work_thread()
        self.spider_runtime.submit_job(job)

    def ensure_work_thread(self) -> WorkThread:
        if self.b_thread and self.b_thread.isRunning():
            return self.b_thread
        self.b_thread = WorkThread(self.gui, event_q=self.spider_runtime.event_q, authority=self)
        self.b_thread._bind_generation = self.binding_generation
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

    def is_job_pending(self, job_id: str | None) -> bool:
        return bool(job_id) and job_id in self.pending_job_ids

    def accept_job(self, job_id: str | None):
        if not job_id or job_id not in self.pending_job_ids:
            return
        self.running_job_ids.add(job_id)
        self.pending_job_ids.discard(job_id)

    def reject_job(self, job_id: str | None):
        if not job_id or job_id not in self.pending_job_ids:
            return
        self.pending_job_ids.discard(job_id)
        self.session_job_ids.discard(job_id)
        if job_id in self._job_task_ids:
            del self._job_task_ids[job_id]
            self._rebuild_session_task_ids()

    def track_task(self, job_id: str | None, task_obj):
        if not job_id:
            return
        expected_task_ids = self._job_task_ids.get(job_id)
        if expected_task_ids is None:
            self._job_task_ids[job_id] = {task_obj.taskid}
            self.session_job_task_ids.add(task_obj.taskid)
            return
        if task_obj.taskid not in expected_task_ids:
            raise ValueError(
                f"runtime emitted unexpected task {task_obj.taskid} for job {job_id}, "
                f"expected one of {sorted(expected_task_ids)}"
            )

    def finish_job(self, job_id: str | None):
        if not job_id:
            return
        self.running_job_ids.discard(job_id)
        self.pending_job_ids.discard(job_id)
        self.session_job_ids.discard(job_id)
        if job_id in self._job_task_ids:
            del self._job_task_ids[job_id]
            self._rebuild_session_task_ids()
        if not self.running_job_ids and not self.pending_job_ids:
            self.all_jobs_finished.emit()

    def has_active_download(self) -> bool:
        return bool(self.running_job_ids or self.pending_job_ids)

    def get_running_task_ids(self) -> set[str]:
        return set(self.session_job_task_ids)

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
        if isinstance(message, str) and message.startswith("[PreviewBookInfoEnd]"):
            return
        self.gui.say(message)

    def on_progress_changed(self, generation: int, job_id: str | None, percent: int):
        if generation != self.binding_generation:
            return

    def on_task_emitted(self, generation: int, job_id: str | None, task_obj):
        if generation != self.binding_generation:
            return
        self.gui.task_mgr.handle(task_obj)

    def on_process_stage_changed(self, generation: int, job_id: str | None, stage: str):
        if generation != self.binding_generation:
            return
        self.process_stage = stage or ""
        self.process_stage_changed.emit(self.process_stage)

    def on_worker_finished(self, generation: int, job_id: str | None, imgs_path: str, success: bool):
        if generation != self.binding_generation:
            return
        self.finish_job(job_id)

    def rebind(self, gui):
        self.gui = gui
        self.binding_generation += 1

        if self.has_active_download():
            # Preserve active session state, only rewire signals
            if self.b_thread:
                self.b_thread.authority = self
                self.b_thread.suspend_dispatch()
                self._disconnect_worker_signals(self.b_thread)
                self.b_thread.rebind(gui)
                self._connect_worker_signals(self.b_thread)
                self.b_thread.resume_dispatch()
        else:
            # No active download: reset all session state
            self.process_stage = ""
            self.session_job_ids.clear()
            self.session_job_task_ids.clear()
            self.pending_job_ids.clear()
            self._job_task_ids.clear()
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
            self.running_job_ids.clear()
            self.process_stage = ""
            self.session_job_ids.clear()
            self.session_job_task_ids.clear()
            self.pending_job_ids.clear()
            self._job_task_ids.clear()
        if stop_mgr and getattr(self.gui, "mid_mgr", None):
            self.gui.mid_mgr.stop()

    def _rebuild_session_task_ids(self):
        merged = set()
        for task_ids in self._job_task_ids.values():
            merged.update(task_ids)
        self.session_job_task_ids = merged
