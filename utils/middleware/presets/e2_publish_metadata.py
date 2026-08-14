# -*- coding: utf-8 -*-
"""E2 — Publish Metadata (Lane E action emitter).

Honors invariant I6: E2 does not perform I/O. It only emits a publish_metadata
Action for the downstream action sink, which serializes, uploads to Discord
CDN, and updates the cf worker index in a separate execution layer.

The publish gate lives in the caller (D3: publish is an optional switch —
the runner constructs/invokes E2 only when `cfg.publish` exists).
"""
from __future__ import annotations

import typing as t

from utils.middleware.executor import Action
from utils.middleware.timeline import TimelineStage


class E2PublishMetadata:
    """Lane E middleware: emits the metadata publish action."""

    lane = "E"
    rule_id = "E2"

    def __init__(
        self,
        bid_provider: t.Optional[t.Callable[[t.Any], str]] = None,
        books_provider: t.Optional[t.Callable[[t.Any], list]] = None,
        site_provider: t.Optional[t.Callable[[t.Any], str]] = None,
        **params,
    ):
        self.params = params
        self._bid_provider = bid_provider
        self._books_provider = books_provider
        self._site_provider = site_provider

    def on_event(self, stage: TimelineStage, ctx):
        if stage != TimelineStage.POSTPROCESSING:
            return None

        bid = self._bid(ctx)
        if not bid:
            raise ValueError("E2: publish bid is required")

        books = self._books(ctx)
        if not books:
            return None

        site = self._site(ctx)
        return Action(
            kind="publish_metadata",
            payload={
                "bid": bid,
                "books": books,
                "site": site,
                "book_names": [book.name for book in books],
            },
            stop_propagation=False,
        )

    def _bid(self, ctx) -> str:
        provider = self._require_provider("bid_provider", self._bid_provider)
        bid = provider(ctx)
        if bid is None:
            return ""
        if not isinstance(bid, str):
            raise ValueError(f"E2: bid_provider must return str, got {type(bid).__name__}")
        return bid.strip()

    def _books(self, ctx) -> list:
        provider = self._require_provider("books_provider", self._books_provider)
        books = provider(ctx)
        if not isinstance(books, list):
            raise ValueError(f"E2: books_provider must return list, got {type(books).__name__}")
        return books

    def _site(self, ctx) -> str:
        provider = self._require_provider("site_provider", self._site_provider)
        site = provider(ctx)
        if not isinstance(site, str):
            raise ValueError(f"E2: site_provider must return str, got {type(site).__name__}")
        return site.strip()

    @staticmethod
    def _require_provider(name: str, provider):
        if provider is None or not callable(provider):
            raise ValueError(f"E2: {name} is required")
        return provider
