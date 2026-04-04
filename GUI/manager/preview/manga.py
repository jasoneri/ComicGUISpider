import json
import pickle
import tempfile
import traceback
from collections import defaultdict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from assets import res as ori_res
from variables import SPIDERS
from utils import bs_theme, conf, temp_p, conf_dir
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
        self._fav_completer_exists = False
        self._check_lc_completer_exists()

    def shutdown(self):
        self.reset()

    def reset(self):
        self.episodes_cache.clear()
        self._inflight_books.clear()
        self._inflight_pages.clear()
        self._dl_scan_runnables.clear()

    def check_lc_completer(self):
        self._check_lc_completer_exists()

    def publish(self, books):
        self.mgr.begin_preview_session()
        self._inflight_books.clear()
        self.mgr.books_cache = {str(book.idx): book for book in books}
        self.mgr.downloaded_book_ids.clear()
        self.episodes_cache.clear()
        self.gui.clean_temp_file()
        self.gui.tf = self._write_cards_html(self._build_cards_html(books))
        self.mgr.show_preview(
            ensure_handler=self._handle_submit_request,
            bridge=self.bridge,
        )

    def show_cached(self):
        self.mgr.show_preview(
            ensure_handler=self._handle_submit_request,
            reload_tf=False,
            bridge=self.bridge,
        )

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
        self.mgr.send_command(
            "manga.favorite.state",
            {"bookKey": str(book_key), "isFavorited": bool(final_state)},
        )

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

    def _on_page_ready(self, session_id):
        self._sync_page_favorites(session_id)
        if self.mgr.books_cache and session_id not in self._dl_scan_runnables:
            self._start_dl_scan(session_id)

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
            self.mgr.send_command(
                "manga.favorites.sync",
                {"bookKeys": fav_keys},
                session_id=session_id,
            )

    @staticmethod
    def _latest_badge_payload(book_key, episodes):
        if not episodes:
            return None
        with_idx = [ep for ep in episodes if isinstance(getattr(ep, "idx", None), (int, float))]
        latest_ep = max(with_idx, key=lambda ep: ep.idx) if with_idx else episodes[-1]
        return {
            "bookKey": str(book_key),
            "latestEpName": str(getattr(latest_ep, "name", "") or ""),
        }

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
        self.mgr.send_command(
            "preview.scan.show",
            {"message": "正在扫描下载记录..."},
            session_id=session_id,
        )
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
        badges = []
        batch_items = []
        for book_key, book_show in matched.items():
            book = self.mgr.books_cache.get(book_key)
            if book is None:
                continue
            badge = {"bookKey": str(book_key), "dlMax": str(book_show.dl_max)}
            if book_key in self.episodes_cache:
                latest_payload = self._latest_badge_payload(book_key, self.episodes_cache[book_key])
                if latest_payload:
                    badge["latestEpName"] = latest_payload["latestEpName"]
                badges.append(badge)
                continue
            token = (session_id, book_key)
            if token in self._inflight_books:
                badges.append(badge)
                continue
            badges.append(badge)
            batch_items.append((session_id, book_key, book, self.mgr.site_index))
        if badges:
            self.mgr.send_command(
                "manga.dl_scan.result",
                {"badges": badges},
                session_id=session_id,
            )
        self.mgr.send_command("preview.scan.hide", {}, session_id=session_id)
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
        self.mgr.send_command("preview.scan.hide", {}, session_id=session_id)

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
        downloaded_items = self.gui.download_state.downloaded_items(episodes)
        downloaded_md5s = {episode.id_and_md5()[1] for episode in downloaded_items}
        downloaded_episode_ids = {
            f"ep{book_key}-{episode.idx}"
            for episode in episodes
            if episode.id_and_md5()[1] in downloaded_md5s
        }
        ep_data = [
            {
                "idx": ep.idx,
                "name": ep.name,
                "downloaded": f"ep{book_key}-{ep.idx}" in downloaded_episode_ids,
            }
            for ep in episodes
        ]
        self.mgr.send_command(
            "manga.episodes.loaded",
            {"bookKey": str(book_key), "episodes": ep_data},
            session_id=session_id,
        )
        if latest_payload := self._latest_badge_payload(book_key, episodes):
            self.mgr.send_command(
                "manga.badge.latest",
                latest_payload,
                session_id=session_id,
            )

    def on_episodes_error(self, generation, session_id, book_key, error):
        self._inflight_books.discard((session_id, book_key))
        if generation != self.mgr._generation or session_id != self.mgr._session_id:
            return
        self.gui.log.error(error)
        self.mgr.send_command(
            "manga.episodes.error",
            {"bookKey": str(book_key), "code": "fetch_failed"},
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Pages fetch
    # ------------------------------------------------------------------

    def on_pages_done(self, generation, book_key, episodes):
        pending = self._inflight_pages.pop(book_key, None)
        if pending is None:
            return
        if generation != self.mgr._generation:
            if not self._inflight_pages:
                self.mgr.send_command("preview.scan.hide", {})
            return
        book, selected_eps = pending
        book.episodes = list(selected_eps)
        self.gui.sel_mgr.submit_decision("EP", book)
        if not self._inflight_pages:
            self.mgr.send_command("preview.scan.hide", {})

    def on_pages_error(self, generation, book_key, error):
        self._inflight_pages.pop(book_key, None)
        if generation == self.mgr._generation:
            self.gui.log.error(error)
            self.mgr.send_command(
                "manga.episodes.error",
                {"bookKey": str(book_key), "code": "pages_fetch_failed"},
            )
        if not self._inflight_pages:
            self.mgr.send_command("preview.scan.hide", {})

    # ------------------------------------------------------------------
    # Selection / ensure
    # ------------------------------------------------------------------

    def _current_submit_payload(self) -> dict:
        output = self.gui.BrowserWindow.output if self.gui.BrowserWindow else None
        if output in (None, []):
            return {"book_ids": [], "episode_ids": []}
        if not isinstance(output, dict):
            raise TypeError(f"preview submit payload must be dict, got {type(output).__name__}")
        action = output.get("action")
        if action not in (None, "submit-download"):
            raise ValueError(f"unexpected preview submit action: {action!r}")
        book_ids = output.get("bookIds") or []
        episode_ids = output.get("episodeIds") or []
        if not isinstance(book_ids, list):
            raise TypeError(f"preview submit payload bookIds must be list, got {type(book_ids).__name__}")
        if not isinstance(episode_ids, list):
            raise TypeError(f"preview submit payload episodeIds must be list, got {type(episode_ids).__name__}")
        return {
            "book_ids": [str(book_id) for book_id in book_ids if book_id not in (None, "")],
            "episode_ids": [str(ep_id) for ep_id in episode_ids if ep_id not in (None, "")],
        }

    def _parse_selected_episodes(self, payload: dict) -> dict:
        checked_ids = payload["episode_ids"]
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

    def _submit_selected_episodes(self, parsed: dict):
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

    def _submit_payload(self, payload: dict):
        self._submit_selected_episodes(self._parse_selected_episodes(payload))

    def submit_page_selections(self):
        self._submit_payload(self._current_submit_payload())

    def _handle_submit_request(self):
        self._submit_payload(self._current_submit_payload())
