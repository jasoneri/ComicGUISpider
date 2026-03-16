from GUI.core.font import font_color
from GUI.types import GUIFlowStage
from GUI.thread.preview import PreviewWorker
from GUI.manager.preview.manga import MangaPreviewFeature
from GUI.manager.preview.ero import EroPreviewFeature
from assets import res as ori_res
from variables import SPIDERS, Spider


class PreviewMgr:
    def __init__(self, gui):
        self.gui = gui
        self.site_index = 0
        self.books_cache = {}
        self._searching = False
        self._worker = None
        self._session_id = 0
        self._current_page = 1
        self._is_local_mode = False
        self._manga = MangaPreviewFeature(self)
        self._ero = EroPreviewFeature(self)
        self.gui.destroyed.connect(self._stop_worker)

    @property
    def is_manga(self):
        return self.site_index in Spider.mangas()

    @property
    def _active(self):
        return self._manga if self.is_manga else self._ero

    @property
    def episodes_cache(self):
        return self._manga.episodes_cache

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        self._searching = False
        self._manga.shutdown()
        self._stop_worker()

    def handle_choosebox_changed(self, index):
        self.site_index = index
        self._manga.check_lc_completer()
        self._is_local_mode = False
        self._current_page = 1
        self.books_cache.clear()
        self._manga.episodes_cache.clear()
        self._manga._inflight_books.clear()
        self._searching = False
        self._active.reset()

    # ------------------------------------------------------------------
    # Search entry
    # ------------------------------------------------------------------

    def on_spreview_clicked(self, keyword=None):
        keyword = keyword or self.gui.searchinput.text().strip()
        if not keyword:
            return

        if keyword == ori_res.GUI.local_fav and self.is_manga:
            self.gui.searchRunning = False
            return self._manga._show_local_fav()
        self._is_local_mode = False

        self._searching = True
        self._current_page = 1
        self.books_cache.clear()
        if self.is_manga:
            self._manga.episodes_cache.clear()
        self._ensure_worker().enqueue_search(keyword, self.site_index, page=1)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate_to(self, target_page: int):
        keyword = self.gui.searchinput.text().strip()
        if self._searching or not keyword or self._is_local_mode:
            return
        if target_page < 1 or target_page == self._current_page:
            return
        self.gui.clean_temp_file()
        self._searching = True
        self._current_page = target_page
        self._session_id += 1
        self.books_cache.clear()
        if self.is_manga:
            self._manga.episodes_cache.clear()
            self._manga._inflight_books.clear()
        self._ensure_worker().enqueue_search(
            keyword, self.site_index, page=target_page
        )

    def on_before_page_turn(self):
        if self.is_manga:
            self._manga.submit_page_selections()
        else:
            self.gui.next()

    # ------------------------------------------------------------------
    # Worker signals
    # ------------------------------------------------------------------

    def _on_search_done(self, _keyword, site_index, books):
        self._searching = False
        if site_index != self.site_index:
            return
        self._is_local_mode = False
        self.gui.flow_stage = GUIFlowStage.SEARCHED
        self.gui.searchRunning = False
        self._active.publish(books)

    def _on_search_error(self, keyword, site_index, error):
        if site_index not in (-1, self.site_index):
            return
        active_kw = self.gui.searchinput.text().strip()
        if keyword and keyword != active_kw:
            return
        self._searching = False
        self.gui.searchReady = False
        self.gui.searchRunning = False
        self.gui.searchinput.setEnabled(True)
        self.gui.flow_stage = GUIFlowStage.IDLE
        self.gui.log.error(error)
        summary = (error.strip().splitlines() or ["unknown preview error"])[-1]
        self.gui.say(
            font_color(
                f"<br>preview search failed ({SPIDERS.get(self.site_index, self.site_index)}): {summary}",
                cls="theme-err", size=3,
            ),
            ignore_http=True,
        )

    # ------------------------------------------------------------------
    # Worker management
    # ------------------------------------------------------------------

    def _ensure_worker(self):
        if self._worker and self._worker.isRunning():
            return self._worker
        if self._worker:
            self._worker.disconnect()
        self._worker = PreviewWorker(self.gui)
        self._worker.search_done.connect(self._on_search_done)
        self._worker.search_error.connect(self._on_search_error)
        self._worker.episodes_done.connect(self._manga.on_episodes_done)
        self._worker.episodes_error.connect(self._manga.on_episodes_error)
        self._worker.start()
        return self._worker

    def _stop_worker(self, *_):
        if self._worker:
            self._worker.disconnect()
            self._worker.stop()
            self._worker.wait(350)
            self._worker = None
