import asyncio
import traceback
from queue import Empty, Queue

import httpx
from PyQt5.QtCore import QThread, pyqtSignal

from utils import conf
from utils.website.core import MangaPreview
from utils.website.registry import spider_utils_map


class MangaPreviewWorker(QThread):
    search_done = pyqtSignal(str, int, object)
    search_error = pyqtSignal(str)
    episodes_done = pyqtSignal(str, object)
    episodes_error = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = True
        self._task_queue = Queue()
        self._site_clients: dict[int, httpx.AsyncClient] = {}
        self._loop = None

    def stop(self):
        self._active = False
        self._task_queue.put(None)

    def enqueue_search(self, keyword, site_index, page=1):
        self._task_queue.put(("search", keyword, site_index, page))

    def enqueue_episodes(self, book_key, book, site_index):
        self._task_queue.put(("episodes", book_key, book, site_index))

    def enqueue_episodes_batch(self, items):
        if items:
            self._task_queue.put(("episodes_batch", items))

    @staticmethod
    def _build_transport():
        if conf.proxies:
            return httpx.AsyncHTTPTransport(proxy=f"http://{conf.proxies[0]}", retries=3)
        return httpx.AsyncHTTPTransport(retries=2)

    def _get_client(self, site_index):
        if cli := self._site_clients.get(site_index):
            return cli
        transport = self._build_transport()
        cli = httpx.AsyncClient(
            transport=transport,
            follow_redirects=True,
            trust_env=not bool(conf.proxies),
        )
        self._site_clients[site_index] = cli
        return cli

    @staticmethod
    def _get_preview_cls(site_index):
        cls = spider_utils_map.get(site_index)
        if cls is None:
            raise ValueError(f"unsupported site index: {site_index}")
        if not issubclass(cls, MangaPreview):
            raise TypeError(f"{cls.__name__} does not support MangaPreview")
        return cls

    async def _do_search(self, keyword, site_index, page=1):
        preview_cls = self._get_preview_cls(site_index)
        return await preview_cls.preview_search(keyword, self._get_client(site_index), page=page)

    async def _do_fetch_episodes(self, book, site_index):
        preview_cls = self._get_preview_cls(site_index)
        return await preview_cls.preview_fetch_episodes(book, self._get_client(site_index))

    async def _do_fetch_episodes_batch(self, items):
        sem = asyncio.Semaphore(4)

        async def _fetch_one(book_key, book, site_index):
            async with sem:
                try:
                    episodes = await self._do_fetch_episodes(book, site_index)
                    self.episodes_done.emit(book_key, episodes)
                except Exception:
                    self.episodes_error.emit(book_key, traceback.format_exc())

        await asyncio.gather(
            *[_fetch_one(bk, b, si) for bk, b, si in items]
        )

    async def _close_clients(self):
        for cli in self._site_clients.values():
            await cli.aclose()
        self._site_clients.clear()

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
                task_type = task[0]
                try:
                    if task_type == "search":
                        _, keyword, site_index, page = task
                        books = self._loop.run_until_complete(
                            self._do_search(keyword, site_index, page=page)
                        )
                        self.search_done.emit(keyword, site_index, books)
                    elif task_type == "episodes":
                        _, book_key, book, site_index = task
                        episodes = self._loop.run_until_complete(
                            self._do_fetch_episodes(book, site_index)
                        )
                        self.episodes_done.emit(book_key, episodes)
                    elif task_type == "episodes_batch":
                        _, items = task
                        self._loop.run_until_complete(
                            self._do_fetch_episodes_batch(items)
                        )
                except Exception:
                    err = traceback.format_exc()
                    if task_type == "episodes":
                        self.episodes_error.emit(task[1], err)
                    else:
                        self.search_error.emit(err)
        finally:
            try:
                self._loop.run_until_complete(self._close_clients())
            except Exception:
                pass
            finally:
                self._loop.close()
