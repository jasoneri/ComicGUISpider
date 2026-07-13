from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from collections import deque
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4

from loguru import logger

from utils import install_qfluentwidgets_notice_filter

install_qfluentwidgets_notice_filter()

from ComicSpider.runtime import SpiderRuntimeThread
from utils import conf, temp_p
from server.errors import ServerRuntimeError
from server.runtime_download import ServerEventSink, SubmittedJobWaiter, build_submitted_download_job
from server.runtime_repair import ServerRepairCatalog
from server.runtime_sessions import EpisodeSelect, ServerSessionCatalog
from server.runtime_state import ServerRuntimeState, utc_now
from variables import Spider


class PreviewRuntime:
    def __init__(self, site_index: int):
        from utils.config.qc import cgs_cfg
        from utils.website import create_gui_site_runtime, resolve_provider_descriptor_by_site
        from utils.website.core import DomainUtils
        from utils.website.site_runtime import ThreadSiteRuntime

        self.site_index = int(site_index)
        self.provider_descriptor = resolve_provider_descriptor_by_site(self.site_index)
        gui_site_runtime = create_gui_site_runtime(self.site_index, conf_state=conf, default_doh_url=cgs_cfg.doh.get_url())
        if issubclass(self.provider_descriptor.provider_cls, DomainUtils) and not gui_site_runtime.peek_cached_domain():
            gui_site_runtime.get_domain()
        self.site_config = gui_site_runtime.build_site_config()
        self.thread_site_runtime = ThreadSiteRuntime(self.provider_descriptor, site_config=self.site_config, conf_state=conf)

    async def __aenter__(self):
        self.thread_site_runtime.get_async_preview_client()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.thread_site_runtime.aclose()

    async def search(self, keyword: str, page: int = 1):
        return await self.thread_site_runtime.preview_search(keyword, page=page)

    async def fetch_episodes(self, book):
        return await self.thread_site_runtime.preview_fetch_episodes(book)

    async def fetch_pages(self, episode):
        return await self.thread_site_runtime.preview_fetch_pages(episode)

    async def fetch_cover_bytes(self, book):
        cover_url = getattr(book, "img_preview", None)
        if not cover_url:
            return b""
        title_url = getattr(book, "preview_url", None) or getattr(book, "url", None)
        return await self.thread_site_runtime.download_cover_bytes(SimpleNamespace(cover_url=cover_url, title_url=title_url))


class ServerRuntime:
    def __init__(
            self,
            *,
            ttl_seconds: int = 900,
            max_events: int = 500,
            max_active_jobs: int | None = None,
            max_pending_jobs: int | None = None,
            clock=time.time,
    ):
        self.sessions = ServerSessionCatalog(ttl_seconds=ttl_seconds, clock=clock)
        self.state = ServerRuntimeState(max_events=max_events)
        self._lock = threading.Lock()
        self._active_thread: threading.Thread | None = None
        self._active_threads: dict[str, threading.Thread] = {}
        self._active_job_sites: dict[str, int] = {}
        self._pending_jobs: deque[dict] = deque()
        self._max_active_jobs = (
            int(max_active_jobs)
            if max_active_jobs is not None
            else _configured_server_max_active_jobs()
        )
        if self._max_active_jobs <= 0:
            raise ValueError("max_active_jobs must be positive")
        self._max_pending_jobs = (
            int(max_pending_jobs)
            if max_pending_jobs is not None
            else _parse_positive_int(os.getenv("CGS_SERVER_MAX_PENDING_JOBS"), default=64)
        )
        if self._max_pending_jobs <= 0:
            raise ValueError("max_pending_jobs must be positive")
        self._spider_runtime: SpiderRuntimeThread | None = None
        self._runtime_event_thread: threading.Thread | None = None
        self._runtime_event_stop = threading.Event()
        self._runtime_event_runtime: SpiderRuntimeThread | None = None
        self._runtime_event_jobs: dict[str, SubmittedJobWaiter] = {}
        self.repairs = ServerRepairCatalog()
        self._foreground_mode = False
        self._shutting_down = False
        self.download_pages = _parse_download_pages(os.getenv("CGS_SERVER_DOWNLOAD_PAGES"))

    def health(self) -> dict:
        return {"ok": True, "server": "ComicGUISpider", "foreground_mode": self._foreground_mode}

    def list_supported_sites(self) -> list[dict]:
        return self.sessions.supported_sites_payload()

    async def search(self, site_index: int, keyword: str, page: int = 1) -> dict:
        self._require_server_available()
        site_index = self.sessions.require_direct_site(site_index)
        try:
            async with PreviewRuntime(site_index) as preview:
                books = list(await preview.search(keyword, page=int(page or 1)) or ())
        except ServerRuntimeError:
            raise
        except Exception as exc:
            raise ServerRuntimeError("search_failed", f"search failed: {exc}") from exc
        session_id, session, book_rows = self.sessions.create_search_session(site_index, books)
        await self._prepare_search_covers(site_index, book_rows)
        dto_books = [self.sessions.book_dto(book, book_key) for book, book_key in book_rows]
        with self._lock:
            self.sessions.store(session_id, session)
        return {"session_id": session_id, "page": int(page or 1), "books": dto_books}

    async def book_episodes(self, session_id: str, book_key: str) -> dict:
        self._require_server_available()
        with self._lock:
            session = self.sessions.get(session_id)
        normalized_book_key = str(book_key or "")
        book = session.books.get(normalized_book_key)
        if book is None:
            raise ServerRuntimeError("invalid_book_key", f"invalid book key: {book_key}")
        if self.sessions.book_select_mode(book) != "chapters":
            raise ServerRuntimeError("chapters_not_supported", f"book does not support chapter selection: {book_key}")
        if normalized_book_key not in session.episodes:
            episodes = getattr(book, "episodes", None)
            if not episodes:
                try:
                    async with PreviewRuntime(session.site_index) as preview:
                        episodes = await preview.fetch_episodes(book)
                except ServerRuntimeError:
                    raise
                except Exception as exc:
                    raise ServerRuntimeError("episodes_fetch_failed", f"episodes fetch failed: {exc}") from exc
            if not isinstance(episodes, list) or not episodes:
                title = getattr(book, "name", None) or normalized_book_key
                raise ServerRuntimeError("episodes_fetch_failed", f"episodes fetch failed for book: {title}")
            self.sessions.cache_episodes(session, normalized_book_key, book, episodes)
        return {
            "session_id": str(session_id),
            "book_key": normalized_book_key,
            "episodes": [
                self.sessions.episode_dto(episode, episode_key)
                for episode_key, episode in session.episode_keys[normalized_book_key].items()
            ],
        }

    def submit(self, session_id: str, book_keys: list[str] | None = None, episode_select=None, episode_selections=None) -> dict:
        self._require_server_available()
        with self._lock:
            session = self.sessions.get(session_id)
        normalized_book_keys = [str(book_key) for book_key in (book_keys or []) if str(book_key or "")]
        selected_episodes = self.sessions.selected_episodes(session, episode_selections)
        if not normalized_book_keys and not selected_episodes:
            raise ServerRuntimeError("invalid_payload", "book_keys or episode_selections must not be empty")
        books = []
        select = self.sessions.normalize_episode_select(episode_select)
        for book_key in normalized_book_keys:
            book = session.books.get(book_key)
            if book is None:
                raise ServerRuntimeError("invalid_book_key", f"invalid book key: {book_key}")
            books.append(book)

        submitted, _thread = self._start_payload_job(
            session.site_index, [*books, *selected_episodes], origin="http-submit", episode_select=select
        )
        return submitted

    def submit_payload(self, site_index: int, payload, *, origin: str = "server-owned") -> dict:
        items = list(payload) if isinstance(payload, (list, tuple)) else [payload]
        if not items:
            raise ServerRuntimeError("invalid_payload", "payload must not be empty")
        return self._start_payload_job(int(site_index), items, origin=origin)[0]

    def submit_payload_and_wait(self, site_index: int, payload, *, timeout_sec: int = 60, origin: str = "server-owned") -> bool:
        submitted, thread = self._start_payload_job(int(site_index), payload, origin=origin, enqueue_if_busy=False)
        timeout_sec = int(timeout_sec)
        if timeout_sec <= 0:
            raise ValueError("server runtime submit timeout_sec must be positive")
        thread.join(timeout=timeout_sec)
        job_id = submitted["job_id"]
        if thread.is_alive():
            raise TimeoutError(f"server-owned download job timed out after {timeout_sec}s: {job_id}")
        with self._lock:
            job = self.state.job_for(job_id)
        if job is None:
            raise RuntimeError(f"server-owned download job disappeared: {job_id}")
        if job.get("status") == "completed":
            return True
        if job.get("status") == "failed":
            raise RuntimeError(job.get("error") or f"server-owned download job failed: {job_id}")
        raise RuntimeError(f"server-owned download job ended in unexpected state {job.get('status')!r}: {job_id}")

    def _start_payload_job(
            self,
            site_index: int,
            payload,
            *,
            origin: str,
            episode_select: EpisodeSelect | None = None,
            enqueue_if_busy: bool = True,
    ) -> tuple[dict, threading.Thread | None]:
        self._require_server_available()
        books = list(payload) if isinstance(payload, (list, tuple)) else [payload]
        if not books:
            raise ServerRuntimeError("invalid_payload", "payload must not be empty")
        job_id = uuid4().hex
        with self._lock:
            self._prune_active_threads_locked()
            if not self._can_start_job_locked(int(site_index)):
                if not enqueue_if_busy:
                    raise ServerRuntimeError("job_running", "CGS job is already running")
                job = self._queue_payload_job_locked(job_id, site_index, books, origin, episode_select or EpisodeSelect())
                return {"submitted": True, "queued": True, "job_id": job_id, "job": job}, self._active_thread
            job, thread = self._start_payload_job_locked(job_id, site_index, books, origin, episode_select or EpisodeSelect())
            return {"submitted": True, "queued": False, "job_id": job_id, "job": job}, thread

    def _queue_payload_job_locked(
            self, job_id: str, site_index: int, books: list, origin: str, episode_select: EpisodeSelect
    ) -> dict:
        now = utc_now()
        if len(self._pending_jobs) >= self._max_pending_jobs:
            self.state.record_event({
                "type": "queue_rejected",
                "job_id": job_id,
                "timestamp": now,
                "origin": origin,
                "queue_depth": len(self._pending_jobs),
                "queue_capacity": self._max_pending_jobs,
            })
            raise ServerRuntimeError("queue_full", "CGS job queue is full")
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued_waiting_runtime",
            "progress": None,
            "task": None,
            "error": None,
            "error_code": None,
            "started_at": None,
            "updated_at": now,
            "finished_at": None,
            "origin": origin,
            "queued_at": now,
        }
        self._pending_jobs.append({
            "job_id": job_id,
            "site_index": int(site_index),
            "books": list(books),
            "origin": origin,
            "episode_select": episode_select,
            "job": dict(job),
        })
        self.state.record_event({"type": "queued", "job_id": job_id, "timestamp": now, "origin": origin, "queue_position": len(self._pending_jobs)})
        return job

    def _start_payload_job_locked(
            self, job_id: str, site_index: int, books: list, origin: str, episode_select: EpisodeSelect
    ) -> tuple[dict, threading.Thread]:
        job = self.state.start_job(job_id, origin=origin)
        self._active_thread = threading.Thread(
            target=self._run_submit_job, args=(job_id, site_index, books, episode_select),
            name="CGSServerSubmit", daemon=True,
        )
        self._active_threads[job_id] = self._active_thread
        self._active_job_sites[job_id] = int(site_index)
        self._active_thread.start()
        return job, self._active_thread

    def status(self) -> dict:
        with self._lock:
            payload = self.state.status(foreground_mode=self._foreground_mode)
            pending = self._pending_job_snapshots_locked()
            payload["queued_count"] = len(pending)
            payload["active_count"] = self._active_count_locked()
            payload["active_capacity"] = self._max_active_jobs
            payload["queue_capacity"] = self._max_pending_jobs
            payload["queue_available"] = max(0, self._max_pending_jobs - len(pending))
            payload["queue"] = pending
            return payload

    def events(self) -> dict:
        with self._lock:
            payload = self.state.event_payload()
            pending = self._pending_job_snapshots_locked()
            payload["queued_count"] = len(pending)
            payload["active_count"] = self._active_count_locked()
            payload["active_capacity"] = self._max_active_jobs
            payload["queue_capacity"] = self._max_pending_jobs
            payload["queue_available"] = max(0, self._max_pending_jobs - len(pending))
            payload["queue"] = pending
            return payload

    def diagnostics(self) -> dict:
        status = self.status()
        with self._lock:
            return self.state.diagnostics(status)

    def record_request_diagnostic(self, entry: dict) -> None:
        with self._lock:
            self.state.record_request_diagnostic(entry)

    def clear_request_diagnostics(self) -> int:
        with self._lock:
            return self.state.clear_request_diagnostics()

    def clear_server_errors(self) -> int:
        with self._lock:
            return self.state.clear_server_errors()

    def clear_work_history(self) -> dict:
        with self._lock:
            if self._has_active_or_queued_work_locked():
                raise ServerRuntimeError("job_running", "cannot clear CGS work history while a job is running")
            cleared = self.state.clear_work_history()
            self._active_thread = None
            self._active_threads.clear()
            self._active_job_sites.clear()
            self.repairs.clear()
        return {"cleared": cleared}

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
        with self._lock:
            self.state.record_server_error(
                summary, detail, source=source, code=code, method=method, path=path, status_code=status_code, exc=exc
            )

    def reset_work_state(self, *, origin: str = "http") -> dict:
        self._require_server_available()
        with self._lock:
            if self._has_active_or_queued_work_locked():
                raise ServerRuntimeError("job_running", "cannot reset CGS work state while a job is running")
            previous_job = dict(self.state.current_job) if self.state.current_job else None
            cleared = {"sessions": len(self.sessions), **self.state.clear_work_history()}
            self.sessions.clear()
            self._active_thread = None
            self._active_threads.clear()
            self._active_job_sites.clear()
            self.repairs.clear()
        return {
            "reset": True,
            "status": "idle",
            "configured": True,
            "available": True,
            "memory_persistent": True,
            "job": None,
            "previous_job": previous_job,
            "cleared": cleared,
            "origin": origin,
        }

    def enter_foreground(self) -> dict:
        with self._lock:
            if self._has_active_or_queued_work_locked():
                raise ServerRuntimeError("job_running", "cannot yield while CGS Server job is running")
            self._foreground_mode = True
        return self.status()

    def leave_foreground(self) -> dict:
        with self._lock:
            self._foreground_mode = False
        return self.status()

    def shutdown(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            self._shutting_down = True
            self._pending_jobs.clear()
            self._runtime_event_stop.set()
            spider_runtime = self._spider_runtime
            active_threads = list(self._active_threads.values())
            self._spider_runtime = None
        errors = []
        if spider_runtime is not None:
            spider_runtime.shutdown()
            spider_runtime.join(timeout=float(timeout))
            if spider_runtime.is_alive():
                errors.append("SpiderRuntimeThread did not stop")
        for active_thread in active_threads:
            if active_thread is not threading.current_thread() and active_thread.is_alive():
                active_thread.join(timeout=float(timeout))
                if active_thread.is_alive():
                    errors.append("active ServerRuntime submit thread did not stop")
        if errors:
            raise RuntimeError("; ".join(errors))

    def record_event(self, event: dict):
        with self._lock:
            self.state.record_event(event)
            self.repairs.apply_event(event)

    async def _prepare_search_covers(self, site_index: int, book_rows: list[tuple[object, str]]) -> None:
        rows = [(book, book_key) for book, book_key in book_rows if getattr(book, "img_preview", None)]
        if not rows:
            return
        async with PreviewRuntime(site_index) as preview:
            for book, book_key in rows:
                try:
                    data = await preview.fetch_cover_bytes(book)
                    cover_static_url = self._write_cover_file(book_key, data)
                except Exception as exc:
                    logger.exception(f"cover preload failed for {book_key}")
                    setattr(book, "cover_error", str(exc))
                    continue
                setattr(book, "cover_static_url", cover_static_url)

    async def _ensure_pages(self, site_index: int, books: list):
        missing = [book for book in books if getattr(book, "pages", None) is None]
        if not missing:
            return
        async with PreviewRuntime(site_index) as preview:
            for book in missing:
                page_urls = await preview.fetch_pages(book)
                if not isinstance(page_urls, list) or not page_urls:
                    title = getattr(book, "name", None) or getattr(book, "idx", "")
                    raise ServerRuntimeError("pages_fetch_failed", f"pages fetch failed for book: {title}")
                book.pages = len(page_urls)
                book.page_urls = list(page_urls)

    async def _prepare_submit_items(self, site_index: int, books: list, episode_select: EpisodeSelect | None = None) -> list:
        if Spider(int(site_index)) not in Spider.mangas():
            await self._ensure_pages(site_index, books)
            return list(books)
        select = episode_select or EpisodeSelect()
        prepared = []
        async with PreviewRuntime(site_index) as preview:
            for book in books:
                if self.sessions.is_episode_item(book):
                    from_book = getattr(book, "from_book", None)
                    prepared.append(await self._prepare_manga_episode_pages(preview, from_book, book))
                else:
                    prepared.extend(await self._manga_episode_submit_items(preview, book, select))
        return prepared

    async def _manga_episode_submit_items(self, preview: PreviewRuntime, book, episode_select: EpisodeSelect) -> list:
        if getattr(book, "page_urls", None):
            return [book]
        episodes = getattr(book, "episodes", None)
        if not episodes:
            episodes = await preview.fetch_episodes(book)
            if not isinstance(episodes, list) or not episodes:
                title = getattr(book, "name", None) or getattr(book, "idx", "")
                raise ServerRuntimeError("episodes_fetch_failed", f"episodes fetch failed for book: {title}")
            book.episodes = episodes
        selected = self.sessions.select_manga_episodes(episodes, episode_select)
        prepared = []
        for episode in selected:
            prepared.append(await self._prepare_manga_episode_pages(preview, book, episode))
        return prepared

    async def _prepare_manga_episode_pages(self, preview: PreviewRuntime, book, episode):
        if getattr(episode, "from_book", None) is None:
            episode.from_book = book
        if not getattr(episode, "page_urls", None):
            page_urls = await preview.fetch_pages(episode)
            if not isinstance(page_urls, list) or not page_urls:
                title = getattr(episode, "display_title", None) or getattr(episode, "name", None) or getattr(book, "name", "")
                raise ServerRuntimeError("pages_fetch_failed", f"pages fetch failed for book: {title}")
            episode.page_urls = list(page_urls)
            episode.pages = len(page_urls)
        return episode

    def _run_submit_job(self, job_id: str, site_index: int, books: list, episode_select: EpisodeSelect):
        try:
            submit_items = asyncio.run(self._prepare_submit_items(site_index, books, episode_select))
            self._apply_download_pages(submit_items)
            with self._lock:
                self.repairs.register(job_id, site_index, submit_items)
            payload = submit_items[0] if len(submit_items) == 1 else submit_items
            import ComicSpider.settings as spider_settings

            spider_settings.SV_PATH = conf.sv_path
            runtime = self._ensure_spider_runtime()
            job, waiter = build_submitted_download_job(site_index, payload, job_id=job_id, event_sink=ServerEventSink(job_id, self))
            self._register_runtime_waiter(runtime, waiter)
            logger.info(f"[submit] spider={job.spider_name} job={job.job_id}")
            runtime.submit_job(job)
            success = waiter.wait(runtime)
            if not success:
                raise ServerRuntimeError("download_submit_failed", "download submit failed")
            self._mark_completed_if_needed(job_id)
        except ServerRuntimeError as exc:
            self._mark_failed(job_id, exc.message, exc.code)
        except Exception as exc:
            logger.exception(exc)
            self._mark_failed(job_id, f"download submit failed: {exc}", "download_submit_failed")
        finally:
            self._unregister_runtime_waiter(job_id)
            self._start_next_queued_job(job_id)

    def reset_spider_runtime(self) -> None:
        """Drop the long-lived Scrapy runtime after config changes.

        Scrapy settings are captured when the runtime thread starts, so updates
        such as /conf sv_path must force the next submit to create a fresh
        runtime with current download settings.
        """
        with self._lock:
            runtime = self._spider_runtime
            self._spider_runtime = None
            self._runtime_event_stop.set()
            event_thread = self._runtime_event_thread
            self._runtime_event_thread = None
            self._runtime_event_runtime = None
            self._runtime_event_jobs.clear()
        if event_thread is not None and event_thread is not threading.current_thread() and event_thread.is_alive():
            event_thread.join(timeout=2)
        if runtime is not None and runtime.is_alive():
            runtime.shutdown()
            runtime.join(timeout=5)

    def _ensure_spider_runtime(self) -> SpiderRuntimeThread:
        with self._lock:
            runtime = self._spider_runtime
            if runtime is None or not runtime.is_alive():
                runtime = SpiderRuntimeThread()
                runtime.daemon = True
                runtime.start()
                self._spider_runtime = runtime
        runtime.wait_ready(timeout=30)
        self._ensure_runtime_event_dispatcher(runtime)
        return runtime

    def _mark_failed(self, job_id: str, message: str, code: str):
        with self._lock:
            event = self.state.mark_failed(job_id, message, code)
            self.repairs.apply_event(event)

    def _mark_completed_if_needed(self, job_id: str):
        with self._lock:
            event = self.state.mark_completed_if_needed(job_id)
            if event is not None:
                self.repairs.apply_event(event)

    def repair_missing_pages(self, job_id: str | None = None) -> dict:
        self._require_server_available()
        with self._lock:
            if self._has_active_or_queued_work_locked():
                raise ServerRuntimeError("job_running", "CGS job is already running")
            current_job = dict(self.state.current_job) if self.state.current_job else None
            if current_job is None:
                raise ServerRuntimeError("missing_job", "missing CGS job to repair")
            target_job_id = str(job_id or current_job.get("job_id") or "").strip()
            if not target_job_id:
                raise ServerRuntimeError("missing_job", "missing CGS job to repair")
            if target_job_id != current_job.get("job_id"):
                raise ServerRuntimeError("invalid_job", f"invalid repair job id: {target_job_id}")
            site_index, repair_items, repairs = self.repairs.repair_plan(target_job_id)
        submitted, _thread = self._start_payload_job(site_index, repair_items, origin="http-repair")
        return {**submitted, "repairs": repairs}

    def _has_active_or_queued_work_locked(self) -> bool:
        self._prune_active_threads_locked()
        return bool(self._active_threads or self._pending_jobs)

    def _pending_job_snapshots_locked(self) -> list[dict]:
        return [dict(item["job"], queue_position=index) for index, item in enumerate(self._pending_jobs, start=1)]

    def _start_next_queued_job(self, finished_job_id: str) -> None:
        with self._lock:
            self._active_threads.pop(str(finished_job_id), None)
            self._active_job_sites.pop(str(finished_job_id), None)
            self._start_queued_jobs_locked()

    def _start_queued_jobs_locked(self) -> None:
        self._prune_active_threads_locked()
        while self._pending_jobs and not self._foreground_mode and not self._shutting_down:
            pending = self._pending_jobs[0]
            if not self._can_start_job_locked(int(pending["site_index"])):
                return
            pending = self._pending_jobs.popleft()
            job, _thread = self._start_payload_job_locked(
                str(pending["job_id"]), int(pending["site_index"]), list(pending["books"]), str(pending["origin"]), pending["episode_select"]
            )
            job["queued_at"] = pending["job"].get("queued_at")
            if self.state.current_job:
                self.state.current_job["queued_at"] = pending["job"].get("queued_at")
            self.state.record_event({
                "type": "dequeued", "job_id": pending["job_id"], "timestamp": utc_now(), "origin": pending["origin"],
                "remaining_queue": len(self._pending_jobs),
            })

    def _active_count_locked(self) -> int:
        self._prune_active_threads_locked()
        return len(self._active_threads)

    def _prune_active_threads_locked(self) -> None:
        finished = [job_id for job_id, thread in self._active_threads.items() if not thread.is_alive()]
        for job_id in finished:
            self._active_threads.pop(job_id, None)
            self._active_job_sites.pop(job_id, None)

    def _can_start_job_locked(self, site_index: int) -> bool:
        active_count = self._active_count_locked()
        if active_count <= 0:
            return True
        if site_index == Spider.MANGA_COPY:
            return False
        if any(active_site == Spider.MANGA_COPY for active_site in self._active_job_sites.values()):
            return False
        return active_count < self._max_active_jobs

    def _register_runtime_waiter(self, runtime: SpiderRuntimeThread, waiter: SubmittedJobWaiter) -> None:
        self._ensure_runtime_event_dispatcher(runtime)
        with self._lock:
            self._runtime_event_jobs[waiter.job_id] = waiter

    def _unregister_runtime_waiter(self, job_id: str) -> None:
        with self._lock:
            self._runtime_event_jobs.pop(str(job_id), None)

    def _ensure_runtime_event_dispatcher(self, runtime: SpiderRuntimeThread) -> None:
        with self._lock:
            if (
                    self._runtime_event_runtime is runtime
                    and self._runtime_event_thread is not None
                    and self._runtime_event_thread.is_alive()
            ):
                return
            self._runtime_event_stop.set()
            self._runtime_event_stop = threading.Event()
            self._runtime_event_runtime = runtime
            self._runtime_event_thread = threading.Thread(
                target=self._dispatch_runtime_events,
                args=(runtime, self._runtime_event_stop),
                name="CGSServerRuntimeEvents",
                daemon=True,
            )
            self._runtime_event_thread.start()

    def _dispatch_runtime_events(self, runtime: SpiderRuntimeThread, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                event = runtime.event_q.get(timeout=0.2)
            except queue.Empty:
                if not runtime.is_alive():
                    return
                continue
            event_job_id = getattr(event, "job_id", None)
            with self._lock:
                if event_job_id:
                    waiter = self._runtime_event_jobs.get(str(event_job_id))
                elif len(self._runtime_event_jobs) == 1:
                    waiter = next(iter(self._runtime_event_jobs.values()))
                else:
                    waiter = None
            if waiter is not None:
                waiter.observe(event)

    def _require_server_available(self):
        if self._foreground_mode:
            raise ServerRuntimeError("foreground_active", "CGS GUI foreground owns runtime")

    def _apply_download_pages(self, books: list):
        if not self.download_pages:
            return
        pages = tuple(self.download_pages)
        for book in books:
            self._apply_download_pages_to_item(book, pages)
            for episode in list(getattr(book, "episodes", None) or []):
                self._apply_download_pages_to_item(episode, pages)

    def _apply_download_pages_to_item(self, item, pages: tuple[int, ...]):
        total_pages = _known_page_count(item)
        target_pages = [page for page in pages if total_pages is None or page <= total_pages]
        if not target_pages:
            title = getattr(item, "display_title", None) or getattr(item, "name", None) or repr(item)
            raise ServerRuntimeError("invalid_download_pages", f"download pages are outside available pages for {title}")
        setattr(item, "download_pages", list(target_pages))
        setattr(item, "page_name_count", len(target_pages))

    def _write_cover_file(self, book_key: str, data: bytes) -> str:
        if not data:
            raise ValueError("cover response is empty")
        cover_dir = temp_p.joinpath("cover")
        cover_dir.mkdir(exist_ok=True)
        filename = f"{book_key}{_cover_extension(data)}"
        cover_dir.joinpath(filename).write_bytes(data)
        return f"/cover/{quote(filename)}"

def _parse_download_pages(value: str | None) -> list[int]:
    if not value:
        return []
    pages: set[int] = set()
    for chunk in str(value).replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_raw, end_raw = chunk.split("-", 1)
            start = int(start_raw.strip())
            end = int(end_raw.strip())
            if start < 1 or end < start:
                raise ValueError(f"invalid CGS_SERVER_DOWNLOAD_PAGES range: {chunk!r}")
            pages.update(range(start, end + 1))
            continue
        page = int(chunk)
        if page < 1:
            raise ValueError(f"invalid CGS_SERVER_DOWNLOAD_PAGES page: {chunk!r}")
        pages.add(page)
    return sorted(pages)


def _parse_positive_int(value: str | None, *, default: int) -> int:
    if value is None or not str(value).strip():
        return int(default)
    result = int(str(value).strip())
    if result <= 0:
        raise ValueError("value must be positive")
    return result


def _configured_server_max_active_jobs() -> int:
    return _parse_positive_int(
        os.getenv("CGS_SERVER_MAX_ACTIVE_JOBS"),
        default=_parse_positive_int(str(conf.concurr_num), default=1),
    )


def _known_page_count(item) -> int | None:
    for attr in ("pages", "page_urls", "pics", "page_links"):
        value = getattr(item, attr, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            count = len(value)
        else:
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
        if count > 0:
            return count
    return None


def _cover_extension(data: bytes) -> str:
    head = bytes(data[:32])
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return ".gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return ".webp"
    if b"ftypavif" in head:
        return ".avif"
    if head.lstrip().startswith((b"<svg", b"<?xml")):
        return ".svg"
    return ".jpg"


runtime = ServerRuntime()
