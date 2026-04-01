import asyncio
import traceback
from copy import deepcopy
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Union

import httpx
from PySide6.QtCore import QThread, Signal

from GUI.types import SearchContextSnapshot
from utils.website.registry import resolve_site_gateway


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


@dataclass(frozen=True, slots=True)
class PagesBatchTask:
    items: list


PreviewTask = Union[SearchTask, EpisodesTask, EpisodesBatchTask, PagesBatchTask]


class PreviewWorker(QThread):
    search_done = Signal(int, str, int, object)
    search_error = Signal(int, str, int, str)
    episodes_done = Signal(int, int, str, object)
    episodes_error = Signal(int, int, str, str)
    pages_done = Signal(int, str, object)
    pages_error = Signal(int, str, str)

    def __init__(self, gui=None, *, snapshot: SearchContextSnapshot, generation: int):
        super().__init__(gui)
        self.gui = gui
        self._active = True
        self._task_queue = Queue()
        self._generation = generation
        self._snapshot = self._copy_snapshot(snapshot)
        self.site_clients: dict[int, httpx.AsyncClient] = {}
        self._loop = None

    def stop(self):
        self._active = False
        self._task_queue.put(None)

    @staticmethod
    def _copy_snapshot(snapshot: SearchContextSnapshot) -> SearchContextSnapshot:
        return SearchContextSnapshot(
            site_index=snapshot.site_index,
            proxies=list(snapshot.proxies),
            cookies=deepcopy(snapshot.cookies),
            domains=dict(snapshot.domains),
            custom_map=deepcopy(snapshot.custom_map),
            doh_url=snapshot.doh_url,
        )

    def update_snapshot(self, snapshot: SearchContextSnapshot):
        self._snapshot = self._copy_snapshot(snapshot)

    def enqueue_search(self, keyword, site_index, page=1):
        self._task_queue.put(SearchTask(keyword, site_index, page))

    def enqueue_episodes(self, session_id, book_key, book, site_index):
        self._task_queue.put(EpisodesTask(session_id, book_key, book, site_index))

    def enqueue_episodes_batch(self, items):
        if items:
            self._task_queue.put(EpisodesBatchTask(items))

    def enqueue_pages_batch(self, items):
        if items:
            self._task_queue.put(PagesBatchTask(items))

    def _build_site_config(self, gateway):
        return gateway.build_site_config_from_snapshot(self._snapshot)

    def _get_client(self, site_index):
        if cli := self.site_clients.get(site_index):
            return cli
        gateway = self._get_gateway(site_index)
        site_config = self._build_site_config(gateway)
        cli = gateway.create_async_preview_client(site_config=site_config)
        self.site_clients[site_index] = cli
        return cli

    @staticmethod
    def _get_gateway(site_index):
        return resolve_site_gateway(site_index)

    async def _do_search(self, keyword, site_index, page=1):
        gateway = self._get_gateway(site_index)
        site_config = self._build_site_config(gateway)
        return await gateway.preview_search(
            keyword,
            self._get_client(site_index),
            page=page,
            site_config=site_config,
        )

    async def _do_fetch_episodes(self, book, site_index):
        gateway = self._get_gateway(site_index)
        site_config = self._build_site_config(gateway)
        return await gateway.preview_fetch_episodes(
            book,
            self._get_client(site_index),
            site_config=site_config,
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

    async def _do_fetch_pages_batch(self, items):
        sem = asyncio.Semaphore(2)

        async def _fetch_one(book_key, episode, site_index):
            async with sem:
                gateway = self._get_gateway(site_index)
                site_config = self._build_site_config(gateway)
                await gateway.preview_fetch_pages(
                    episode,
                    self._get_client(site_index),
                    site_config=site_config,
                )

        grouped = {}
        for book_key, episode, site_index in items:
            grouped.setdefault(book_key, []).append((episode, site_index))

        async def _fetch_book(book_key, ep_list):
            try:
                await asyncio.gather(
                    *[_fetch_one(book_key, ep, si) for ep, si in ep_list]
                )
                episodes = [ep for ep, _ in ep_list]
                self.pages_done.emit(self._generation, book_key, episodes)
            except Exception:
                self.pages_error.emit(self._generation, book_key, traceback.format_exc())

        await asyncio.gather(
            *[_fetch_book(bk, eps) for bk, eps in grouped.items()]
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
                        case PagesBatchTask(items=its):
                            self._loop.run_until_complete(
                                self._do_fetch_pages_batch(its)
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
