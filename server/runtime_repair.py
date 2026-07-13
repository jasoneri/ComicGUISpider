from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field

from server.errors import ServerRuntimeError
from server.runtime_state import task_progress_page_number


@dataclass(slots=True)
class RepairTaskRecord:
    job_id: str
    site_index: int
    task_id: str
    task_info: object
    total_pages: int
    candidate_pages: tuple[int, ...]
    downloaded_pages: set[int] = field(default_factory=set)
    local_path: str | None = None
    status: str | None = None
    error: str | None = None

    def missing_pages(self) -> tuple[int, ...]:
        downloaded = set(self.downloaded_pages)
        if self.local_path and os.path.isdir(self.local_path):
            downloaded.update(
                page_number for filename in os.listdir(self.local_path)
                if (page_number := task_progress_page_number(filename)) is not None
            )
        return tuple(page for page in self.candidate_pages if page not in downloaded)

    def repair_task_info(self, pages: tuple[int, ...]):
        task_info = deepcopy(self.task_info)
        task_info.download_pages = tuple(int(page) for page in pages)
        task_info.page_name_count = int(self.total_pages)
        return task_info


class ServerRepairCatalog:
    def __init__(self) -> None:
        self._records_by_job: dict[str, dict[str, RepairTaskRecord]] = {}

    def clear(self) -> None:
        self._records_by_job.clear()

    def register(self, job_id: str, site_index: int, submit_items: list) -> None:
        records = {}
        for item in submit_items:
            if not hasattr(item, "to_tasks_obj"):
                continue
            tasks_obj = item.to_tasks_obj()
            total_pages = int(
                getattr(item, "page_name_count", None)
                or getattr(tasks_obj, "page_name_count", None)
                or tasks_obj.tasks_count
            )
            download_pages = tuple(int(page) for page in (getattr(item, "download_pages", None) or ()))
            candidate_pages = download_pages or tuple(range(1, total_pages + 1))
            records[tasks_obj.taskid] = RepairTaskRecord(
                job_id=job_id, site_index=int(site_index), task_id=tasks_obj.taskid, task_info=deepcopy(item),
                total_pages=total_pages, candidate_pages=tuple(candidate_pages),
                downloaded_pages={
                    page_number for task_obj in getattr(tasks_obj, "downloaded", []) or []
                    if (
                        getattr(task_obj, "success", True)
                        and (page_number := task_progress_page_number(getattr(task_obj, "page", None))) is not None
                    )
                },
                local_path=getattr(tasks_obj, "local_path", None),
            )
        self._records_by_job[job_id] = records

    def repair_plan(self, job_id: str) -> tuple[int, list, list[dict]]:
        records = list((self._records_by_job.get(job_id) or {}).values())
        if not records:
            raise ServerRuntimeError("no_repair_records", "no repair records for current CGS job")

        repairs = []
        repair_items = []
        for record in records:
            pages = record.missing_pages()
            if not pages:
                continue
            repairs.append({"task_id": record.task_id, "pages": list(pages), "total_pages": record.total_pages})
            repair_items.append(record.repair_task_info(pages))

        if not repair_items:
            raise ServerRuntimeError("no_missing_pages", "no missing pages to repair")
        return records[0].site_index, repair_items, repairs

    def apply_event(self, event: dict) -> None:
        job_id = str(event.get("job_id") or "")
        if not job_id:
            return
        records = self._records_by_job.get(job_id)
        if not records:
            return
        event_type = event.get("type")
        if event_type == "task":
            self._apply_task_event(records, event)
            return
        if event_type == "error":
            for record in records.values():
                record.status = "failed"
                record.error = str(event.get("message") or event.get("error") or event.get("detail") or "")
            return
        if event_type == "finished":
            status = "failed" if event.get("success") is False else "completed"
            for record in records.values():
                record.status = status
                if event.get("success") is False:
                    record.error = str(event.get("message") or event.get("error") or event.get("detail") or "")

    def _apply_task_event(self, records: dict[str, RepairTaskRecord], event: dict) -> None:
        task_id = str(event.get("task_id") or "")
        record = records.get(task_id)
        if record is None:
            return
        if event.get("is_new"):
            record.local_path = str(event.get("local_path") or record.local_path or "") or None
            if total_pages := positive_int(event.get("total_pages") or event.get("tasks_count")):
                record.total_pages = total_pages
            record.status = "running"
            return
        if event.get("success", True):
            page_number = task_progress_page_number(event.get("page"))
            if page_number is not None:
                record.downloaded_pages.add(page_number)
        record.status = "running"


def positive_int(value) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None
