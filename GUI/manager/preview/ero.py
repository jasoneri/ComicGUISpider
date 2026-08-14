import json

from PySide6.QtCore import QThreadPool

from assets import res as ori_res
from utils import conf
from utils.preview import PreviewHtml
from utils.subscription.library import LocalLibraryStore
from variables import DEFAULT_COMPLETER
from GUI.manager.preview.manga import _BookMd5DedupRunnable


class EroPreviewFeature:
    def __init__(self, mgr):
        self._mgr = mgr
        self.gui = mgr.gui
        self._library = LocalLibraryStore()
        self._fav_completer_exists = False
        self._book_dedup_runnable = None
        self._check_lc_completer_exists()

    def shutdown(self):
        self._book_dedup_runnable = None

    def reset(self):
        self._book_dedup_runnable = None
        self._mgr.downloaded_book_ids.clear()

    def publish(self, books):
        self._mgr.begin_preview_session()
        self._mgr.books_cache = {str(book.idx): book for book in books}
        self._mgr.downloaded_book_ids.clear()
        self.gui.clean_temp_file()
        infos = sorted(self._mgr.books_cache.values(), key=lambda item: item.idx)
        preview = PreviewHtml("", infos)
        preview.duel_contents()
        self.gui.tf = preview.created_temp_html
        self._mgr.show_preview(bridge=self._mgr._manga.bridge)
        self._start_book_dedup(self._mgr._session_id)

    def _show_online_fav(self, books):
        for idx, book in enumerate(books):
            book.idx = idx
        self._mgr._is_local_mode = True
        self._mgr._current_page = 1
        self._mgr._active_keyword = ori_res.GUI.online_fav
        self.publish(books)

    def _show_local_fav(self):
        books = self._library.load(self._mgr.site_index)
        for idx, book in enumerate(books):
            book.idx = idx
        self._mgr._is_local_mode = True
        self._mgr._current_page = 1
        self.publish(books)

    def toggle_favorite(self, book_key):
        book = self._mgr.books_cache.get(str(book_key))
        if book is None:
            return
        final_state = self._library.toggle(self._mgr.site_index, book)
        if final_state is None:
            return
        if final_state and not self._fav_completer_exists:
            self._ensure_local_fav_completer()
            self._fav_completer_exists = True
        self._mgr.send_command(
            "manga.favorite.state",
            {"bookKey": str(book_key), "isFavorited": bool(final_state)},
        )
        if final_state:
            self._mgr.follow.after_library_added(str(book_key), book)

    def _check_lc_completer_exists(self):
        keyword = ori_res.GUI.local_fav
        completer_list = conf.completer.get(self._mgr.site_index)
        self._fav_completer_exists = bool(completer_list and keyword in completer_list)

    def _ensure_local_fav_completer(self):
        idx = self._mgr.site_index
        keyword = ori_res.GUI.local_fav
        completer_list = conf.completer.get(idx)
        if completer_list is None:
            completer_list = list(DEFAULT_COMPLETER.get(idx, []))
            conf.completer[idx] = completer_list
        if keyword not in completer_list:
            completer_list.insert(0, keyword)
            conf.update()
            self.gui.set_completer()

    def _ensure_online_fav_completer(self):
        idx = self._mgr.site_index
        keyword = ori_res.GUI.online_fav
        completer_list = conf.completer.get(idx)
        if completer_list is None:
            completer_list = list(DEFAULT_COMPLETER.get(idx, []))
            conf.completer[idx] = completer_list
        if keyword not in completer_list:
            completer_list.insert(0, keyword)
            conf.update()
            self.gui.set_completer()

    def show_cached(self):
        self._mgr.show_preview(reload_tf=False, bridge=self._mgr._manga.bridge)

    def _on_page_ready(self, session_id):
        self._sync_page_favorites(session_id)
        self._project_downloaded_if_ready(session_id)

    def _start_book_dedup(self, session_id: int) -> None:
        if not conf.isDeduplicate:
            return
        books = list(self._mgr.books_cache.values())
        if not books:
            return
        runnable = _BookMd5DedupRunnable(session_id, books, self.gui.download_state)
        runnable.signals.done.connect(self._on_book_dedup_done)
        self._book_dedup_runnable = runnable
        QThreadPool.globalInstance().start(runnable)

    def _on_book_dedup_done(self, session_id: int, book_keys) -> None:
        if session_id != self._mgr._session_id:
            return
        self._mgr.downloaded_book_ids = set(book_keys or ())
        self._book_dedup_runnable = None
        self._project_downloaded_if_ready(session_id)

    def _project_downloaded_if_ready(self, session_id: int) -> None:
        if not conf.isDeduplicate or not self._mgr.downloaded_book_ids:
            return
        browser = getattr(self.gui, "BrowserWindow", None)
        if not browser or not browser.page_runtime.page_ready:
            return
        js_code = (
            f"previewRuntime.markDownloaded({json.dumps(sorted(self._mgr.downloaded_book_ids))}, []);"
        )
        self._mgr._legacy_run_js(js_code, session_id)

    def _sync_page_favorites(self, session_id):
        if not self._mgr.books_cache:
            return
        if self._mgr._is_local_mode:
            fav_keys = list(self._mgr.books_cache.keys())
        else:
            favorite_urls = self._library.urls(self._mgr.site_index)
            fav_keys = [
                key for key, book in self._mgr.books_cache.items()
                if LocalLibraryStore.book_unique_url(book) in favorite_urls
            ]
        self._mgr.send_command("manga.favorites.sync", {"bookKeys": fav_keys}, session_id=session_id)
