from utils.preview import PreviewHtml


class EroPreviewFeature:
    def __init__(self, mgr):
        self._mgr = mgr
        self.gui = mgr.gui

    def shutdown(self):
        pass

    def reset(self):
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
        self.gui.present_browser(
            ensure_handler=None,
            enable_page_frame=True,
            reload_tf=reload_tf,
        )
