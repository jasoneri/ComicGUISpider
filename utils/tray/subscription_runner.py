# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import inspect
import queue
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

import httpx

from ComicSpider.runtime import SpiderRuntimeThread
from utils import conf, get_httpx_verify
from utils.middleware.presets.c3_feature_diff import filter_new_books
from utils.middleware.presets.d2_episode_diff import D2EpisodeDiff
from utils.middleware.presets.e2_publish_metadata import E2PublishMetadata
from utils.middleware.timeline import TimelineStage
from utils.protocol import ErrorEvent, JobFinishedEvent, SpiderDownloadJob
from utils.redViewer_tools import Handler as RedViewerHandler
from utils.share import DiscordShareAPI, IndexRecord, WorkerIndexClient, deserialize_books, serialize_books
from utils.sql.download_state import DownloadStateStore
from utils.subscription import MODE_BROADCASTER, MODE_SUBSCRIBER, SubscriptionStore
from utils.subscription.schema import BookEntry, FeatureEntry, SubscriptionConfig
from utils.tray.feature_search import filter_feature_books, supported_features, unsupported_feature_summary, unsupported_features
from utils.tray.schedule_presentation import ScheduleCache, ScheduleCacheState
from utils.config.qc import cgs_cfg
from utils.website.info import (
    BookInfo,
    ComicabcBookInfo,
    Dm5BookInfo,
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
    EhBookInfo,
)
from utils.website.registry import resolve_provider_descriptor_by_site
from utils.website.runtime_context import PreviewSiteConfig
from utils.website.site_runtime import ThreadSiteRuntime
from variables import CGS_DISCORD_SHARE_API, CGS_METADATA_CHANNEL_ID, SPIDERS

BookRuntimeFactory = Callable[[str], Any]
DownloadSubmitter = Callable[[int, Any], bool | Awaitable[bool]]
DiscordApiFactory = Callable[[str], DiscordShareAPI]
WorkerClientFactory = Callable[[str], WorkerIndexClient]
CdnFetcher = Callable[[str], Awaitable[bytes]]
TokenProvider = Callable[[SubscriptionConfig], str]
DlMaxProvider = Callable[[Any], str]
Md5sProvider = Callable[[Any, list], set[str]]
ProgressCallback = Callable[[dict], None]

_DEFAULT_DOWNLOAD_TIMEOUT_SEC = 60


@dataclass
class SubscriptionRunSummary:
    mode: str
    run_id: str = field(default_factory=lambda: uuid4().hex)
    trigger: str = "schedule"
    status: str = "ok"
    stage: str = ""
    started_at: str = ""
    finished_at: str = ""
    elapsed_sec: float = 0.0
    scanned_books: int = 0
    pending_episodes: int = 0
    submitted_jobs: int = 0
    published_metadata: bool = False
    pulled_feeds: int = 0
    latest_message: str = ""
    pending_items: list[dict[str, str | int | bool]] = field(default_factory=list)
    cache: ScheduleCacheState = field(default_factory=lambda: ScheduleCacheState(status="missing"))

    @property
    def message(self) -> str:
        parts = [
            f"mode={self.mode}",
            f"books={self.scanned_books}",
            f"pending={self.pending_episodes}",
            f"jobs={self.submitted_jobs}",
        ]
        if self.pulled_feeds:
            parts.append(f"feeds={self.pulled_feeds}")
        if self.published_metadata:
            parts.append("metadata=published")
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
                "pending_episodes": self.pending_episodes,
                "submitted_jobs": self.submitted_jobs,
                "published_metadata": self.published_metadata,
                "pulled_feeds": self.pulled_feeds,
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
    """Mode-driven subscription execution entry used by the tray process."""

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
    ) -> None:
        self.store = store or SubscriptionStore()
        self.cache = ScheduleCache()
        self._config_loader = config_loader
        self._site_runtime_factory = site_runtime_factory or _DefaultSiteRuntimeSession
        self._download_submitter = download_submitter or _RuntimeDownloadSubmitter()
        self._discord_api_factory = discord_api_factory or self._default_discord_api
        self._worker_client_factory = worker_client_factory or self._default_worker_client
        self._cdn_fetcher = cdn_fetcher or _fetch_cdn_bytes
        self._token_provider = token_provider or _default_token
        self._dl_max_provider = dl_max_provider
        self._md5s_provider = md5s_provider
        self._progress_callback = progress_callback
        self._show_max_cache: Optional[dict] = None
        self._download_state = DownloadStateStore()

    def run_once(self) -> SubscriptionRunSummary:
        return asyncio.run(self.run_once_async())

    def load_config(self) -> SubscriptionConfig:
        if self._config_loader is not None:
            return self._config_loader()
        return self.store.load()

    def shutdown(self) -> None:
        close = getattr(self._download_submitter, "close", None)
        if callable(close):
            close()

    async def run_once_async(self) -> SubscriptionRunSummary:
        started_at = _utc_ts()
        started = time.monotonic()
        cfg = self.load_config()
        cfg.validate()
        if cfg.mode == MODE_BROADCASTER:
            summary = await self._run_broadcaster(cfg)
        elif cfg.mode == MODE_SUBSCRIBER:
            summary = await self._run_subscriber(cfg)
        else:
            raise ValueError(f"unsupported subscription mode: {cfg.mode!r}")
        summary.started_at = started_at
        summary.finished_at = _utc_ts()
        summary.elapsed_sec = round(time.monotonic() - started, 3)
        summary.latest_message = summary.message
        self.cache.write_summary(summary.schedule_payload())
        return summary

    def _progress(self, summary: SubscriptionRunSummary, *, stage: Optional[str] = None, message: str = "") -> None:
        """Emit a live stage/counter snapshot to the optional progress callback.

        Qt-free: the callback receives a plain dict. The tray consumer marshals it
        onto the Qt thread via a signal. Called from the runner's async thread.
        """
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

    async def _run_broadcaster(self, cfg: SubscriptionConfig) -> SubscriptionRunSummary:
        entries = [entry for entry in cfg.broadcaster.books if entry.enabled]
        feature_entries = supported_features(cfg.broadcaster.features)
        unsupported = unsupported_features(cfg.broadcaster.features)
        if unsupported:
            raise ValueError(f"unsupported feature tracking: {unsupported_feature_summary(unsupported)}")
        summary = SubscriptionRunSummary(mode=MODE_BROADCASTER, stage="Config")
        self._progress(summary, message="config loaded")
        if not entries and not feature_entries:
            self._progress(summary, stage="Scan", message="no enabled books or supported features")
            return summary

        self._progress(summary, stage="Scan", message="scanning sources")
        pending_books: list[_PendingBook] = []
        book_groups = _group_books_by_site([_book_from_entry(entry) for entry in entries])
        feature_groups = _group_features_by_site(feature_entries)
        for site_key in _merged_site_keys(book_groups, feature_groups):
            site_index = _site_index_for(site_key)
            async with self._site_runtime_factory(site_key) as runtime:
                site_books = list(book_groups.get(site_key, ()))
                for entry in feature_groups.get(site_key, ()):
                    self._progress(summary, stage="Scan", message=f"feature search: {entry.kind} {entry.value}")
                    results = await runtime.preview_feature_search(kind=entry.kind, value=entry.value, page=1)
                    if not isinstance(results, list):
                        raise TypeError(f"preview_feature_search must return list, got {type(results).__name__}")
                    matched = filter_feature_books(entry, results)
                    site_books.extend(filter_new_books(matched, seen_keys=self._downloaded_book_md5s(entry, matched)))
                    self._progress(summary, message=f"feature {entry.kind}:{entry.value} matched {len(matched)} books")
                summary.scanned_books += len(site_books)
                for book in site_books:
                    self._progress(summary, stage="Episodes", message=f"episodes: {getattr(book, 'name', '') or book.url}")
                    pending = await self._pending_for_book(book, runtime, site_index=site_index)
                    pending_books.append(pending)
                    summary.pending_episodes += len(pending.pending_episodes)
                    summary.pending_items.extend(_pending_item_rows(pending))
                    self._progress(summary, message=f"{len(pending.pending_episodes)} pending in {getattr(book, 'name', '') or book.url}")
                    if pending.pending_episodes:
                        self._progress(summary, stage="Submit", message=f"submitting {getattr(book, 'name', '') or book.url}")
                        await self._submit_download(site_index, pending.pending_episodes)
                        summary.submitted_jobs += 1
                        self._progress(summary, message=f"submitted {getattr(book, 'name', '') or book.url}")

        publish_bid = str(cfg.broadcaster.publish_bid or "").strip()
        if summary.submitted_jobs and publish_bid:
            self._progress(summary, stage="Metadata", message="publishing metadata")
            await self._publish_metadata(cfg, [item.metadata_book for item in pending_books])
            summary.published_metadata = True
        elif summary.submitted_jobs:
            self._progress(summary, message="metadata sync skipped: share card is not published")
        if pending_books:
            summary.cache = self.cache.write_books([item.metadata_book for item in pending_books])
        return summary

    async def _run_subscriber(self, cfg: SubscriptionConfig) -> SubscriptionRunSummary:
        summary = SubscriptionRunSummary(mode=MODE_SUBSCRIBER, stage="Config")
        self._progress(summary, message="config loaded")
        if not cfg.subscriber.auto_download:
            return summary

        if not cfg.subscriber.follows:
            return summary

        token = self._token_provider(cfg)
        if not token:
            raise ValueError("discord_share_user_token is required for subscriber metadata pull")

        pulled_books: list[BookInfo] = []
        for follow in cfg.subscriber.follows:
            self._progress(summary, stage="Worker", message=f"worker index {follow.bid}")
            worker = self._worker_client_factory(token)
            record = await worker.get_index(follow.bid)
            self._progress(summary, stage="PKL", message="downloading pkl")
            payload = await self._cdn_fetcher(record.attachment_url)
            books = deserialize_books(payload)
            summary.pulled_feeds += 1
            summary.scanned_books += len(books)
            pulled_books.extend(books)
            self._progress(summary, message=f"pulled {len(books)} books from {follow.bid}")
        if pulled_books:
            summary.cache = self.cache.write_books(pulled_books)

        for site_key, site_books in _group_books_by_site(pulled_books).items():
            site_index = _site_index_for(site_key)
            async with self._site_runtime_factory(site_key) as runtime:
                for book in site_books:
                    self._progress(summary, stage="Episodes", message=f"episodes: {getattr(book, 'name', '') or getattr(book, 'url', '')}")
                    pending = await self._pending_for_book(book, runtime, site_index=site_index)
                    summary.pending_episodes += len(pending.pending_episodes)
                    summary.pending_items.extend(_pending_item_rows(pending))
                    if pending.pending_episodes:
                        self._progress(summary, stage="Submit", message=f"submitting {getattr(book, 'name', '') or getattr(book, 'url', '')}")
                        await self._submit_download(site_index, pending.pending_episodes)
                        summary.submitted_jobs += 1
        return summary

    async def _pending_for_book(self, book: BookInfo, runtime, *, site_index: int) -> _PendingBook:
        site_episodes = await runtime.preview_fetch_episodes(book)
        site_episodes = list(site_episodes or [])
        for idx, episode in enumerate(site_episodes, start=1):
            if getattr(episode, "idx", None) is None:
                episode.idx = idx
            episode.from_book = book
        pending = self._filter_episodes(book, site_episodes)
        for episode in pending:
            page_urls = await runtime.preview_fetch_pages(episode)
            if not isinstance(page_urls, list):
                raise TypeError(f"preview_fetch_pages must return list, got {type(page_urls).__name__}")
            episode.page_urls = list(page_urls)
            episode.pages = len(page_urls)
        return _PendingBook(book=book, site_index=site_index, pending_episodes=pending, metadata_book=_metadata_book(book, site_episodes))

    def _filter_episodes(self, book: BookInfo, site_episodes: list) -> list:
        ctx = SimpleNamespace(eps={str(idx): episode for idx, episode in enumerate(site_episodes, start=1)})
        middleware = D2EpisodeDiff(
            dl_max_provider=lambda _ctx: self._dl_max_for(book),
            md5s_provider=lambda _ctx, episodes: self._downloaded_md5s(book, episodes),
        )
        middleware.on_event(TimelineStage.WAIT_EP_DECISION, ctx)
        return list(ctx.eps.values())

    async def _submit_download(self, site_index: int, episodes: list, *, timeout_sec: Optional[int] = None) -> None:
        payload = episodes[0] if len(episodes) == 1 else list(episodes)
        if isinstance(self._download_submitter, _RuntimeDownloadSubmitter):
            result = self._download_submitter(site_index, payload, timeout_sec=timeout_sec or _DEFAULT_DOWNLOAD_TIMEOUT_SEC)
        else:
            result = self._download_submitter(site_index, payload)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            raise RuntimeError(f"subscription download job failed for site_index={site_index}")

    async def _publish_metadata(self, cfg: SubscriptionConfig, books: list[BookInfo]) -> None:
        token = self._token_provider(cfg)
        if not token:
            raise ValueError("discord_share_user_token is required for broadcaster metadata publish")
        channel_id = str(CGS_METADATA_CHANNEL_ID or "").strip()
        if not channel_id:
            raise ValueError("CGS_METADATA_CHANNEL_ID is required for metadata publish")

        e2 = E2PublishMetadata(
            mode_provider=lambda _ctx: cfg.mode,
            bid_provider=lambda _ctx: cfg.broadcaster.publish_bid,
            books_provider=lambda _ctx: books,
            site_provider=lambda _ctx: "subscription",
        )
        action = e2.on_event(TimelineStage.POSTPROCESSING, SimpleNamespace())
        if action is None:
            return

        payload_bytes = serialize_books(action.payload["books"])
        discord = self._discord_api_factory(token)
        upload = await discord.upload_metadata(
            payload_bytes=payload_bytes,
            site=action.payload["site"],
            book_names=action.payload["book_names"],
            channel_id=channel_id,
        )
        worker = self._worker_client_factory(token)
        record = IndexRecord(message_id=upload.message_id, attachment_url=upload.attachment_url, updated_at=upload.updated_at)
        await worker.put_index(action.payload["bid"], record)

    def _dl_max_for(self, book: BookInfo) -> str:
        if self._dl_max_provider is not None:
            return str(self._dl_max_provider(book) or "")
        if self._show_max_cache is None:
            self._show_max_cache = RedViewerHandler().show_max()
        show = self._show_max_cache.get(getattr(book, "name", ""))
        return str(getattr(show, "dl_max", "") or "")

    def _downloaded_md5s(self, book: BookInfo, episodes: list) -> set[str]:
        if self._md5s_provider is not None:
            return set(self._md5s_provider(book, episodes) or set())
        return set(self._download_state.downloaded_md5s(episodes))

    def _downloaded_book_md5s(self, entry: FeatureEntry, books: list) -> set[str]:
        if self._md5s_provider is not None:
            return set(self._md5s_provider(entry, books) or set())
        return set(self._download_state.downloaded_md5s(books))

    @staticmethod
    def _default_discord_api(token: str) -> DiscordShareAPI:
        return DiscordShareAPI(str(CGS_DISCORD_SHARE_API or "").strip(), token)

    @staticmethod
    def _default_worker_client(token: str) -> WorkerIndexClient:
        return WorkerIndexClient(auth_token=token)


class _DefaultSiteRuntimeSession:
    def __init__(self, site_key: str) -> None:
        self.site_key = site_key
        self.runtime = None

    async def __aenter__(self):
        descriptor = resolve_provider_descriptor_by_site(self.site_key)
        site_config = PreviewSiteConfig.create(
            descriptor.provider_name, cookies_by_site=conf.cookies, domains=getattr(conf, "domains", None),
            custom_map=conf.custom_map, proxies=conf.proxies, doh_url=cgs_cfg.doh.get_url(),
        )
        self.runtime = ThreadSiteRuntime(descriptor, site_config=site_config, conf_state=conf)
        self.runtime.get_async_preview_client()
        return self.runtime

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.runtime is not None:
            await self.runtime.aclose()


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

    def __call__(self, site_index: int, payload, *, timeout_sec: int = _DEFAULT_DOWNLOAD_TIMEOUT_SEC) -> bool:
        timeout_sec = int(timeout_sec)
        if timeout_sec <= 0:
            raise ValueError("subscription download timeout_sec must be positive")
        deadline = time.monotonic() + timeout_sec
        runtime = self._runtime()
        job = SpiderDownloadJob(job_id=uuid4().hex, spider_name=SPIDERS[site_index], site_index=site_index, payload=payload, options={})
        runtime.submit_job(job)
        while True:
            try:
                event = runtime.event_q.get(timeout=0.2)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"subscription download job timed out after {timeout_sec}s: {job.job_id}")
                continue
            if getattr(event, "job_id", None) != job.job_id:
                continue
            if isinstance(event, ErrorEvent):
                raise RuntimeError(event.error)
            if isinstance(event, JobFinishedEvent):
                if event.success:
                    return True
                raise RuntimeError(event.error or f"subscription download job failed: {job.job_id}")

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


def _book_from_entry(entry: BookEntry) -> BookInfo:
    site = str(entry.site or "").strip()
    if not site:
        raise ValueError("book entry site is required")
    book_type = _BOOK_TYPES.get(site)
    if book_type is None:
        resolve_provider_descriptor_by_site(site)
        book_type = BookInfo
    return book_type(id=entry.url, source=site if book_type is BookInfo else None, url=entry.url, preview_url=entry.url, name=entry.title)


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
        groups.setdefault(site, []).append(entry)
    return groups


def _merged_site_keys(book_groups: dict[str, list[BookInfo]], feature_groups: dict[str, list[FeatureEntry]]) -> list[str]:
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
                "source_id": f"book:{getattr(book, 'source', '')}:{getattr(book, 'url', '')}",
                "site": str(getattr(book, "source", "") or ""),
                "title": str(getattr(book, "name", "") or ""),
                "episode": str(getattr(episode, "name", "") or ""),
                "status": "pending",
                "stage": "Submit" if getattr(episode, "page_urls", None) else "Diff",
                "message": f"{getattr(episode, 'pages', 0) or 0} pages",
                "cover_url": str(getattr(book, "img_preview", "") or ""),
                "source_url": str(getattr(book, "preview_url", None) or getattr(book, "url", "") or ""),
            }
        )
    return rows


def _latest_episode_name(site_episodes: list) -> str:
    if not site_episodes:
        return ""
    return str(getattr(site_episodes[0], "name", "") or "")


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
