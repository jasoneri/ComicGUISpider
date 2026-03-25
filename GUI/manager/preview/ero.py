import contextlib
import json

from utils import conf
from utils.preview import PreviewHtml


class EroPreviewFeature:
    def __init__(self, mgr):
        self._mgr = mgr
        self.gui = mgr.gui
        self._pending_mark_browser = None

    def shutdown(self):
        self._disconnect_mark_sync()

    def reset(self):
        self._disconnect_mark_sync()
        browser = getattr(self.gui, "BrowserWindow", None)
        if browser:
            browser.set_ensure_handler()

    def publish(self, books):
        self._mgr._session_id += 1
        self._mgr.books_cache = {str(book.idx): book for book in books}
        self.gui.clean_temp_file()
        infos = self.gui.mark_tip(self._mgr.books_cache)
        preview = PreviewHtml("", infos)
        preview.duel_contents()
        self.gui.tf = preview.created_temp_html
        self._show_browser(reload_tf=True)

    def show_cached(self):
        self._show_browser(reload_tf=False)

    def _show_browser(self, reload_tf=True):
        browser = self.gui.present_browser(
            ensure_handler=None,
            enable_page_frame=True,
            reload_tf=reload_tf,
        )
        if reload_tf:
            self._sync_download_marks(browser)

    def _downloaded_book_ids(self):
        return [
            key for key, book in self._mgr.books_cache.items()
            if getattr(book, "mark_tip", None) == "downloaded"
        ]

    def _sync_download_marks(self, browser):
        self._disconnect_mark_sync()
        if not conf.isDeduplicate:
            return

        downloaded_ids = self._downloaded_book_ids()
        if not downloaded_ids:
            return

        def on_load_finished(ok):
            if not ok:
                self._disconnect_mark_sync()
                return
            js_code = f"previewRuntime.markDownloaded({json.dumps(downloaded_ids)}, []);"
            browser.page_runtime.run_js(js_code, self._write_marked_html)
            self._disconnect_mark_sync()

        browser.view.loadFinished.connect(on_load_finished)
        self._pending_mark_browser = (browser, on_load_finished)

    def _disconnect_mark_sync(self):
        if not self._pending_mark_browser:
            return
        browser, callback = self._pending_mark_browser
        with contextlib.suppress(TypeError, RuntimeError):
            browser.view.loadFinished.disconnect(callback)
        self._pending_mark_browser = None

    def _write_marked_html(self, html):
        if html and self.gui.tf:
            with open(self.gui.tf, "w", encoding="utf-8") as f:
                f.write(html)
