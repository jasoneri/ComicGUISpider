from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import conf
from utils.share import DiscordShareAPI, WorkerIndexClient
from utils.subscript import (
    BookEntry,
    DEFAULT_CUSTOMNAME,
    FollowEntry,
    FeatureEntry,
    MODE_BROADCASTER,
    MODE_SUBSCRIBER,
    ScheduleSection,
    ShareCard,
    SubscriptConfig,
    load_subscript,
    save_subscript,
)
from variables import CGS_DISCORD_SHARE_API, CGS_METADATA_CHANNEL_ID


VALID_SUBSCRIPTION_MODES = frozenset({MODE_BROADCASTER, MODE_SUBSCRIBER})


def load_subscription_config(customname: str = DEFAULT_CUSTOMNAME, *, base_dir: Path | None = None) -> dict[str, Any]:
    return subscription_config_payload(load_subscript(_customname(customname), base_dir=base_dir))


def save_subscription_config(payload: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    cfg = _config_from_payload(payload)
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def switch_subscription_mode(
    mode: str,
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    normalized_mode = str(mode or "").strip()
    if normalized_mode not in VALID_SUBSCRIPTION_MODES:
        raise ValueError(f"unsupported subscription mode: {mode!r}")
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    cfg.mode = normalized_mode
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def add_broadcaster_book(
    payload: dict[str, Any],
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    entry = _book_from_payload(payload)
    if entry.url in {book.url for book in cfg.broadcaster.books}:
        raise ValueError(f"broadcaster book already exists: {entry.url}")
    cfg.broadcaster.books.append(entry)
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def update_broadcaster_book(
    index: int,
    payload: dict[str, Any],
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    book = _indexed(cfg.broadcaster.books, index, "broadcaster book")
    next_book = BookEntry(
        site=_optional_text(payload, "site", book.site),
        url=_optional_text(payload, "url", book.url),
        title=_optional_text(payload, "title", book.title),
        enabled=_optional_bool(payload, "enabled", book.enabled),
    )
    _validate_book(next_book)
    duplicate_index = next(
        (row for row, candidate in enumerate(cfg.broadcaster.books) if row != index and candidate.url == next_book.url),
        None,
    )
    if duplicate_index is not None:
        raise ValueError(f"broadcaster book already exists: {next_book.url}")
    cfg.broadcaster.books[index] = next_book
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def remove_broadcaster_book(
    index: int,
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    _indexed(cfg.broadcaster.books, index, "broadcaster book")
    del cfg.broadcaster.books[index]
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def add_subscriber_follow(
    payload: dict[str, Any],
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    cfg.subscriber.follows.append(_follow_from_payload(payload))
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def update_subscriber_follow(
    index: int,
    payload: dict[str, Any],
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    follow = _indexed(cfg.subscriber.follows, index, "subscriber follow")
    cfg.subscriber.follows[index] = FollowEntry(
        bid=_optional_text(payload, "bid", follow.bid),
        alias=_optional_text(payload, "alias", follow.alias, allow_empty=True),
        added_at=_utc_now(),
    )
    _validate_follow(cfg.subscriber.follows[index])
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


def remove_subscriber_follow(
    index: int,
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    _indexed(cfg.subscriber.follows, index, "subscriber follow")
    del cfg.subscriber.follows[index]
    save_subscript(cfg, base_dir=base_dir)
    return load_subscription_config(cfg.customname, base_dir=base_dir)


async def publish_subscription_share_card(
    *,
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = load_subscript(_customname(customname), base_dir=base_dir)
    broadcaster = cfg.broadcaster
    if broadcaster.share_card and broadcaster.share_card.posted_at:
        raise ValueError("share_card already published")
    enabled_books = [book for book in broadcaster.books if book.enabled]
    if not enabled_books:
        raise ValueError("at least one enabled broadcaster book is required before publishing share_card")

    token = _require_discord_token()
    registration = await WorkerIndexClient(auth_token=token).register_publish_bid(
        summary={
            "site": enabled_books[0].site,
            "title": enabled_books[0].title,
            "book_url": enabled_books[0].url,
        }
    )
    channel_id = _require_metadata_channel_id()
    result = await DiscordShareAPI(str(CGS_DISCORD_SHARE_API or "").strip(), token).publish_share_card(
        channel_id=channel_id,
        book_names=[book.title for book in enabled_books],
    )

    broadcaster.publish_bid = registration.bid
    broadcaster.share_card = ShareCard(
        posted_at=result.posted_at,
        discord_channel=result.discord_channel,
        discord_message_id=result.discord_message_id,
    )
    save_subscript(cfg, base_dir=base_dir)
    payload = load_subscription_config(cfg.customname, base_dir=base_dir)
    payload["publish_result"] = {
        "bid": registration.bid,
        "posted_at": result.posted_at,
        "discord_channel": result.discord_channel,
        "discord_message_id": result.discord_message_id,
    }
    return payload


def subscription_config_payload(cfg: SubscriptConfig) -> dict[str, Any]:
    return {
        "customname": cfg.customname,
        "mode": cfg.mode,
        "broadcaster": {
            "publish_bid": cfg.broadcaster.publish_bid,
            "share_card": asdict(cfg.broadcaster.share_card) if cfg.broadcaster.share_card else None,
            "books": [asdict(book) for book in cfg.broadcaster.books],
            "features": [asdict(feature) for feature in cfg.broadcaster.features],
            "schedule": asdict(cfg.broadcaster.schedule),
        },
        "subscriber": {
            "follows": [asdict(follow) for follow in cfg.subscriber.follows],
            "pull_interval_hours": cfg.subscriber.pull_interval_hours,
            "initial_lookback_days": cfg.subscriber.initial_lookback_days,
            "auto_download": cfg.subscriber.auto_download,
        },
    }


def _config_from_payload(payload: dict[str, Any]) -> SubscriptConfig:
    if not isinstance(payload, dict):
        raise ValueError("subscription config payload must be a mapping")
    customname = _customname(str(payload.get("customname") or DEFAULT_CUSTOMNAME))
    mode = str(payload.get("mode") or MODE_BROADCASTER).strip()
    if mode not in VALID_SUBSCRIPTION_MODES:
        raise ValueError(f"unsupported subscription mode: {mode!r}")
    broadcaster_payload = _mapping(payload.get("broadcaster"), "broadcaster")
    subscriber_payload = _mapping(payload.get("subscriber"), "subscriber")
    cfg = SubscriptConfig(customname=customname, mode=mode)
    cfg.broadcaster.publish_bid = _nullable_text(broadcaster_payload.get("publish_bid"))
    cfg.broadcaster.share_card = _share_card_from_payload(broadcaster_payload.get("share_card"))
    cfg.broadcaster.books = [_book_from_payload(item) for item in _list(broadcaster_payload.get("books"), "broadcaster.books")]
    cfg.broadcaster.features = [
        _feature_from_payload(item) for item in _list(broadcaster_payload.get("features"), "broadcaster.features")
    ]
    cfg.broadcaster.schedule = _schedule_from_payload(broadcaster_payload.get("schedule"))
    cfg.subscriber.follows = [_follow_from_payload(item, keep_added_at=True) for item in _list(subscriber_payload.get("follows"), "subscriber.follows")]
    cfg.subscriber.pull_interval_hours = _positive_int(
        subscriber_payload.get("pull_interval_hours"), "pull_interval_hours", default=6
    )
    cfg.subscriber.initial_lookback_days = _non_negative_int(
        subscriber_payload.get("initial_lookback_days"), "initial_lookback_days", default=7
    )
    cfg.subscriber.auto_download = _bool(subscriber_payload.get("auto_download"), default=True)
    cfg.validate()
    return cfg


def _book_from_payload(payload: dict[str, Any]) -> BookEntry:
    if not isinstance(payload, dict):
        raise ValueError("book payload must be a mapping")
    entry = BookEntry(
        site=_required_text(payload.get("site"), "site"),
        url=_required_text(payload.get("url"), "url"),
        title=_required_text(payload.get("title"), "title"),
        enabled=_bool(payload.get("enabled"), default=True),
    )
    _validate_book(entry)
    return entry


def _validate_book(entry: BookEntry) -> None:
    if not entry.site or not entry.url or not entry.title:
        raise ValueError("book requires site, url, and title")


def _follow_from_payload(payload: dict[str, Any], *, keep_added_at: bool = False) -> FollowEntry:
    if not isinstance(payload, dict):
        raise ValueError("follow payload must be a mapping")
    follow = FollowEntry(
        bid=_required_text(payload.get("bid"), "bid"),
        alias=_nullable_text(payload.get("alias")) or "",
        added_at=_nullable_text(payload.get("added_at")) if keep_added_at else _utc_now(),
    )
    _validate_follow(follow)
    return follow


def _feature_from_payload(payload: dict[str, Any]) -> FeatureEntry:
    if not isinstance(payload, dict):
        raise ValueError("feature payload must be a mapping")
    entry = FeatureEntry(
        site=_required_text(payload.get("site"), "site"),
        kind=_required_text(payload.get("kind"), "kind"),
        value=_required_text(payload.get("value"), "value"),
        enabled=_bool(payload.get("enabled"), default=True),
    )
    entry.validate()
    return entry


def _validate_follow(entry: FollowEntry) -> None:
    if not entry.bid:
        raise ValueError("follow requires bid")


def _schedule_from_payload(payload: Any) -> ScheduleSection:
    if payload is None:
        return ScheduleSection()
    data = _mapping(payload, "schedule")
    weekdays = [str(item).strip() for item in _list(data.get("weekdays"), "schedule.weekdays") if str(item).strip()]
    invalid = [weekday for weekday in weekdays if weekday not in {"1", "2", "3", "4", "5", "6", "7"}]
    if invalid:
        raise ValueError(f"schedule.weekdays must be 1..7, got {invalid}")
    time_value = _required_text(data.get("time") or "21:00", "schedule.time")
    try:
        datetime.strptime(time_value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"schedule.time must be HH:MM, got {time_value!r}") from exc
    return ScheduleSection(weekdays=weekdays, time=time_value)


def _share_card_from_payload(payload: Any) -> ShareCard | None:
    if payload is None:
        return None
    data = _mapping(payload, "share_card")
    return ShareCard(
        posted_at=_nullable_text(data.get("posted_at")),
        discord_channel=_nullable_text(data.get("discord_channel")),
        discord_message_id=_nullable_text(data.get("discord_message_id")),
    )


def _customname(value: str) -> str:
    return str(value or "").strip() or DEFAULT_CUSTOMNAME


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_text(payload: dict[str, Any], key: str, current: str, *, allow_empty: bool = False) -> str:
    if key not in payload:
        return current
    text = str(payload.get(key) or "").strip()
    if not text and not allow_empty:
        raise ValueError(f"{key} is required")
    return text


def _bool(value: Any, *, default: bool) -> bool:
    return default if value is None else bool(value)


def _optional_bool(payload: dict[str, Any], key: str, current: bool) -> bool:
    return current if key not in payload else bool(payload.get(key))


def _positive_int(value: Any, label: str, *, default: int) -> int:
    number = int(default if value is None else value)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _non_negative_int(value: Any, label: str, *, default: int) -> int:
    number = int(default if value is None else value)
    if number < 0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _indexed(values: list[Any], index: int, label: str) -> Any:
    if index < 0 or index >= len(values):
        raise IndexError(f"{label} index out of range: {index}")
    return values[index]


def _require_discord_token() -> str:
    token = str(getattr(conf, "discord_share_user_token", "") or "").strip()
    if not token:
        raise ValueError("conf.discord_share_user_token is required")
    return token


def _require_metadata_channel_id() -> str:
    channel_id = str(CGS_METADATA_CHANNEL_ID or "").strip()
    if not channel_id:
        raise ValueError("CGS_METADATA_CHANNEL_ID is required before publishing share_card")
    return channel_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
