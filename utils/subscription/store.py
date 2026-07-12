"""YAML store for one subscription_<customname>.yml identity.

SubscriptionStore owns customname + base_dir + paths.
I1: save keeps the opposing-mode segment. Legacy subscript_*.yml migrates once.
"""
from __future__ import annotations

import pathlib as p
import re
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
_CUSTOMNAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class SubscriptionConfigPathConflictError(FileExistsError):
    """Both legacy and canonical subscription files exist for the same identity."""


def _require_customname(value: str) -> str:
    name = str(value or "").strip() or DEFAULT_CUSTOMNAME
    if name in {".", ".."} or not _CUSTOMNAME_RE.fullmatch(name):
        raise ValueError(f"invalid subscription customname: {value!r}")
    return name


class SubscriptionStore:
    """One config-file identity: name, base, paths, load/save."""

    def __init__(self, customname: str = DEFAULT_CUSTOMNAME, *, base_dir: Optional[p.Path] = None) -> None:
        self.customname = _require_customname(customname)
        self.base_dir = p.Path(base_dir) if base_dir is not None else p.Path(temp_p)
        self.path = self.base_dir / f"subscription_{self.customname}.yml"
        self.legacy_path = self.base_dir / f"subscript_{self.customname}.yml"

    def rebind(self, customname: str) -> SubscriptionStore:
        """Same base_dir, different profile identity."""
        return SubscriptionStore(customname, base_dir=self.base_dir)

    def load(self) -> SubscriptionConfig:
        path = self._resolved_path()
        if not path.exists():
            cfg = SubscriptionConfig(customname=self.customname)
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
        cfg.customname = self.customname
        cfg.validate()
        return cfg

    def save(self, cfg: SubscriptionConfig) -> None:
        cfg.customname = self.customname
        cfg.validate()
        path = self._resolved_path()
        payload = _to_dict(cfg)
        if path.exists():
            with open(path, "r", encoding="utf-8") as fp:
                prior = yaml.safe_load(fp.read()) or {}
            if isinstance(prior, dict):
                unknown = set(prior.keys()) - _TOP_LEVEL_KEYS
                if unknown:
                    raise ValueError(f"subscription yaml has unknown top-level keys: {sorted(unknown)}")
                opposing = "subscriber" if cfg.mode == "broadcaster" else "broadcaster"
                if opposing in prior:
                    builder = _build_subscriber if opposing == "subscriber" else _build_broadcaster
                    dumper = _subscriber_to_dict if opposing == "subscriber" else _broadcaster_to_dict
                    payload[opposing] = dumper(builder(prior[opposing]))
        _write_yaml(path, payload)

    def _resolved_path(self) -> p.Path:
        if self.path.exists() and self.legacy_path.exists():
            raise SubscriptionConfigPathConflictError(
                "subscription config path conflict: both "
                f"{self.path.name!r} and {self.legacy_path.name!r} exist under {self.path.parent}"
            )
        if self.legacy_path.exists() and not self.path.exists():
            self.legacy_path.replace(self.path)
        return self.path


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
    declared = {f.name for f in fields(cls)}
    unknown = set(raw.keys()) - declared
    if unknown:
        raise ValueError(f"{cls.__name__} got unknown keys: {sorted(unknown)} (declared: {sorted(declared)})")
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
        "books": [_book_to_dict(b) for b in section.books],
        "features": [_feature_to_dict(f) for f in section.features],
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
        "follows": [_follow_to_dict(f) for f in section.follows],
        "pull_interval_hours": int(section.pull_interval_hours),
        "initial_lookback_days": int(section.initial_lookback_days),
        "auto_download": bool(section.auto_download),
    }


def _book_to_dict(entry: BookEntry) -> dict:
    return {"site": entry.site, "url": entry.url, "title": entry.title, "enabled": bool(entry.enabled)}


def _feature_to_dict(entry: FeatureEntry) -> dict:
    entry.validate()
    return {"site": entry.site, "kind": entry.kind, "value": entry.value, "enabled": bool(entry.enabled)}


def _follow_to_dict(entry: FollowEntry) -> dict:
    payload = {"bid": entry.bid}
    if entry.alias:
        payload["alias"] = entry.alias
    if entry.added_at:
        payload["added_at"] = entry.added_at
    return payload


def _schedule_to_dict(section: ScheduleSection) -> dict:
    return {"weekdays": list(section.weekdays), "time": section.time}


def _share_card_to_dict(card: ShareCard) -> dict:
    payload = {}
    if card.posted_at:
        payload["posted_at"] = card.posted_at
    if card.discord_channel:
        payload["discord_channel"] = card.discord_channel
    if card.discord_message_id:
        payload["discord_message_id"] = card.discord_message_id
    return payload
