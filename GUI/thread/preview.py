import asyncio
import traceback
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Union

import httpx
from PySide6.QtCore import QThread, Signal

from GUI.types import SearchContextSnapshot
from utils.website.core import Previewer, build_proxy_transport
from utils.website.registry import spider_utils_map


@dataclass(frozen=True, slots=True)
class SearchTask:
    keyword: str
    site_index: int
    page: int = 1


@dataclass(frozen=True, slots=True)
class EpisodesTask:
    session_id: int
    book_key: str
    book: object
    site_index: int


@dataclass(frozen=True, slots=True)
class EpisodesBatchTask:
    items: list


PreviewTask = Union[SearchTask, EpisodesTask, EpisodesBatchTask]


class PreviewWorker(QThread):
    search_done = Signal(int, str, int, object)
    search_error = Signal(int, str, int, str)
    episodes_done = Signal(int, int, str, object)
    episodes_error = Signal(int, int, str, str)

    def __init__(self, parent=None, *, snapshot: SearchContextSnapshot, generation: int):
        super().__init__(parent)
        self._active = True
        self._task_queue = Queue()
        self._generation = generation
        self._proxies = list(snapshot.proxies)
        self._cookies = dict(snapshot.cookies)
        self._domains = dict(snapshot.domains)
        self.site_clients: dict[int, httpx.AsyncClient] = {}
        self._loop = None

    def stop(self):
        self._active = False
        self._task_queue.put(None)

    def update_snapshot(self, snapshot: SearchContextSnapshot):
        self._proxies = list(snapshot.proxies)
        self._cookies = dict(snapshot.cookies)
        self._domains = dict(snapshot.domains)

    def enqueue_search(self, keyword, site_index, page=1):
        self._task_queue.put(SearchTask(keyword, site_index, page))

    def enqueue_episodes(self, session_id, book_key, book, site_index):
        self._task_queue.put(EpisodesTask(session_id, book_key, book, site_index))

    def enqueue_episodes_batch(self, items):
        if items:
            self._task_queue.put(EpisodesBatchTask(items))

    def _build_site_context(self, preview_cls):
        context = {}
        if preview_cls.name in self._cookies:
            context["cookies"] = self._cookies[preview_cls.name]
        if preview_cls.name in self._domains:
            context["domain"] = self._domains[preview_cls.name]
        return context

    def _get_client(self, site_index):
        if cli := self.site_clients.get(site_index):
            return cli
        preview_cls = self._get_preview_cls(site_index)
        site_kw = preview_cls.preview_client_config(**self._build_site_context(preview_cls))
        policy = getattr(preview_cls, "proxy_policy", "proxy")
        verify = site_kw.pop("verify", True)
        transport, trust_env = build_proxy_transport(policy, self._proxies, verify=verify)
        base_kw = dict(
            transport=transport,
            follow_redirects=True,
            trust_env=trust_env, headers=None
        )
        base_kw.update(site_kw)
        cli = httpx.AsyncClient(**base_kw)
        self.site_clients[site_index] = cli
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
        return await preview_cls.preview_search(
            keyword,
            cli,
            page=page,
            **self._build_site_context(preview_cls),
        )

    async def _do_fetch_episodes(self, book, site_index):
        preview_cls = self._get_preview_cls(site_index)
        return await preview_cls.preview_fetch_episodes(
            book,
            self._get_client(site_index),
            **self._build_site_context(preview_cls),
        )

    async def _do_fetch_episodes_batch(self, items):
        sem = asyncio.Semaphore(4)

        async def _fetch_one(session_id, book_key, book, site_index):
            async with sem:
                try:
                    episodes = await self._do_fetch_episodes(book, site_index)
                    self.episodes_done.emit(self._generation, session_id, book_key, episodes)
                except Exception:
                    self.episodes_error.emit(self._generation, session_id, book_key, traceback.format_exc())

        await asyncio.gather(
            *[_fetch_one(sid, bk, b, si) for sid, bk, b, si in items]
        )

    async def _close_clients(self):
        for cli in self.site_clients.values():
            await cli.aclose()
        self.site_clients.clear()

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
                            self.search_done.emit(self._generation, kw, si, books)
                        case EpisodesTask(session_id=sid, book_key=bk, book=b, site_index=si):
                            episodes = self._loop.run_until_complete(
                                self._do_fetch_episodes(b, si)
                            )
                            self.episodes_done.emit(self._generation, sid, bk, episodes)
                        case EpisodesBatchTask(items=its):
                            self._loop.run_until_complete(
                                self._do_fetch_episodes_batch(its)
                            )
                except Exception:
                    err = traceback.format_exc()
                    match task:
                        case SearchTask(keyword=kw, site_index=si):
                            self.search_error.emit(self._generation, kw, si, err)
                        case EpisodesTask(session_id=sid, book_key=bk):
                            self.episodes_error.emit(self._generation, sid, bk, err)
                        case _:
                            self.search_error.emit(self._generation, "", -1, err)
        finally:
            try:
                self._loop.run_until_complete(self._close_clients())
            except Exception:
                pass
            finally:
                self._loop.close()
