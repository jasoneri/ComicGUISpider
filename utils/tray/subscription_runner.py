# -*- coding: utf-8 -*-
"""Subscription tray run orchestrator.

Design (grok-search: Pipeline + Stage Template Method + Strategy/Registry +
fault isolation; style-refactor: no god-method nest of try/if/for):

- ``SubscriptionRunner`` — thin public façade (load config, inject deps, run).
- ``_RunSession`` — one-run context (summary, observations, pending books).
- Ordered pipeline stages with flat bodies; item-level faults isolate via
  ``_isolate`` helpers, never deep nested try trees.
- Book resolve / site session live in sibling modules (owners, not private hell).
"""
from __future__ import annotations

import asyncio
import json
import queue
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

import httpx

from ComicSpider.runtime import SpiderRuntimeThread
from utils import conf, get_httpx_verify, temp_p
from utils.middleware.presets.c3_feature_diff import filter_new_books
from utils.middleware.presets.d2_episode_diff import D2EpisodeDiff
from utils.middleware.presets.e2_publish_metadata import E2PublishMetadata
from utils.middleware.timeline import TimelineStage
from utils.protocol import ErrorEvent, JobFinishedEvent, SpiderDownloadJob
from utils.redViewer_tools import Handler as RedViewerHandler
from utils.share import DiscordShareAPI, IndexRecord, WorkerIndexClient, deserialize_books, serialize_books
from utils.sql.download_state import DownloadStateStore
from utils.subscription import SubscriptionStore
from utils.subscription.check_state import (
    BookCheckState,
    CheckinSiteState,
    CheckinStateStore,
    CheckStateStore,
    is_checkin_due,
    mark_checkin,
    recalculate,
)
from utils.subscription.check_slot import effective_slot
from utils.subscription.library import LocalLibraryStore
from utils.subscription.schema import BookEntry, FeatureEntry, SubscriptionConfig
from utils.tray.feature_search import (
    filter_feature_books,
    supported_features,
    unsupported_feature_summary,
    unsupported_features,
)
from utils.tray.schedule_presentation import ScheduleCache, ScheduleCacheState
from utils.tray.subscription_book_resolve import BookInfoResolver, book_from_entry
from utils.tray.subscription_site_session import SiteRuntimeSession
from utils.website.account import CheckinResult, resolve_checkin_spec, run_checkin
from utils.website.info import BookInfo
from utils.website.registry import resolve_provider_descriptor_by_site
from variables import CGS_DISCORD_SHARE_API, CGS_METADATA_CHANNEL_ID, SPIDERS

# Compatibility re-exports (account flows / temp repros import these names).
_book_from_entry = book_from_entry
_DefaultSiteRuntimeSession = SiteRuntimeSession

BookRuntimeFactory = Callable[[str], Any]
DownloadSubmitter = Callable[[int, Any], bool | Awaitable[bool]]
DiscordApiFactory = Callable[[str], DiscordShareAPI]
WorkerClientFactory = Callable[[str], WorkerIndexClient]
CdnFetcher = Callable[[str], Awaitable[bytes]]
TokenProvider = Callable[[SubscriptionConfig], str]
DlMaxProvider = Callable[[Any], str]
Md5sProvider = Callable[[Any, list], set[str]]
ProgressCallback = Callable[[dict], None]
NowProvider = Callable[[], datetime]

_DEFAULT_DOWNLOAD_TIMEOUT_SEC = 60


@dataclass
class SubscriptionRunSummary:
    run_id: str = field(default_factory=lambda: uuid4().hex)
    trigger: str = "schedule"
    status: str = "ok"
    stage: str = ""
    started_at: str = ""
    finished_at: str = ""
    elapsed_sec: float = 0.0
    scanned_books: int = 0
    own_books: int = 0
    follow_books: int = 0
    pending_episodes: int = 0
    submitted_jobs: int = 0
    published_metadata: bool = False
    pulled_feeds: int = 0
    checkin_ok: int = 0
    checkin_already: int = 0
    checkin_failed: int = 0
    book_errors: int = 0
    feature_errors: int = 0
    latest_message: str = ""
    pending_items: list[dict[str, str | int | bool]] = field(default_factory=list)
    cache: ScheduleCacheState = field(default_factory=lambda: ScheduleCacheState(status="missing"))

    @property
    def message(self) -> str:
        parts = [
            f"books={self.scanned_books}",
            f"pending={self.pending_episodes}",
            f"jobs={self.submitted_jobs}",
        ]
        if self.follow_books:
            parts.append(f"follows={self.follow_books}")
        if self.pulled_feeds:
            parts.append(f"feeds={self.pulled_feeds}")
        if self.published_metadata:
            parts.append("metadata=published")
        if self.checkin_ok or self.checkin_already or self.checkin_failed:
            parts.append(
                f"checkin ok={self.checkin_ok} already={self.checkin_already} failed={self.checkin_failed}"
            )
        if self.book_errors:
            parts.append(f"book_errors={self.book_errors}")
        if self.feature_errors:
            parts.append(f"feature_errors={self.feature_errors}")
        return " ".join(parts)

    def schedule_payload(self) -> dict[str, Any]:
        return {
            "cache": asdict(self.cache),
            "run": {
                "run_id": self.run_id,
                "trigger": self.trigger,
                "status": self.status,
                "stage": self.stage,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed_sec": self.elapsed_sec,
                "scanned_books": self.scanned_books,
                "own_books": self.own_books,
                "follow_books": self.follow_books,
                "pending_episodes": self.pending_episodes,
                "submitted_jobs": self.submitted_jobs,
                "published_metadata": self.published_metadata,
                "pulled_feeds": self.pulled_feeds,
                "checkin_ok": self.checkin_ok,
                "checkin_already": self.checkin_already,
                "checkin_failed": self.checkin_failed,
                "book_errors": self.book_errors,
                "feature_errors": self.feature_errors,
                "latest_message": self.latest_message,
            },
            "pending_items": self.pending_items,
        }


@dataclass
class _PendingBook:
    book: BookInfo
    site_index: int
    pending_episodes: list
    metadata_book: BookInfo


class SubscriptionRunner:
    """Public façade: inject collaborators, run one subscription cycle."""

    def __init__(
        self,
        *,
        store: Optional[SubscriptionStore] = None,
        config_loader: Optional[Callable[[], SubscriptionConfig]] = None,
        site_runtime_factory: Optional[BookRuntimeFactory] = None,
        download_submitter: Optional[DownloadSubmitter] = None,
        discord_api_factory: Optional[DiscordApiFactory] = None,
        worker_client_factory: Optional[WorkerClientFactory] = None,
        cdn_fetcher: Optional[CdnFetcher] = None,
        token_provider: Optional[TokenProvider] = None,
        dl_max_provider: Optional[DlMaxProvider] = None,
        md5s_provider: Optional[Md5sProvider] = None,
        progress_callback: Optional[ProgressCallback] = None,
        check_state_store: Optional[CheckStateStore] = None,
        checkin_state_store: Optional[CheckinStateStore] = None,
        checkin_runner: Optional[Callable[[str], CheckinResult]] = None,
        library_store: Optional[LocalLibraryStore] = None,
        latest_seen_path: Optional[Path] = None,
        now_provider: Optional[NowProvider] = None,
    ) -> None:
        self.store = store or SubscriptionStore()
        self.cache = ScheduleCache()
        self._config_loader = config_loader
        self._site_runtime_factory = site_runtime_factory or SiteRuntimeSession
        self._download_submitter = download_submitter or _RuntimeDownloadSubmitter()
        self._discord_api_factory = discord_api_factory or self._default_discord_api
        self._worker_client_factory = worker_client_factory or self._default_worker_client
        self._cdn_fetcher = cdn_fetcher or _fetch_cdn_bytes
        self._token_provider = token_provider or _default_token
        self._dl_max_provider = dl_max_provider
        self._md5s_provider = md5s_provider
        self._progress_callback = progress_callback
        self._check_state_store = check_state_store or CheckStateStore()
        self._checkin_state_store = checkin_state_store or CheckinStateStore()
        self._checkin_runner = checkin_runner or run_checkin
        self._library_store = library_store or LocalLibraryStore()
        self._book_resolver = BookInfoResolver(self._library_store)
        self._latest_seen_path = (
            Path(latest_seen_path)
            if latest_seen_path is not None
            else temp_p / "subscription_latest_seen.json"
        )
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._show_max_cache: Optional[dict] = None
        self._download_state = DownloadStateStore()

    def _downloaded_book_md5s(self, entry: FeatureEntry, books: list) -> set[str]:
        if self._md5s_provider is not None:
            return set(self._md5s_provider(entry, books) or set())
        return set(self._download_state.downloaded_md5s(books))

    def run_once(self, *, trigger: str = "schedule") -> SubscriptionRunSummary:
        return asyncio.run(self.run_once_async(trigger=trigger))

    def load_config(self) -> SubscriptionConfig:
        if self._config_loader is not None:
            return self._config_loader()
        return self.store.load()

    def shutdown(self) -> None:
        close = getattr(self._download_submitter, "close", None)
        if callable(close):
            close()

    async def run_once_async(self, *, trigger: str = "schedule") -> SubscriptionRunSummary:
        started_at = _utc_ts()
        started = time.monotonic()
        cfg = self.load_config()
        cfg.validate()
        summary = await _RunSession(self, cfg, trigger).execute()
        summary.started_at = started_at
        summary.finished_at = _utc_ts()
        summary.elapsed_sec = round(time.monotonic() - started, 3)
        summary.latest_message = summary.message
        self.cache.write_summary(summary.schedule_payload())
        return summary

    def _progress(
        self,
        summary: SubscriptionRunSummary,
        *,
        stage: Optional[str] = None,
        message: str = "",
    ) -> None:
        if stage is not None:
            summary.stage = stage
        if self._progress_callback is None:
            return
        self._progress_callback(
            {
                "run_id": summary.run_id,
                "trigger": summary.trigger,
                "stage": summary.stage,
                "scanned_books": summary.scanned_books,
                "pending_episodes": summary.pending_episodes,
                "submitted_jobs": summary.submitted_jobs,
                "pulled_feeds": summary.pulled_feeds,
                "latest_message": message or summary.stage,
            }
        )

    @staticmethod
    def _default_discord_api(token: str) -> DiscordShareAPI:
        return DiscordShareAPI(str(CGS_DISCORD_SHARE_API or "").strip(), token)

    @staticmethod
    def _default_worker_client(token: str) -> WorkerIndexClient:
        return WorkerIndexClient(auth_token=token)


class _RunSession:
    """One subscription cycle: ordered stages over shared mutable context."""

    def __init__(self, runner: SubscriptionRunner, cfg: SubscriptionConfig, trigger: str) -> None:
        self.runner = runner
        self.cfg = cfg
        self.trigger = trigger
        self.manual = trigger == "manual"
        self.now = runner._now_provider()
        self.summary = SubscriptionRunSummary(trigger=trigger, stage="Config")
        self.book_entries: list[BookEntry] = []
        self.feature_entries: list[FeatureEntry] = []
        self.scan_books: list[BookInfo] = []
        self.state_key_by_book: dict[int, str] = {}
        self.follow_books: list[BookInfo] = []
        self.follow_ids: set[int] = set()
        self.latest_seen: dict[str, str] = {}
        self.latest_seen_updates: dict[str, str] = {}
        self.states: dict[str, BookCheckState] = {}
        self.checkin_states: dict[str, CheckinSiteState] = {}
        self.checkin_state_changed = False
        self.observations: dict[str, bool] = {}
        self.pending_books: list[_PendingBook] = []

    async def execute(self) -> SubscriptionRunSummary:
        self.runner._progress(self.summary, message="config loaded")
        self._prepare_entries()
        await self._pull_follows()
        await self._scan_sites()
        await self._publish_if_needed()
        self._writeback_state()
        if self.summary.book_errors or self.summary.feature_errors:
            self.summary.status = "degraded"
        return self.summary

    def _prepare_entries(self) -> None:
        unsupported = unsupported_features(self.cfg.features)
        if unsupported:
            raise ValueError(
                f"unsupported feature tracking: {unsupported_feature_summary(unsupported)}"
            )
        if self.cfg.books:
            self.runner._library_store.ensure_books_from_yaml(self.cfg.books)
        enabled = [
            entry
            for entry in self.runner._library_store.book_entries(yaml_books=self.cfg.books)
            if entry.enabled
        ]
        # D-w6: Layer C is_due is NOT the primary due gate. State still loads for writeback.
        self.states = self.runner._check_state_store.load()
        self.book_entries = (
            enabled
            if self.manual
            else _filter_books_for_trigger(enabled, self.cfg, self.now, trigger=self.trigger)
        )
        self.feature_entries = supported_features(self.cfg.features)
        self.checkin_states = self.runner._checkin_state_store.load()
        for entry in self.book_entries:
            book = self.runner._book_resolver.resolve(entry)
            self.scan_books.append(book)
            self.state_key_by_book[id(book)] = _book_state_key(entry)
        self.runner._progress(
            self.summary,
            stage="Scan",
            message=f"{len(self.book_entries)} slot books, {len(self.feature_entries)} features",
        )

    async def _pull_follows(self) -> None:
        if not self.cfg.follows:
            return
        token = self.runner._token_provider(self.cfg)
        if not token:
            raise ValueError("discord_share_user_token is required for follow metadata pull")
        self.latest_seen = _load_latest_seen(self.runner._latest_seen_path)
        for follow in self.cfg.follows:
            self.runner._progress(self.summary, stage="Pull", message=f"worker index {follow.bid}")
            worker = self.runner._worker_client_factory(token)
            record = await worker.get_index(follow.bid)
            payload = await self.runner._cdn_fetcher(record.attachment_url)
            books = deserialize_books(payload)
            self.summary.pulled_feeds += 1
            for book in books:
                latest = str(getattr(book, "latest_sec", "") or "")
                seen_key = _follow_seen_key(book)
                if latest and not self.manual and self.latest_seen.get(seen_key) == latest:
                    continue
                if latest:
                    self.latest_seen_updates[seen_key] = latest
                self.follow_books.append(book)
            self.runner._progress(
                self.summary, message=f"pulled {len(books)} books from {follow.bid}"
            )
        self.follow_ids = {id(book) for book in self.follow_books}

    async def _scan_sites(self) -> None:
        book_groups = _group_books_by_site(self.scan_books + self.follow_books)
        feature_groups = _group_features_by_site(self.feature_entries)
        for site_key in _merged_site_keys(book_groups, feature_groups):
            await _SiteScanPass(self, site_key, book_groups, feature_groups).run()

    async def _publish_if_needed(self) -> None:
        if self.cfg.publish is not None and self.summary.submitted_jobs:
            self.runner._progress(self.summary, stage="Metadata", message="publishing metadata")
            await self._publish_metadata([item.metadata_book for item in self.pending_books])
            self.summary.published_metadata = True
        elif self.summary.submitted_jobs:
            self.runner._progress(
                self.summary, message="metadata sync skipped: config is not published"
            )
        if self.pending_books:
            self.summary.cache = self.runner.cache.write_books(
                [item.metadata_book for item in self.pending_books]
            )

    def _writeback_state(self) -> None:
        if self.observations:
            catchup_days = _catchup_interval_days()
            for key, found_new in self.observations.items():
                prior = self.states.get(key) or BookCheckState(key=key)
                self.states[key] = recalculate(
                    prior,
                    found_new=found_new,
                    now=self.now,
                    catchup_interval_days=catchup_days,
                )
            self.runner._check_state_store.save(self.states)
        if self.checkin_state_changed:
            self.runner._checkin_state_store.save(self.checkin_states)
        if self.latest_seen_updates:
            _save_latest_seen(
                self.runner._latest_seen_path,
                {**self.latest_seen, **self.latest_seen_updates},
            )

    async def _publish_metadata(self, books: list[BookInfo]) -> None:
        token = self.runner._token_provider(self.cfg)
        if not token:
            raise ValueError("discord_share_user_token is required for metadata publish")
        channel_id = str(CGS_METADATA_CHANNEL_ID or "").strip()
        if not channel_id:
            raise ValueError("CGS_METADATA_CHANNEL_ID is required for metadata publish")
        e2 = E2PublishMetadata(
            bid_provider=lambda _ctx: self.cfg.publish.bid,
            books_provider=lambda _ctx: books,
            site_provider=lambda _ctx: "subscription",
        )
        action = e2.on_event(TimelineStage.POSTPROCESSING, SimpleNamespace())
        if action is None:
            return
        payload_bytes = serialize_books(action.payload["books"])
        discord = self.runner._discord_api_factory(token)
        upload = await discord.upload_metadata(
            payload_bytes=payload_bytes,
            site=action.payload["site"],
            book_names=action.payload["book_names"],
            channel_id=channel_id,
        )
        worker = self.runner._worker_client_factory(token)
        record = IndexRecord(
            message_id=upload.message_id,
            attachment_url=upload.attachment_url,
            updated_at=upload.updated_at,
        )
        await worker.put_index(action.payload["bid"], record)


class _SiteScanPass:
    """Per-site stage: checkin → open runtime → features → books → submit.

    Fault isolation is item-scoped (feature / book / site open), not nested hell.
    """

    def __init__(
        self,
        session: _RunSession,
        site_key: str,
        book_groups: dict[str, list[BookInfo]],
        feature_groups: dict[str, list[FeatureEntry]],
    ) -> None:
        self.session = session
        self.site_key = site_key
        self.site_index = _site_index_for(site_key)
        self.site_books = list(book_groups.get(site_key, ()))
        self.feature_entries = list(feature_groups.get(site_key, ()))
        self.feature_owner_by_book: dict[int, str] = {}
        self.runner = session.runner
        self.summary = session.summary

    async def run(self) -> None:
        if await self._maybe_checkin():
            self.session.checkin_state_changed = True
        runtime_cm = self._open_runtime_cm()
        if runtime_cm is None:
            return
        try:
            async with runtime_cm as runtime:
                await self._scan_features(runtime)
                self._tally_site_books()
                await self._scan_books(runtime)
        except Exception as site_exc:
            self._record_site_error(site_exc)

    def _open_runtime_cm(self):
        try:
            return self.runner._site_runtime_factory(
                self.site_key,
                site_proxy=getattr(self.session.cfg, "site_proxy", None) or {},
            )
        except Exception as site_exc:
            self._record_site_error(site_exc)
            return None

    async def _maybe_checkin(self) -> bool:
        cfg = self.session.cfg
        if not cfg.checkin.enabled or resolve_checkin_spec(self.site_key) is None:
            return False
        if not is_checkin_due(
            self.session.checkin_states.get(self.site_key),
            cfg.checkin.interval_preset,
            self.session.now,
        ):
            return False
        self.runner._progress(self.summary, message=f"checkin: {self.site_key}")
        try:
            result = await asyncio.to_thread(self.runner._checkin_runner, self.site_key)
        except Exception as exc:
            _CheckinOutcome.failed(
                self.summary,
                self.site_key,
                detail=f"{type(exc).__name__}: {exc}",
                exc=exc,
            )
            return False
        if not _CheckinOutcome.apply(self.summary, self.site_key, result):
            return False
        mark_checkin(self.session.checkin_states, self.site_key, self.session.now)
        return True

    async def _scan_features(self, runtime) -> None:
        for entry in self.feature_entries:
            await self._scan_one_feature(runtime, entry)

    async def _scan_one_feature(self, runtime, entry: FeatureEntry) -> None:
        label = f"{entry.kind}:{entry.value}"
        self.runner._progress(
            self.summary, stage="Scan", message=f"feature search: {entry.kind} {entry.value}"
        )
        try:
            results = await runtime.preview_feature_search(
                kind=entry.kind, value=entry.value, page=1
            )
            if not isinstance(results, list):
                raise TypeError(
                    f"preview_feature_search must return list, got {type(results).__name__}"
                )
            matched = filter_feature_books(entry, results)
            new_books = filter_new_books(
                matched, seen_keys=self.runner._downloaded_book_md5s(entry, matched)
            )
        except Exception as feature_exc:
            self.summary.feature_errors += 1
            _log_book_error(
                kind="feature_error",
                site=self.site_key,
                title=label,
                exc=feature_exc,
            )
            self.runner._progress(
                self.summary,
                message=f"feature error {label}: {type(feature_exc).__name__}",
            )
            return
        feature_key = _feature_state_key(entry)
        self.session.observations[feature_key] = (
            self.session.observations.get(feature_key, False) or bool(new_books)
        )
        for book in new_books:
            self.feature_owner_by_book[id(book)] = feature_key
        self.site_books.extend(new_books)
        self.runner._progress(
            self.summary,
            message=f"feature {label} matched {len(matched)} books",
        )

    def _tally_site_books(self) -> None:
        follow_ids = self.session.follow_ids
        self.summary.scanned_books += len(self.site_books)
        self.summary.follow_books += sum(1 for book in self.site_books if id(book) in follow_ids)
        self.summary.own_books += sum(1 for book in self.site_books if id(book) not in follow_ids)

    async def _scan_books(self, runtime) -> None:
        for book in self.site_books:
            await self._process_one_book(runtime, book)

    async def _process_one_book(self, runtime, book: BookInfo) -> None:
        book_label = str(getattr(book, "name", "") or getattr(book, "url", "") or self.site_key)
        self.runner._progress(self.summary, stage="Episodes", message=f"episodes: {book_label}")
        try:
            pending = await self._pending_for_book(book, runtime)
        except Exception as book_exc:
            self.summary.book_errors += 1
            _log_book_error(kind="book_error", site=self.site_key, title=book_label, exc=book_exc)
            self.runner._progress(
                self.summary,
                message=f"book error {book_label}: {type(book_exc).__name__}",
            )
            return
        self.session.pending_books.append(pending)
        self.summary.pending_episodes += len(pending.pending_episodes)
        self.summary.pending_items.extend(_pending_item_rows(pending))
        self.runner._progress(
            self.summary,
            message=f"{len(pending.pending_episodes)} pending in {book_label}",
        )
        found_new = bool(pending.pending_episodes)
        book_key = self.session.state_key_by_book.get(id(book))
        if book_key is not None:
            self.session.observations[book_key] = found_new
        feature_key = self.feature_owner_by_book.get(id(book))
        if feature_key is not None:
            self.session.observations[feature_key] = (
                self.session.observations.get(feature_key, False) or found_new
            )
        if not pending.pending_episodes:
            return
        await self._submit_pending(book_label, pending)

    async def _submit_pending(self, book_label: str, pending: _PendingBook) -> None:
        self.runner._progress(self.summary, stage="Submit", message=f"submitting {book_label}")
        try:
            await self._submit_download(pending.pending_episodes)
        except Exception as submit_exc:
            self.summary.book_errors += 1
            _log_book_error(
                kind="submit_error", site=self.site_key, title=book_label, exc=submit_exc
            )
            self.runner._progress(
                self.summary,
                message=f"submit error {book_label}: {type(submit_exc).__name__}",
            )
            return
        self.summary.submitted_jobs += 1
        self.runner._progress(self.summary, message=f"submitted {book_label}")

    async def _pending_for_book(self, book: BookInfo, runtime) -> _PendingBook:
        site_episodes = list(await runtime.preview_fetch_episodes(book) or [])
        for idx, episode in enumerate(site_episodes, start=1):
            if getattr(episode, "idx", None) is None:
                episode.idx = idx
            episode.from_book = book
        pending = self._filter_episodes(book, site_episodes)
        for episode in pending:
            page_urls = await runtime.preview_fetch_pages(episode)
            if not isinstance(page_urls, list):
                raise TypeError(
                    f"preview_fetch_pages must return list, got {type(page_urls).__name__}"
                )
            episode.page_urls = list(page_urls)
            episode.pages = len(page_urls)
        return _PendingBook(
            book=book,
            site_index=self.site_index,
            pending_episodes=pending,
            metadata_book=_metadata_book(book, site_episodes),
        )

    def _filter_episodes(self, book: BookInfo, site_episodes: list) -> list:
        ctx = SimpleNamespace(
            eps={str(idx): episode for idx, episode in enumerate(site_episodes, start=1)}
        )
        middleware = D2EpisodeDiff(
            dl_max_provider=lambda _ctx: self._dl_max_for(book),
            md5s_provider=lambda _ctx, episodes: self._downloaded_md5s(book, episodes),
        )
        middleware.on_event(TimelineStage.WAIT_EP_DECISION, ctx)
        return list(ctx.eps.values())

    async def _submit_download(
        self, episodes: list, *, timeout_sec: Optional[int] = None
    ) -> None:
        payload = episodes[0] if len(episodes) == 1 else list(episodes)
        submitter = self.runner._download_submitter
        try:
            result = submitter(
                self.site_index,
                payload,
                timeout_sec=timeout_sec or _DEFAULT_DOWNLOAD_TIMEOUT_SEC,
            )
        except TypeError:
            result = submitter(self.site_index, payload)
        if not result:
            raise RuntimeError(
                f"subscription download job failed for site_index={self.site_index}"
            )

    def _dl_max_for(self, book: BookInfo) -> str:
        if self.runner._dl_max_provider is not None:
            return str(self.runner._dl_max_provider(book) or "")
        if self.runner._show_max_cache is None:
            self.runner._show_max_cache = RedViewerHandler().show_max()
        show = self.runner._show_max_cache.get(getattr(book, "name", ""))
        return str(getattr(show, "dl_max", "") or "")

    def _downloaded_md5s(self, book: BookInfo, episodes: list) -> set[str]:
        if self.runner._md5s_provider is not None:
            return set(self.runner._md5s_provider(book, episodes) or set())
        return set(self.runner._download_state.downloaded_md5s(episodes))

    def _record_site_error(self, site_exc: BaseException) -> None:
        self.summary.book_errors += 1
        _log_book_error(kind="site_error", site=self.site_key, title=self.site_key, exc=site_exc)
        self.runner._progress(
            self.summary,
            message=f"site error {self.site_key}: {type(site_exc).__name__}",
        )


class _CheckinOutcome:
    """Map CheckinResult → summary counters + tray log (flat, no if ladder at call site)."""

    @staticmethod
    def failed(
        summary: SubscriptionRunSummary,
        site_key: str,
        *,
        detail: str,
        exc: Optional[BaseException] = None,
    ) -> None:
        summary.checkin_failed += 1
        _log_checkin("checkin_failed", site_key, result="error", detail=detail, exc=exc)

    @staticmethod
    def apply(summary: SubscriptionRunSummary, site_key: str, result: CheckinResult) -> bool:
        if result.ok:
            summary.checkin_ok += 1
            _log_checkin("checkin_ok", site_key, result="ok", detail=result.message)
            return True
        if result.already:
            summary.checkin_already += 1
            _log_checkin("checkin_already", site_key, result="ok", detail=result.message)
            return True
        _CheckinOutcome.failed(
            summary, site_key, detail=result.message or "checkin failed"
        )
        return False


def _log_book_error(*, kind: str, site: str, title: str, exc: BaseException) -> None:
    from utils.tray.event_log import TrayEventLog

    detail = f"{title}: {type(exc).__name__}: {exc}"
    TrayEventLog().append(kind, book=site, result="error", detail=detail[:500], exc=exc)


def _log_checkin(
    kind: str,
    site: str,
    *,
    result: str,
    detail: str,
    exc: Optional[BaseException] = None,
) -> None:
    from utils.tray.event_log import TrayEventLog

    TrayEventLog().append(kind, book=site, result=result, detail=detail, exc=exc)


async def _fetch_cdn_bytes(url: str) -> bytes:
    transport = httpx.AsyncHTTPTransport(verify=get_httpx_verify())
    async with httpx.AsyncClient(transport=transport, trust_env=False, timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def _default_token(cfg: SubscriptionConfig) -> str:
    return str(conf.discord_share_user_token or "").strip()


class _RuntimeDownloadSubmitter:
    def __init__(self) -> None:
        self.runtime: Optional[SpiderRuntimeThread] = None

    def __call__(
        self,
        site_index: int,
        payload,
        *,
        timeout_sec: int = _DEFAULT_DOWNLOAD_TIMEOUT_SEC,
    ) -> bool:
        timeout_sec = int(timeout_sec)
        if timeout_sec <= 0:
            raise ValueError("subscription download timeout_sec must be positive")
        deadline = time.monotonic() + timeout_sec
        runtime = self._runtime()
        job = SpiderDownloadJob(
            job_id=uuid4().hex,
            spider_name=SPIDERS[site_index],
            site_index=site_index,
            payload=payload,
            options={},
        )
        runtime.submit_job(job)
        while True:
            try:
                event = runtime.event_q.get(timeout=0.2)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"subscription download job timed out after {timeout_sec}s: {job.job_id}"
                    )
                continue
            if getattr(event, "job_id", None) != job.job_id:
                continue
            if isinstance(event, ErrorEvent):
                raise RuntimeError(event.error)
            if isinstance(event, JobFinishedEvent):
                if event.success:
                    return True
                raise RuntimeError(
                    event.error or f"subscription download job failed: {job.job_id}"
                )

    def close(self) -> None:
        if self.runtime is None:
            return
        self.runtime.shutdown()
        self.runtime.join(timeout=5)
        self.runtime = None

    def _runtime(self) -> SpiderRuntimeThread:
        if self.runtime is None or not self.runtime.is_alive():
            self.runtime = SpiderRuntimeThread()
            self.runtime.daemon = True
            self.runtime.start()
            self.runtime.wait_ready(timeout=30)
        return self.runtime


def _book_state_key(entry: BookEntry) -> str:
    return f"{entry.site}:{entry.url}"


def _feature_state_key(entry: FeatureEntry) -> str:
    return f"{entry.site}:{entry.kind}:{entry.value}"


def _follow_seen_key(book: BookInfo) -> str:
    return f"follow-book:{_book_site_key(book)}:{getattr(book, 'url', '')}"


def _filter_books_for_trigger(
    book_entries: list[BookEntry],
    cfg: SubscriptionConfig,
    now: datetime,
    *,
    trigger: str,
) -> list[BookEntry]:
    """Primary: enabled ∩ effective_slot.matches. Catchup/schedule-generic: all enabled.

    Layer C ``is_due`` is intentionally not consulted (D-w6).
    """
    trigger_text = str(trigger or "").strip().lower()
    primary_like = (
        trigger_text.startswith("primary")
        or "primary_card" in trigger_text
        or "weekday slot" in trigger_text
    )
    if not primary_like:
        return list(book_entries)
    return [
        entry
        for entry in book_entries
        if effective_slot(entry, cfg.check).matches(now)
    ]


def _catchup_interval_days() -> Optional[float]:
    from utils.subscription.schema import PRESET_INTERVAL_HOURS
    from utils.subscription.store import get_subscription_catchup_preset

    hours = PRESET_INTERVAL_HOURS.get(get_subscription_catchup_preset())
    if hours is None:
        return None
    return max(float(hours) / 24.0, 1.0 / 24.0)


def _load_latest_seen(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict):
        raise ValueError("subscription latest-seen state must be a mapping")
    for key, value in payload.items():
        if not isinstance(value, str):
            raise ValueError(f"latest-seen entry for {key!r} must be a string")
    return dict(payload)


def _save_latest_seen(path: Path, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(entries, fp, ensure_ascii=False, separators=(",", ":"))


def _book_site_key(book: BookInfo) -> str:
    source = str(getattr(book, "source", "") or "").strip()
    if not source:
        raise ValueError(f"subscription book missing source: {getattr(book, 'name', '')!r}")
    return source


def _group_books_by_site(books: list[BookInfo]) -> dict[str, list[BookInfo]]:
    groups: dict[str, list[BookInfo]] = {}
    for book in books:
        groups.setdefault(_book_site_key(book), []).append(book)
    return groups


def _group_features_by_site(entries: list[FeatureEntry]) -> dict[str, list[FeatureEntry]]:
    groups: dict[str, list[FeatureEntry]] = {}
    for entry in entries:
        site = str(entry.site or "").strip()
        if not site:
            raise ValueError(f"feature entry site is required for {entry.kind}:{entry.value}")
        groups.setdefault(site).append(entry)
    return groups


def _merged_site_keys(
    book_groups: dict[str, list[BookInfo]],
    feature_groups: dict[str, list[FeatureEntry]],
) -> list[str]:
    keys = list(book_groups)
    keys.extend(key for key in feature_groups if key not in book_groups)
    return keys


def _site_index_for(site_key: str) -> int:
    descriptor = resolve_provider_descriptor_by_site(site_key)
    if descriptor.site_index is None:
        raise ValueError(f"provider descriptor does not expose numeric site index: {site_key!r}")
    return int(descriptor.site_index)


def _metadata_book(book: BookInfo, site_episodes: list) -> BookInfo:
    cloned = deepcopy(book)
    cloned.episodes = None
    latest_name = _latest_episode_name(site_episodes)
    if latest_name and hasattr(cloned, "latest_sec"):
        cloned.latest_sec = latest_name
    return cloned


def _pending_item_rows(pending: _PendingBook) -> list[dict[str, str | int | bool]]:
    book = pending.book
    rows = []
    for episode in pending.pending_episodes:
        item_id = str(getattr(episode, "id", "") or getattr(episode, "name", "") or "")
        rows.append(
            {
                "item_id": item_id,
                "book": str(getattr(book, "name", "") or ""),
                "site": _book_site_key(book),
                "episode": str(getattr(episode, "name", "") or item_id),
                "pages": int(getattr(episode, "pages", 0) or 0),
                "submitted": False,
            }
        )
    return rows


def _latest_episode_name(site_episodes: list) -> str:
    if not site_episodes:
        return ""
    return str(getattr(site_episodes[0], "name", "") or "")


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
