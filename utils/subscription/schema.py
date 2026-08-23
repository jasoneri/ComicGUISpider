# -*- coding: utf-8 -*-
"""Subscription value objects — flat binding schema, no legacy dual shapes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Optional

FEATURE_KIND_ARTIST = "artist"
FEATURE_KIND_TAG = "tag"
VALID_FEATURE_KINDS = frozenset({FEATURE_KIND_ARTIST, FEATURE_KIND_TAG})

VALID_INTERVAL_PRESETS = frozenset({"never", "12h", "daily", "2d", "weekly", "manual", "off"})
PRESET_INTERVAL_HOURS: dict[str, Optional[int]] = {
    "never": None,
    "off": None,
    "3h": 3,
    "12h": 12,
    "daily": 24,
    "2d": 48,
    "weekly": 168,
    "manual": None,
}
DAY_ALIGNED_PRESETS = frozenset({"daily", "2d", "weekly"})

# Tray-global 后巡查 only (not SidePanel interval). No weekly — too sparse for catch-up.
VALID_CATCHUP_PRESETS = frozenset({"off", "3h", "12h", "daily", "2d"})
CATCHUP_PRESET_ITEMS = (
    ("off", "关闭"),
    ("3h", "每3小时"),
    ("12h", "每12小时"),
    ("daily", "每天"),
    ("2d", "每2天"),
)
# Legacy qconfig values map into the current catch-up set.
CATCHUP_PRESET_LEGACY_ALIASES = {
    "weekly": "2d",
}

VALID_WEEKDAY_IDS = frozenset({"1", "2", "3", "4", "5", "6", "7"})
ALL_WEEKDAYS = ("1", "2", "3", "4", "5", "6", "7")

DEFAULT_TZ_OFFSET = 8
MIN_TZ_OFFSET = -12
MAX_TZ_OFFSET = 14
VALID_TZ_OFFSETS = tuple(range(MIN_TZ_OFFSET, MAX_TZ_OFFSET + 1))

_TIME_OF_DAY_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def format_tz_offset_label(offset_hours: int) -> str:
    offset = int(offset_hours)
    if offset > 0:
        return f"+{offset}"
    if offset < 0:
        return f"{offset}"
    return "+0"


def format_tz_offset_menu_text(offset_hours: int) -> str:
    label = format_tz_offset_label(offset_hours)
    hints = {
        8: "北京",
        9: "东京",
        0: "UTC",
        -5: "美东",
        -8: "美西",
    }
    hint = hints.get(int(offset_hours))
    if hint:
        return f"UTC{label} · {hint}"
    return f"UTC{label}"


def normalize_tz_offset(raw) -> int:
    if raw is None or raw == "":
        return DEFAULT_TZ_OFFSET
    try:
        offset = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"check.tz_offset must be an int hour offset, got {raw!r}") from exc
    if offset not in VALID_TZ_OFFSETS:
        raise ValueError(
            f"check.tz_offset must be {MIN_TZ_OFFSET}..{MAX_TZ_OFFSET}, got {offset}"
        )
    return offset


def format_weekdays_label(weekdays: list[str]) -> str:
    normalized = CheckSlot.normalize_weekdays(weekdays)
    if not normalized:
        return "-"
    if set(normalized) == set(ALL_WEEKDAYS):
        return "每天"
    return ",".join(normalized)


def _declared_field_names(cls) -> set[str]:
    return {item.name for item in fields(cls)}


def _require_mapping(raw: Any, label: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a mapping, got {type(raw).__name__}")
    return raw


def _filter_known_fields(cls, raw: dict, *, label: str) -> dict:
    declared = _declared_field_names(cls)
    unknown = set(raw.keys()) - declared
    if unknown:
        raise ValueError(f"{label} unknown keys: {sorted(unknown)}")
    return {key: value for key, value in raw.items() if key in declared}


@dataclass
class CheckSlot:
    """Atomic primary check window: weekdays + wall-clock time + tz offset."""

    weekdays: list[str] = field(default_factory=list)
    time: str = "03:00"
    tz_offset: int = DEFAULT_TZ_OFFSET

    @staticmethod
    def normalize_weekdays(raw) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, (str, int)):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            raise ValueError(f"check.weekdays must be a list, got {type(raw).__name__}")
        ordered: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text and text not in ordered:
                ordered.append(text)
        return ordered

    @classmethod
    def from_mapping(cls, raw: Any) -> "CheckSlot":
        data = _require_mapping(raw, "CheckSlot")
        allowed = {"weekdays", "time", "tz_offset"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"CheckSlot unknown keys: {sorted(unknown)}")
        slot = cls(
            weekdays=cls.normalize_weekdays(data.get("weekdays")),
            time=str(data["time"]) if data.get("time") is not None else "03:00",
            tz_offset=normalize_tz_offset(data.get("tz_offset", DEFAULT_TZ_OFFSET)),
        )
        slot.validate()
        return slot

    def to_mapping(self) -> dict:
        self.validate()
        return {
            "weekdays": list(self.weekdays),
            "time": self.time,
            "tz_offset": int(self.tz_offset),
        }

    def copy(self) -> "CheckSlot":
        return CheckSlot.from_mapping(self.to_mapping())

    def validate(self) -> None:
        normalized = self.normalize_weekdays(self.weekdays)
        invalid = [item for item in normalized if item not in VALID_WEEKDAY_IDS]
        if invalid:
            raise ValueError(f"check.weekdays must be 1..7, got {invalid}")
        self.weekdays = normalized
        if not isinstance(self.time, str) or not _TIME_OF_DAY_RE.fullmatch(self.time):
            raise ValueError(f"check.time must be HH:MM, got {self.time!r}")
        self.tz_offset = normalize_tz_offset(self.tz_offset)

    def matches(self, now: datetime) -> bool:
        self.validate()
        if not self.weekdays:
            return False
        local_now = self.as_local(now)
        if self.weekday_id(local_now) not in set(self.weekdays):
            return False
        hour, minute = self.parse_hhmm(self.time)
        return (local_now.hour, local_now.minute) >= (hour, minute)

    def next_occurrence(self, now: datetime) -> Optional[datetime]:
        self.validate()
        if not self.weekdays:
            return None
        hour, minute = self.parse_hhmm(self.time)
        weekdays = set(self.weekdays)
        zone = self.tzinfo()
        local_now = self.as_local(now)
        for day_offset in range(0, 8):
            day = (local_now + timedelta(days=day_offset)).date()
            candidate_local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            if self.weekday_id(candidate_local) not in weekdays:
                continue
            if candidate_local < local_now:
                continue
            if now.tzinfo is None:
                return candidate_local.astimezone(self.system_local_tzinfo()).replace(tzinfo=None)
            return candidate_local.astimezone(now.tzinfo)
        return None

    def fingerprint(self) -> str:
        self.validate()
        days = ",".join(self.weekdays) if self.weekdays else "-"
        return f"{days}@{self.time}{format_tz_offset_label(self.tz_offset)}"

    def tzinfo(self) -> tzinfo:
        return timezone(timedelta(hours=int(self.tz_offset)))

    def as_local(self, moment: datetime) -> datetime:
        zone = self.tzinfo()
        if moment.tzinfo is None:
            return moment.replace(tzinfo=self.system_local_tzinfo()).astimezone(zone)
        return moment.astimezone(zone)

    @staticmethod
    def system_local_tzinfo() -> tzinfo:
        return datetime.now().astimezone().tzinfo or timezone.utc

    @staticmethod
    def weekday_id(moment: datetime) -> str:
        return str(moment.weekday() + 1)

    @staticmethod
    def parse_hhmm(value: str) -> tuple[int, int]:
        text = str(value or "").strip()
        if not _TIME_OF_DAY_RE.fullmatch(text):
            raise ValueError(f"check.time must be HH:MM, got {value!r}")
        hour_text, minute_text = text.split(":")
        return int(hour_text), int(minute_text)


@dataclass
class ShareCard:
    posted_at: Optional[str] = None
    discord_channel: Optional[str] = None
    discord_message_id: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Any) -> Optional["ShareCard"]:
        if raw is None:
            return None
        data = _filter_known_fields(cls, _require_mapping(raw, "share_card"), label="ShareCard")
        return cls(**data)

    def to_mapping(self) -> dict:
        payload = {}
        if self.posted_at:
            payload["posted_at"] = self.posted_at
        if self.discord_channel:
            payload["discord_channel"] = self.discord_channel
        if self.discord_message_id:
            payload["discord_message_id"] = self.discord_message_id
        return payload


@dataclass
class BookEntry:
    site: str
    url: str
    title: str
    enabled: bool = True
    check: Optional[CheckSlot] = None

    @classmethod
    def from_mapping(cls, raw: Any) -> "BookEntry":
        data = dict(_require_mapping(raw, "book"))
        check_raw = data.pop("check", None)
        filtered = _filter_known_fields(cls, data, label="BookEntry")
        entry = cls(**filtered)
        if check_raw is not None:
            entry.check = CheckSlot.from_mapping(check_raw)
        return entry

    def to_mapping(self) -> dict:
        payload = {
            "site": self.site,
            "url": self.url,
            "title": self.title,
            "enabled": bool(self.enabled),
        }
        if self.check is not None:
            payload["check"] = self.check.to_mapping()
        return payload

    def effective_slot(self, profile: "CheckSection | CheckSlot") -> CheckSlot:
        if self.check is not None:
            return self.check.copy()
        if isinstance(profile, CheckSlot):
            return profile.copy()
        return profile.as_slot()


@dataclass
class FeatureEntry:
    site: str
    kind: str
    value: str
    enabled: bool = True

    @classmethod
    def from_mapping(cls, raw: Any) -> "FeatureEntry":
        entry = cls(**_filter_known_fields(cls, _require_mapping(raw, "feature"), label="FeatureEntry"))
        entry.validate()
        return entry

    def to_mapping(self) -> dict:
        self.validate()
        return {
            "site": self.site,
            "kind": self.kind,
            "value": self.value,
            "enabled": bool(self.enabled),
        }

    def validate(self) -> None:
        if self.kind not in VALID_FEATURE_KINDS:
            raise ValueError(
                f"FeatureEntry kind must be one of {sorted(VALID_FEATURE_KINDS)}, got {self.kind!r}"
            )
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("FeatureEntry value must be a non-empty string")


@dataclass
class FollowEntry:
    bid: str
    alias: str = ""
    added_at: str = ""

    @classmethod
    def from_mapping(cls, raw: Any) -> "FollowEntry":
        return cls(**_filter_known_fields(cls, _require_mapping(raw, "follow"), label="FollowEntry"))

    def to_mapping(self) -> dict:
        payload = {"bid": self.bid}
        if self.alias:
            payload["alias"] = self.alias
        if self.added_at:
            payload["added_at"] = self.added_at
        return payload


@dataclass
class CheckSection:
    """Profile default CheckSlot fields + auto_download arm."""

    weekdays: list[str] = field(default_factory=list)
    time: str = "03:00"
    tz_offset: int = DEFAULT_TZ_OFFSET
    auto_download: bool = True

    @classmethod
    def from_mapping(cls, raw: Any) -> "CheckSection":
        if raw is None:
            return cls()
        data = _require_mapping(raw, "check")
        allowed = {"weekdays", "time", "tz_offset", "auto_download"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"CheckSection unknown keys: {sorted(unknown)}")
        section = cls(
            weekdays=CheckSlot.normalize_weekdays(data.get("weekdays")),
            time=str(data["time"]) if data.get("time") is not None else "03:00",
            tz_offset=normalize_tz_offset(data.get("tz_offset", DEFAULT_TZ_OFFSET)),
            auto_download=bool(data["auto_download"]) if "auto_download" in data else True,
        )
        section.validate()
        return section

    def to_mapping(self) -> dict:
        self.validate()
        return {
            "weekdays": list(self.weekdays),
            "time": self.time,
            "tz_offset": int(self.tz_offset),
            "auto_download": bool(self.auto_download),
        }

    def as_slot(self) -> CheckSlot:
        return CheckSlot(
            weekdays=list(self.weekdays),
            time=str(self.time),
            tz_offset=int(self.tz_offset),
        ).copy()

    def validate(self) -> None:
        slot = self.as_slot()
        self.weekdays = list(slot.weekdays)
        self.time = slot.time
        self.tz_offset = slot.tz_offset


@dataclass
class CheckinSection:
    enabled: bool = False
    interval_preset: str = "daily"

    @classmethod
    def from_mapping(cls, raw: Any) -> "CheckinSection":
        if raw is None:
            return cls()
        section = cls(
            **_filter_known_fields(cls, _require_mapping(raw, "checkin"), label="CheckinSection")
        )
        section.validate()
        return section

    def to_mapping(self) -> dict:
        self.validate()
        return {
            "enabled": bool(self.enabled),
            "interval_preset": self.interval_preset,
        }

    def validate(self) -> None:
        allowed = VALID_INTERVAL_PRESETS - {"off"}
        if self.interval_preset not in allowed:
            raise ValueError(
                f"checkin.interval_preset must be one of {sorted(allowed)}, "
                f"got {self.interval_preset!r}"
            )


@dataclass
class PublishSection:
    bid: str
    share_card: Optional[ShareCard] = None

    @classmethod
    def from_mapping(cls, raw: Any) -> Optional["PublishSection"]:
        if raw is None:
            return None
        data = dict(_require_mapping(raw, "publish"))
        share_raw = data.pop("share_card", None)
        filtered = _filter_known_fields(cls, data, label="PublishSection")
        section = cls(**filtered)
        section.share_card = ShareCard.from_mapping(share_raw)
        return section

    def to_mapping(self) -> dict:
        payload = {"bid": str(self.bid).strip()}
        if self.share_card is not None:
            payload["share_card"] = self.share_card.to_mapping()
        return payload


@dataclass
class SubscriptionConfig:
    customname: str = "default"
    books: list[BookEntry] = field(default_factory=list)
    features: list[FeatureEntry] = field(default_factory=list)
    follows: list[FollowEntry] = field(default_factory=list)
    check: CheckSection = field(default_factory=CheckSection)
    checkin: CheckinSection = field(default_factory=CheckinSection)
    publish: Optional[PublishSection] = None
    site_proxy: dict[str, bool] = field(default_factory=dict)

    TOP_LEVEL_KEYS = frozenset(
        {"customname", "books", "features", "follows", "check", "checkin", "publish", "site_proxy"}
    )

    @classmethod
    def from_mapping(cls, raw: Any) -> "SubscriptionConfig":
        data = _require_mapping(raw, "subscription")
        unknown = set(data.keys()) - cls.TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(f"subscription yaml unknown top-level keys: {sorted(unknown)}")
        from utils.subscription.site_proxy import SiteProxyMap

        config = cls(
            customname=str(data.get("customname") or "default"),
            books=[BookEntry.from_mapping(item) for item in (data.get("books") or [])],
            features=[FeatureEntry.from_mapping(item) for item in (data.get("features") or [])],
            follows=[FollowEntry.from_mapping(item) for item in (data.get("follows") or [])],
            check=CheckSection.from_mapping(data.get("check")),
            checkin=CheckinSection.from_mapping(data.get("checkin")),
            publish=PublishSection.from_mapping(data.get("publish")),
            site_proxy=SiteProxyMap.from_mapping(data.get("site_proxy")).as_dict(),
        )
        config.validate()
        return config

    def to_mapping(self) -> dict:
        self.validate()
        from utils.subscription.site_proxy import SiteProxyMap

        payload = {
            "customname": self.customname,
            "books": [entry.to_mapping() for entry in self.books],
            "features": [entry.to_mapping() for entry in self.features],
            "follows": [entry.to_mapping() for entry in self.follows],
            "check": self.check.to_mapping(),
        }
        if self.checkin.enabled:
            payload["checkin"] = self.checkin.to_mapping()
        if self.publish is not None:
            payload["publish"] = self.publish.to_mapping()
        proxy_map = SiteProxyMap.from_mapping(self.site_proxy).as_dict()
        if proxy_map:
            payload["site_proxy"] = {key: bool(proxy_map[key]) for key in sorted(proxy_map)}
        return payload

    def validate(self) -> None:
        self.check.validate()
        self.checkin.validate()
        for book in self.books:
            if book.check is not None:
                book.check.validate()
        for feature in self.features:
            feature.validate()
        if self.publish is not None and not str(self.publish.bid or "").strip():
            raise ValueError("publish.bid must be non-empty when publish section exists")
        if self.site_proxy is None:
            self.site_proxy = {}
        if not isinstance(self.site_proxy, dict):
            raise ValueError(
                f"site_proxy must be a mapping of site_key -> bool, got {type(self.site_proxy).__name__}"
            )
        from utils.subscription.site_proxy import SiteProxyMap

        self.site_proxy = SiteProxyMap.from_mapping(self.site_proxy).as_dict()
