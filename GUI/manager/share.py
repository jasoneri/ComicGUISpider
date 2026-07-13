from __future__ import annotations

import typing as t
from copy import deepcopy
from dataclasses import dataclass

from PySide6.QtCore import Qt, QObject, Signal
from qfluentwidgets import InfoBar, InfoBarPosition

from GUI.manager.async_task import AsyncTaskManager
from utils import conf
from utils.share import DiscordShareAPI, DiscordSharePayloadTooLargeError, build_cover_bytes, deserialize_books, serialize_books
from utils.website.info import BookInfo, Episode
from variables import CGS_DISCORD_SHARE_API

_UPLOAD_SIZE_LIMIT_BYTES = 10 * 1024 * 1024
SHARE_UPLOAD_MAX_BOOKS = 10


@dataclass(slots=True)
class ShareUploadResult:
    share_id: str
    site: str
    book_count: int
    total_pages: int
    uploaded_urls: tuple[str, ...]


class Shares(QObject):
    changed = Signal()
    upload_started = Signal()
    upload_finished = Signal(object)

    def __init__(self, gui):
        parent = gui if isinstance(gui, QObject) else None
        super().__init__(parent)
        self.gui = gui
        self._items: list[BookInfo] = []
        self.site = ""
        self._uploading = False
        self.task_mgr = AsyncTaskManager(gui, gui)

    @property
    def items(self) -> list[BookInfo]:
        return self.snapshot()

    def is_empty(self) -> bool:
        return not self._items

    def is_uploading(self) -> bool:
        return self._uploading

    def server_mode_switch_blockers(self) -> list[str]:
        blockers = []
        if self._uploading:
            blockers.append("share upload")
        if self.task_mgr.get_running_tasks():
            blockers.append("share task")
        return blockers

    def count(self) -> int:
        return len(self._items)

    def snapshot(self) -> list[BookInfo]:
        return [deepcopy(item) for item in self._items]

    def contains_url(self, url: str) -> bool:
        target = self._normalize_url(url)
        if not target:
            return False
        return any(self._normalize_url(getattr(item, "url", None)) == target for item in self._items)

    def clear(self):
        self._items.clear()
        self.site = ""
        self.changed.emit()

    def add(self, book: BookInfo):
        if not isinstance(book, BookInfo):
            raise TypeError(f"share item must be BookInfo, got {type(book).__name__}")
        if not getattr(book, "source", ""):
            raise ValueError("share item missing source")
        book_url = self._normalize_url(getattr(book, "url", None))
        if not book_url:
            raise ValueError("share item missing url")
        if self.site and book.source != self.site:
            raise ValueError(f"curr share only support {self.site}")
        if any(self._normalize_url(getattr(item, "url", None)) == book_url for item in self._items):
            return False
        if len(self._items) >= SHARE_UPLOAD_MAX_BOOKS:
            raise ValueError(f"share batch full (max {SHARE_UPLOAD_MAX_BOOKS})")
        if not self.site:
            self.site = book.source
        cloned = deepcopy(book)
        cloned.local_path = getattr(book, "local_path", None)
        self._items.append(cloned)
        self.changed.emit()
        return True

    def remove_by_url(self, url: str):
        target_url = self._normalize_url(url)
        remained = [item for item in self._items if self._normalize_url(getattr(item, "url", None)) != target_url]
        if len(remained) == len(self._items):
            return
        self._items = remained
        if not self._items:
            self.site = ""
        self.changed.emit()

    def total_pages(self, books: t.Iterable[BookInfo] | None = None) -> int:
        total = 0
        for book in self._items if books is None else books:
            total += int(getattr(book, "pages", 0) or 0)
            for episode in list(getattr(book, "episodes", None) or []):
                total += int(getattr(episode, "pages", 0) or 0)
        return total

    @staticmethod
    def rebuild_from_share_payload(payload: dict) -> BookInfo:
        book = deepcopy(payload.get("book"))
        book.local_path = str(payload.get("local_path") or "")
        return book

    @staticmethod
    def build_share_payload(task_info) -> dict:
        if isinstance(task_info, Episode):
            source_book = deepcopy(task_info.from_book)
            source_book.episodes = [deepcopy(task_info)]
            source_book.episodes[0].from_book = source_book
            target = source_book
        elif isinstance(task_info, BookInfo):
            target = deepcopy(task_info)
            for episode in list(getattr(target, "episodes", None) or []):
                episode.from_book = target
        else:
            raise TypeError(f"unsupported share payload source: {type(task_info).__name__}")
        return {"book": target, "local_path": None}

    def _current_user_token(self) -> str:
        return str(conf.discord_share_user_token or "").strip()

    def _current_api_url(self) -> str:
        return str(CGS_DISCORD_SHARE_API or "").strip()

    def upload(self):
        upload_books = self.snapshot()
        self._uploading = True
        self.upload_started.emit()
        started = self.task_mgr.execute_simple_task(
            self._upload_impl,
            success_callback=self._on_upload_success,
            error_callback=self._on_upload_error,
            tooltip_title="discord share",
            tooltip_content="准备上传",
            success_message="分享上传完成",
            task_id="discord_share_upload",
            show_success_info=False,
            books_snapshot=upload_books,
        )
        if not started:
            self._uploading = False
            self.upload_finished.emit(None)
        return started

    async def _upload_impl(self, books_snapshot: list[BookInfo], *, progress_callback=None):
        if progress_callback is not None:
            progress_callback("生成分享文件")
        payload_bytes = serialize_books(books_snapshot)
        if progress_callback is not None:
            progress_callback("生成封面")
        covers: list[tuple[str, bytes]] = []
        book_names: list[str] = []
        uploaded_urls: list[str] = []
        for book in books_snapshot:
            cover_bytes = build_cover_bytes(book)
            covers.append((getattr(book, "name", "") or "", cover_bytes))
            book_names.append(getattr(book, "name", "") or "")
            uploaded_urls.append(self._normalize_url(getattr(book, "url", None)))
        payload_size = len(payload_bytes) + sum(len(cover_bytes) for _name, cover_bytes in covers)
        if payload_size > _UPLOAD_SIZE_LIMIT_BYTES:
            raise DiscordSharePayloadTooLargeError(payload_size, limit_bytes=_UPLOAD_SIZE_LIMIT_BYTES)
        if progress_callback is not None:
            progress_callback("上传到 Discord share")
        api = DiscordShareAPI(self._current_api_url(), self._current_user_token())
        share_id = await api.upload_share(
            payload_bytes=payload_bytes,
            covers=covers,
            site=self._site_for_books(books_snapshot),
            book_names=book_names,
        )
        return ShareUploadResult(
            share_id=share_id,
            site=self._site_for_books(books_snapshot),
            book_count=len(books_snapshot),
            total_pages=self.total_pages(books_snapshot),
            uploaded_urls=tuple(uploaded_urls),
        )

    def _on_upload_success(self, result: ShareUploadResult):
        self._uploading = False
        InfoBar.success(
            title='', content=f"分享上传完成 {result.share_id}",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=3000, parent=self.gui,
        )
        self.upload_finished.emit(result)

    def _on_upload_error(self, _error: str):
        self._uploading = False
        self.upload_finished.emit(None)

    def download(self, share_id: str):
        return self.task_mgr.execute_simple_task(
            self._download_impl,
            success_callback=self._on_download_success,
            tooltip_title="discord share",
            tooltip_content="下载分享内容",
            success_message="分享已载入预览",
            task_id=f"discord_share_download_{share_id}",
            show_success_info=False,
            share_id=share_id,
        )

    async def _download_impl(self, share_id: str, *, progress_callback=None):
        if progress_callback is not None:
            progress_callback("下载分享文件")
        api = DiscordShareAPI(self._current_api_url(), self._current_user_token())
        payload = await api.download_share(share_id)
        if progress_callback is not None:
            progress_callback("解析分享内容")
        return deserialize_books(payload)

    def _on_download_success(self, books: list[BookInfo]):
        self.gui.preview_mgr.publish_share_books(books)
        self.upload_finished.emit(books)

    @staticmethod
    def _normalize_url(url: str | None) -> str:
        return str(url or "").strip()

    def _site_for_books(self, books: list[BookInfo]) -> str:
        if books:
            return str(getattr(books[0], "source", "") or self.site)
        return self.site
