import json
import pickle
import tempfile
import time
import traceback
from collections import defaultdict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWebChannel import QWebChannel

from assets import res as ori_res
from variables import SPIDERS
from utils import bs_theme, conf, temp_p, conf_dir
from utils.sql import SqlRecorder
from utils.preview import TF, El, format_path


class MangaPreviewBridge(QObject):
    def __init__(self, manager):
        super().__init__()
        self.mgr = manager

    @Slot(str)
    def fetchEpisodes(self, bookKey):
        self.mgr.start_fetch_episodes(bookKey)

    @Slot(str)
    def toggleFavorite(self, bookKey):
        self.mgr.toggle_favorite(bookKey)


class _ScanSignals(QObject):
    scan_done = Signal(int, dict)
    scan_error = Signal(int, str)


class _ScanRunnable(QRunnable):
    def __init__(self, session_id, books_snapshot, rv_tools):
        super().__init__()
        self.signals = _ScanSignals()
        self._sid = session_id
        self._books = books_snapshot
        self._rv_tools = rv_tools

    def run(self):
        try:
            bsm = self._rv_tools.show_max()
            matched = {}
            for book_key, book in self._books.items():
                name = getattr(book, "name", "")
                if not name:
                    continue
                book_show = bsm.get(name)
                if book_show and getattr(book_show, "dl_max", ""):
                    matched[book_key] = book_show
            self.signals.scan_done.emit(self._sid, matched)
        except Exception:
            self.signals.scan_error.emit(self._sid, traceback.format_exc())


class _FavoriteStore:
    def __init__(self, favorites_dir):
        self._favorites_dir = favorites_dir
        self._favorites_dir.mkdir(parents=True, exist_ok=True)

    def load(self, site_index):
        pkl_path = self._favorites_pkl_path(site_index)
        if pkl_path is None or not pkl_path.exists():
            return []
        with open(pkl_path, "rb") as f:
            data = pickle.load(f)
        deduped, seen = [], set()
        for book in data:
            key = self.book_unique_url(book)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(book)
        return deduped

    def save(self, site_index, books):
        pkl_path = self._favorites_pkl_path(site_index)
        if pkl_path is None:
            return False
        self._favorites_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = pkl_path.with_name(f"{pkl_path.name}.tmp")
        try:
            with open(tmp_path, "wb") as f:
                pickle.dump(books, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_path.replace(pkl_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
        return True

    def urls(self, site_index):
        return {
            url for book in self.load(site_index)
            if (url := self.book_unique_url(book))
        }

    def toggle(self, site_index, book):
        book_url = self.book_unique_url(book)
        if not book_url:
            return None
        favorites = self.load(site_index)
        existed_index = next(
            (i for i, fav in enumerate(favorites) if self.book_unique_url(fav) == book_url),
            None
        )
        if existed_index is None:
            favorites.append(book)
            final_state = True
        else:
            favorites.pop(existed_index)
            final_state = False
        return final_state if self.save(site_index, favorites) else None

    @staticmethod
    def book_unique_url(book):
        return (getattr(book, "url", None) or getattr(book, "preview_url", "") or "").strip()

    def _favorites_pkl_path(self, site_index):
        spider_name = SPIDERS.get(site_index)
        if not spider_name:
            return None
        return self._favorites_dir.joinpath(f"{spider_name}_local.pkl")


class _PreviewPageController:
    def __init__(self, gui, bridge, get_session_id, on_page_ready):
        self._gui = gui
        self._bridge = bridge
        self._get_session_id = get_session_id
        self._on_page_ready = on_page_ready
        self._channel = None
        self._channel_page = None
        self._page_ready = False
        self._pending_js = []
        self._page_load_page = None
        self._show_started_at = None
        self._queued_js_count = 0
        self._dispatched_js_count = 0

    def shutdown(self):
        self._disconnect_page_load()
        self._page_ready = False
        self._pending_js.clear()
        self._channel = None
        self._channel_page = None

    def reset_session(self):
        self._page_ready = False
        self._pending_js.clear()
        self._queued_js_count = 0
        self._dispatched_js_count = 0

    def _log_debug(self, message: str):
        logger = getattr(self._gui, "log", None)
        if logger:
            logger.debug(f"[preview.js] {message}")

    def show(self, ensure_handler, reload_tf=True):
        self._show_started_at = time.perf_counter()
        browser = self._gui.present_browser(
            ensure_handler=ensure_handler,
            close_handler=self._on_preview_window_closed,
            enable_page_frame=True,
            reload_tf=reload_tf,
        )
        page = browser.view.page()
        self._ensure_web_channel(page)
        self._page_ready = False
        self._bind_page_load(page)

    def run_js(self, js, session_id):
        if session_id != self._get_session_id():
            return
        if not self._page_ready:
            self._queued_js_count += 1
            self._pending_js.append((session_id, js))
            return
        if browser := self._gui.BrowserWindow:
            self._dispatched_js_count += 1
            browser.page_runtime.run_js(js)

    def _ensure_web_channel(self, page):
        if self._channel and self._channel_page is page:
            return
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)
        self._channel_page = page
        self._log_debug("installed QWebChannel on preview page")

    def _bind_page_load(self, page):
        if self._page_load_page is page:
            return
        self._disconnect_page_load()
        page.loadFinished.connect(self._on_page_load_finished)
        self._page_load_page = page

    def _disconnect_page_load(self):
        if self._page_load_page is not None:
            self._page_load_page.loadFinished.disconnect(self._on_page_load_finished)
            self._page_load_page = None

    def _on_page_load_finished(self, ok):
        if not ok:
            return
        browser = self._gui.BrowserWindow
        if not browser:
            return
        self._page_ready = True
        sid = self._get_session_id()
        pending = self._pending_js
        self._pending_js = []
        for saved_sid, js in pending:
            if saved_sid == sid:
                self._dispatched_js_count += 1
                browser.page_runtime.run_js(js)
        self._on_page_ready(sid)
        elapsed_ms = None
        if self._show_started_at is not None:
            elapsed_ms = (time.perf_counter() - self._show_started_at) * 1000
        self._log_debug(
            "page ready "
            f"session={sid} elapsed_ms={elapsed_ms:.1f} pending_flush={len(pending)} "
            f"queued={self._queued_js_count} dispatched={self._dispatched_js_count}"
            if elapsed_ms is not None else
            f"page ready session={sid} pending_flush={len(pending)} "
            f"queued={self._queued_js_count} dispatched={self._dispatched_js_count}"
        )

    def _on_preview_window_closed(self, browser, event):
        self._disconnect_page_load()
        self._page_ready = False
        self._pending_js.clear()
        self._channel = None
        self._channel_page = None
        event.ignore()

        def _save_and_close(html):
            if html and self._gui.tf:
                with open(self._gui.tf, "w", encoding="utf-8") as f:
                    f.write(html)
            browser.close()

        browser.page_runtime.page_to_html(
            _save_and_close,
            description="preview close HTML snapshot",
            error_callback=lambda _exc: _save_and_close(""),
        )


class MangaPreviewFeature:
    def __init__(self, mgr):
        self.mgr = mgr
        self.gui = mgr.gui
        self.episodes_cache = {}
        self._inflight_books = set()
        self._inflight_pages = {}
        self._dl_scan_runnables = {}
        self.bridge = MangaPreviewBridge(self)
        self._favorites = _FavoriteStore(conf_dir.joinpath("manga"))
        self._page = _PreviewPageController(
            self.gui, self.bridge,
            lambda: self.mgr._session_id,
            self._sync_page_favorites,
        )
        self._fav_completer_exists = False
        self._check_lc_completer_exists()

    def shutdown(self):
        self._inflight_books.clear()
        self._inflight_pages.clear()
        self._dl_scan_runnables.clear()
        self._page.shutdown()

    def reset(self):
        self.episodes_cache.clear()
        self._inflight_books.clear()
        self._inflight_pages.clear()
        browser = getattr(self.gui, "BrowserWindow", None)
        if browser:
            browser.set_ensure_handler()

    def check_lc_completer(self):
        self._check_lc_completer_exists()

    def publish(self, books):
        self.mgr._session_id += 1
        sid = self.mgr._session_id
        self._page.reset_session()
        self._inflight_books.clear()
        self.mgr.books_cache = {str(book.idx): book for book in books}
        self.episodes_cache.clear()
        self.gui.clean_temp_file()
        self.gui.tf = self._write_cards_html(self._build_cards_html(books))
        self._page.show(self._handle_ensure_result)
        self._start_dl_scan(sid)

    def show_cached(self):
        self._page.show(self._handle_ensure_result, reload_tf=False)

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------

    def toggle_favorite(self, book_key):
        book = self.mgr.books_cache.get(book_key)
        if book is None:
            return
        final_state = self._favorites.toggle(self.mgr.site_index, book)
        if final_state is None:
            return
        if final_state and not self._fav_completer_exists:
            self._ensure_local_fav_completer()
            self._fav_completer_exists = True
        js = (
            f"if (typeof updateFavoriteState === 'function') "
            f"updateFavoriteState('{book_key}', {'true' if final_state else 'false'});"
        )
        self._js_guarded(js, self.mgr._session_id)

    def _check_lc_completer_exists(self):
        kw = ori_res.GUI.local_fav
        completer_list = conf.completer.get(self.mgr.site_index)
        self._fav_completer_exists = bool(completer_list and kw in completer_list)

    def _ensure_local_fav_completer(self):
        idx = self.mgr.site_index
        kw = ori_res.GUI.local_fav
        completer_list = conf.completer.get(idx)
        if completer_list is None:
            from variables import DEFAULT_COMPLETER
            completer_list = list(DEFAULT_COMPLETER.get(idx, []))
            conf.completer[idx] = completer_list
        if kw not in completer_list:
            completer_list.insert(0, kw)
            conf.update()
            self.gui.set_completer()

    def _show_local_fav(self):
        books = self._favorites.load(self.mgr.site_index)
        for idx, book in enumerate(books):
            book.idx = idx
        self.mgr._is_local_mode = True
        self.mgr._current_page = 1
        self.publish(books)

    # ------------------------------------------------------------------
    # HTML build
    # ------------------------------------------------------------------

    def _build_cards_html(self, books):
        if not books:
            return '<div class="book-grid-empty"><p>无结果</p></div>'
        manga_el = El("manga")
        return "\n".join(manga_el.create_from_book(book) for book in books)

    def _write_cards_html(self, body):
        with open(format_path.joinpath("manga.html"), encoding="utf-8") as f:
            template = f.read()
        html = template.replace("{bs_theme}", bs_theme()).replace("{body}", body)
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(html.encode("utf-8"))
        file_path = tf.name
        tf.close()
        return TF(file_path)

    # ------------------------------------------------------------------
    # JS bridge helpers
    # ------------------------------------------------------------------

    def _sync_page_favorites(self, session_id):
        if self.mgr.books_cache:
            if self.mgr._is_local_mode:
                fav_keys = list(self.mgr.books_cache.keys())
            else:
                favorite_urls = self._favorites.urls(self.mgr.site_index)
                fav_keys = [
                    key for key, book in self.mgr.books_cache.items()
                    if self._favorites.book_unique_url(book) in favorite_urls
                ]
            keys_json = json.dumps(fav_keys)
            js = (
                f"if (typeof initFavoriteStates === 'function') initFavoriteStates({keys_json});"
            )
            self._js_guarded(js, session_id)

    def _js_guarded(self, js, session_id=None):
        sid = self.mgr._session_id if session_id is None else session_id
        self._page.run_js(js, sid)

    # ------------------------------------------------------------------
    # Download scan
    # ------------------------------------------------------------------

    def _track_dl_scan(self, session_id, runnable):
        self._dl_scan_runnables[session_id] = runnable
        self.gui.log.debug(f"[preview.dlscan] track session={session_id} active={len(self._dl_scan_runnables)}")

    def _release_dl_scan(self, session_id):
        runnable = self._dl_scan_runnables.pop(session_id, None)
        self.gui.log.debug(f"[preview.dlscan] release session={session_id} active={len(self._dl_scan_runnables)}")
        return runnable

    def _start_dl_scan(self, session_id):
        if not self.mgr.books_cache:
            return
        self._js_guarded('showScanNotification("正在扫描下载记录...")', session_id)
        runnable = _ScanRunnable(session_id, self.mgr.books_cache.copy(), self.gui.rv_tools)
        runnable.signals.scan_done.connect(self._on_dl_scan_done)
        runnable.signals.scan_error.connect(self._on_dl_scan_error)
        self._track_dl_scan(session_id, runnable)
        try:
            QThreadPool.globalInstance().start(runnable)
        except Exception:
            self._release_dl_scan(session_id)
            raise

    def _on_dl_scan_done(self, session_id, matched):
        self._release_dl_scan(session_id)
        if session_id != self.mgr._session_id:
            return
        js_parts = []
        batch_items = []
        for book_key, book_show in matched.items():
            book = self.mgr.books_cache.get(book_key)
            if book is None:
                continue
            book_key_js = json.dumps(str(book_key))
            dl_max_js = json.dumps(str(book_show.dl_max), ensure_ascii=False)
            js_parts.append(f"renderCardBadgeDl({book_key_js}, {dl_max_js})")
            if book_key in self.episodes_cache:
                latest_js = self._latest_badge_js(book_key, self.episodes_cache[book_key])
                if latest_js:
                    js_parts.append(latest_js)
                continue
            token = (session_id, book_key)
            if token in self._inflight_books:
                continue
            batch_items.append((session_id, book_key, book, self.mgr.site_index))
        js_parts.append("hideScanNotification()")
        self._js_guarded(";".join(js_parts), session_id)
        if batch_items and self.mgr.worker:
            for _, book_key, _, _ in batch_items:
                self._inflight_books.add((session_id, book_key))
            self.mgr.worker.enqueue_episodes_batch(batch_items)
        if browser := getattr(self.gui, "BrowserWindow", None):
            browser.page_runtime.log_js_metrics(
                "manga-dl-scan",
                session=session_id,
                matched=len(matched),
                batch=len(batch_items),
            )

    def _on_dl_scan_error(self, session_id, error):
        self._release_dl_scan(session_id)
        if session_id != self.mgr._session_id:
            return
        self.gui.log.error(error)
        self._js_guarded("hideScanNotification()", session_id)

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def start_fetch_episodes(self, book_key):
        if book_key not in self.mgr.books_cache:
            return
        if book_key in self.episodes_cache:
            self.on_episodes_done(self.mgr._generation, self.mgr._session_id, book_key, self.episodes_cache[book_key])
            return
        worker = self.mgr.worker
        if not worker:
            return
        token = (self.mgr._session_id, book_key)
        if token in self._inflight_books:
            return
        self._inflight_books.add(token)
        worker.enqueue_episodes(
            self.mgr._session_id, book_key, self.mgr.books_cache[book_key], self.mgr.site_index
        )

    def on_episodes_done(self, generation, session_id, book_key, episodes):
        self._inflight_books.discard((session_id, book_key))
        if generation != self.mgr._generation or session_id != self.mgr._session_id:
            return
        if book_key not in self.mgr.books_cache:
            return
        self.episodes_cache[book_key] = episodes
        ep_data = [{"idx": ep.idx, "name": ep.name} for ep in episodes]
        js_arg = json.dumps(json.dumps(ep_data, ensure_ascii=False))
        self._js_guarded(f"updateEpisodes('{book_key}', {js_arg})", session_id)
        if dled_ids := self._mark_downloaded_episodes(book_key, episodes):
            dled_json = json.dumps(dled_ids)
            self._js_guarded(f"markDownloadedEpisodes({dled_json})", session_id)
        if episodes:
            with_idx = [ep for ep in episodes if isinstance(getattr(ep, "idx", None), (int, float))]
            latest_ep = max(with_idx, key=lambda ep: ep.idx) if with_idx else episodes[-1]
            latest_name = json.dumps(str(getattr(latest_ep, "name", "") or ""), ensure_ascii=False)
            self._js_guarded(f"renderCardBadgeLatest('{book_key}', {latest_name})", session_id)

    def _mark_downloaded_episodes(self, book_key, episodes):
        if not episodes:
            return []
        sql_utils = SqlRecorder()
        try:
            md5_to_ep = {}
            md5s = []
            for ep in episodes:
                _, ep_md5 = ep.id_and_md5()
                md5_to_ep[ep_md5] = ep
                md5s.append(ep_md5)
            if not md5s:
                return []
            downloaded_md5 = sql_utils.batch_check_dupe(md5s)
        finally:
            sql_utils.close()
        return [
            f"ep{book_key}-{md5_to_ep[m].idx}"
            for m in downloaded_md5 if m in md5_to_ep
        ]

    def on_episodes_error(self, generation, session_id, book_key, error):
        self._inflight_books.discard((session_id, book_key))
        if generation != self.mgr._generation or session_id != self.mgr._session_id:
            return
        self.gui.log.error(error)
        key_js = json.dumps(str(book_key))
        code_js = json.dumps("fetch_failed")
        self._js_guarded(f"showEpisodeFetchError({key_js}, {code_js})", session_id)

    # ------------------------------------------------------------------
    # Pages fetch
    # ------------------------------------------------------------------

    def on_pages_done(self, generation, book_key, episodes):
        pending = self._inflight_pages.pop(book_key, None)
        if pending is None:
            return
        if generation != self.mgr._generation:
            if not self._inflight_pages:
                self._js_guarded("hideScanNotification()")
            return
        book, selected_eps = pending
        book.episodes = list(selected_eps)
        self.gui.sel_mgr.submit_decision("EP", book)
        if not self._inflight_pages:
            self._js_guarded("hideScanNotification()")

    def on_pages_error(self, generation, book_key, error):
        self._inflight_pages.pop(book_key, None)
        if generation == self.mgr._generation:
            self.gui.log.error(error)
            key_js = json.dumps(str(book_key))
            self._js_guarded(f"showEpisodeFetchError({key_js}, '\"pages_fetch_failed\"')")
        if not self._inflight_pages:
            self._js_guarded("hideScanNotification()")

    # ------------------------------------------------------------------
    # Selection / ensure
    # ------------------------------------------------------------------

    def _parse_checked_output(self) -> dict:
        checked_ids = self.gui.BrowserWindow.output if self.gui.BrowserWindow else []
        if not checked_ids:
            return {}
        grouped = defaultdict(list)
        for cid in checked_ids:
            if not isinstance(cid, str) or not cid.startswith("ep"):
                continue
            book_ep = cid.removeprefix("ep").split("-", 1)
            if len(book_ep) != 2:
                continue
            book_key, ep_idx_text = book_ep
            try:
                ep_idx = int(ep_idx_text)
            except ValueError:
                continue
            grouped[book_key].append(ep_idx)

        result = {}
        for book_key, ep_idxes in grouped.items():
            if book_key not in self.mgr.books_cache or book_key not in self.episodes_cache:
                continue
            book = self.mgr.books_cache[book_key]
            all_episodes = self.episodes_cache[book_key]
            selected_set = set(ep_idxes)
            selected_eps = [ep for ep in all_episodes if ep.idx in selected_set]
            if not selected_eps:
                continue
            result[book_key] = selected_eps
        return result

    def _submit_checked_output(self, parsed: dict):
        if not self.mgr.worker:
            return
        batch_items = []
        for book_key, selected_eps in parsed.items():
            book = self.mgr.books_cache.get(book_key)
            if book is None or not selected_eps:
                continue
            needs_pages = [ep for ep in selected_eps if ep.pages is None]
            if not needs_pages:
                book.episodes = list(selected_eps)
                self.gui.sel_mgr.submit_decision("EP", book)
                continue
            if book_key in self._inflight_pages:
                continue
            self._inflight_pages[book_key] = (book, selected_eps)
            for ep in needs_pages:
                batch_items.append((book_key, ep, self.mgr.site_index))
        if batch_items:
            self.mgr.worker.enqueue_pages_batch(batch_items)
            self._js_guarded('showScanNotification("正在获取页面信息...")')

    def submit_page_selections(self):
        self._submit_checked_output(self._parse_checked_output())

    def _handle_ensure_result(self):
        self._submit_checked_output(self._parse_checked_output())
