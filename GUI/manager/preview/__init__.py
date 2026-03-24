import contextlib

from GUI.core.font import font_color
from GUI.types import GUIFlowStage, SearchContextSnapshot, SearchLifecycleState
from GUI.thread.preview import PreviewWorker
from GUI.manager.preview.manga import MangaPreviewFeature
from GUI.manager.preview.ero import EroPreviewFeature
from assets import res as ori_res
from utils import select
from variables import SPIDERS, Spider


class PreviewMgr:
    def __init__(self, gui):
        self.gui = gui
        self.site_index = 0
        self.search_context: SearchContextSnapshot | None = None
        self.books_cache = {}
        self._worker = None
        self._generation = 0
        self._session_id = 0
        self._current_page = 1
        self._target_page = None
        self._active_keyword = ""
        self._is_local_mode = False
        self._manga = MangaPreviewFeature(self)
        self._ero = EroPreviewFeature(self)
        self.gui.destroyed.connect(self._stop_worker)

    @property
    def is_manga(self):
        return self.site_index in Spider.mangas()

    @property
    def is_pageable(self):
        return self.site_index in SPIDERS and not self._is_local_mode

    @property
    def worker(self):
        return self._worker

    @property
    def _active(self):
        return self._manga if self.is_manga else self._ero

    @property
    def episodes_cache(self):
        return self._manga.episodes_cache

    def shutdown(self):
        self._generation += 1
        self.search_context = None
        self._active_keyword = ""
        self._manga.shutdown()
        self._stop_worker()

    def handle_choosebox_changed(self, index, snapshot: SearchContextSnapshot | None):
        self._generation += 1
        self.site_index = index
        self.search_context = snapshot
        self._session_id = 0
        self._active_keyword = ""
        self._manga.check_lc_completer()
        self._is_local_mode = False
        self._current_page = 1
        self._target_page = None
        self.books_cache.clear()
        self._manga.episodes_cache.clear()
        self._manga._inflight_books.clear()
        self.gui.pageEdit.setValue(1)
        self._active.reset()
        if index in SPIDERS and snapshot is not None:
            self.create_worker(snapshot)
        else:
            self._stop_worker()
        self.gui.refresh_lifecycle_state()

    def update_search_context(self, snapshot: SearchContextSnapshot):
        self.search_context = snapshot
        if self._worker:
            self._worker.update_snapshot(snapshot)

    def on_spreview_clicked(self, keyword=None):
        keyword = keyword or self.gui.searchinput.text().strip()
        if not keyword:
            return

        self._active_keyword = keyword
        self._target_page = 1
        if keyword == ori_res.GUI.local_fav and self.is_manga:
            self._manga._show_local_fav()
            self.gui.flow_stage = GUIFlowStage.SEARCHED
            self.gui.lifecycle_state = SearchLifecycleState.LockedIdle
            return

        self._is_local_mode = False
        self.books_cache.clear()
        if self.is_manga:
            self._manga.episodes_cache.clear()
        if self._worker:
            self._worker.enqueue_search(keyword, self.site_index, page=1)

    def navigate_to(self, target_page: int):
        keyword = self._active_keyword.strip()
        if self.gui.lifecycle_state is SearchLifecycleState.LockedSearching or not keyword or self._is_local_mode:
            return
        if target_page < 1 or target_page == self._current_page:
            return
        self.on_before_page_turn()
        self.gui.lifecycle_state = SearchLifecycleState.LockedSearching
        self._target_page = target_page
        self._session_id += 1
        if self._worker:
            self._worker.enqueue_search(keyword, self.site_index, page=target_page)

    def _save_preview_selections(self):
        browser = getattr(self.gui, "BrowserWindow", None)
        if not browser:
            return
        idxes = f"{str(browser.output)}"
        cache = {int(k): v for k, v in self.books_cache.items()}
        selected_books = select(idxes, cache)
        self.gui.sel_mgr.submit_decision(
            "BOOK", selected_books, flow_stage=self.gui.flow_stage
        )

    def on_before_page_turn(self):
        if self.is_manga:
            self._manga.submit_page_selections()
        else:
            self._save_preview_selections()

    def _on_search_done(self, generation, _keyword, site_index, books):
        if generation != self._generation or site_index != self.site_index:
            return
        if self._target_page is not None:
            self._current_page = self._target_page
            self._target_page = None
        self.gui.pageEdit.setValue(self._current_page)
        self._is_local_mode = False
        self.gui.flow_stage = GUIFlowStage.SEARCHED
        self.gui.lifecycle_state = SearchLifecycleState.LockedIdle
        self._active.publish(books)

    def _on_search_error(self, generation, keyword, site_index, error):
        if generation != self._generation or site_index not in (-1, self.site_index):
            return
        if keyword and keyword != self._active_keyword:
            return
        self._target_page = None
        self.gui.pageEdit.setValue(self._current_page)
        self.gui.flow_stage = GUIFlowStage.IDLE
        self.gui.lifecycle_state = SearchLifecycleState.LockedIdle
        self.gui.log.error(error)
        summary = (error.strip().splitlines() or ["unknown preview error"])[-1]
        self.gui.say(
            font_color(
                f"<br>preview search failed ({SPIDERS.get(self.site_index, self.site_index)}): {summary}",
                cls="theme-err", size=3,
            ),
            ignore_http=True,
        )

    def create_worker(self, snapshot: SearchContextSnapshot):
        self._stop_worker()
        self._worker = PreviewWorker(self.gui, snapshot=snapshot, generation=self._generation)
        self._worker.search_done.connect(self._on_search_done)
        self._worker.search_error.connect(self._on_search_error)
        self._worker.episodes_done.connect(self._manga.on_episodes_done)
        self._worker.episodes_error.connect(self._manga.on_episodes_error)
        self._worker.start()
        return self._worker

    @staticmethod
    def _disconnect_worker_signals(worker: PreviewWorker):
        for signal in (
            worker.search_done,
            worker.search_error,
            worker.episodes_done,
            worker.episodes_error,
        ):
            with contextlib.suppress(TypeError):
                signal.disconnect()

    def _stop_worker(self, *_):
        if self._worker:
            self._disconnect_worker_signals(self._worker)
            self._worker.stop()
            self._worker.wait(350)
            self._worker = None
