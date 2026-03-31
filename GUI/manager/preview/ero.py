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
        self.gui.clean_temp_file()
        infos = self.gui.mark_tip(self._mgr.books_cache)
        preview = PreviewHtml("", infos)
        preview.duel_contents()
        self.gui.tf = preview.created_temp_html
        self._mgr.show_preview()

    def show_cached(self):
        self._mgr.show_preview(reload_tf=False)

    def _downloaded_book_ids(self):
        return [
            key for key, book in self._mgr.books_cache.items()
            if getattr(book, "mark_tip", None) == "downloaded"
        ]

    def _on_page_ready(self, session_id):
        if not conf.isDeduplicate:
            return
        downloaded_ids = self._downloaded_book_ids()
        if not downloaded_ids:
            return
        js_code = f"previewRuntime.markDownloaded({json.dumps(downloaded_ids)}, []);"
        self._mgr._legacy_run_js(js_code, session_id)
