import contextlib
import json

from PySide6.QtWebChannel import QWebChannel

from GUI.core.font import font_color
from GUI.types import GUIFlowStage, PreviewRequestState, SearchContextSnapshot, SearchLifecycleState
from GUI.thread.preview import PreviewWorker
from GUI.manager.preview.manga import MangaPreviewFeature
from GUI.manager.preview.ero import EroPreviewFeature
from GUI.manager.preview.fix import FixPreviewFeature
from assets import res as ori_res
from utils import select
from variables import SPIDERS, Spider


class PreviewMgr:
    def __init__(self, gui):
        self.gui = gui
        self.site_index = 0
        self.search_context: SearchContextSnapshot | None = None
        self.books_cache = {}
        self.downloaded_book_ids = set()
        self._worker = None
        self._generation = 0
        self._session_id = 0
        self._current_page = 1
        self._target_page = None
        self._active_keyword = ""
        self._is_local_mode = False
        self._page_channel = None
        self._page_channel_page = None
        self._page_bridge = None
        self._interactive_browser = None
        self._manga = MangaPreviewFeature(self)
        self._ero = EroPreviewFeature(self)
        self._fix = FixPreviewFeature(self)
        self.gui.destroyed.connect(self._stop_worker)

    @property
    def is_manga(self):
        return self.site_index in Spider.mangas()

    @property
    def is_fix(self):
        return self.site_index == Spider.JM

    @property
    def is_pageable(self):
        return self.site_index in SPIDERS and not self._is_local_mode

    @property
    def worker(self):
        return self._worker

    @property
    def _active(self):
        if self.is_manga:
            return self._manga
        if self.is_fix:
            return self._fix
        return self._ero

    @property
    def episodes_cache(self):
        if self.is_fix:
            return self._fix.episodes_cache
        return self._manga.episodes_cache

    def shutdown(self):
        self._generation += 1
        self.search_context = None
        self._active_keyword = ""
        self.downloaded_book_ids.clear()
        self.reset_preview_page()
        self._manga.shutdown()
        self._ero.shutdown()
        self._fix.shutdown()
        self._stop_worker()

    def handle_choosebox_changed(self, index, snapshot: SearchContextSnapshot | None):
        self._generation += 1
        self.site_index = index
        self.search_context = snapshot
        self._session_id = 0
        self._active_keyword = ""
        self._manga.check_lc_completer()
        self._fix.check_lc_completer()
        self._is_local_mode = False
        self._current_page = 1
        self._target_page = None
        self.books_cache.clear()
        self.downloaded_book_ids.clear()
        self.reset_preview_page()
        self._manga.reset()
        self._ero.reset()
        self._fix.reset()
        self.gui.pageEdit.setValue(1)
        if index in SPIDERS and snapshot is not None:
            self.create_worker(snapshot)
        else:
            self._stop_worker()
        self.gui.refresh_lifecycle_state()

    def update_search_context(self, snapshot: SearchContextSnapshot):
        self.search_context = snapshot
        if self._worker:
            self._worker.update_snapshot(snapshot)

    def begin_preview_session(self):
        self._session_id += 1
        self._reset_page_state()
        return self._session_id

    def reset_preview_page(self):
        self._reset_page_state()
        browser = getattr(self.gui, "BrowserWindow", None)
        if browser:
            browser.set_ensure_handler()
            browser.set_close_handler()

    def show_preview(self, *, ensure_handler=None, reload_tf=True, bridge=None):
        browser_created = getattr(self.gui, "BrowserWindow", None) is None
        browser = self.gui.present_browser(
            ensure_handler=ensure_handler,
            ensure_result_kind="preview_submit" if ensure_handler is not None else "checked_ids",
            close_handler=self._on_preview_window_closed,
            enable_page_frame=True,
            reload_tf=reload_tf,
        )
        page = browser.view.page()
        self._ensure_web_channel(page, bridge)
        self._bind_page_interactive(browser)
        if not browser_created and not reload_tf and browser.page_runtime.page_ready:
            self._on_browser_page_ready("fast-path", -1.0)
        return browser

    def _legacy_run_js(self, js, session_id):
        if session_id != self._session_id:
            return False
        browser = getattr(self.gui, "BrowserWindow", None)
        if browser:
            browser.page_runtime.run_js(js)
            return True
        return False

    def send_command(self, cmd_type, payload, session_id=None):
        sid = self._session_id if session_id is None else session_id
        if sid != self._session_id:
            return False
        browser = getattr(self.gui, "BrowserWindow", None)
        if not browser or not browser.page_runtime.page_ready:
            return False
        envelope = json.dumps({"type": cmd_type, "sid": sid, "payload": payload}, ensure_ascii=False)
        browser.page_runtime.run_js(f"window.previewCommandBus.dispatch({envelope});")
        return True

    def on_spreview_clicked(self, keyword=None):
        keyword = keyword or self.gui.searchinput.text().strip()
        if not keyword:
            return

        self.gui.update_search_ui(
            session=SearchLifecycleState.Locked,
            request=PreviewRequestState.Running,
        )
        self._active_keyword = keyword
        self._target_page = 1
        if keyword == ori_res.GUI.local_fav and (self.is_manga or self.is_fix):
            self._active._show_local_fav()
            self.gui.flow_stage = GUIFlowStage.SEARCHED
            self.gui.update_search_ui(request=PreviewRequestState.Idle)
            return

        self._is_local_mode = False
        self.books_cache.clear()
        if self.is_manga:
            self._manga.episodes_cache.clear()
        elif self.is_fix:
            self._fix.episodes_cache.clear()
        if self._worker:
            self._worker.enqueue_search(keyword, self.site_index, page=1)
            return
        self.gui.update_search_ui(request=PreviewRequestState.Idle)

    def navigate_to(self, target_page: int):
        keyword = self._active_keyword.strip()
        if self.gui.search_ui_state.request is PreviewRequestState.Running or not keyword or self._is_local_mode:
            return
        if target_page < 1 or target_page == self._current_page:
            return
        self.on_before_page_turn()
        self.gui.update_search_ui(request=PreviewRequestState.Running)
        self._target_page = target_page
        self.begin_preview_session()
        if self._worker:
            self._worker.enqueue_search(keyword, self.site_index, page=target_page)
            return
        self.gui.update_search_ui(request=PreviewRequestState.Idle)

    def submit_browser_selection(self):
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
        if self.is_manga or self.is_fix:
            self._active.submit_page_selections()
        else:
            self.submit_browser_selection()

    def _on_empty_search_done(self):
        target_page = self._target_page
        self._target_page = None
        self._is_local_mode = False
        if target_page in (None, 1):
            self._current_page = 1
            self.gui.flow_stage = GUIFlowStage.IDLE
            self.gui.clean_preview()
        self.gui.pageEdit.setValue(self._current_page)
        self.gui.update_search_ui(request=PreviewRequestState.Idle)
        self.gui.say(f"<br>{'✈' * 15}<br>{font_color(ori_res.SPIDER.SayToGui.frame_book_print_retry_tip, cls='theme-err', size=4)}", 
                     ignore_http=True)

    def _on_search_done(self, generation, _keyword, site_index, books):
        if generation != self._generation or site_index != self.site_index:
            return
        if not books:
            return self._on_empty_search_done()
        if self._target_page is not None:
            self._current_page = self._target_page
            self._target_page = None
        self.gui.pageEdit.setValue(self._current_page)
        self._is_local_mode = False
        self.gui.flow_stage = GUIFlowStage.SEARCHED
        self.gui.update_search_ui(request=PreviewRequestState.Idle)
        self._active.publish(books)

    def _on_search_error(self, generation, keyword, site_index, error):
        if generation != self._generation or site_index not in (-1, self.site_index):
            return
        if keyword and keyword != self._active_keyword:
            return
        self._target_page = None
        self.gui.pageEdit.setValue(self._current_page)
        self.gui.flow_stage = GUIFlowStage.IDLE
        self.gui.update_search_ui(request=PreviewRequestState.Idle)
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
        ep_handler = self._fix if self.is_fix else self._manga
        self._worker.episodes_done.connect(ep_handler.on_episodes_done)
        self._worker.episodes_error.connect(ep_handler.on_episodes_error)
        self._worker.pages_done.connect(ep_handler.on_pages_done)
        self._worker.pages_error.connect(ep_handler.on_pages_error)
        self._worker.start()
        return self._worker

    @staticmethod
    def _disconnect_worker_signals(worker: PreviewWorker):
        for signal in (
            worker.search_done,
            worker.search_error,
            worker.episodes_done,
            worker.episodes_error,
            worker.pages_done,
            worker.pages_error,
        ):
            with contextlib.suppress(TypeError):
                signal.disconnect()

    def _stop_worker(self, *_):
        if self._worker:
            self._disconnect_worker_signals(self._worker)
            self._worker.stop()
            self._worker.wait(350)
            self._worker = None

    def _log_page_debug(self, message: str):
        logger = getattr(self.gui, "log", None)
        if logger:
            logger.debug(f"[preview.js] {message}")

    def _ensure_web_channel(self, page, bridge):
        if bridge is None:
            self._page_channel = None
            self._page_channel_page = None
            self._page_bridge = None
            return
        if self._page_channel and self._page_channel_page is page and self._page_bridge is bridge:
            return
        self._page_channel = QWebChannel(page)
        self._page_channel.registerObject("bridge", bridge)
        page.setWebChannel(self._page_channel)
        self._page_channel_page = page
        self._page_bridge = bridge
        self._log_page_debug("installed QWebChannel on preview page")

    def _bind_page_interactive(self, browser):
        if self._interactive_browser is browser:
            return
        self._unbind_page_interactive()
        browser.pageInteractive.connect(self._on_browser_page_ready)
        self._interactive_browser = browser

    def _unbind_page_interactive(self):
        if self._interactive_browser is None:
            return
        with contextlib.suppress(TypeError, RuntimeError):
            self._interactive_browser.pageInteractive.disconnect(self._on_browser_page_ready)
        self._interactive_browser = None

    def _reset_page_state(self):
        self._unbind_page_interactive()
        self._page_channel = None
        self._page_channel_page = None
        self._page_bridge = None

    def _on_browser_page_ready(self, reason, elapsed_ms):
        session_id = self._session_id
        self._log_page_debug(
            f"page ready session={session_id} reason={reason} elapsed_ms={elapsed_ms:.1f}"
        )
        self._active._on_page_ready(session_id)

    def _on_preview_window_closed(self, browser, event):
        self._reset_page_state()
        event.ignore()

        def _save_and_close(html):
            if html and self.gui.tf:
                with open(self.gui.tf, "w", encoding="utf-8") as f:
                    f.write(html)
            browser.close()

        def _on_snapshot_error(exc):
            logger = getattr(self.gui, "log", None)
            if logger:
                logger.warning(f"preview close snapshot failed: {exc}")
            _save_and_close("")

        browser.page_runtime.page_to_html(
            _save_and_close,
            description="preview close HTML snapshot",
            error_callback=_on_snapshot_error,
        )
