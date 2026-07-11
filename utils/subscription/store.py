"""YAML loader/saver for subscription_<customname>.yml.

Honors invariant I1 — switching mode preserves the opposing-mode segment.
Migrates legacy `subscript_<customname>.yml` to the canonical path on first load.
"""
from __future__ import annotations

import pathlib as p
from dataclasses import fields
from typing import Any, Optional

import yaml

from utils import temp_p
from utils.subscription.schema import (
    BookEntry,
    BroadcasterSection,
    FeatureEntry,
    FollowEntry,
    ScheduleSection,
    ShareCard,
    SubscriberSection,
    SubscriptionConfig,
)

DEFAULT_CUSTOMNAME = "default"

_TOP_LEVEL_KEYS = frozenset({"customname", "mode", "broadcaster", "subscriber"})


class SubscriptionConfigPathConflictError(FileExistsError):
    """Raised when both legacy and canonical subscription config files exist."""


def subscription_path(
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Optional[p.Path] = None,
) -> p.Path:
    """Resolve `temp_p/subscription_<customname>.yml` (or override base for tests)."""
    base = p.Path(base_dir) if base_dir is not None else temp_p
    return base / f"subscription_{customname}.yml"


def legacy_subscription_path(
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Optional[p.Path] = None,
) -> p.Path:
    """Resolve the pre-rename path `temp_p/subscript_<customname>.yml`."""
    base = p.Path(base_dir) if base_dir is not None else temp_p
    return base / f"subscript_{customname}.yml"


def load_subscription(
    customname: str = DEFAULT_CUSTOMNAME,
    base_dir: Optional[p.Path] = None,
) -> SubscriptionConfig:
    """Load config from disk; create+persist default on first load."""
    path = _resolve_subscription_path(customname, base_dir=base_dir)
    if not path.exists():
        cfg = SubscriptionConfig(customname=customname)
        cfg.validate()
        _write_yaml(path, _to_dict(cfg))
        return cfg

    with open(path, "r", encoding="utf-8") as fp:
        raw = yaml.safe_load(fp.read())
    if not isinstance(raw, dict):
        raise ValueError(f"subscription yaml root must be a mapping, got {type(raw).__name__}")

    unknown = set(raw.keys()) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(f"subscription yaml has unknown top-level keys: {sorted(unknown)}")
    if "mode" not in raw:
        raise ValueError("subscription yaml missing required 'mode' field")

    cfg = _from_dict(raw)
    cfg.validate()
    return cfg


def save_subscription(
    cfg: SubscriptionConfig,
    base_dir: Optional[p.Path] = None,
) -> None:
    """Persist config; merges with existing file to preserve opposing-mode segment (I1)."""
    cfg.validate()
    path = _resolve_subscription_path(cfg.customname, base_dir=base_dir)
    new_payload = _to_dict(cfg)

    if path.exists():
        with open(path, "r", encoding="utf-8") as fp:
            prior = yaml.safe_load(fp.read()) or {}
        if isinstance(prior, dict):
            # I1: preserve opposing-mode segment regardless of in-memory cfg's content
            unknown = set(prior.keys()) - _TOP_LEVEL_KEYS
            if unknown:
                raise ValueError(f"subscription yaml has unknown top-level keys: {sorted(unknown)}")
            opposing = "subscriber" if cfg.mode == "broadcaster" else "broadcaster"
            if opposing == "subscriber" and "subscriber" in prior:
                new_payload[opposing] = _subscriber_to_dict(_build_subscriber(prior[opposing]))
            elif opposing == "broadcaster" and "broadcaster" in prior:
                new_payload[opposing] = _broadcaster_to_dict(_build_broadcaster(prior[opposing]))

    _write_yaml(path, new_payload)


def _resolve_subscription_path(
    customname: str,
    base_dir: Optional[p.Path] = None,
) -> p.Path:
    """Resolve the canonical config path, migrating legacy filenames once."""
    canonical_path = subscription_path(customname, base_dir=base_dir)
    legacy_path = legacy_subscription_path(customname, base_dir=base_dir)
    canonical_exists = canonical_path.exists()
    legacy_exists = legacy_path.exists()

    if canonical_exists and legacy_exists:
        raise SubscriptionConfigPathConflictError(
            "subscription config path conflict: both "
            f"{canonical_path.name!r} and {legacy_path.name!r} exist under {canonical_path.parent}"
        )
    if legacy_exists and not canonical_exists:
        legacy_path.replace(canonical_path)
        return canonical_path
    return canonical_path


# ---------- internal helpers ----------

def _write_yaml(path: p.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        yaml.safe_dump(payload, fp, allow_unicode=True, sort_keys=False)


def _from_dict(raw: dict) -> SubscriptionConfig:
    return SubscriptionConfig(
        customname=raw.get("customname", DEFAULT_CUSTOMNAME),
        mode=raw["mode"],
        broadcaster=_build_broadcaster(raw.get("broadcaster")),
        subscriber=_build_subscriber(raw.get("subscriber")),
    )


def _build_broadcaster(raw: Any) -> BroadcasterSection:
    if raw is None:
        return BroadcasterSection()
    if not isinstance(raw, dict):
        raise ValueError(f"broadcaster section must be a mapping, got {type(raw).__name__}")
    data = _filter_fields(BroadcasterSection, raw)
    data["share_card"] = _build_share_card(data.get("share_card"))
    data["books"] = [_build_book(b) for b in (data.get("books") or [])]
    data["features"] = [_build_feature(f) for f in (data.get("features") or [])]
    data["schedule"] = _build_schedule(data.get("schedule"))
    return BroadcasterSection(**data)


def _build_share_card(raw: Any) -> Optional[ShareCard]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"share_card must be a mapping, got {type(raw).__name__}")
    return ShareCard(**_filter_fields(ShareCard, raw))


def _build_book(raw: Any) -> BookEntry:
    if not isinstance(raw, dict):
        raise ValueError(f"book entry must be a mapping, got {type(raw).__name__}")
    return BookEntry(**_filter_fields(BookEntry, raw))


def _build_feature(raw: Any) -> FeatureEntry:
    if not isinstance(raw, dict):
        raise ValueError(f"feature entry must be a mapping, got {type(raw).__name__}")
    entry = FeatureEntry(**_filter_fields(FeatureEntry, raw))
    entry.validate()
    return entry


def _build_schedule(raw: Any) -> ScheduleSection:
    if raw is None:
        return ScheduleSection()
    if not isinstance(raw, dict):
        raise ValueError(f"schedule section must be a mapping, got {type(raw).__name__}")
    return ScheduleSection(**_filter_fields(ScheduleSection, raw))


def _build_subscriber(raw: Any) -> SubscriberSection:
    if raw is None:
        return SubscriberSection()
    if not isinstance(raw, dict):
        raise ValueError(f"subscriber section must be a mapping, got {type(raw).__name__}")
    data = _filter_fields(SubscriberSection, raw)
    data["follows"] = [_build_follow(f) for f in (data.get("follows") or [])]
    return SubscriberSection(**data)


def _build_follow(raw: Any) -> FollowEntry:
    if not isinstance(raw, dict):
        raise ValueError(f"follow entry must be a mapping, got {type(raw).__name__}")
    return FollowEntry(**_filter_fields(FollowEntry, raw))


def _filter_fields(cls, raw: dict) -> dict:
    """Drop yaml keys not declared on the dataclass — raise if unknown to avoid silent drift."""
    declared = {f.name for f in fields(cls)}
    unknown = set(raw.keys()) - declared
    if unknown:
        raise ValueError(
            f"{cls.__name__} got unknown keys: {sorted(unknown)} (declared: {sorted(declared)})"
        )
    return {k: v for k, v in raw.items() if k in declared}


def _to_dict(cfg: SubscriptionConfig) -> dict:
    return {
        "customname": cfg.customname,
        "mode": cfg.mode,
        "broadcaster": _broadcaster_to_dict(cfg.broadcaster),
        "subscriber": _subscriber_to_dict(cfg.subscriber),
    }


def _broadcaster_to_dict(section: BroadcasterSection) -> dict:
    payload = {
        "books": [_book_to_dict(book) for book in section.books],
        "features": [_feature_to_dict(feature) for feature in section.features],
        "schedule": _schedule_to_dict(section.schedule),
    }
    publish_bid = str(section.publish_bid or "").strip()
    if publish_bid:
        payload["publish_bid"] = publish_bid
    if section.share_card is not None:
        payload["share_card"] = _share_card_to_dict(section.share_card)
    return payload


def _subscriber_to_dict(section: SubscriberSection) -> dict:
    return {
        "follows": [_follow_to_dict(follow) for follow in section.follows],
        "pull_interval_hours": int(section.pull_interval_hours),
        "initial_lookback_days": int(section.initial_lookback_days),
        "auto_download": bool(section.auto_download),
    }


def _book_to_dict(entry: BookEntry) -> dict:
    return {
        "site": entry.site,
        "url": entry.url,
        "title": entry.title,
        "enabled": bool(entry.enabled),
    }


def _feature_to_dict(entry: FeatureEntry) -> dict:
    entry.validate()
    return {
        "site": entry.site,
        "kind": entry.kind,
        "value": entry.value,
        "enabled": bool(entry.enabled),
    }


def _follow_to_dict(entry: FollowEntry) -> dict:
    payload = {"bid": entry.bid}
    if entry.alias:
        payload["alias"] = entry.alias
    if entry.added_at:
        payload["added_at"] = entry.added_at
    return payload


def _schedule_to_dict(section: ScheduleSection) -> dict:
    return {
        "weekdays": list(section.weekdays),
        "time": section.time,
    }


def _share_card_to_dict(card: ShareCard) -> dict:
    payload = {}
    if card.posted_at:
        payload["posted_at"] = card.posted_at
    if card.discord_channel:
        payload["discord_channel"] = card.discord_channel
    if card.discord_message_id:
        payload["discord_message_id"] = card.discord_message_id
    return payload
