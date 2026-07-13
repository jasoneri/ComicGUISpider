from __future__ import annotations

import queue
import threading
from collections.abc import Sized
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from ComicSpider.runtime import SpiderRuntimeThread
from utils.protocol import (
    BarProgressEvent,
    ErrorEvent,
    JobAcceptedEvent,
    JobFinishedEvent,
    LogEvent,
    ProcessStateEvent,
    SpiderDownloadJob,
    TasksObjEvent,
)
from variables import SPIDERS


@dataclass(slots=True)
class DownloadQuantityRecord:
    expected_pages: int | None = None
    expected_registered_tasks_count: int | None = None
    registered_tasks_count: int | None = None
    processed_events: int = 0

    @property
    def is_aligned(self) -> bool:
        expected_registered = {
            value for value in (self.expected_pages, self.expected_registered_tasks_count)
            if value is not None
        }
        return (
            self.expected_pages is not None
            and self.registered_tasks_count in expected_registered
            and self.expected_pages == self.processed_events
        )


class DownloadQuantityProbe:
    def __init__(self, payload):
        self.records: dict[str, DownloadQuantityRecord] = {}
        self._seed_from_payload(payload)

    def _iter_payload_items(self, payload):
        if payload is None:
            return
        if isinstance(payload, list):
            for item in payload:
                if hasattr(item, "to_tasks_obj"):
                    yield item
            return
        if hasattr(payload, "to_tasks_obj"):
            yield payload

    def _seed_from_payload(self, payload):
        for item in self._iter_payload_items(payload):
            tasks_obj = item.to_tasks_obj()
            record = self.records.setdefault(tasks_obj.taskid, DownloadQuantityRecord())
            download_pages = tuple(int(page) for page in (getattr(item, "download_pages", None) or ()))
            total_pages = int(
                getattr(item, "page_name_count", None)
                or getattr(tasks_obj, "page_name_count", None)
                or tasks_obj.tasks_count
            )
            record.expected_pages = len(download_pages) if download_pages else total_pages
            record.expected_registered_tasks_count = total_pages

    def observe(self, event: TasksObjEvent):
        task = getattr(event, "task_obj", None)
        taskid = getattr(task, "taskid", None)
        if not taskid:
            return
        record = self.records.setdefault(taskid, DownloadQuantityRecord())
        if event.is_new:
            record.registered_tasks_count = getattr(task, "tasks_count", None)
            if record.expected_pages is None:
                record.expected_pages = record.registered_tasks_count
            return
        record.processed_events += 1

    def summarize(self) -> tuple[list[str], list[str]]:
        aligned = []
        drifted = []
        for taskid, record in sorted(self.records.items()):
            summary = (
                f"{taskid}: expected={record.expected_pages}, "
                f"registered_expected={record.expected_registered_tasks_count}, "
                f"registered={record.registered_tasks_count}, processed={record.processed_events}"
            )
            if record.is_aligned:
                aligned.append(summary)
            else:
                drifted.append(summary)
        return aligned, drifted


class ServerEventSink:
    def __init__(self, job_id: str, owner):
        self.job_id = job_id
        self.owner = owner

    def protocol_event(self, event):
        self.owner.record_event(serialize_protocol_event(event, default_job_id=self.job_id))


class SubmittedJobWaiter:
    def __init__(self, job_id: str, payload, *, event_sink: ServerEventSink | None = None):
        self.job_id = str(job_id)
        self.event_sink = event_sink
        self.quantity_probe = DownloadQuantityProbe(payload)
        self._condition = threading.Condition()
        self._finished = False
        self._success = False
        self._drifted: list[str] = []
        self._last_percent = None

    def observe(self, event) -> None:
        event_job_id = getattr(event, "job_id", None)
        if event_job_id and str(event_job_id) != self.job_id:
            return
        if self.event_sink:
            self.event_sink.protocol_event(event)
        if isinstance(event, JobAcceptedEvent):
            logger.info(f"[accepted] {event.job_id}")
        elif isinstance(event, LogEvent):
            logger.info(str(event.message))
        elif isinstance(event, ProcessStateEvent):
            logger.debug(f"[stage] {event.process}")
        elif isinstance(event, BarProgressEvent):
            if event.percent != self._last_percent:
                self._last_percent = event.percent
                logger.info(f"[progress] {event.percent}%")
        elif isinstance(event, TasksObjEvent):
            self.quantity_probe.observe(event)
            task = event.task_obj
            if event.is_new:
                title = getattr(task, "display_title", None) or getattr(task, "taskid", "")
                logger.info(f"[task] {title}")
        elif isinstance(event, ErrorEvent):
            logger.error(event.error)
        elif isinstance(event, JobFinishedEvent):
            aligned, drifted = self.quantity_probe.summarize()
            for summary in aligned:
                logger.info(f"[quantity] aligned {summary}")
            for summary in drifted:
                logger.error(f"[quantity] drift {summary}")
            with self._condition:
                self._success = bool(event.success)
                self._drifted = drifted
                self._finished = True
                self._condition.notify_all()
            logger.info(f"[finished] success={self._success}")

    def wait(self, runtime: SpiderRuntimeThread) -> bool:
        while True:
            with self._condition:
                if self._finished:
                    return self._success and not self._drifted
                self._condition.wait(timeout=0.2)
            if not runtime.is_alive():
                raise RuntimeError("SpiderRuntimeThread stopped before job finished")

    def done(self) -> bool:
        with self._condition:
            return self._finished

    def result(self) -> bool:
        with self._condition:
            if not self._finished:
                raise RuntimeError(f"download job has not finished: {self.job_id}")
            return self._success and not self._drifted


def build_submitted_download_job(
        site_index: int, payload, *, job_id: str, event_sink: ServerEventSink | None = None
) -> tuple[SpiderDownloadJob, SubmittedJobWaiter]:
    job = SpiderDownloadJob(job_id=job_id, spider_name=SPIDERS[site_index], site_index=site_index, payload=payload, options={})
    return job, SubmittedJobWaiter(job_id, payload, event_sink=event_sink)


def serialize_protocol_event(event, *, default_job_id: str) -> dict:
    event_job_id = getattr(event, "job_id", None) or default_job_id
    if isinstance(event, JobAcceptedEvent):
        return {"type": "accepted", "job_id": event_job_id, "timestamp": _utc_now()}
    if isinstance(event, LogEvent):
        return {
            "type": "log",
            "job_id": event_job_id,
            "timestamp": _utc_now(),
            "level": str(event.level),
            "message": str(event.message),
        }
    if isinstance(event, ProcessStateEvent):
        return {"type": "stage", "job_id": event_job_id, "timestamp": _utc_now(), "stage": str(event.process)}
    if isinstance(event, BarProgressEvent):
        return {"type": "progress", "job_id": event_job_id, "timestamp": _utc_now(), "percent": event.percent}
    if isinstance(event, TasksObjEvent):
        return {
            "type": "task",
            "job_id": event_job_id,
            "timestamp": _utc_now(),
            "is_new": bool(event.is_new),
            **_task_fields(event.task_obj),
        }
    if isinstance(event, ErrorEvent):
        return {"type": "error", "job_id": event_job_id, "timestamp": _utc_now(), "error": str(event.error)}
    if isinstance(event, JobFinishedEvent):
        payload = {
            "type": "finished", "job_id": event_job_id,
            "timestamp": _utc_now(), "success": bool(event.success),
        }
        if event.error:
            payload["error"] = str(event.error)
        return payload
    return {
        "type": "unknown",
        "job_id": event_job_id,
        "timestamp": _utc_now(),
        "message": repr(event),
        "event_class": event.__class__.__name__,
    }


def submit_and_wait(site_index: int, payload, *, job_id: str, event_sink: ServerEventSink | None = None) -> bool:
    runtime = SpiderRuntimeThread()
    runtime.daemon = True
    runtime.start()
    runtime.wait_ready(timeout=30)
    try:
        return run_submitted_job(runtime, site_index, payload, job_id=job_id, event_sink=event_sink)
    finally:
        runtime.shutdown()
        runtime.join(timeout=5)


def run_submitted_job(runtime: SpiderRuntimeThread, site_index: int, payload, *, job_id: str, event_sink=None) -> bool:
    job, waiter = build_submitted_download_job(site_index, payload, job_id=job_id, event_sink=event_sink)
    logger.info(f"[submit] spider={job.spider_name} job={job.job_id}")
    runtime.submit_job(job)
    while True:
        try:
            event = runtime.event_q.get(timeout=0.2)
        except queue.Empty:
            if not runtime.is_alive():
                raise RuntimeError("SpiderRuntimeThread stopped before job finished")
            continue
        event_job_id = getattr(event, "job_id", None)
        if event_job_id and event_job_id != job.job_id:
            continue
        waiter.observe(event)
        if waiter.done():
            return waiter.result()


def _task_fields(task) -> dict:
    fields = {}
    for attr, key in (
        ("taskid", "task_id"),
        ("tasks_count", "tasks_count"),
        ("page_name_count", "total_pages"),
        ("page", "page"),
        ("url", "url"),
        ("title_url", "source_url"),
        ("cover_url", "cover_url"),
        ("local_path", "local_path"),
        ("source", "site"),
        ("success", "success"),
    ):
        if (value := getattr(task, attr, None)) is not None:
            fields[key] = str(value) if attr in {"taskid", "url", "title_url", "cover_url", "local_path", "source"} else value
    if (title := getattr(task, "display_title", None) or getattr(task, "title", None)) is not None:
        fields["task_title"] = str(title)
    if (book_title := getattr(task, "title", None)) is not None:
        fields["book_title"] = str(book_title)
    if (episode_title := getattr(task, "episode_name", None)) is not None:
        fields["episode_title"] = str(episode_title)
    if (downloaded := getattr(task, "downloaded", None)) is not None and isinstance(downloaded, Sized):
        fields["downloaded"] = len(downloaded)
    return fields


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
