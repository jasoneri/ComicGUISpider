from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from utils import temp_p
from utils.share.serializer import deserialize_books, serialize_books
from utils.subscription import MODE_BROADCASTER, MODE_SUBSCRIBER
from utils.subscription.schema import BookEntry, FeatureEntry, FollowEntry, SubscriptionConfig
from utils.tray.feature_search import feature_status, supported_features, unsupported_feature_summary, unsupported_features

SCHEDULE_PRESENTATION_SCHEMA = 1
RUN_STAGES = {
    MODE_BROADCASTER: ("Config", "Scan", "Episodes", "Diff", "Submit", "Metadata"),
    MODE_SUBSCRIBER: ("Config", "Worker", "PKL", "Episodes", "Diff", "Submit"),
}


class ScheduleCacheError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScheduleCacheState:
    status: str
    pkl_path: str = ""
    summary_path: str = ""
    updated_at: str = ""
    message: str = ""
    book_count: int = 0


@dataclass(frozen=True)
class ScheduleSourceRow:
    source_id: str
    kind: str
    site: str
    title: str
    enabled: bool
    locator: str
    status: str
    latest: str = ""
    pending_count: int = 0


@dataclass(frozen=True)
class SchedulePendingItemRow:
    item_id: str
    source_id: str
    site: str
    title: str
    episode: str
    status: str
    stage: str
    message: str = ""
    cover_url: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class ScheduleRunView:
    run_id: str = ""
    trigger: str = ""
    status: str = "idle"
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
    error: str = ""


@dataclass(frozen=True)
class SchedulePlanView:
    mode: str
    mode_label: str
    automation_state: str
    automation_label: str
    next_run_at: str
    config_owner: str
    blocker: str
    blocker_action: str
    timing: str
    publish_bid: str
    enabled_books: int
    enabled_features: int
    follows: int
    auto_download: bool
    lookback_days: int
    pull_interval_hours: int


@dataclass(frozen=True)
class SchedulePresentation:
    schema_version: int
    generated_at: str
    plan: SchedulePlanView
    cache: ScheduleCacheState
    run: ScheduleRunView
    sources: list[ScheduleSourceRow] = field(default_factory=list)
    pending_items: list[SchedulePendingItemRow] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    debug_payload: dict[str, Any] = field(default_factory=dict)


class ScheduleCache:
    """Owns schedule cache paths and summary/pkl I/O under temp_p/subscription_schedule."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else temp_p / "subscription_schedule"
        self.summary_path = self.root / "summary.json"
        self.pkl_path = self.root / "bookinfo.pkl"

    def read_summary(self) -> dict[str, Any]:
        with open(self.summary_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        if not isinstance(payload, dict):
            raise ScheduleCacheError(f"schedule summary must be a mapping: {self.summary_path}")
        version = payload.get("schema_version")
        if version != SCHEDULE_PRESENTATION_SCHEMA:
            raise ScheduleCacheError(f"unsupported schedule summary schema {version!r}: {self.summary_path}")
        return payload

    def write_summary(self, payload: dict[str, Any]) -> None:
        versioned = {"schema_version": SCHEDULE_PRESENTATION_SCHEMA, **payload}
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.summary_path, "w", encoding="utf-8") as fp:
            json.dump(versioned, fp, ensure_ascii=False, indent=2, sort_keys=True)

    def write_books(self, books: list) -> ScheduleCacheState:
        payload = serialize_books(books)
        self.pkl_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pkl_path, "wb") as fp:
            fp.write(payload)
        return ScheduleCacheState(
            status="ready",
            pkl_path=str(self.pkl_path),
            summary_path=str(self.summary_path),
            updated_at=_utc_now(),
            message="bookinfo cache ready",
            book_count=len(books),
        )

    def load_books(self) -> list:
        try:
            with open(self.pkl_path, "rb") as fp:
                payload = fp.read()
            return deserialize_books(payload)
        except Exception as exc:
            raise ScheduleCacheError(f"failed to load schedule pkl cache: {self.pkl_path}: {exc}") from exc

    def state_from_summary(self, summary: Optional[dict[str, Any]]) -> ScheduleCacheState:
        if summary is None:
            if self.pkl_path.exists():
                return ScheduleCacheState(
                    status="summary missing",
                    pkl_path=str(self.pkl_path),
                    summary_path=str(self.summary_path),
                    message="pkl exists but summary is missing",
                )
            return ScheduleCacheState(
                status="missing",
                pkl_path=str(self.pkl_path),
                summary_path=str(self.summary_path),
                message="cache summary and pkl are missing",
            )

        cache = summary.get("cache")
        if not isinstance(cache, dict):
            raise ScheduleCacheError("schedule summary missing cache mapping")
        state = ScheduleCacheState(
            status=str(cache.get("status") or "unknown"),
            pkl_path=str(cache.get("pkl_path") or self.pkl_path),
            summary_path=str(cache.get("summary_path") or self.summary_path),
            updated_at=str(cache.get("updated_at") or ""),
            message=str(cache.get("message") or ""),
            book_count=int(cache.get("book_count") or 0),
        )
        if state.status == "ready" and state.pkl_path and not Path(state.pkl_path).exists():
            return ScheduleCacheState(
                status="degraded",
                pkl_path=state.pkl_path,
                summary_path=state.summary_path,
                updated_at=state.updated_at,
                message="summary exists but pkl cache is missing",
                book_count=state.book_count,
            )
        return state


def build_schedule_presentation(
    cfg: SubscriptionConfig,
    *,
    status=None,
    cache_summary: Optional[dict[str, Any]] = None,
    events: Iterable[dict] = (),
    run: Optional[ScheduleRunView] = None,
    blocker: str = "",
    config_owner: str = "main application settings",
    cache: ScheduleCache | None = None,
) -> SchedulePresentation:
    cfg.validate()
    schedule_cache = cache or ScheduleCache()
    plan = _build_plan(cfg, status=status, blocker=blocker, config_owner=config_owner)
    sources = _source_rows(cfg)
    pending_items = _pending_rows(cache_summary)
    history = [_history_row(event) for event in events]
    cache_state = schedule_cache.state_from_summary(cache_summary)
    run_view = run or _run_from_summary(cache_summary)
    return SchedulePresentation(
        schema_version=SCHEDULE_PRESENTATION_SCHEMA,
        generated_at=_utc_now(),
        plan=plan,
        cache=cache_state,
        run=run_view,
        sources=sources,
        pending_items=pending_items,
        history=history,
        stages=list(RUN_STAGES.get(cfg.mode, ())),
        debug_payload={
            "mode": cfg.mode,
            "cache": asdict(cache_state),
            "run": asdict(run_view),
            "summary": cache_summary or {},
        },
    )


def _build_plan(cfg: SubscriptionConfig, *, status, blocker: str, config_owner: str) -> SchedulePlanView:
    next_run = getattr(status, "next_run_at", None)
    next_run_at = next_run.isoformat(timespec="minutes") if next_run is not None else "-"
    broadcaster = cfg.broadcaster
    subscriber = cfg.subscriber
    enabled_books = len([entry for entry in broadcaster.books if entry.enabled])
    enabled_features = len([entry for entry in broadcaster.features if entry.enabled])
    follows = len(subscriber.follows)
    timing = _schedule_label(cfg)
    config_blocker, blocker_action = _config_blocker(cfg)
    effective_blocker = str(blocker or config_blocker or "")
    if blocker:
        blocker_action = "等待 CGS Server 回到空闲状态后再运行，或关闭占用中的前台任务。"
    automation_state = "blocked" if effective_blocker else "ready"
    if cfg.mode == MODE_SUBSCRIBER and not subscriber.auto_download and not blocker:
        automation_state = "disabled"
    return SchedulePlanView(
        mode=cfg.mode,
        mode_label=_mode_label(cfg.mode),
        automation_state=automation_state,
        automation_label=_automation_label(automation_state),
        next_run_at=next_run_at,
        config_owner=config_owner,
        blocker=effective_blocker,
        blocker_action=blocker_action,
        timing=timing,
        publish_bid=str(broadcaster.publish_bid or "").strip() or "-",
        enabled_books=enabled_books,
        enabled_features=enabled_features,
        follows=follows,
        auto_download=bool(subscriber.auto_download),
        lookback_days=int(subscriber.initial_lookback_days),
        pull_interval_hours=int(subscriber.pull_interval_hours),
    )


def _source_rows(cfg: SubscriptionConfig) -> list[ScheduleSourceRow]:
    rows: list[ScheduleSourceRow] = []
    for index, entry in enumerate(cfg.broadcaster.books, start=1):
        rows.append(_book_source_row(index, entry))
    for index, entry in enumerate(cfg.broadcaster.features, start=1):
        rows.append(_feature_source_row(index, entry))
    for index, entry in enumerate(cfg.subscriber.follows, start=1):
        rows.append(_follow_source_row(index, entry))
    return rows


def _book_source_row(index: int, entry: BookEntry) -> ScheduleSourceRow:
    return ScheduleSourceRow(
        source_id=f"book:{index}:{entry.site}:{entry.url}",
        kind="book",
        site=str(entry.site or ""),
        title=str(entry.title or ""),
        enabled=bool(entry.enabled),
        locator=_tail(str(entry.url or "")),
        status="enabled" if entry.enabled else "disabled",
    )


def _feature_source_row(index: int, entry: FeatureEntry) -> ScheduleSourceRow:
    return ScheduleSourceRow(
        source_id=f"feature:{index}:{entry.site}:{entry.kind}:{entry.value}",
        kind=entry.kind,
        site=str(entry.site or ""),
        title=str(entry.value or ""),
        enabled=bool(entry.enabled),
        locator=entry.kind,
        status=feature_status(entry),
    )


def _follow_source_row(index: int, entry: FollowEntry) -> ScheduleSourceRow:
    title = str(entry.alias or "").strip() or str(entry.bid)
    return ScheduleSourceRow(
        source_id=f"follow:{index}:{entry.bid}",
        kind="follow",
        site="worker",
        title=title,
        enabled=True,
        locator=_tail(str(entry.bid)),
        status="following",
    )


def _pending_rows(summary: Optional[dict[str, Any]]) -> list[SchedulePendingItemRow]:
    if not summary:
        return []
    raw_items = summary.get("pending_items") or []
    if not isinstance(raw_items, list):
        raise ScheduleCacheError("schedule summary pending_items must be a list")
    rows = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ScheduleCacheError("schedule summary pending item must be a mapping")
        rows.append(
            SchedulePendingItemRow(
                item_id=str(item.get("item_id") or ""),
                source_id=str(item.get("source_id") or ""),
                site=str(item.get("site") or ""),
                title=str(item.get("title") or ""),
                episode=str(item.get("episode") or ""),
                status=str(item.get("status") or "pending"),
                stage=str(item.get("stage") or ""),
                message=str(item.get("message") or ""),
                cover_url=str(item.get("cover_url") or ""),
                source_url=str(item.get("source_url") or ""),
            )
        )
    return rows


def _run_from_summary(summary: Optional[dict[str, Any]]) -> ScheduleRunView:
    if not summary:
        return ScheduleRunView()
    raw = summary.get("run") or {}
    if not isinstance(raw, dict):
        raise ScheduleCacheError("schedule summary run must be a mapping")
    return ScheduleRunView(
        run_id=str(raw.get("run_id") or ""),
        trigger=str(raw.get("trigger") or ""),
        status=str(raw.get("status") or "idle"),
        stage=str(raw.get("stage") or ""),
        started_at=str(raw.get("started_at") or ""),
        finished_at=str(raw.get("finished_at") or ""),
        elapsed_sec=float(raw.get("elapsed_sec") or 0.0),
        scanned_books=int(raw.get("scanned_books") or 0),
        pending_episodes=int(raw.get("pending_episodes") or 0),
        submitted_jobs=int(raw.get("submitted_jobs") or 0),
        published_metadata=bool(raw.get("published_metadata")),
        pulled_feeds=int(raw.get("pulled_feeds") or 0),
        latest_message=str(raw.get("latest_message") or ""),
        error=str(raw.get("error") or ""),
    )


def _history_row(event: dict) -> dict[str, str]:
    return {
        "ts": str(event.get("ts", "")),
        "kind": str(event.get("kind", "")),
        "result": str(event.get("result", "")),
        "detail": str(event.get("detail", "")),
    }


def _schedule_label(cfg: SubscriptionConfig) -> str:
    if cfg.mode == MODE_BROADCASTER:
        weekdays = ",".join(cfg.broadcaster.schedule.weekdays) or "-"
        return f"{weekdays} {cfg.broadcaster.schedule.time}"
    if cfg.mode == MODE_SUBSCRIBER:
        return f"every {int(cfg.subscriber.pull_interval_hours)}h"
    return "-"


def _mode_label(mode: str) -> str:
    if mode == MODE_BROADCASTER:
        return "追更"
    if mode == MODE_SUBSCRIBER:
        return "订阅源"
    return mode


def _automation_label(state: str) -> str:
    labels = {
        "ready": "可自动检查",
        "blocked": "需要处理",
        "disabled": "已关闭",
        "running": "正在检查",
    }
    return labels.get(str(state or ""), str(state or "-"))


def _config_blocker(cfg: SubscriptionConfig) -> tuple[str, str]:
    if cfg.mode == MODE_BROADCASTER:
        enabled_books = len([entry for entry in cfg.broadcaster.books if entry.enabled])
        supported = supported_features(cfg.broadcaster.features)
        unsupported = unsupported_features(cfg.broadcaster.features)
        if unsupported:
            return f"有暂不支持后台扫描的作者/标签特征：{unsupported_feature_summary(unsupported)}", "停用这些特征，或改为添加明确作品追更。"
        if enabled_books <= 0 and not supported:
            return "没有启用的追更对象", "从预览页勾选作品加入追更，或在主窗口追更配置里启用已有对象。"
        if not cfg.broadcaster.schedule.weekdays:
            return "未选择自动检查日期", "在主窗口追更配置里选择至少一个检查日。"
        return "", ""
    if cfg.mode == MODE_SUBSCRIBER:
        if not cfg.subscriber.auto_download:
            return "订阅源自动下载已关闭", "在主窗口订阅源配置里开启自动下载。"
        if not cfg.subscriber.follows:
            return "没有订阅源 follow bid", "在主窗口订阅源配置里添加至少一个 follow bid。"
        return "", ""
    return f"unsupported subscription mode: {cfg.mode!r}", "检查 subscription 配置里的 mode 字段。"


def _tail(value: str, limit: int = 28) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
