# -*- coding: utf-8 -*-
"""Feature Diff (feature-tracking new-book diff, mode-agnostic).

Second subscription semantic alongside D2 (episode-tracking). Where D2 anchors a
single book URL and tracks its *new episodes*, this rule anchors a feature
(artist/tag) and tracks *newly appearing books* in that feature's search results:
fresh search results ⊖ already-seen set -> new books to download.

Mirrors `d2_episode_diff.py` structure exactly:
  - a pure filter primitive (`filter_new_books`) testable without GUI/SQL,
  - a thin middleware shim (`FeatureDiff`) that mutates `ctx.books` in place and
    returns no Action so downstream selectors see the narrowed set,
  - provider injection (`seen_keys_provider`) so the seen-set source stays
    swappable and unit-testable (SOLID-D).

The diff runs at the BOOK lane (the lane that owns books) because feature-diff
operates on books, not episodes. It is mode-agnostic for the same reason D2 is
(I5): the diff semantics do not change between broadcaster and subscriber; only
HOW the books enter the lane differs.
"""
from __future__ import annotations

import logging
import typing as t

from utils.middleware.timeline import TimelineStage

_log = logging.getLogger(__name__)


def _book_key(book) -> t.Optional[str]:
    """Stable unique key for a book, used as the diff identity.

    Prefers the md5 half of `id_and_md5()` (Ero/doujinshi expose
    `id_and_md5() -> (uid, u_md5)`), aligning with D2's exact dedup identity and
    DownloadStateStore's md5 keys. Falls back to `uid` then `url` for book types
    without `id_and_md5`. Returns None when no stable identity exists, so the
    caller keeps the book conservatively (better to re-download than silently
    drop a genuinely new book).
    """
    fn = getattr(book, "id_and_md5", None)
    if callable(fn):
        # Existence check is legitimate type dispatch (Manga has no id_and_md5 ->
        # fall through to uid/url). But if it exists, trust it: a malformed
        # id_and_md5 is a real upstream bug that must propagate, not be swallowed
        # (I11 / architecture.md "No Defensive Silent Fallback").
        return fn()[1]
    uid = getattr(book, "uid", None)
    if uid:
        return str(uid)
    url = getattr(book, "url", None)
    if url:
        return str(url)
    return None


def filter_new_books(
    search_results: t.Iterable,
    seen_keys: t.Optional[t.Set[str]] = None,
) -> list:
    """Return books from `search_results` whose key is not in `seen_keys`.

    Pipeline:
      1. Drop books whose `_book_key` already lives in `seen_keys`.
      2. Books without a parseable key are kept conservatively (a new book with
         an unusual identity should surface, not vanish).
      3. Ordering of the input iterable is preserved in the output.

    Edge cases:
      - Empty input -> [].
      - Empty/None seen_keys -> every (non-None) book is new.
      - All keys already seen -> [].

    Args:
        search_results: iterable of BookInfo-like objects; identity comes from
            `id_and_md5()` / `uid` / `url` (see `_book_key`).
        seen_keys: precomputed set of already-seen book keys; None means nothing
            seen yet.

    Returns:
        Filtered list preserving original order.
    """
    books = [book for book in search_results if book is not None]
    if not books:
        return []

    seen = seen_keys or set()

    kept: list = []
    for book in books:
        key = _book_key(book)
        if key is not None and key in seen:
            continue
        kept.append(book)
    return kept


class FeatureDiff:
    """BOOK lane middleware: filters `ctx.books` to newly-appeared books only.

    Mode-agnostic. Mutates `ctx.books` in place and returns no Action so the
    chain continues (downstream auto-selectors see the narrowed dict).

    Provider is injected to keep this preset GUI/SQL-free:
      - `seen_keys_provider(ctx, books) -> Iterable[str]`: typically wraps
        `DownloadStateStore.downloaded_md5s` (the lightest seen-set load-bearer:
        it reuses the existing download-history SQL and aligns md5 keys with
        `_book_key`, so feature-tracking needs no new store).
    """

    lane = "C"
    rule_id = "C3"

    def __init__(
        self,
        seen_keys_provider: t.Optional[t.Callable[[t.Any, list], t.Iterable[str]]] = None,
        **params,
    ):
        self.params = params
        self._seen_keys_provider = seen_keys_provider

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.WAIT_BOOK_DECISION:
            return None
        books = getattr(ctx, "books", None) or {}
        if not books:
            return None

        ordered_keys = list(books.keys())
        ordered_books = [books[k] for k in ordered_keys]

        seen_iter = self._seen_keys_provider(ctx, ordered_books) if self._seen_keys_provider else ()
        seen_set = set(seen_iter or ())

        kept_books = filter_new_books(ordered_books, seen_keys=seen_set)
        if len(kept_books) == len(ordered_books):
            return None  # nothing new to drop; do not mutate ctx

        kept_id = {id(book) for book in kept_books}
        ctx.books = {k: v for k, v in books.items() if id(v) in kept_id}
        return None
