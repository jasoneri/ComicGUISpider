from utils.preview import PreviewByFixHtml, El
from GUI.manager.preview.manga import MangaPreviewFeature


class FixPreviewFeature(MangaPreviewFeature):
    def __init__(self, mgr):
        super().__init__(mgr)
        self._inflight_book_pages = {}

    @staticmethod
    def is_episode_card(book) -> bool:
        return bool(getattr(book, "episodes", None) or "青年漫" in (getattr(book, "btype", None) or ""))

    def _clear_fix_state(self):
        self._inflight_book_pages.clear()

    def publish(self, books):
        self.mgr.begin_preview_session()
        self._inflight_books.clear()
        self._clear_fix_state()
        self.mgr.books_cache = {str(book.idx): book for book in books}
        direct_books = [
            book for book in books
            if not self.is_episode_card(book)
        ]
        self.mgr.downloaded_book_ids = {
            str(book.idx) for book in self.gui.download_state.downloaded_items(direct_books)
        }
        self.episodes_cache.clear()
        self.gui.clean_temp_file()
        upper_cards = []
        lower_cards = []
        ero_el = El(None)
        manga_el = El("manga")
        for book in books:
            if self.is_episode_card(book):
                lower_cards.append(manga_el.create_from_book(book, with_favorite=False))
            else:
                upper_cards.append(ero_el.create_from_book(book))
        self.gui.tf = PreviewByFixHtml.created_temp_html(
            upper_html="\n".join(upper_cards),
            lower_html="\n".join(lower_cards),
        )
        self.mgr.show_preview(
            ensure_handler=self._handle_submit_request,
            bridge=self.bridge,
        )

    def shutdown(self):
        self._clear_fix_state()
        super().shutdown()

    def reset(self):
        self._clear_fix_state()
        super().reset()

    def _on_page_ready(self, session_id):
        if self.mgr.downloaded_book_ids:
            self.mgr.send_command(
                "preview.books.downloaded",
                {"bookIds": sorted(self.mgr.downloaded_book_ids)},
                session_id=session_id,
            )
        if self.mgr.books_cache and session_id not in self._dl_scan_runnables:
            self._start_dl_scan(session_id)

    def _hide_scan_if_idle(self):
        if not self._inflight_pages and not self._inflight_book_pages:
            self.mgr.send_command("preview.scan.hide", {})

    @staticmethod
    def _same_book(left, right) -> bool:
        if left is None or right is None:
            return False
        return (
            left is right
            or (
                getattr(left, "preview_url", None)
                and getattr(left, "preview_url", None) == getattr(right, "preview_url", None)
            )
            or (
                getattr(left, "url", None)
                and getattr(left, "url", None) == getattr(right, "url", None)
            )
        )

    def _submit_direct_books(self, books):
        ready_books = []
        batch_items = []
        for book in books:
            book_key = str(getattr(book, "idx", ""))
            if book.pages is not None:
                ready_books.append(book)
                continue
            if not book_key or book_key in self._inflight_book_pages:
                continue
            self._inflight_book_pages[book_key] = book
            batch_items.append((book_key, book, self.mgr.site_index))
        if ready_books:
            self.gui.sel_mgr.submit_decision(
                "BOOK", ready_books, flow_stage=self.gui.flow_stage,
            )
        if batch_items and self.mgr.worker:
            self.mgr.worker.enqueue_pages_batch(batch_items)

    def _submit_selected_episodes_for_book(self, book_key, book, selected_eps):
        if not selected_eps:
            return
        needs_pages = [ep for ep in selected_eps if ep.pages is None]
        if not needs_pages:
            book.episodes = list(selected_eps)
            self.gui.sel_mgr.submit_decision("EP", book)
            return
        if book_key in self._inflight_pages:
            return
        self._inflight_pages[book_key] = (book, selected_eps)
        batch_items = [(book_key, ep, self.mgr.site_index) for ep in needs_pages]
        if batch_items and self.mgr.worker:
            self.mgr.worker.enqueue_pages_batch(batch_items)

    def _on_dl_scan_done(self, session_id, matched):
        self._release_dl_scan(session_id)
        if session_id != self.mgr._session_id:
            return
        badges = []
        for book_key, book_show in matched.items():
            if book_key not in self.mgr.books_cache:
                continue
            badges.append({"bookKey": str(book_key), "dlMax": str(book_show.dl_max)})
        if badges:
            self.mgr.send_command(
                "manga.dl_scan.result",
                {"badges": badges}, session_id=session_id,
            )
        self.mgr.send_command("preview.scan.hide", {}, session_id=session_id)
        batch_items = []
        for book_key in matched:
            if book_key not in self.mgr.books_cache or book_key in self.episodes_cache:
                continue
            book = self.mgr.books_cache[book_key]
            if not self.is_episode_card(book):
                continue
            token = (session_id, book_key)
            if token in self._inflight_books:
                continue
            batch_items.append((session_id, book_key, book, self.mgr.site_index))
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

    def start_fetch_episodes(self, book_key):
        book = self.mgr.books_cache.get(book_key)
        if book is None or not self.is_episode_card(book):
            return
        super().start_fetch_episodes(book_key)

    def on_pages_done(self, generation, book_key, items):
        book = self._inflight_book_pages.pop(book_key, None)
        if book is not None:
            if generation == self.mgr._generation:
                ready_book = next((item for item in items if hasattr(item, "to_tasks_obj")), book)
                cached_book = self.mgr.books_cache.get(book_key)
                if self._same_book(cached_book, book):
                    self.mgr.books_cache[book_key] = ready_book
                self.gui.sel_mgr.submit_decision(
                    "BOOK", ready_book, flow_stage=self.gui.flow_stage,
                )
            self._hide_scan_if_idle()
            return
        pending = self._inflight_pages.pop(book_key, None)
        if pending is None:
            return
        if generation == self.mgr._generation:
            book, selected_eps = pending
            book.episodes = list(selected_eps)
            self.gui.sel_mgr.submit_decision("EP", book)
        self._hide_scan_if_idle()

    def on_pages_error(self, generation, book_key, error):
        book = self._inflight_book_pages.pop(book_key, None)
        if book is not None:
            if generation == self.mgr._generation:
                self.gui.log.error(error)
            self._hide_scan_if_idle()
            return
        pending = self._inflight_pages.pop(book_key, None)
        if pending is not None and generation == self.mgr._generation:
            self.gui.log.error(error)
            self.mgr.send_command(
                "manga.episodes.error",
                {"bookKey": str(book_key), "code": "pages_fetch_failed"},
            )
        self._hide_scan_if_idle()

    def _submit_payload(self, payload: dict):
        selected_episodes = self._parse_selected_episodes(payload)
        self._submit_selected_episodes(selected_episodes)

        direct_books = []
        for book_id in payload["book_ids"]:
            book = self.mgr.books_cache.get(book_id)
            if book is None or self.is_episode_card(book):
                continue
            direct_books.append(book)
        if direct_books:
            self._submit_direct_books(direct_books)

    def submit_page_selections(self):
        self._submit_payload(self._current_submit_payload())

    def _handle_submit_request(self):
        self._submit_payload(self._current_submit_payload())
