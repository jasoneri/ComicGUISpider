import json

from assets import res as ori_res
from utils import conf
from utils.preview import PreviewHtml
from variables import DEFAULT_COMPLETER


class EroPreviewFeature:
    def __init__(self, mgr):
        self._mgr = mgr
        self.gui = mgr.gui

    def shutdown(self):
        pass

    def reset(self):
        pass

    def publish(self, books):
        self._mgr.begin_preview_session()
        self._mgr.books_cache = {str(book.idx): book for book in books}
        downloaded_md5s = self.gui.download_state.downloaded_md5s(self._mgr.books_cache.values())
        self._mgr.downloaded_book_ids = {
            key
            for key, book in self._mgr.books_cache.items()
            if hasattr(book, "id_and_md5") and book.id_and_md5()[1] in downloaded_md5s
        }
        self.gui.clean_temp_file()
        infos = sorted(self._mgr.books_cache.values(), key=lambda item: item.idx)
        preview = PreviewHtml("", infos)
        preview.duel_contents()
        self.gui.tf = preview.created_temp_html
        # ensure_handler=None → checked_ids + gui.next → submit_browser_selection
        # → BOOK lane → spider (parse_section 等) 落地; 与搜索 ero 同路。
        self._mgr.show_preview()

    def _show_online_fav(self, books):
        """线上收藏 → 正式 ero preview 网格 (与搜索/index.html 同路基 + 可下载)。"""
        for idx, book in enumerate(books):
            book.idx = idx
        self._mgr._is_local_mode = True
        self._mgr._current_page = 1
        self._mgr._active_keyword = ori_res.GUI.online_fav
        self.publish(books)

    def _ensure_online_fav_completer(self):
        """线上收藏关键词注入 completer (与 manga 对称, ehentai 等 ero 站入口)。"""
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
        self._mgr.show_preview(reload_tf=False)

    def _on_page_ready(self, session_id):
        if not conf.isDeduplicate:
            return
        if not self._mgr.downloaded_book_ids:
            return
        js_code = (
            f"previewRuntime.markDownloaded({json.dumps(sorted(self._mgr.downloaded_book_ids))}, []);"
        )
        self._mgr._legacy_run_js(js_code, session_id)
