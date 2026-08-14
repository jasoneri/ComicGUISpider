# -*- coding: utf-8 -*-
"""Local library pkl SSoT for own tracked books.

Ownership split:
- ``LibraryBookView`` — pure field extractors (url/title/site/enabled).
- ``LibraryPklRepository`` — per-site pickle load/save + path map.
- ``YamlBookOverlay`` — merge library rows with binding yaml books[].
- ``YamlLibrarySeeder`` — idempotent seed missing pkl rows from yaml.
- ``LocalLibraryStore`` — façade kept for callers (GUI / tray / server).
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterable, Optional

from utils.config import conf_dir
from utils.subscription.schema import BookEntry
from variables import SPIDERS

LIBRARY_DIR = conf_dir.joinpath("library")


class LibraryBookView:
    """Read BookInfo-like objects without owning storage."""

    @staticmethod
    def unique_url(book) -> str:
        return (getattr(book, "url", None) or getattr(book, "preview_url", "") or "").strip()

    @staticmethod
    def title(book) -> str:
        return str(getattr(book, "name", "") or "").strip()

    @staticmethod
    def site(book, *, site_index: Optional[int] = None) -> str:
        source = str(getattr(book, "source", "") or "").strip()
        if source:
            return source
        if site_index is not None:
            return str(SPIDERS.get(site_index) or "").strip()
        return ""

    @staticmethod
    def subscribe_enabled(book) -> bool:
        raw = getattr(book, "subscribe_enabled", None)
        if raw is None:
            return True
        return bool(raw)

    @classmethod
    def as_entry(cls, book, *, site_index: Optional[int] = None) -> BookEntry:
        return BookEntry(
            site=cls.site(book, site_index=site_index),
            url=cls.unique_url(book),
            title=cls.title(book),
            enabled=cls.subscribe_enabled(book),
        )

    @staticmethod
    def site_index_for_name(site: str) -> Optional[int]:
        name = str(site or "").strip()
        if not name:
            return None
        for site_index, spider_name in SPIDERS.items():
            if spider_name == name:
                return int(site_index)
        return None

    @staticmethod
    def book_from_entry(entry: BookEntry):
        from utils.website.info import BookInfo

        site = str(entry.site or "").strip()
        url = str(entry.url or "").strip()
        title = str(entry.title or "").strip() or url
        book = BookInfo(id=url, source=site, url=url, preview_url=url, name=title)
        setattr(book, "subscribe_enabled", bool(entry.enabled))
        return book

    @staticmethod
    def entry_key(site: str, url: str) -> str:
        return f"{str(site or '').strip()}:{str(url or '').strip()}"


class LibraryPklRepository:
    """File gateway for conf_dir/library/{spider}_local.pkl — list I/O only."""

    def __init__(self, library_dir: Optional[Path] = None) -> None:
        self.library_dir = Path(library_dir) if library_dir is not None else LIBRARY_DIR
        self.library_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, site_index: int) -> Optional[Path]:
        spider_name = SPIDERS.get(site_index)
        if not spider_name:
            return None
        return self.library_dir.joinpath(f"{spider_name}_local.pkl")

    def load(self, site_index: int) -> list:
        pkl_path = self.path_for(site_index)
        if pkl_path is None or not pkl_path.exists():
            return []
        with open(pkl_path, "rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, list):
            raise ValueError(f"library pkl must be a list, got {type(payload).__name__}")
        deduped: list = []
        seen: set[str] = set()
        for book in payload:
            key = LibraryBookView.unique_url(book)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(book)
        return deduped

    def save(self, site_index: int, books: list) -> bool:
        pkl_path = self.path_for(site_index)
        if pkl_path is None:
            return False
        self.library_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = pkl_path.with_name(f"{pkl_path.name}.tmp")
        try:
            with open(temporary_path, "wb") as handle:
                pickle.dump(list(books), handle, protocol=pickle.HIGHEST_PROTOCOL)
            temporary_path.replace(pkl_path)
        except Exception:
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
            raise
        return True

    def iter_all(self) -> list[tuple[int, object]]:
        rows: list[tuple[int, object]] = []
        for site_index in SPIDERS:
            for book in self.load(int(site_index)):
                rows.append((int(site_index), book))
        return rows


class YamlBookOverlay:
    """Merge library pkl rows with binding yaml books[] (enabled + check SSoT)."""

    @staticmethod
    def index_yaml(yaml_books: Optional[Iterable[BookEntry]]) -> dict[str, BookEntry]:
        indexed: dict[str, BookEntry] = {}
        if yaml_books is None:
            return indexed
        for yaml_entry in yaml_books:
            key = LibraryBookView.entry_key(yaml_entry.site, yaml_entry.url)
            if key != ":":
                indexed[key] = yaml_entry
        return indexed

    @classmethod
    def merge(
        cls,
        library_rows: list[tuple[int, object]],
        yaml_books: Optional[Iterable[BookEntry]] = None,
    ) -> list[BookEntry]:
        yaml_by_key = cls.index_yaml(yaml_books)
        entries: list[BookEntry] = []
        seen: set[str] = set()
        for site_index, book in library_rows:
            entry = LibraryBookView.as_entry(book, site_index=site_index)
            if not entry.url:
                continue
            key = LibraryBookView.entry_key(entry.site, entry.url)
            if key in seen:
                continue
            seen.add(key)
            yaml_entry = yaml_by_key.get(key)
            if yaml_entry is not None:
                entry.enabled = bool(yaml_entry.enabled)
                if yaml_entry.check is not None:
                    entry.check = yaml_entry.check.copy()
            entries.append(entry)
        for key, yaml_entry in yaml_by_key.items():
            if key in seen:
                continue
            if not str(yaml_entry.url or "").strip():
                continue
            entries.append(
                BookEntry(
                    site=str(yaml_entry.site or "").strip(),
                    url=str(yaml_entry.url or "").strip(),
                    title=str(yaml_entry.title or "").strip(),
                    enabled=bool(yaml_entry.enabled),
                    check=yaml_entry.check.copy() if yaml_entry.check is not None else None,
                )
            )
        return entries


class YamlLibrarySeeder:
    """Idempotent add-only seed of missing pkl rows from yaml books[]."""

    def __init__(self, store: "LocalLibraryStore") -> None:
        self._store = store

    def ensure(self, entries: Iterable[BookEntry]) -> int:
        added = 0
        for entry in entries:
            site_index = LibraryBookView.site_index_for_name(entry.site)
            if site_index is None:
                continue
            if entry.url in self._store.urls(site_index):
                self._store.update_book_subscribe_conf(
                    site_index,
                    entry.url,
                    enabled=bool(entry.enabled),
                )
                continue
            if self._store.add_book(site_index, LibraryBookView.book_from_entry(entry)):
                added += 1
        return added


class LocalLibraryStore:
    """Façade: own-book library SSoT under conf_dir/library/{spider}_local.pkl."""

    def __init__(self, library_dir: Optional[Path] = None) -> None:
        self._repo = LibraryPklRepository(library_dir)
        self.library_dir = self._repo.library_dir

    def load(self, site_index: int) -> list:
        return self._repo.load(site_index)

    def save(self, site_index: int, books: list) -> bool:
        return self._repo.save(site_index, books)

    def urls(self, site_index: int) -> set[str]:
        return {
            url for book in self.load(site_index)
            if (url := LibraryBookView.unique_url(book))
        }

    def toggle(self, site_index: int, book) -> Optional[bool]:
        book_url = LibraryBookView.unique_url(book)
        if not book_url:
            return None
        library_books = self.load(site_index)
        existed_index = next(
            (
                index
                for index, item in enumerate(library_books)
                if LibraryBookView.unique_url(item) == book_url
            ),
            None,
        )
        if existed_index is None:
            library_books.append(book)
            final_state = True
        else:
            library_books.pop(existed_index)
            final_state = False
        return final_state if self.save(site_index, library_books) else None

    def add_book(self, site_index: int, book) -> bool:
        book_url = LibraryBookView.unique_url(book)
        if not book_url:
            return False
        library_books = self.load(site_index)
        if any(LibraryBookView.unique_url(item) == book_url for item in library_books):
            return False
        library_books.append(book)
        return self.save(site_index, library_books)

    def remove_url(self, site_index: int, url: str) -> bool:
        target = str(url or "").strip()
        if not target:
            return False
        library_books = self.load(site_index)
        next_books = [
            book for book in library_books if LibraryBookView.unique_url(book) != target
        ]
        if len(next_books) == len(library_books):
            return False
        return self.save(site_index, next_books)

    def remove_entry(self, entry: BookEntry) -> bool:
        site_index = LibraryBookView.site_index_for_name(entry.site)
        if site_index is None:
            return False
        return self.remove_url(site_index, entry.url)

    def update_book_subscribe_conf(
        self,
        site_index: int,
        url: str,
        *,
        enabled: bool | None = None,
    ) -> bool:
        """Mirror enabled onto library pkl for card visual only (yml remains check SSoT)."""
        book_url = str(url or "").strip()
        if not book_url:
            return False
        library_books = self.load(int(site_index))
        target = next(
            (
                item
                for item in library_books
                if LibraryBookView.unique_url(item) == book_url
            ),
            None,
        )
        if target is None:
            return False
        if enabled is not None:
            setattr(target, "subscribe_enabled", bool(enabled))
        return self.save(int(site_index), library_books)

    def update_book_img_preview(self, site_index: int, url: str, img_preview: str) -> bool:
        book_url = str(url or "").strip()
        cover = str(img_preview or "").strip()
        if not book_url or not cover:
            return False
        library_books = self.load(int(site_index))
        target = next(
            (
                item
                for item in library_books
                if LibraryBookView.unique_url(item) == book_url
            ),
            None,
        )
        if target is None:
            return False
        current = str(getattr(target, "img_preview", "") or "").strip()
        if current == cover:
            return True
        setattr(target, "img_preview", cover)
        return self.save(int(site_index), library_books)

    def iter_all_books(self) -> list[tuple[int, object]]:
        return self._repo.iter_all()

    def book_entries(self, *, yaml_books: Optional[Iterable[BookEntry]] = None) -> list[BookEntry]:
        return YamlBookOverlay.merge(self.iter_all_books(), yaml_books)

    def ensure_books_from_yaml(self, entries: Iterable[BookEntry]) -> int:
        return YamlLibrarySeeder(self).ensure(entries)

    # --- stable static surface (GUI / card / side_panel call these) ---

    @staticmethod
    def book_unique_url(book) -> str:
        return LibraryBookView.unique_url(book)

    @staticmethod
    def book_title(book) -> str:
        return LibraryBookView.title(book)

    @staticmethod
    def book_site(book, *, site_index: Optional[int] = None) -> str:
        return LibraryBookView.site(book, site_index=site_index)

    @staticmethod
    def book_subscribe_enabled(book) -> bool:
        return LibraryBookView.subscribe_enabled(book)

    @classmethod
    def book_entry_from_book(cls, book, *, site_index: Optional[int] = None) -> BookEntry:
        return LibraryBookView.as_entry(book, site_index=site_index)

    @staticmethod
    def site_index_for_name(site: str) -> Optional[int]:
        return LibraryBookView.site_index_for_name(site)

    @staticmethod
    def _book_from_entry(entry: BookEntry):
        return LibraryBookView.book_from_entry(entry)
