# -*- coding: utf-8 -*-
"""Subscribe background workers — PreviewWorker lifecycle, not try/except seals.

Architecture (project evidence: GUI/thread/preview.py + GUI/manager/preview/__init__.py):
1. Signals live on the QThread worker itself (not on SubscribeWindow, not a global hub).
2. Window close / refresh: disconnect slots → stop worker → wait finished → deleteLater.
3. Stale results: generation int compared in the slot (normal discard, not exception).
4. Domain failures (network, decode): cover_error signal → log; never sys.excepthook.
5. QRunnable + window-parented QObject was wrong: QueuedConnection can still touch a
   deleted signal source → RuntimeError → CGS ExceptionRouter white QMessageBox per card.

Qt / industry sources for this shape:
- Qt docs: QObject thread affinity; signals/slots across threads (QueuedConnection).
- Qt docs: stop worker threads before destroying receivers; disconnect before delete.
- PreviewWorker in this repo is the local gold standard for cover download lifecycle.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from PySide6.QtCore import QObject, QThread, Signal

from utils import conf, temp_p
from utils.core import TasksObj

_log = logging.getLogger("GUI.tools.subscribe.workers")

_COVER_FETCH_MAX_CONCURRENT = 5
_COVER_DISK_CACHE_DIR = temp_p.joinpath("subscribe_covers")


def cover_disk_cache_path(card_key: str) -> Path:
    """Stable on-disk path for a subscribe card cover (binary blob, no re-encode)."""
    digest = hashlib.sha1(str(card_key or "").encode("utf-8")).hexdigest()
    return _COVER_DISK_CACHE_DIR.joinpath(f"{digest}.cover")


def load_cover_disk_cache(card_key: str) -> bytes | None:
    path = cover_disk_cache_path(card_key)
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data if data else None


def save_cover_disk_cache(card_key: str, data: bytes) -> None:
    if not data:
        return
    path = cover_disk_cache_path(card_key)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_bytes(data)
    temporary_path.replace(path)


@dataclass(frozen=True, slots=True)
class CoverFetchTask:
    generation: int
    card_key: str
    site_index: int
    tasks_obj: TasksObj
    book_url: str = ""


class SubscribeCoverWorker(QThread):
    """Long-lived cover fetcher owned by SubscribeWindow session.

    Same contract as PreviewWorker CoverTask:
    - one event loop for the thread lifetime
    - download_cover_bytes then await ThreadSiteRuntime.aclose() in that loop
    - signals on *this* QThread instance (affinity = worker thread when emitting)
    - stop() then wait; owner disconnects before deleteLater
    """

    cover_done = Signal(int, str, object)  # generation, card_key, bytes
    cover_error = Signal(int, str, str)  # generation, card_key, message
    # Missing img_preview was hydrated from owner page (persist on GUI thread).
    cover_meta = Signal(int, str, str)  # generation, card_key, cover_url

    def __init__(self, parent: QObject | None = None):
        # parent must outlive stop/wait; SubscribeWindow is OK if closeEvent waits.
        super().__init__(parent)
        self._active = True
        self._task_queue: Queue[CoverFetchTask | None] = Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.setObjectName("SubscribeCoverWorker")

    def enqueue(self, task: CoverFetchTask) -> None:
        if not self._active:
            return
        self._task_queue.put(task)

    def stop(self) -> None:
        """Request shutdown; does not wait (owner waits after disconnect)."""
        self._active = False
        self._task_queue.put(None)

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            while self._active:
                batch = self._drain_batch()
                if batch is None:
                    break
                if not batch:
                    continue
                self._loop.run_until_complete(self._fetch_batch(batch))
        finally:
            if self._loop is not None:
                self._loop.close()
                self._loop = None

    def _drain_batch(self) -> list[CoverFetchTask] | None:
        """Block for first item; then non-blocking drain up to concurrency cap.

        Returns None on stop sentinel, empty list on idle timeout (loop again).
        """
        try:
            first = self._task_queue.get(timeout=0.12)
        except Empty:
            return []
        if first is None:
            return None
        batch = [first]
        while len(batch) < _COVER_FETCH_MAX_CONCURRENT:
            try:
                item = self._task_queue.get_nowait()
            except Empty:
                break
            if item is None:
                # Preserve stop for outer loop after this batch.
                self._task_queue.put(None)
                break
            batch.append(item)
        return batch

    async def _fetch_batch(self, batch: list[CoverFetchTask]) -> None:
        semaphore = asyncio.Semaphore(_COVER_FETCH_MAX_CONCURRENT)

        async def _one(task: CoverFetchTask) -> None:
            async with semaphore:
                await self._fetch_one(task)

        await asyncio.gather(*[_one(task) for task in batch])

    async def _fetch_one(self, task: CoverFetchTask) -> None:
        # Disk cache: normal path, OSError is a real fault → cover_error.
        try:
            cached = load_cover_disk_cache(task.card_key)
        except OSError as exc:
            self.cover_error.emit(
                task.generation,
                task.card_key,
                f"disk_cache_read {type(exc).__name__}: {exc}",
            )
            cached = None
        if cached:
            self.cover_done.emit(task.generation, task.card_key, cached)
            return

        from utils.website.registry import create_gui_site_runtime

        runtime = None
        try:
            gui_runtime = create_gui_site_runtime(task.site_index, conf_state=conf)
            cover_url = str(getattr(task.tasks_obj, "cover_url", None) or "").strip()
            if not cover_url.startswith(("http://", "https://")):
                hydrated = await self._hydrate_cover_url(gui_runtime, task)
                if not hydrated:
                    self.cover_error.emit(
                        task.generation,
                        task.card_key,
                        f"missing cover_url; book_url={task.book_url or getattr(task.tasks_obj, 'title_url', '')}",
                    )
                    return
                cover_url = hydrated
                task.tasks_obj.cover_url = cover_url
                self.cover_meta.emit(task.generation, task.card_key, cover_url)
            headers = gui_runtime.build_cover_headers(task.tasks_obj)
            runtime = gui_runtime.create_thread_site_runtime()
            data = await runtime.download_cover_bytes(
                task.tasks_obj,
                browser_headers=headers,
            )
        except Exception as exc:
            cover_url = getattr(task.tasks_obj, "cover_url", None) or ""
            self.cover_error.emit(
                task.generation,
                task.card_key,
                f"{type(exc).__name__}: {exc}; cover_url={cover_url}",
            )
            return
        finally:
            if runtime is not None:
                # Must aclose inside this same loop (ThreadSiteRuntime contract).
                await runtime.aclose()

        if not data:
            self.cover_error.emit(
                task.generation,
                task.card_key,
                "empty cover bytes",
            )
            return
        try:
            save_cover_disk_cache(task.card_key, data)
        except OSError as exc:
            # Still deliver pixels; cache miss is non-fatal for this paint.
            self.cover_error.emit(
                task.generation,
                task.card_key,
                f"disk_cache_write {type(exc).__name__}: {exc}",
            )
        self.cover_done.emit(task.generation, task.card_key, data)

    async def _hydrate_cover_url(self, gui_runtime, task: CoverFetchTask) -> str:
        """Resolve img_preview from book owner page when library row was saved without cover.

        jestful (and similar) rows can land with empty img_preview + id=url when added
        outside search/index parse paths. Owner-page parse fills cover once.
        """
        book_url = str(task.book_url or getattr(task.tasks_obj, "title_url", "") or "").strip()
        if not book_url.startswith(("http://", "https://")):
            return ""
        provider_cls = getattr(gui_runtime, "provider_cls", None)
        parser = getattr(provider_cls, "parser", None) if provider_cls is not None else None
        parse_owner = getattr(parser, "parse_book_owner_state", None)
        normalize = getattr(parser, "normalize_site_resource", None)
        if not callable(parse_owner):
            return ""
        runtime = None
        try:
            runtime = gui_runtime.create_thread_site_runtime()
            client = runtime.get_async_preview_client()
            response = await client.get(book_url, follow_redirects=True, timeout=12)
            response.raise_for_status()
            owner_state = await asyncio.to_thread(
                parse_owner, response.text, owner_url=str(response.url)
            )
        finally:
            if runtime is not None:
                await runtime.aclose()
        if not isinstance(owner_state, dict):
            return ""
        raw_cover = str(owner_state.get("cover_url") or "").strip()
        if not raw_cover:
            return ""
        if callable(normalize):
            try:
                raw_cover = str(normalize(raw_cover) or raw_cover).strip()
            except Exception:
                pass
        if raw_cover.startswith(("http://", "https://")):
            return raw_cover
        return ""


class DlScanWorker(QThread):
    """One-shot local DL max scan (rv_tools.show_max), same lifecycle rules as covers."""

    scan_done = Signal(int, object)  # generation, matched dict
    scan_error = Signal(int, str)

    def __init__(
        self,
        *,
        generation: int,
        titles_by_key: dict[str, str],
        rv_tools,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._generation = int(generation)
        self._titles_by_key = dict(titles_by_key or {})
        self._rv_tools = rv_tools
        self.setObjectName("SubscribeDlScanWorker")

    def run(self) -> None:
        try:
            book_show_map = self._rv_tools.show_max() if self._rv_tools is not None else {}
        except Exception as exc:
            self.scan_error.emit(self._generation, f"{type(exc).__name__}: {exc}")
            return
        matched: dict[str, object] = {}
        if not isinstance(book_show_map, dict):
            self.scan_done.emit(self._generation, matched)
            return
        for card_key, title in self._titles_by_key.items():
            name = str(title or "").strip()
            if not name:
                continue
            book_show = book_show_map.get(name)
            if book_show is not None and str(getattr(book_show, "dl_max", "") or "").strip():
                matched[str(card_key)] = book_show
        self.scan_done.emit(self._generation, matched)


# --- lifecycle helpers used by SubscribeWindow (mirror PreviewManager) ---


def disconnect_cover_worker(worker: SubscribeCoverWorker | None) -> None:
    if worker is None:
        return
    for signal in (worker.cover_done, worker.cover_error, worker.cover_meta):
        try:
            signal.disconnect()
        except TypeError:
            pass


def disconnect_dl_scan_worker(worker: DlScanWorker | None) -> None:
    if worker is None:
        return
    for signal in (worker.scan_done, worker.scan_error):
        try:
            signal.disconnect()
        except TypeError:
            pass
