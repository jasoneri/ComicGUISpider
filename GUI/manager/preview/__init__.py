import json
import pickle
import tempfile
import traceback
import contextlib
from collections import defaultdict
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, QUrl
from PyQt5.QtWebChannel import QWebChannel
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.core.font import font_color
from GUI.thread.manga_preview import MangaPreviewWorker
from assets import res as ori_res
from variables import SPIDERS

from utils import bs_theme, conf, temp_p, conf_dir
from utils.sql import SqlRecorder
from utils.preview import TF, El, format_path


class MangaPreviewBridge(QObject):
    def __init__(self, manager):
        super().__init__()
        self._mgr = manager

    @pyqtSlot(str)
    def fetchEpisodes(self, bookKey):
        self._mgr.start_fetch_episodes(bookKey)

    @pyqtSlot(str)
    def toggleFavorite(self, bookKey):
        self._mgr.toggle_favorite(bookKey)


class _ScanSignals(QObject):
    scan_done = pyqtSignal(int, dict)
    scan_error = pyqtSignal(int, str)


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

    def shutdown(self):
        self._disconnect_page_load()
        self._page_ready = False
        self._pending_js.clear()
        self._channel = None
        self._channel_page = None

    def reset_session(self):
        self._page_ready = False
        self._pending_js.clear()

    def show(self, ensure_handler):
        browser = self._show_browser()
        page = browser.view.page()
        self._ensure_web_channel(page)
        self._page_ready = False
        self._bind_page_load(page)
        browser.set_ensure_handler(ensure_handler)
        browser.set_close_handler(self._on_preview_window_closed)
        browser.show()

    def run_js(self, js, session_id):
        if session_id != self._get_session_id():
            return
        if not self._page_ready:
            self._pending_js.append((session_id, js))
            return
        if browser := self._gui.BrowserWindow:
            browser.js_execute(js, lambda _: None)

    def _show_browser(self):
        if self._gui.previewInit or not self._gui.BrowserWindow:
            self._gui.previewInit = False
            self._gui.set_preview()
            browser = self._gui.BrowserWindow
            browser.setMinimumWidth(browser.minimumWidth() + 30)
            browser.setMinimumHeight(browser.minimumHeight() + 30)
            self._channel = None
            self._channel_page = None
            return browser
        browser = self._gui.BrowserWindow
        if self._gui.previewSecondInit:
            browser.second_init()
            self._gui.previewSecondInit = False
        else:
            browser.home_url = QUrl.fromLocalFile(self._gui.tf)
            browser.load_home()
        return browser

    def _ensure_web_channel(self, page):
        if self._channel and self._channel_page is page:
            return
        self._channel = QWebChannel(page)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)
        self._channel_page = page

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
                browser.js_execute(js, lambda _: None)
        self._on_page_ready(sid)

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

        browser.js_execute("get_curr_hml();", _save_and_close)


class MangaPreviewManager:
    def __init__(self, gui):
        self.gui = gui
        self.site_index = 0
        self.books_cache = {}
        self.episodes_cache = {}
        self.bridge = MangaPreviewBridge(self)
        self._favorites = _FavoriteStore(conf_dir.joinpath("manga"))
        self._searching = False
        self._worker = None
        self._session_id = 0
        self._current_page = 1
        self._current_keyword = ""
        self._inflight_books = set()
        self._is_local_mode = False
        self._page = _PreviewPageController(
            gui,
            self.bridge,
            lambda: self._session_id,
            self._sync_page_favorites,
        )
        self._fav_completer_exists = False
        self._check_lc_completer_exists()
        self.gui.destroyed.connect(self._stop_worker)

    def shutdown(self):
        self._searching = False
        self._inflight_books.clear()
        self._page.shutdown()
        self._stop_worker()

    def _check_lc_completer_exists(self):
        kw = ori_res.GUI.local_fav
        completer_list = conf.completer.get(self.site_index)
        self._fav_completer_exists = bool(completer_list and kw in completer_list)

    def _stop_worker(self, *_):
        if self._worker:
            self._worker.disconnect()
            self._worker.stop()
            self._worker.wait(350)
            self._worker = None

    def _ensure_worker(self):
        if self._worker and self._worker.isRunning():
            return self._worker
        if self._worker:
            self._worker.disconnect()
        self._worker = MangaPreviewWorker(self.gui)
        self._worker.search_done.connect(self._on_search_done)
        self._worker.search_error.connect(self._on_search_error)
        self._worker.episodes_done.connect(self._on_episodes_done)
        self._worker.episodes_error.connect(self._on_episodes_error)
        self._worker.start()
        return self._worker

    def toggle_favorite(self, book_key):
        book = self.books_cache.get(book_key)
        if book is None:
            return
        final_state = self._favorites.toggle(self.site_index, book)
        if final_state is None:
            return
        if final_state and not self._fav_completer_exists:
            self._ensure_local_fav_completer()
            self._fav_completer_exists = True
        js = (
            f"if (typeof updateFavoriteState === 'function') "
            f"updateFavoriteState('{book_key}', {'true' if final_state else 'false'});"
        )
        self._js_guarded(js, self._session_id)

    def _ensure_local_fav_completer(self):
        idx = self.site_index
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
        books = self._favorites.load(self.site_index)
        for idx, book in enumerate(books):
            book.idx = idx
        self._is_local_mode = True
        self._searching = False
        self._current_page = 1
        self._current_keyword = ori_res.GUI.local_fav
        self._publish_books(books)

    def handle_choosebox_changed(self, index):
        self.site_index = index
        self._check_lc_completer_exists()
        self._is_local_mode = False
        self._current_page = 1
        self._current_keyword = ""
        self.books_cache.clear()
        self.episodes_cache.clear()
        self._inflight_books.clear()
        self._searching = False
        browser = getattr(self.gui, "BrowserWindow", None)
        if browser:
            browser.set_ensure_handler()

    def on_spreview_clicked(self):
        if self._searching:
            return
        keyword = self.gui.searchinput.text().strip()
        if not keyword:
            InfoBar.info(
                title='', content='先输入搜索词吧', isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=2000, parent=self.gui.textBrowser
            )
            return

        if keyword == ori_res.GUI.local_fav:
            return self._show_local_fav()
        self._is_local_mode = False

        if (keyword == self._current_keyword
                and self.books_cache
                and self.gui.tf
                and Path(self.gui.tf).exists()):
            if self.gui.BrowserWindow:
                self.gui.BrowserWindow.show()
                self.gui.BrowserWindow.activateWindow()
            else:
                self._page.show(self._handle_ensure_result)
            return
        self._searching = True
        self._current_page = 1
        self._current_keyword = keyword
        self.books_cache.clear()
        self.episodes_cache.clear()
        self._ensure_worker().enqueue_search(keyword, self.site_index, page=1)

    def navigate_page(self, direction: str):
        if (self._searching or not self._current_keyword) or \
            self._is_local_mode or \
            direction not in {"next", "prev"}:
            return
        new_page = self._current_page + (1 if direction == "next" else -1)
        if new_page < 1:
            return
        self.gui.clean_temp_file()
        self._searching = True
        self._current_page = new_page
        self._session_id += 1
        self.books_cache.clear()
        self.episodes_cache.clear()
        self._inflight_books.clear()
        self._ensure_worker().enqueue_search(
            self._current_keyword, self.site_index, page=new_page
        )

    def _on_search_done(self, _keyword, site_index, books):
        self._searching = False
        if site_index != self.site_index:
            return
        self._is_local_mode = False
        self._publish_books(books)

    def _on_search_error(self, error):
        self._searching = False
        self.gui.log.error(error)
        self.gui.say(
            font_color(
                f"<br>normal preview search error:<br><pre>{error}</pre>",
                cls="theme-err", size=3,
            ),
            ignore_http=True,
        )

    def _build_cards_html(self, books):
        if not books:
            return '<div class="text-center p-5"><p>无结果</p></div>'
        manga_el = El("manga")
        cards = []
        for book in books:
            img_src = getattr(book, "img_preview", None) or ""
            title = getattr(book, "name", "") or "-"
            url = getattr(book, "preview_url", None) or getattr(book, "url", "")

            meta = []
            if artist := getattr(book, "artist", None):
                meta.append(f"作者: {artist}")
            if popular := getattr(book, "popular", None):
                meta.append(f"热度: {popular}")
            if last_chapter := getattr(book, "last_chapter_name", None):
                meta.append(f"最新: {last_chapter}")
            if updated := getattr(book, "datetime_updated", None):
                meta.append(f"更新: {updated}")

            cards.append(manga_el.create(book.idx, img_src, title, url, meta=meta or None))
        return "\n".join(cards)

    def _publish_books(self, books):
        self._session_id += 1
        sid = self._session_id
        self._page.reset_session()
        self._inflight_books.clear()
        self.books_cache = {str(book.idx): book for book in books}
        self.episodes_cache.clear()
        self.gui.clean_temp_file()
        self.gui.tf = self._write_cards_html(self._build_cards_html(books))
        self._page.show(self._handle_ensure_result)
        self._start_dl_scan(sid)

    def _write_cards_html(self, body):
        with open(format_path.joinpath("manga.html"), encoding="utf-8") as f:
            template = f.read()
        html = template.replace("{bs_theme}", bs_theme()).replace("{body}", body)
        tf = tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(html.encode("utf-8"))
        file_path = tf.name
        tf.close()
        return TF(file_path)

    def _sync_page_favorites(self, session_id):
        if self.books_cache:
            if self._is_local_mode:
                fav_keys = list(self.books_cache.keys())
            else:
                favorite_urls = self._favorites.urls(self.site_index)
                fav_keys = [
                    key for key, book in self.books_cache.items()
                    if self._favorites.book_unique_url(book) in favorite_urls
                ]
            keys_json = json.dumps(fav_keys)
            js = (
                f"if (typeof initFavoriteStates === 'function') initFavoriteStates({keys_json});"
            )
            self._js_guarded(js, session_id)

    def _js_guarded(self, js, session_id=None):
        sid = self._session_id if session_id is None else session_id
        self._page.run_js(js, sid)

    def _start_dl_scan(self, session_id):
        if not self.books_cache:
            return
        self._js_guarded('showScanNotification("正在扫描下载记录...")', session_id)
        runnable = _ScanRunnable(session_id, self.books_cache.copy(), self.gui.rv_tools)
        runnable.signals.scan_done.connect(self._on_dl_scan_done)
        runnable.signals.scan_error.connect(self._on_dl_scan_error)
        QThreadPool.globalInstance().start(runnable)

    def _on_dl_scan_done(self, session_id, matched):
        if session_id != self._session_id:
            return
        for book_key, book_show in matched.items():
            if book_key not in self.books_cache:
                continue
            dl_max_js = json.dumps(str(book_show.dl_max), ensure_ascii=False)
            self._js_guarded(f"renderCardBadgeDl('{book_key}', {dl_max_js})", session_id)
        self._js_guarded("hideScanNotification()", session_id)
        batch_items = []
        for book_key in matched:
            if book_key not in self.books_cache or book_key in self.episodes_cache:
                continue
            token = (session_id, book_key)
            if token in self._inflight_books:
                continue
            self._inflight_books.add(token)
            batch_items.append((book_key, self.books_cache[book_key], self.site_index))
        if batch_items:
            self._ensure_worker().enqueue_episodes_batch(batch_items)

    def _on_dl_scan_error(self, session_id, error):
        if session_id != self._session_id:
            return
        self.gui.log.error(error)
        self._js_guarded("hideScanNotification()", session_id)

    def start_fetch_episodes(self, book_key):
        if book_key not in self.books_cache:
            return
        if book_key in self.episodes_cache:
            self._on_episodes_done(book_key, self.episodes_cache[book_key])
            return
        token = (self._session_id, book_key)
        if token in self._inflight_books:
            return
        self._inflight_books.add(token)
        self._ensure_worker().enqueue_episodes(
            book_key, self.books_cache[book_key], self.site_index
        )

    def _on_episodes_done(self, book_key, episodes):
        if book_key not in self.books_cache:
            return
        self._inflight_books.discard((self._session_id, book_key))
        self.episodes_cache[book_key] = episodes
        ep_data = [{"idx": ep.idx, "name": ep.name} for ep in episodes]
        js_arg = json.dumps(json.dumps(ep_data, ensure_ascii=False))
        self._js_guarded(f"updateEpisodes('{book_key}', {js_arg})", self._session_id)
        if dled_ids := self._mark_downloaded_episodes(book_key, episodes):
            dled_json = json.dumps(dled_ids)
            self._js_guarded(f"markDownloadedEpisodes({dled_json})", self._session_id)
        if episodes:
            with_idx = [ep for ep in episodes if isinstance(getattr(ep, "idx", None), (int, float))]
            latest_ep = max(with_idx, key=lambda ep: ep.idx) if with_idx else episodes[-1]
            latest_name = json.dumps(str(getattr(latest_ep, "name", "") or ""), ensure_ascii=False)
            self._js_guarded(f"renderCardBadgeLatest('{book_key}', {latest_name})", self._session_id)

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

    def _on_episodes_error(self, book_key, error):
        self._inflight_books.discard((self._session_id, book_key))
        self.gui.log.error(error)
        key_js = json.dumps(str(book_key))
        code_js = json.dumps("fetch_failed")
        self._js_guarded(f"showEpisodeFetchError({key_js}, {code_js})", self._session_id)

    def _handle_ensure_result(self):
        checked_ids = self.gui.BrowserWindow.output if self.gui.BrowserWindow else []
        if not checked_ids:
            return
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

        for book_key, ep_idxes in grouped.items():
            if book_key not in self.books_cache or book_key not in self.episodes_cache:
                continue
            book = self.books_cache[book_key]
            all_episodes = self.episodes_cache[book_key]
            selected_set = set(ep_idxes)
            selected_eps = [ep for ep in all_episodes if ep.idx in selected_set]
            if not selected_eps:
                continue
            assert all(ep.from_book is book for ep in selected_eps)
            book.episodes = selected_eps
            self.gui.ensure_work_thread()
            self.gui.submit_decision("EP", book)
