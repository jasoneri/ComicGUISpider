# -*- coding: utf-8 -*-
"""BookInfo resolution for subscription tray runs.

Patterns (see grok-search batch-job refactor notes):
- Registry: site → BookInfo type / id extractor / url normalizer
- Strategy: per-site url shape (JM album vs photo) without if-ladders in the caller
- Single owner: ``BookInfoResolver`` — library pickle first, yaml reconstruct second
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Callable, Optional, Protocol

from utils.subscription.library import LocalLibraryStore
from utils.subscription.schema import BookEntry
from utils.website.info import (
    BookInfo,
    ComicabcBookInfo,
    Dm5BookInfo,
    EhBookInfo,
    HComicBookInfo,
    HitomiBookInfo,
    JComicBookInfo,
    JestfulBookInfo,
    JmBookInfo,
    KbBookInfo,
    MangabzBookInfo,
    ManhuaguiBookInfo,
    Mh1234BookInfo,
    NhentaiBookInfo,
    WnacgBookInfo,
)
from utils.website.registry import resolve_provider_descriptor_by_site

BookTypeFactory = Callable[..., BookInfo]
IdExtractor = Callable[[str], str]


class BookUrlNormalizer(Protocol):
    """Strategy: rewrite book url fields for a site after construct/hydrate."""

    def normalize(
        self,
        book: BookInfo,
        *,
        site: str,
        entry_url: str,
        reconstruct: bool = False,
    ) -> BookInfo:
        ...


class IdentityUrlNormalizer:
    def normalize(
        self,
        book: BookInfo,
        *,
        site: str,
        entry_url: str,
        reconstruct: bool = False,
    ) -> BookInfo:
        return book


class JmUrlNormalizer:
    """JM list cards store photo URLs; episode parse needs album preview_url."""

    def normalize(
        self,
        book: BookInfo,
        *,
        site: str,
        entry_url: str,
        reconstruct: bool = False,
    ) -> BookInfo:
        book_id = str(getattr(book, "id", "") or "").strip() or _numeric_path_id(entry_url)
        if not book_id:
            return book
        album_url, photo_url = jm_album_and_photo_urls(
            str(getattr(book, "url", "") or entry_url),
            str(book_id),
        )
        if not str(getattr(book, "id", "") or "").strip():
            setattr(book, "id", str(book_id))
        setattr(book, "preview_url", album_url)
        existing_url = str(getattr(book, "url", "") or "").strip()
        if reconstruct:
            setattr(book, "url", photo_url or existing_url or entry_url)
        elif not existing_url:
            setattr(book, "url", photo_url)
        return book


_NUMERIC_PATH_RE = re.compile(r"/(?:photo|album|photos-index-aid-|aid-)(\d+)")
_TRAILING_ID_RE = re.compile(r"/(\d+)(?:/)?(?:\?.*)?$")


def _numeric_path_id(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    match = _NUMERIC_PATH_RE.search(text)
    if match:
        return match.group(1)
    match = _TRAILING_ID_RE.search(text)
    if match:
        return match.group(1)
    return ""


def jm_album_and_photo_urls(url: str, book_id: str) -> tuple[str, str]:
    text = str(url or "").strip()
    photo = text
    album = text
    if "/photo/" in text:
        album = text.replace("/photo/", "/album/")
    elif "/album/" in text:
        photo = text.replace("/album/", "/photo/")
    elif book_id:
        album = f"/album/{book_id}"
        photo = f"/photo/{book_id}"
    return album, photo


def extract_book_id(site: str, url: str) -> str:
    """Derive provider book id from a stored url when pkl BookInfo is unavailable."""
    text = str(url or "").strip()
    if not text:
        return ""
    site_key = str(site or "").strip().lower()
    extractor = BookTypeRegistry.id_extractor_for(site_key)
    return extractor(text)


def _id_numeric_sites(url: str) -> str:
    return _numeric_path_id(url) or url


def _id_full_url(url: str) -> str:
    return url


class BookTypeRegistry:
    """Site → BookInfo type / id extractor / url normalizer (extensible registry)."""

    _BOOK_TYPES: dict[str, type[BookInfo]] = {
        "kaobei": KbBookInfo,
        "manga_copy": KbBookInfo,
        "mangabz": MangabzBookInfo,
        "jestful": JestfulBookInfo,
        "manhuagui": ManhuaguiBookInfo,
        "dm5": Dm5BookInfo,
        "dm": Dm5BookInfo,
        "comicabc": ComicabcBookInfo,
        "mh1234": Mh1234BookInfo,
        "jm": JmBookInfo,
        "wnacg": WnacgBookInfo,
        "ehentai": EhBookInfo,
        "hitomi": HitomiBookInfo,
        "h_comic": HComicBookInfo,
        "nhentai": NhentaiBookInfo,
        "jcomic": JComicBookInfo,
    }
    _ID_EXTRACTORS: dict[str, IdExtractor] = {
        "jm": _id_numeric_sites,
        "wnacg": _id_numeric_sites,
        "jcomic": _id_numeric_sites,
    }
    _NORMALIZERS: dict[str, BookUrlNormalizer] = {
        "jm": JmUrlNormalizer(),
    }
    _DEFAULT_NORMALIZER: BookUrlNormalizer = IdentityUrlNormalizer()

    @classmethod
    def book_type_for(cls, site: str) -> type[BookInfo]:
        site_key = str(site or "").strip()
        if not site_key:
            raise ValueError("book entry site is required")
        book_type = cls._BOOK_TYPES.get(site_key)
        if book_type is not None:
            return book_type
        resolve_provider_descriptor_by_site(site_key)
        return BookInfo

    @classmethod
    def id_extractor_for(cls, site: str) -> IdExtractor:
        return cls._ID_EXTRACTORS.get(str(site or "").strip().lower(), _id_full_url)

    @classmethod
    def normalizer_for(cls, site: str) -> BookUrlNormalizer:
        return cls._NORMALIZERS.get(str(site or "").strip().lower(), cls._DEFAULT_NORMALIZER)

    @classmethod
    def construct(cls, entry: BookEntry) -> BookInfo:
        site = str(entry.site or "").strip()
        book_type = cls.book_type_for(site)
        book_id = extract_book_id(site, entry.url) or str(entry.url or "").strip()
        url = str(entry.url or "").strip()
        book = book_type(
            id=book_id,
            source=site if book_type is BookInfo else None,
            url=url,
            preview_url=url,
            name=entry.title,
        )
        return cls.normalizer_for(site).normalize(
            book, site=site, entry_url=url, reconstruct=True
        )


class BookInfoResolver:
    """Resolve BookEntry → BookInfo: local library pickle, else yaml construct."""

    def __init__(self, library_store: Optional[LocalLibraryStore] = None) -> None:
        self._library = library_store or LocalLibraryStore()

    def resolve(self, entry: BookEntry) -> BookInfo:
        hydrated = self._try_library(entry)
        if hydrated is not None:
            return hydrated
        return BookTypeRegistry.construct(entry)

    def _try_library(self, entry: BookEntry) -> Optional[BookInfo]:
        site_index = LocalLibraryStore.site_index_for_name(entry.site)
        target_url = LocalLibraryStore.book_unique_url(
            SimpleNamespace(url=entry.url, preview_url=entry.url)
        ) or str(entry.url or "").strip()
        if site_index is None or not target_url:
            return None
        for book in self._library.load(int(site_index)):
            if LocalLibraryStore.book_unique_url(book) != target_url:
                continue
            if not self._is_usable_shell(book):
                return None
            return self._hydrate_library_book(book, entry, target_url)
        return None

    @staticmethod
    def _is_usable_shell(book: BookInfo) -> bool:
        book_id = str(getattr(book, "id", "") or "").strip()
        book_url = str(getattr(book, "url", "") or "").strip()
        return bool(book_id or book_url)

    def _hydrate_library_book(self, book: BookInfo, entry: BookEntry, target_url: str) -> BookInfo:
        site = str(entry.site or "").strip()
        if not str(getattr(book, "source", "") or "").strip():
            setattr(book, "source", site)
        if not str(getattr(book, "name", "") or "").strip() and entry.title:
            setattr(book, "name", entry.title)
        return BookTypeRegistry.normalizer_for(site).normalize(
            book, site=site, entry_url=target_url, reconstruct=False
        )


def book_from_entry(entry: BookEntry) -> BookInfo:
    """Public construct path (no library). Used by account flows and tests."""
    return BookTypeRegistry.construct(entry)
