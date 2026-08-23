from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from utils import conf
from utils.share import DiscordShareAPI, WorkerIndexClient
from utils.subscription import (
    BookEntry,
    CheckSection,
    CheckSlot,
    CheckinSection,
    DEFAULT_CUSTOMNAME,
    FeatureEntry,
    FollowEntry,
    PublishSection,
    ShareCard,
    SubscriptionConfig,
    SubscriptionStore,
    normalize_tz_offset,
    remove_yaml_book,
)
from utils.subscription.library import LibraryBookView, LocalLibraryStore
from utils.subscription.site_proxy import normalize_site_proxy_map
from variables import CGS_DISCORD_SHARE_API, CGS_METADATA_CHANNEL_ID


def load_subscription_config(store: SubscriptionStore) -> dict[str, Any]:
    return subscription_config_payload(store.load())


def save_subscription_config(store: SubscriptionStore, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = config_from_payload(payload, customname=store.customname)
    store.save(cfg)
    return subscription_config_payload(store.load())


def add_book(store: SubscriptionStore, payload: dict[str, Any]) -> dict[str, Any]:
    entry = _book_from_payload(payload)
    library = LocalLibraryStore()
    if library.site_index_for_name(entry.site) is None:
        raise ValueError(f"unknown subscription book site: {entry.site}")
    config = store.load()
    if any((book.site, book.url) == (entry.site, entry.url) for book in config.books):
        raise ValueError(f"subscription book already exists: {entry.url}")
    config.books.append(entry)
    store.save(config)
    return subscription_config_payload(store.load())


def update_book(store: SubscriptionStore, index: int, payload: dict[str, Any]) -> dict[str, Any]:
    library = LocalLibraryStore()
    config = store.load()
    book = _indexed(config.books, index, "subscription book")
    next_book = BookEntry(
        site=_optional_text(payload, "site", book.site),
        url=_optional_text(payload, "url", book.url),
        title=_optional_text(payload, "title", book.title),
        enabled=_optional_bool(payload, "enabled", book.enabled),
        check=book.check.copy() if book.check is not None else None,
    )
    _validate_book(next_book)
    if library.site_index_for_name(next_book.site) is None:
        raise ValueError(f"unknown subscription book site: {next_book.site}")
    if any(
        item_index != index and (item.site, item.url) == (next_book.site, next_book.url)
        for item_index, item in enumerate(config.books)
    ):
        raise ValueError(f"subscription book already exists: {next_book.url}")
    config.books[index] = next_book
    store.save(config)
    return subscription_config_payload(store.load())


def remove_book(store: SubscriptionStore, index: int) -> dict[str, Any]:
    library = LocalLibraryStore()
    config = store.load()
    entry = _indexed(config.books, index, "subscription book")
    if not remove_yaml_book(config, entry.site, entry.url):
        raise RuntimeError(f"yaml books[] remove failed: {entry.url}")
    store.save(config)
    site_index = library.site_index_for_name(entry.site)
    if site_index is not None:
        library.remove_entry(entry)
    return subscription_config_payload(store.load())


def add_follow(store: SubscriptionStore, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = store.load()
    cfg.follows.append(_follow_from_payload(payload))
    store.save(cfg)
    return subscription_config_payload(store.load())


def update_follow(store: SubscriptionStore, index: int, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = store.load()
    follow = _indexed(cfg.follows, index, "subscription follow")
    cfg.follows[index] = FollowEntry(
        bid=_optional_text(payload, "bid", follow.bid),
        alias=_optional_text(payload, "alias", follow.alias, allow_empty=True),
        added_at=_utc_now(),
    )
    _validate_follow(cfg.follows[index])
    store.save(cfg)
    return subscription_config_payload(store.load())


def remove_follow(store: SubscriptionStore, index: int) -> dict[str, Any]:
    cfg = store.load()
    _indexed(cfg.follows, index, "subscription follow")
    del cfg.follows[index]
    store.save(cfg)
    return subscription_config_payload(store.load())


async def publish_subscription_share_card(store: SubscriptionStore) -> dict[str, Any]:
    cfg = store.load()
    if cfg.publish is not None and cfg.publish.share_card and cfg.publish.share_card.posted_at:
        raise ValueError("share_card already published")
    enabled_books = [entry for entry in cfg.books if entry.enabled]
    if not enabled_books:
        raise ValueError("at least one enabled subscription book is required before publishing share_card")

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

    cfg.publish = PublishSection(
        bid=registration.bid,
        share_card=ShareCard(
            posted_at=result.posted_at,
            discord_channel=result.discord_channel,
            discord_message_id=result.discord_message_id,
        ),
    )
    store.save(cfg)
    payload = subscription_config_payload(store.load())
    payload["publish_result"] = {
        "bid": registration.bid,
        "posted_at": result.posted_at,
        "discord_channel": result.discord_channel,
        "discord_message_id": result.discord_message_id,
    }
    return payload


def subscription_config_payload(cfg: SubscriptionConfig) -> dict[str, Any]:
    library = LocalLibraryStore()
    joined_entries = library.book_entries(yaml_books=cfg.books)
    joined_by_key = {
        LibraryBookView.entry_key(entry.site, entry.url): entry
        for entry in joined_entries
    }
    library_books = [
        joined_by_key.get(
            LibraryBookView.entry_key(book.site, book.url),
            book,
        )
        for book in cfg.books
    ]
    return {
        "customname": cfg.customname,
        "books": [asdict(book) for book in library_books],
        "features": [asdict(feature) for feature in cfg.features],
        "follows": [asdict(follow) for follow in cfg.follows],
        "check": asdict(cfg.check),
        "checkin": asdict(cfg.checkin),
        "publish": _publish_payload(cfg.publish),
        "site_proxy": dict(cfg.site_proxy or {}),
    }


def config_from_payload(payload: dict[str, Any], *, customname: str = DEFAULT_CUSTOMNAME) -> SubscriptionConfig:
    if not isinstance(payload, dict):
        raise ValueError("subscription config payload must be a mapping")
    cfg = SubscriptionConfig(
        customname=customname,
        books=[_book_from_payload(item) for item in _list(payload.get("books"), "books")],
        features=[_feature_from_payload(item) for item in _list(payload.get("features"), "features")],
        follows=[
            _follow_from_payload(item, keep_added_at=True) for item in _list(payload.get("follows"), "follows")
        ],
        check=_check_from_payload(payload.get("check")),
        checkin=_checkin_from_payload(payload.get("checkin")),
        publish=_publish_from_payload(payload.get("publish")),
        site_proxy=normalize_site_proxy_map(payload.get("site_proxy")),
    )
    cfg.validate()
    return cfg


def _publish_payload(publish: PublishSection | None) -> dict[str, Any] | None:
    if publish is None:
        return None
    return {
        "bid": publish.bid,
        "share_card": asdict(publish.share_card) if publish.share_card else None,
    }


def _check_from_payload(payload: Any) -> CheckSection:
    """Flat CheckSection: weekdays + time + tz_offset + auto_download."""
    data = _mapping(payload, "check")
    defaults = CheckSection()
    time_value = data.get("time")
    if time_value is None or str(time_value).strip() == "":
        time_value = defaults.time
    weekdays_raw = data.get("weekdays")
    if weekdays_raw is None:
        weekdays = list(defaults.weekdays)
    elif isinstance(weekdays_raw, (list, tuple)):
        weekdays = [str(item).strip() for item in weekdays_raw if str(item).strip()]
    else:
        raise ValueError("check.weekdays must be a list")
    section = CheckSection(
        weekdays=weekdays,
        time=str(time_value).strip(),
        tz_offset=normalize_tz_offset(
            data.get("tz_offset") if data.get("tz_offset") is not None else defaults.tz_offset
        ),
        auto_download=_bool(data.get("auto_download"), default=defaults.auto_download),
    )
    section.validate()
    return section


def _checkin_from_payload(payload: Any) -> CheckinSection:
    data = _mapping(payload, "checkin")
    defaults = CheckinSection()
    section = CheckinSection(
        enabled=_bool(data.get("enabled"), default=defaults.enabled),
        interval_preset=str(data.get("interval_preset") or defaults.interval_preset).strip(),
    )
    section.validate()
    return section


def _publish_from_payload(payload: Any) -> PublishSection | None:
    if payload is None:
        return None
    data = _mapping(payload, "publish")
    return PublishSection(
        bid=_required_text(data.get("bid"), "publish.bid"),
        share_card=_share_card_from_payload(data.get("share_card")),
    )


def _book_from_payload(payload: dict[str, Any]) -> BookEntry:
    if not isinstance(payload, dict):
        raise ValueError("book payload must be a mapping")
    check_raw = payload.get("check")
    check_slot = None
    if check_raw is not None:
        # Book-level override uses the same flat fields as profile check (no auto_download).
        section = _check_from_payload(check_raw)
        check_slot = CheckSlot(
            weekdays=list(section.weekdays),
            time=str(section.time),
            tz_offset=int(section.tz_offset),
        ).copy()
    return BookEntry(
        site=_required_text(payload.get("site"), "site"),
        url=_required_text(payload.get("url"), "url"),
        title=_required_text(payload.get("title"), "title"),
        enabled=_bool(payload.get("enabled"), default=True),
        check=check_slot,
    )


def _validate_book(entry: BookEntry) -> None:
    if not entry.site or not entry.url or not entry.title:
        raise ValueError("book requires site, url, and title")


def _follow_from_payload(payload: dict[str, Any], *, keep_added_at: bool = False) -> FollowEntry:
    if not isinstance(payload, dict):
        raise ValueError("follow payload must be a mapping")
    follow = FollowEntry(
        bid=_required_text(payload.get("bid"), "bid"),
        alias=_nullable_text(payload.get("alias")) or "",
        added_at=(_nullable_text(payload.get("added_at")) or "") if keep_added_at else _utc_now(),
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


def _share_card_from_payload(payload: Any) -> ShareCard | None:
    if payload is None:
        return None
    data = _mapping(payload, "share_card")
    return ShareCard(
        posted_at=_nullable_text(data.get("posted_at")),
        discord_channel=_nullable_text(data.get("discord_channel")),
        discord_message_id=_nullable_text(data.get("discord_message_id")),
    )




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
