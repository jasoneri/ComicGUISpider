# -*- coding: utf-8 -*-
"""D2 — Episode Diff (Lane D filter, mode-agnostic).

Honors invariant I5 — broadcaster and subscriber share identical diff semantics;
mode difference lives only in HOW BookInfo enters the lane (B/C skip strategy).

Pure filter primitive `filter_undownloaded` is exposed for unit-testing without
GUI/SQL dependencies; the `D2EpisodeDiff` middleware is a thin context shim that
mutates `ctx.eps` in place and returns no Action (so downstream selectors like
AutoSelectLatest see the narrowed set).
"""
from __future__ import annotations

import logging
import re
import typing as t

from utils.middleware.timeline import TimelineStage

_log = logging.getLogger(__name__)

# Mirrors utils/redViewer_tools.py:_get_max_sections regex — section number is the
# first numeric chunk (with optional decimal) in the episode name, e.g. "第12.5话" -> 12.5
_SECTION_RE = re.compile(r".*?(\d+\.?\d*)")


def _section_num(name: t.Optional[str]) -> t.Optional[float]:
    """Extract leading section number from an episode/section name.

    Returns None when the name is empty or contains no numeric chunk; the caller
    decides whether None means "treat as new" or "treat as boundary mismatch".
    """
    if not name:
        return None
    m = _SECTION_RE.search(str(name))
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def filter_undownloaded(
    site_episodes: t.Iterable,
    dl_max: str = "",
    downloaded_md5s: t.Optional[t.Set[str]] = None,
) -> list:
    """Return site episodes not yet downloaded locally.

    Pipeline (I5 semantics):
      1. Drop episodes whose md5 already lives in `downloaded_md5s` (exact dedup).
      2. Drop episodes whose section number <= `dl_max`'s section number (ordinal cut).
      3. Episodes without a parseable section number are kept conservatively
         (better to re-fetch than silently miss a new ep with an unusual name).
      4. Ordering of the input iterable is preserved in the output.

    Edge cases (I5 Validation Matrix):
      - Empty input -> [].
      - Empty/None dl_max -> ordinal cut is skipped; only md5 dedup applies.
      - dl_max parses but is >= every site section -> [] (treated as fully local).
      - dl_max is unparseable -> log warn and skip ordinal cut (do not crash).

    Args:
        site_episodes: iterable of objects with `.name` (str) and ideally
            `.id_and_md5() -> (uid, md5)` for the dedup step.
        dl_max: highest locally-downloaded section name for the book.
        downloaded_md5s: optional precomputed md5 set; if None, dedup is skipped.

    Returns:
        Filtered list preserving original order.
    """
    eps = [ep for ep in site_episodes if ep is not None]
    if not eps:
        return []

    md5_set = downloaded_md5s or set()

    def _md5_of(ep) -> t.Optional[str]:
        fn = getattr(ep, "id_and_md5", None)
        if not callable(fn):
            return None
        # Existence check is legitimate type dispatch; if it exists, trust it.
        # A malformed id_and_md5 is a real upstream bug that must propagate,
        # not be swallowed (I11 / architecture.md "No Defensive Silent Fallback").
        return fn()[1]

    cutoff: t.Optional[float] = None
    if dl_max:
        cutoff = _section_num(dl_max)
        if cutoff is None:
            _log.warning("D2: dl_max=%r has no parseable section number; ordinal cut skipped", dl_max)

    kept: list = []
    for ep in eps:
        ep_md5 = _md5_of(ep)
        if ep_md5 and ep_md5 in md5_set:
            continue
        if cutoff is not None:
            ep_num = _section_num(getattr(ep, "name", None))
            if ep_num is not None and ep_num <= cutoff:
                continue
        kept.append(ep)
    return kept


class D2EpisodeDiff:
    """Lane D middleware: filters `ctx.eps` to undownloaded episodes only.

    Mode-agnostic (I5). Mutates `ctx.eps` in place and returns no Action so the
    chain continues (downstream auto-selectors see the narrowed dict).

    Providers are injected to keep this preset GUI/SQL-free:
      - `dl_max_provider(ctx) -> str`: typically wraps redViewer Handler.show_max
      - `md5s_provider(ctx, episodes) -> Iterable[str]`: typically wraps
        DownloadStateStore.downloaded_md5s
    """

    lane = "D"
    rule_id = "D2"

    def __init__(
        self,
        dl_max_provider: t.Optional[t.Callable[[t.Any], str]] = None,
        md5s_provider: t.Optional[t.Callable[[t.Any, list], t.Iterable[str]]] = None,
        **params,
    ):
        self.params = params
        self._dl_max_provider = dl_max_provider
        self._md5s_provider = md5s_provider

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.WAIT_EP_DECISION:
            return None
        eps = getattr(ctx, "eps", None) or {}
        if not eps:
            return None

        ordered_keys = list(eps.keys())
        ordered_eps = [eps[k] for k in ordered_keys]

        dl_max = self._dl_max_provider(ctx) if self._dl_max_provider else ""
        md5s_iter = self._md5s_provider(ctx, ordered_eps) if self._md5s_provider else ()
        md5_set = set(md5s_iter or ())

        kept_eps = filter_undownloaded(ordered_eps, dl_max=dl_max or "", downloaded_md5s=md5_set)
        if len(kept_eps) == len(ordered_eps):
            return None  # nothing to drop; do not mutate ctx

        kept_id = {id(ep) for ep in kept_eps}
        ctx.eps = {k: v for k, v in eps.items() if id(v) in kept_id}
        return None
