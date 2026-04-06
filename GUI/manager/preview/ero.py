import json

from utils import conf
from utils.preview import PreviewHtml


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
        self._mgr.show_preview()

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
