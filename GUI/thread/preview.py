import asyncio
from dataclasses import dataclass
from queue import Empty, Queue
import traceback
from typing import Union

from PySide6.QtCore import QThread, Signal

from utils.website.info import Episode
from utils.website import ThreadSiteRuntime


@dataclass(frozen=True, slots=True)
class SearchTask:
    keyword: str
    page: int = 1


@dataclass(frozen=True, slots=True)
class EpisodesTask:
    session_id: int
    book_key: str
    book: object


@dataclass(frozen=True, slots=True)
class EpisodesBatchTask:
    items: list


@dataclass(frozen=True, slots=True)
class PagesBatchTask:
    items: list


@dataclass(frozen=True, slots=True)
class CoverTask:
    task_id: str
    tasks_obj: object
    browser_headers: dict[str, str] | None = None


PreviewTask = Union[SearchTask, EpisodesTask, EpisodesBatchTask, PagesBatchTask, CoverTask]


class PreviewWorker(QThread):
    search_done = Signal(int, str, int, object)
    search_error = Signal(int, str, int, str)
    episodes_done = Signal(int, int, str, object)
    episodes_error = Signal(int, int, str, str)
    pages_done = Signal(int, str, object)
    cover_done = Signal(int, str, object)
    cover_error = Signal(int, str, str)

    def __init__(self, gui=None, *, thread_site_runtime: ThreadSiteRuntime, generation: int):
        super().__init__(gui)
        self.gui = gui
        self._active = True
        self._task_queue = Queue()
        self._generation = generation
        self.thread_site_runtime = thread_site_runtime
        self.site_index = thread_site_runtime.site_index
        self._loop = None

    def stop(self):
        self._active = False
        self._task_queue.put(None)

    def enqueue(self, _type, *args, **kw):
        match _type:
            case 'search': 
                _ = SearchTask
            case 'episodes': 
                _ = EpisodesTask
            case 'episodes_batch': 
                _ = EpisodesBatchTask
            case 'pages_batch': 
                _ = PagesBatchTask
            case 'cover': 
                _ = CoverTask
        self._task_queue.put(_(*args, **kw))

    async def _do_fetch_episodes_batch(self, items):
        semaphore = asyncio.Semaphore(self.thread_site_runtime.preview_batch_limit("episodes", 4))

        async def _fetch_one(session_id, book_key, book):
            async with semaphore:
                try:
                    episodes = await self.thread_site_runtime.preview_fetch_episodes(book)
                except Exception as exc:
                    return self.episodes_error.emit(self._generation, session_id, book_key, str(exc))
                self.episodes_done.emit(self._generation, session_id, book_key, episodes)

        await asyncio.gather(*[_fetch_one(sid, bk, b) for sid, bk, b in items])

    async def _do_fetch_pages_batch(self, items):
        semaphore = asyncio.Semaphore(self.thread_site_runtime.preview_batch_limit("pages", 2))

        async def _fetch_one(book_key, item):
            async with semaphore:
                page_urls = await self.thread_site_runtime.preview_fetch_pages(item)
                if isinstance(page_urls, list):
                    item.pages = len(page_urls)
                    item.page_urls = list(page_urls)

        grouped = {}
        for book_key, episode in items:
            grouped.setdefault(book_key, []).append(episode)

        async def _fetch_book(book_key, episodes):
            await asyncio.gather(*[_fetch_one(book_key, ep) for ep in episodes])
            self.pages_done.emit(self._generation, book_key, episodes)

        await asyncio.gather(*[_fetch_book(bk, eps) for bk, eps in grouped.items()])

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            while self._active:
                try:
                    task = self._task_queue.get(timeout=0.12)
                except Empty:
                    continue
                if task is None:
                    continue
                match task:
                    case SearchTask(keyword=kw, page=pg):
                        try:
                            books = self._loop.run_until_complete(self.thread_site_runtime.preview_search(kw, page=pg))
                        except Exception as exc:
                            self.thread_site_runtime.invalidate_domain_cache(exc)
                            self.search_error.emit(self._generation, kw, self.site_index, f"任务执行 > {exc}\n{traceback.format_exc()}")
                            continue
                        self.search_done.emit(self._generation, kw, self.site_index, books)
                    case EpisodesTask(session_id=sid, book_key=bk, book=b):
                        try:
                            episodes = self._loop.run_until_complete(self.thread_site_runtime.preview_fetch_episodes(b))
                        except Exception as exc:
                            self.episodes_error.emit(self._generation, sid, bk, str(exc))
                            continue
                        self.episodes_done.emit(self._generation, sid, bk, episodes)
                    case EpisodesBatchTask(items=its):
                        try:
                            self._loop.run_until_complete(self._do_fetch_episodes_batch(its))
                        except Exception as exc:
                            self.search_error.emit(
                                self._generation, "episodes_batch", self.site_index,
                                f"任务执行 > {exc}\n{traceback.format_exc()}",
                            )
                    case PagesBatchTask(items=its):
                        self._loop.run_until_complete(self._do_fetch_pages_batch(its))
                    case CoverTask(task_id=tid, tasks_obj=tasks_obj, browser_headers=headers):
                        try:
                            data = self._loop.run_until_complete(
                                self.thread_site_runtime.download_cover_bytes(tasks_obj, browser_headers=headers)
                            )
                        except Exception as exc:
                            self.cover_error.emit(self._generation, tid, f"任务执行 > {exc}\n{traceback.format_exc()}")
                        else:
                            self.cover_done.emit(self._generation, tid, data)
        finally:
            try:
                self._loop.run_until_complete(self.thread_site_runtime.aclose())
            finally:
                self._loop.close()
