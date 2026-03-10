#!/usr/bin/python
# -*- coding: utf-8 -*-
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SpiderDownloadJob:
    job_id: str
    spider_name: str
    site_index: int
    payload: Any
    options: dict
    created_at: float = field(default_factory=time.time)


@dataclass
class SubmitJobCommand:
    job: SpiderDownloadJob


@dataclass
class CancelJobCommand:
    job_id: str


@dataclass
class ShutdownCommand:
    pass


@dataclass
class JobAcceptedEvent:
    job_id: str


@dataclass
class TaskCreatedEvent:
    job_id: str
    task_id: str
    url: str


@dataclass
class TaskProgressEvent:
    job_id: str
    task_id: str
    status: str


@dataclass
class DownloadProgressEvent:
    job_id: str
    task_id: str
    downloaded: int
    total: int


@dataclass
class LogEvent:
    job_id: Optional[str]
    level: str
    message: str


@dataclass
class ErrorEvent:
    job_id: str
    error: str


@dataclass
class JobFinishedEvent:
    job_id: str
    success: bool


@dataclass
class BarProgressEvent:
    job_id: Optional[str]
    percent: int


@dataclass
class ProcessStateEvent:
    job_id: Optional[str]
    process: str


@dataclass
class TasksObjEvent:
    job_id: Optional[str]
    task_obj: Any
    is_new: bool = False


class RuntimeState:
    def __init__(self):
        self._lock = threading.Lock()
        self.stage: str = "idle"
        self.progress: float = 0.0
        self.active_job_id: Optional[str] = None
        self.error: Optional[str] = None
        self.version: int = 0

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.version += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "stage": self.stage,
                "progress": self.progress,
                "active_job_id": self.active_job_id,
                "error": self.error,
                "version": self.version,
            }


@dataclass
class JobContext:
    job_id: str
    tasks: dict = field(default_factory=dict)
    tasks_path: dict = field(default_factory=dict)
    total: int = 0
    record_sql: Any = None
    rv_sql: Any = None
    mr: Any = None
