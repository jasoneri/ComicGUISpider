import asyncio
import traceback
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Union

import httpx
from PyQt5.QtCore import QThread, pyqtSignal

from utils import conf
from utils.website.core import Previewer, build_proxy_transport
from utils.website.registry import spider_utils_map


@dataclass(frozen=True, slots=True)
class SearchTask:
    keyword: str
    site_index: int
    page: int = 1


@dataclass(frozen=True, slots=True)
class EpisodesTask:
    book_key: str
    book: object
    site_index: int


@dataclass(frozen=True, slots=True)
class EpisodesBatchTask:
    items: list


PreviewTask = Union[SearchTask, EpisodesTask, EpisodesBatchTask]


class PreviewWorker(QThread):
    search_done = pyqtSignal(str, int, object)
    search_error = pyqtSignal(str, int, str)
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
        self._task_queue.put(SearchTask(keyword, site_index, page))

    def enqueue_episodes(self, book_key, book, site_index):
        self._task_queue.put(EpisodesTask(book_key, book, site_index))

    def enqueue_episodes_batch(self, items):
        if items:
            self._task_queue.put(EpisodesBatchTask(items))

    def _get_client(self, site_index):
        if cli := self._site_clients.get(site_index):
            return cli
        preview_cls = self._get_preview_cls(site_index)
        site_kw = preview_cls.preview_client_config()
        policy = getattr(preview_cls, "proxy_policy", "proxy")
        verify = site_kw.pop("verify", True)
        transport, trust_env = build_proxy_transport(policy, conf.proxies, verify=verify)
        base_kw = dict(
            transport=transport,
            follow_redirects=True,
            trust_env=trust_env, headers=None
        )
        base_kw.update(site_kw)
        cli = httpx.AsyncClient(**base_kw)
        self._site_clients[site_index] = cli
        return cli

    @staticmethod
    def _get_preview_cls(site_index):
        cls = spider_utils_map.get(site_index)
        if cls is None:
            raise ValueError(f"unsupported site index: {site_index}")
        if not issubclass(cls, Previewer):
            raise TypeError(f"{cls.__name__} does not support Previewer")
        return cls

    async def _do_search(self, keyword, site_index, page=1):
        preview_cls = self._get_preview_cls(site_index)
        cli = self._get_client(site_index)
        return await preview_cls.preview_search(keyword, cli, page=page)

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
                try:
                    match task:
                        case SearchTask(keyword=kw, site_index=si, page=pg):
                            books = self._loop.run_until_complete(
                                self._do_search(kw, si, page=pg)
                            )
                            self.search_done.emit(kw, si, books)
                        case EpisodesTask(book_key=bk, book=b, site_index=si):
                            episodes = self._loop.run_until_complete(
                                self._do_fetch_episodes(b, si)
                            )
                            self.episodes_done.emit(bk, episodes)
                        case EpisodesBatchTask(items=its):
                            self._loop.run_until_complete(
                                self._do_fetch_episodes_batch(its)
                            )
                except Exception:
                    err = traceback.format_exc()
                    match task:
                        case SearchTask(keyword=kw, site_index=si):
                            self.search_error.emit(kw, si, err)
                        case EpisodesTask(book_key=bk):
                            self.episodes_error.emit(bk, err)
                        case _:
                            self.search_error.emit("", -1, err)
        finally:
            try:
                self._loop.run_until_complete(self._close_clients())
            except Exception:
                pass
            finally:
                self._loop.close()
