# -*- coding: utf-8 -*-
"""Cover + DL-scan session owner for subscribe waterfall."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QPixmap

from utils.subscription.library import LocalLibraryStore

from .card import SubscribeCard
from .workers import (
    CoverFetchTask,
    DlScanWorker,
    SubscribeCoverWorker,
    disconnect_cover_worker,
    disconnect_dl_scan_worker,
    load_cover_disk_cache,
)

if TYPE_CHECKING:
    from .window import SubscribeWindow


class CoverSession(QObject):
    """Generation-gated cover fetch + manga DL badge scan for the library board."""

    def __init__(
        self,
        host: "SubscribeWindow",
        *,
        cards_by_key: Callable[[], dict[str, SubscribeCard]],
        cards: Callable[[], list[SubscribeCard]],
        is_closing: Callable[[], bool],
        parent: QObject | None = None,
    ):
        super().__init__(parent if parent is not None else host)
        self._host = host
        self._cards_by_key = cards_by_key
        self._cards = cards
        self._is_closing = is_closing
        self.cover_inflight: set[str] = set()
        self.cover_cache: dict[str, bytes] = {}
        self.cover_generation = 0
        self.dl_scan_generation = 0
        self._cover_worker: SubscribeCoverWorker | None = None
        self._dl_scan_worker: DlScanWorker | None = None

    @property
    def closing(self) -> bool:
        return bool(self._is_closing())

    def invalidate_covers(self) -> None:
        self.cover_generation += 1
        self.cover_inflight.clear()

    def forget_card(self, card_key: str) -> None:
        key = str(card_key or "")
        self.cover_cache.pop(key, None)
        self.cover_inflight.discard(key)

    def apply_cover_for_card(self, card: SubscribeCard) -> None:
        """Local file → memory/disk cache → remote schedule."""
        if card.try_load_local_cover():
            return
        key = card.card_key
        cached = self.cover_cache.get(key)
        if not cached:
            cached = load_cover_disk_cache(key)
            if cached:
                self.cover_cache[key] = cached
        if cached:
            pixmap = QPixmap()
            pixmap.loadFromData(cached)
            card.set_cover_pixmap(pixmap, source="cache")
            return
        if card.needs_remote_cover():
            self.schedule_cover_fetch(card)

    def shutdown(self, *, wait: bool = True) -> None:
        self.cover_generation += 1
        self.dl_scan_generation += 1
        self.cover_inflight.clear()
        self.stop_cover_worker(wait=wait)
        self.stop_dl_scan_worker(wait=wait)

    def ensure_cover_worker(self) -> SubscribeCoverWorker | None:
        if self.closing:
            return None
        worker = self._cover_worker
        if worker is not None and worker.isRunning():
            return worker
        if worker is not None:
            self.stop_cover_worker(wait=True)
        worker = SubscribeCoverWorker(self)
        worker.cover_done.connect(self._on_cover_done)
        worker.cover_error.connect(self._on_cover_error)
        worker.cover_meta.connect(self._on_cover_meta)
        worker.start()
        self._cover_worker = worker
        return worker

    def stop_cover_worker(self, *, wait: bool = False) -> None:
        worker = self._cover_worker
        self._cover_worker = None
        if worker is None:
            return
        disconnect_cover_worker(worker)
        worker.stop()
        if wait and worker.isRunning():
            worker.wait(5000)
        if worker.isRunning():
            worker.finished.connect(worker.deleteLater)
        else:
            worker.deleteLater()

    def stop_dl_scan_worker(self, *, wait: bool = False) -> None:
        worker = self._dl_scan_worker
        self._dl_scan_worker = None
        if worker is None:
            return
        disconnect_dl_scan_worker(worker)
        if wait and worker.isRunning():
            worker.wait(3000)
        if worker.isRunning():
            worker.finished.connect(worker.deleteLater)
        else:
            worker.deleteLater()

    def schedule_cover_fetch(self, card: SubscribeCard) -> None:
        if self.closing:
            return
        key = card.card_key
        if key in self.cover_inflight or key in self.cover_cache:
            return
        if not card.needs_remote_cover():
            return
        worker = self.ensure_cover_worker()
        if worker is None:
            return
        self.cover_inflight.add(key)
        book_url = LocalLibraryStore.book_unique_url(card.book) or str(
            getattr(card, "_site_url", "") or ""
        )
        worker.enqueue(
            CoverFetchTask(
                generation=self.cover_generation,
                card_key=key,
                site_index=int(card.site_index),
                tasks_obj=card.to_cover_tasks_obj(),
                book_url=str(book_url or ""),
            )
        )

    def start_dl_scan(self) -> None:
        cards = self._cards()
        if not cards or self.closing:
            return
        gui = self._host.gui
        rv_tools = getattr(gui, "rv_tools", None) if gui is not None else None
        if rv_tools is None:
            return
        titles_by_key = {
            card.card_key: LocalLibraryStore.book_title(card.book)
            for card in cards
        }
        self.stop_dl_scan_worker()
        self.dl_scan_generation += 1
        generation = self.dl_scan_generation
        worker = DlScanWorker(
            generation=generation,
            titles_by_key=titles_by_key,
            rv_tools=rv_tools,
            parent=self,
        )
        worker.scan_done.connect(self._on_dl_scan_finished)
        worker.scan_error.connect(self._on_dl_scan_error)
        worker.finished.connect(self._on_dl_scan_worker_finished)
        self._dl_scan_worker = worker
        worker.start()

    @Slot(int, object)
    def _on_dl_scan_finished(self, generation: int, matched) -> None:
        if self.closing or int(generation) != int(self.dl_scan_generation):
            return
        if not isinstance(matched, dict) or not matched:
            return
        cards_by_key = self._cards_by_key()
        for card_key, book_show in matched.items():
            card = cards_by_key.get(str(card_key))
            if card is None:
                continue
            dl_max = str(getattr(book_show, "dl_max", "") or "").strip()
            if not dl_max:
                continue
            card.apply_dl_scan_badge(dl_max=dl_max)

    @Slot(int, str)
    def _on_dl_scan_error(self, generation: int, message: str) -> None:
        if self.closing or int(generation) != int(self.dl_scan_generation):
            return
        logger = getattr(self._host.gui, "log", None) if self._host.gui is not None else None
        if logger is not None:
            logger.warning(f"[subscribe.dl_scan] {message}")

    @Slot()
    def _on_dl_scan_worker_finished(self) -> None:
        worker = self.sender()
        if worker is None:
            return
        if worker is self._dl_scan_worker:
            self._dl_scan_worker = None
        disconnect_dl_scan_worker(worker)
        worker.deleteLater()

    @Slot(int, str, object)
    def _on_cover_done(self, generation: int, card_key: str, data) -> None:
        if self.closing or int(generation) != int(self.cover_generation):
            return
        key = str(card_key)
        self.cover_inflight.discard(key)
        if not data:
            return
        self.cover_cache[key] = data
        card = self._cards_by_key().get(key)
        if card is None:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            logger = getattr(self._host.gui, "log", None) if self._host.gui is not None else None
            if logger is not None:
                logger.warning(f"[subscribe.cover] decode failed card={key}")
            return
        card.set_cover_pixmap(pixmap, source="cache")

    @Slot(int, str, str)
    def _on_cover_meta(self, generation: int, card_key: str, cover_url: str) -> None:
        if self.closing or int(generation) != int(self.cover_generation):
            return
        key = str(card_key)
        cover = str(cover_url or "").strip()
        if not cover.startswith(("http://", "https://")):
            return
        card = self._cards_by_key().get(key)
        if card is None:
            return
        setattr(card.book, "img_preview", cover)
        book_url = LocalLibraryStore.book_unique_url(card.book)
        if not book_url:
            return
        try:
            self._host.library.update_book_img_preview(int(card.site_index), book_url, cover)
        except Exception as exc:
            logger = getattr(self._host.gui, "log", None) if self._host.gui is not None else None
            if logger is not None:
                logger.warning(f"[subscribe.cover] persist img_preview failed card={key}: {exc}")

    @Slot(int, str, str)
    def _on_cover_error(self, generation: int, card_key: str, message: str) -> None:
        if self.closing or int(generation) != int(self.cover_generation):
            return
        key = str(card_key)
        self.cover_inflight.discard(key)
        logger = getattr(self._host.gui, "log", None) if self._host.gui is not None else None
        if logger is not None:
            logger.warning(f"[subscribe.cover] {key} | {message}")
