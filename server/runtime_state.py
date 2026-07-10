from __future__ import annotations

import os
import traceback
from collections import deque
from datetime import datetime, timezone


SERVER_PROGRESS_ITEM_LIMIT = 40


class ServerRuntimeState:
    def __init__(self, *, max_events: int = 500) -> None:
        self.max_events = int(max_events)
        self.events: deque[dict] = deque(maxlen=self.max_events)
        self.logs: deque[dict] = deque(maxlen=self.max_events)
        self.request_diagnostics: deque[dict] = deque(maxlen=self.max_events)
        self.server_errors: deque[dict] = deque(maxlen=self.max_events)
        self.current_job: dict | None = None

    def start_job(self, job_id: str, *, origin: str) -> dict:
        now = utc_now()
        self.current_job = {
            "job_id": job_id,
            "status": "starting",
            "stage": None,
            "progress": None,
            "task": None,
            "error": None,
            "error_code": None,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "origin": origin,
        }
        return dict(self.current_job)

    def status(self, *, foreground_mode: bool) -> dict:
        job = dict(self.current_job) if self.current_job else None
        if job is not None:
            job["progress_items"] = self.progress_items(job, str(job.get("status") or ""))
        if foreground_mode:
            status = "unavailable"
        elif job:
            status = job["status"]
        else:
            status = "idle"
        return {
            "status": status,
            "configured": True,
            "available": not foreground_mode,
            "reason": "CGS GUI foreground owns runtime" if foreground_mode else None,
            "memory_persistent": True,
            "job": job,
        }

    def event_payload(self) -> dict:
        job_id = self.current_job["job_id"] if self.current_job else None
        return {"job_id": job_id, "events": list(self.events), "logs": list(self.logs)}

    def progress_items(self, job: dict | None = None, status: str | None = None) -> list[dict]:
        source_job = job if isinstance(job, dict) else self.current_job
        source_status = str(status or (source_job or {}).get("status") or "")
        items: dict[str, dict] = {}
        order: list[str] = []
        downloaded_keys: dict[str, set[tuple]] = {}
        for event in self.events:
            if not isinstance(event, dict) or event.get("type") != "task":
                continue
            task_id = str(event.get("task_id") or event.get("task_title") or event.get("url") or len(order) + 1)
            if task_id not in items:
                items[task_id] = {
                    "task_id": task_id,
                    "unit_id": task_id,
                    "status": "queued",
                    "latest_message": "-",
                }
                downloaded_keys[task_id] = set()
                order.append(task_id)
            item = items[task_id]
            item.update({key: value for key, value in event.items() if value not in (None, "") and not key.startswith("_")})
            item["unit_id"] = str(item.get("unit_id") or item.get("task_id") or task_id)
            if event.get("is_new"):
                item["status"] = "running"
                item["latest_message"] = "task registered"
            page_key = event.get("page") or event.get("url")
            if page_key:
                if event.get("success", True) is not False:
                    downloaded_keys[task_id].add(task_progress_downloaded_key(event))
                    item["downloaded"] = max(coerce_int(item.get("downloaded")) or 0, len(downloaded_keys[task_id]))
                    item["status"] = "running"
                    item["latest_message"] = f"saved page {event.get('page') or len(downloaded_keys[task_id])}"
                else:
                    item["status"] = "failed"
                    item["latest_message"] = f"failed page {event.get('page') or '-'}"
                if not item.get("source_url"):
                    item["source_url"] = event.get("url")

        latest_task = source_job.get("task") if isinstance(source_job, dict) and isinstance(source_job.get("task"), dict) else None
        if latest_task:
            task_id = str(latest_task.get("task_id") or latest_task.get("task_title") or "current")
            if task_id not in items:
                items[task_id] = {"task_id": task_id, "unit_id": task_id}
                downloaded_keys[task_id] = set()
                order.append(task_id)
            items[task_id].update({key: value for key, value in latest_task.items() if value not in (None, "")})
            items[task_id]["unit_id"] = str(items[task_id].get("unit_id") or items[task_id].get("task_id") or task_id)
            items[task_id]["status"] = "failed" if source_status == "failed" else "running"
            items[task_id].setdefault("latest_message", "latest task")

        if not items and source_job:
            task_id = str(source_job.get("job_id") or "job")
            items[task_id] = {
                "task_id": task_id,
                "unit_id": task_id,
                "scope": "job",
                "task_title": source_job.get("stage") or "CGS job",
                "status": source_status,
                "latest_message": source_job.get("error") or source_job.get("stage") or "-",
            }
            order.append(task_id)

        rows = []
        for task_id in order[-SERVER_PROGRESS_ITEM_LIMIT:]:
            item = dict(items[task_id])
            total = coerce_int(item.get("total_pages") or item.get("tasks_count")) or 0
            downloaded = coerce_int(item.get("downloaded")) or len(downloaded_keys.get(task_id) or ())
            explicit_percent = coerce_percent(item.get("percent")) if item.get("percent") is not None else None
            percent = coerce_percent(downloaded / total * 100) if total else (explicit_percent if explicit_percent is not None else 0)
            item["total_pages"] = total
            item["downloaded"] = downloaded
            if source_status == "completed" and item.get("status") != "failed":
                item["downloaded"] = total or downloaded
                item["percent"] = 100
                item["status"] = "completed"
            else:
                item["percent"] = 100 if total and downloaded >= total else percent
            if total and item["downloaded"] >= total and item.get("status") != "failed":
                item["percent"] = 100
                item["status"] = "completed"
            if source_status == "failed" and task_id == order[-1] and item.get("status") != "completed":
                item["status"] = "failed"
            normalize_progress_item_labels(item)
            rows.append(item)
        return rows

    def diagnostics(self, status: dict) -> dict:
        return {
            "status": status,
            "requests": list(self.request_diagnostics),
            "server_errors": list(self.server_errors),
        }

    def record_request_diagnostic(self, entry: dict) -> None:
        self.request_diagnostics.append(dict(entry))

    def clear_request_diagnostics(self) -> int:
        count = len(self.request_diagnostics)
        self.request_diagnostics.clear()
        return count

    def clear_server_errors(self) -> int:
        count = len(self.server_errors)
        self.server_errors.clear()
        return count

    def clear_work_history(self) -> dict:
        cleared = {
            "events": len(self.events),
            "logs": len(self.logs),
            "job": 1 if self.current_job else 0,
        }
        self.events.clear()
        self.logs.clear()
        self.current_job = None
        return cleared

    def job_for(self, job_id: str) -> dict | None:
        if self.current_job and self.current_job.get("job_id") == job_id:
            return dict(self.current_job)
        return None

    def record_server_error(
            self,
            summary: str,
            detail: str = "",
            *,
            source: str = "server",
            code: str | None = None,
            method: str | None = None,
            path: str | None = None,
            status_code: int | None = None,
            exc: BaseException | None = None,
    ) -> None:
        self.server_errors.append({
            "timestamp": utc_now(),
            "source": str(source),
            "summary": str(summary),
            "detail": str(detail or ""),
            "code": None if code is None else str(code),
            "method": None if method is None else str(method),
            "path": None if path is None else str(path),
            "status_code": None if status_code is None else int(status_code),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc is not None else None,
        })

    def record_event(self, event: dict) -> None:
        self.apply_event(event)
        if event.get("type") == "progress":
            return
        self.events.append(event)
        if event.get("type") == "log":
            self.logs.append(event)

    def mark_failed(self, job_id: str, message: str, code: str) -> dict:
        event = {
            "type": "error", "job_id": job_id, "timestamp": utc_now(),
            "code": code, "message": message,
        }
        self.events.append(event)
        self.apply_event(event)
        return event

    def mark_completed_if_needed(self, job_id: str) -> dict | None:
        job = self.current_job
        if job is None or job.get("job_id") != job_id or job.get("status") in {"completed", "failed"}:
            return None
        event = {"type": "finished", "job_id": job_id, "timestamp": utc_now(), "success": True}
        self.record_event(event)
        return event

    def apply_event(self, event: dict) -> None:
        if self.current_job is None:
            return
        if event.get("job_id") and event.get("job_id") != self.current_job["job_id"]:
            return
        event_type = event.get("type")
        self.current_job["updated_at"] = utc_now()
        if event_type == "accepted":
            self.current_job["status"] = "running"
        elif event_type == "stage":
            self.current_job["stage"] = event.get("stage") or event.get("name") or event.get("message")
            self.current_job["status"] = "running"
        elif event_type == "progress":
            self.current_job["progress"] = {
                k: v for k, v in event.items() if k not in {"type", "job_id", "timestamp"}
            }
            self.current_job["status"] = "running"
        elif event_type == "task":
            self.current_job["task"] = {
                k: v for k, v in event.items() if k not in {"type", "job_id", "timestamp"}
            }
            self.current_job["status"] = "running"
        elif event_type == "error":
            self.current_job["status"] = "failed"
            self.current_job["error"] = event.get("message") or event.get("error") or event.get("detail")
            self.current_job["error_code"] = event.get("code") or "error"
            self.current_job["finished_at"] = utc_now()
        elif event_type == "finished":
            if event.get("success") is False:
                self.current_job["status"] = "failed"
                self.current_job["error"] = event.get("message") or event.get("error") or event.get("detail")
                self.current_job["error_code"] = event.get("code") or "failed"
            else:
                self.current_job["status"] = "completed"
            self.current_job["finished_at"] = utc_now()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_progress_item_labels(item: dict) -> None:
    episode_title = str(item.get("episode_title") or item.get("episode_name") or "").strip()
    book_title = str(item.get("book_title") or item.get("title") or "").strip()
    task_title = str(item.get("task_title") or "").strip()
    if episode_title:
        item["kind"] = "ep"
        item["label"] = episode_title
        item["episode_title"] = episode_title
    else:
        item["kind"] = "book"
        item["label"] = book_title or task_title or str(item.get("task_id") or "")
    if book_title:
        item["book_title"] = book_title
    if not task_title:
        if episode_title and book_title:
            item["task_title"] = f"{book_title} - {episode_title}"
        elif item.get("label"):
            item["task_title"] = str(item["label"])


def task_progress_downloaded_key(event: dict) -> tuple:
    page = event.get("page")
    page_number = task_progress_page_number(page)
    if page_number is not None:
        return "page", page_number
    return "raw", page, event.get("url")


def task_progress_page_number(page) -> int | None:
    if page is None:
        return None
    page_str = str(page).strip()
    if not page_str:
        return None
    stem, _ext = os.path.splitext(page_str)
    stem = stem.lower()
    if stem.isdigit():
        return int(stem.lstrip("0") or "0")
    return 1 if stem in {"cover", "front", "first"} else None


def coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_percent(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
