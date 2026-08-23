from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from utils import temp_p
from utils.share.serializer import deserialize_books, serialize_books
from utils.subscription.schema import BookEntry, FeatureEntry, FollowEntry, SubscriptionConfig
from utils.tray.feature_search import feature_status, supported_features, unsupported_feature_summary, unsupported_features

SCHEDULE_PRESENTATION_SCHEMA = 1
RUN_STAGES = ("Config", "Scan", "Pull", "Episodes", "Diff", "Submit", "Metadata")


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
    local_path: str = ""
    local_cover_path: str = ""


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
    own_books: int = 0
    follow_books: int = 0
    pending_episodes: int = 0
    submitted_jobs: int = 0
    published_metadata: bool = False
    pulled_feeds: int = 0
    latest_message: str = ""
    error: str = ""


@dataclass(frozen=True)
class SchedulePlanView:
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

    def read_summary(self) -> dict[str, Any] | None:
        """Return summary mapping, or None when no run has written a cache yet.

        Missing file is a valid cold-start domain state (not an error).
        Corrupt / wrong-schema payloads raise ScheduleCacheError and must propagate.
        """
        if not self.summary_path.exists():
            return None
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
    config_owner: str | None = None,
    cache: ScheduleCache | None = None,
) -> SchedulePresentation:
    cfg.validate()
    if not config_owner:
        profile = str(getattr(cfg, "customname", "") or "default").strip() or "default"
        config_owner = f"subscription binding «{profile}» (tray executes)"
    schedule_cache = cache or ScheduleCache()
    plan = _build_plan(cfg, status=status, blocker=blocker, config_owner=config_owner)
    pending_items = _pending_rows(cache_summary)
    sources = _source_rows(cfg, pending_items=pending_items)
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
        stages=list(RUN_STAGES),
        debug_payload={
            "cache": asdict(cache_state),
            "run": asdict(run_view),
            "summary": cache_summary or {},
            "binding_books": len(cfg.books),
            "binding_enabled_books": len([entry for entry in cfg.books if entry.enabled]),
        },
    )


def _build_plan(cfg: SubscriptionConfig, *, status, blocker: str, config_owner: str) -> SchedulePlanView:
    next_run = getattr(status, "next_run_at", None)
    next_run_at = next_run.isoformat(timespec="minutes") if next_run is not None else "-"
    # Counts must match the active subscription_*.yml binding, not whole-library bookmarks.
    enabled_books = len([entry for entry in cfg.books if entry.enabled])
    enabled_features = len([entry for entry in cfg.features if entry.enabled])
    follows = len(cfg.follows)
    config_blocker, blocker_action = _config_blocker(cfg)
    effective_blocker = str(blocker or config_blocker or "")
    if blocker:
        blocker_action = "等待 CGS Server 回到空闲状态后再运行，或关闭占用中的前台任务。"
    automation_state = "blocked" if effective_blocker else "ready"
    if not cfg.check.auto_download and not blocker:
        automation_state = "disabled"
    return SchedulePlanView(
        automation_state=automation_state,
        automation_label=_automation_label(automation_state),
        next_run_at=next_run_at,
        config_owner=config_owner,
        blocker=effective_blocker,
        blocker_action=blocker_action,
        timing=_format_plan_timing(cfg),
        publish_bid=str(cfg.publish.bid).strip() if cfg.publish is not None else "-",
        enabled_books=enabled_books,
        enabled_features=enabled_features,
        follows=follows,
        auto_download=bool(cfg.check.auto_download),
    )


def _format_plan_timing(cfg: SubscriptionConfig) -> str:
    """Profile default CheckSlot + catchup label (not Layer C clock)."""
    from utils.subscription.schema import (
        CATCHUP_PRESET_ITEMS,
        format_tz_offset_label,
        format_weekdays_label,
    )
    from utils.subscription.store import get_subscription_catchup_preset

    profile_slot = cfg.check.as_slot()
    weekdays_label = format_weekdays_label(list(profile_slot.weekdays))
    time_text = str(profile_slot.time or "").strip() or "-"
    tz_label = format_tz_offset_label(profile_slot.tz_offset)
    catchup = get_subscription_catchup_preset()
    catchup_label = next((label for key, label in CATCHUP_PRESET_ITEMS if key == catchup), catchup)
    # Copy: default slot is profile default; cards may override; catchup is tray-global.
    return (
        f"档案默认 {weekdays_label} @ {time_text}{tz_label} "
        f"· 卡可覆盖 · 后巡查 {catchup_label}"
    )


def _source_rows(
    cfg: SubscriptionConfig,
    *,
    pending_items: Optional[list[SchedulePendingItemRow]] = None,
) -> list[ScheduleSourceRow]:
    """Schedule objects = active binding yaml books/features/follows only."""
    rows: list[ScheduleSourceRow] = []
    pending_by_source = _pending_count_by_source(pending_items or [])
    for index, entry in enumerate(cfg.books, start=1):
        rows.append(
            _book_source_row(
                index,
                entry,
                profile_check=cfg.check,
                pending_by_source=pending_by_source,
            )
        )
    for index, entry in enumerate(cfg.features, start=1):
        rows.append(_feature_source_row(index, entry))
    for index, entry in enumerate(cfg.follows, start=1):
        rows.append(_follow_source_row(index, entry))
    return rows


def _pending_count_by_source(pending_items: list[SchedulePendingItemRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in pending_items:
        key = str(item.source_id or "").strip()
        if not key:
            site = str(item.site or "").strip()
            title = str(item.title or "").strip()
            key = f"title:{site}:{title}" if site or title else ""
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _book_source_row(
    index: int,
    entry: BookEntry,
    *,
    profile_check,
    pending_by_source: Optional[dict[str, int]] = None,
) -> ScheduleSourceRow:
    source_id = f"book:{entry.site}:{entry.url}"
    # Always surface the effective CheckSlot (card override or profile default).
    # ``latest`` is reserved for 刊期 fingerprint — not pending-chapter counts.
    try:
        slot = entry.effective_slot(profile_check)
        latest = slot.fingerprint() if slot is not None else ""
    except Exception:
        latest = ""
    pending_count = 0
    if pending_by_source:
        pending_count = int(pending_by_source.get(source_id, 0))
        if pending_count <= 0:
            pending_count = int(
                pending_by_source.get(
                    f"title:{str(entry.site or '').strip()}:{str(entry.title or '').strip()}",
                    0,
                )
            )
    return ScheduleSourceRow(
        source_id=source_id or f"book:{index}:{entry.site}:{entry.url}",
        kind="book",
        site=str(entry.site or ""),
        title=str(entry.title or ""),
        enabled=bool(entry.enabled),
        locator=_tail(str(entry.url or "")),
        status="enabled" if entry.enabled else "disabled",
        latest=latest,
        pending_count=pending_count,
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
        # Runner historically wrote ``book``; presentation reads ``title``.
        title = str(item.get("title") or item.get("book") or "")
        site = str(item.get("site") or "")
        source_url = str(item.get("source_url") or item.get("url") or "")
        source_id = str(item.get("source_id") or "")
        if not source_id and site and source_url:
            source_id = f"book:{site}:{source_url}"
        episode = str(item.get("episode") or "")
        local_path = str(item.get("local_path") or "").strip()
        # Prefer live chapter-dir resolve; drop stale book-root paths from old runs.
        resolved = _resolve_download_local_path(title, episode)
        if resolved:
            local_path = resolved
        elif local_path and not _is_chapter_local_path(local_path, title, episode):
            local_path = ""
        # Disk chapter dir is the only authority for "已下载". Stale summary
        # status/local_path must not keep items finished without a chapter folder.
        if local_path and Path(local_path).is_dir():
            status = "finished"
        else:
            status = "queued"
        local_cover = str(item.get("local_cover_path") or item.get("cover_path") or "").strip()
        if not local_cover and local_path:
            local_cover = _first_local_cover_file(local_path)
        cover_url = str(item.get("cover_url") or item.get("img_preview") or "").strip()
        rows.append(
            SchedulePendingItemRow(
                item_id=str(item.get("item_id") or ""),
                source_id=source_id,
                site=site,
                title=title,
                episode=episode,
                status=status,
                stage=str(item.get("stage") or ""),
                message=str(item.get("message") or ""),
                cover_url=local_cover or cover_url,
                source_url=source_url,
                local_path=local_path,
                local_cover_path=local_cover,
            )
        )
    return rows


def _resolve_download_local_path(title: str, episode: str) -> str:
    """Map book+episode onto conf.sv_path chapter folder only.

    Returns empty when the chapter directory is missing. Never returns the book
    root alone — that falsely marks every episode as downloaded.
    """
    from utils import conf
    from utils.core import sanitize_for_path

    book_title = str(title or "").strip()
    episode_name = str(episode or "").strip()
    if not book_title or not episode_name:
        return ""
    root = Path(getattr(conf, "sv_path", "") or "")
    if not root:
        return ""
    episode_dir = root.joinpath(sanitize_for_path(book_title), sanitize_for_path(episode_name))
    if episode_dir.is_dir():
        return str(episode_dir)
    return ""


def _is_chapter_local_path(local_path: str, title: str, episode: str) -> bool:
    """True only when path looks like .../<book>/<episode>, not the book root."""
    path = Path(str(local_path or "").strip())
    if not path.is_dir():
        return False
    episode_name = str(episode or "").strip()
    if not episode_name:
        return False
    from utils.core import sanitize_for_path

    return path.name == sanitize_for_path(episode_name) or path.name == episode_name


def _first_local_cover_file(local_path: str) -> str:
    root = Path(local_path)
    if not root.is_dir():
        return ""
    suffixes = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp"}
    preferred_names = (
        "1.jpg",
        "1.jpeg",
        "1.png",
        "01.jpg",
        "001.jpg",
        "cover.jpg",
        "cover.png",
        "front.jpg",
    )
    for name in preferred_names:
        candidate = root / name
        if candidate.is_file():
            return str(candidate)
    try:
        files = sorted(
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in suffixes
        )
    except OSError:
        return ""
    return str(files[0]) if files else ""


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
        own_books=int(raw.get("own_books") or 0),
        follow_books=int(raw.get("follow_books") or 0),
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


def _automation_label(state: str) -> str:
    labels = {
        "ready": "可自动检查",
        "blocked": "需要处理",
        "disabled": "已关闭",
        "running": "正在检查",
    }
    return labels.get(str(state or ""), str(state or "-"))


def _config_blocker(cfg: SubscriptionConfig) -> tuple[str, str]:
    unsupported = unsupported_features(cfg.features)
    if unsupported:
        return f"有暂不支持后台扫描的作者/标签特征：{unsupported_feature_summary(unsupported)}", "停用这些特征，或改为添加明确作品追更。"
    enabled_books = len([entry for entry in cfg.books if entry.enabled])
    supported = supported_features(cfg.features)
    if enabled_books <= 0 and not supported and not cfg.follows:
        return (
            "当前 binding 的 yml 没有启用书",
            "在追更工作台 SidePanel 启用作品并保存周期到 subscription_*.yml；"
            "tray 只执行 yml 绑定，不会扫描整库收藏。",
        )
    return "", ""


def _tail(value: str, limit: int = 28) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
