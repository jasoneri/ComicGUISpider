# -*- coding: utf-8 -*-
"""Shared constants and pure helpers for subscribe UI package."""
from __future__ import annotations

from pathlib import Path

from utils import conf
from utils.core import sanitize_for_path
from utils.subscription.library import LocalLibraryStore
from utils.subscription.schema import ALL_WEEKDAYS
from utils.subscription.site_proxy import normalize_site_proxy_key
from variables import Spider

WEEKDAY_IDS = tuple(ALL_WEEKDAYS)  # "1".."7" — Monday..Sunday

# ComfyJobCard / Danbooru DEFAULT metrics — local copy avoids importing danbooru.style at startup.
CARD_CONTENT_MARGIN = 4
CARD_COLUMN_WIDTH = 228
CARD_PREVIEW_WIDTH_PADDING = 20
CARD_PREVIEW_CONTENT_WIDTH = max(1, CARD_COLUMN_WIDTH - CARD_PREVIEW_WIDTH_PADDING)
CARD_PREVIEW_BASE_HEIGHT = 168
CARD_PREVIEW_MAX_HEIGHT = 182
# manga book-card-body: tight title + single meta line (no conf chip row).
CARD_TITLE_META_RESERVE = 44
CARD_ACTION_SIZE = (30, 30)
CARD_ACTION_ICON = (16, 16)
CARD_OVERLAY_MARGIN = 6
CARD_OVERLAY_SPACING = 4

# Solid icon tints on dark cover chips (QIcon paint; chip chrome lives in subscribe.qss).
OVERLAY_ICON_COLORS = {
    "folder": "#60A5FA",
    "link": "#4ADE80",
    "del": "#F87171",
}


def subscribe_site_indexes() -> frozenset[int]:
    """Subscription is manga-only. JM/ero/specials are out of scope (mangaCard path)."""
    return frozenset(int(site_index) for site_index in Spider.mangas())


def resolve_subscribe_site_index(book, *, fallback_site_index: int | None = None) -> int | None:
    raw_site = LocalLibraryStore.book_site(book)
    site_index = LocalLibraryStore.site_index_for_name(raw_site)
    if site_index is None and raw_site:
        site_index = LocalLibraryStore.site_index_for_name(normalize_site_proxy_key(raw_site))
    if site_index is None and fallback_site_index is not None:
        site_index = int(fallback_site_index)
    return int(site_index) if site_index is not None else None


def resolve_local_path(book) -> str | None:
    explicit = str(getattr(book, "local_path", "") or "").strip()
    if explicit:
        path = Path(explicit)
        if path.exists():
            return str(path)
    title = LocalLibraryStore.book_title(book)
    if not title:
        return None
    candidate = Path(conf.sv_path).joinpath(sanitize_for_path(title))
    if candidate.exists() and candidate.is_dir():
        return str(candidate)
    return None
