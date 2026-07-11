"""Dataclass schema for subscription_<customname>.yml.

Mirrors PRD §`Config Schema`; honors invariant I1 — mode is mutually exclusive single-select.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MODE_BROADCASTER = "broadcaster"
MODE_SUBSCRIBER = "subscriber"
VALID_MODES = frozenset({MODE_BROADCASTER, MODE_SUBSCRIBER})

FEATURE_KIND_ARTIST = "artist"
FEATURE_KIND_TAG = "tag"
VALID_FEATURE_KINDS = frozenset({FEATURE_KIND_ARTIST, FEATURE_KIND_TAG})


@dataclass
class ShareCard:
    """One-shot idempotent share-card publication marker (I8)."""
    posted_at: Optional[str] = None
    discord_channel: Optional[str] = None
    discord_message_id: Optional[str] = None


@dataclass
class BookEntry:
    site: str
    url: str
    title: str
    enabled: bool = True


@dataclass
class FeatureEntry:
    """Feature-tracking subscription seed (artist/tag), parallel to BookEntry.

    Anchors a search feature (artist or tag) instead of a single book URL —
    used by the broadcaster to follow newly appearing books. See task
    06-08 PRD §Technical Approach ③ (feature-tracking).
    """
    site: str
    kind: str
    value: str
    enabled: bool = True

    def validate(self) -> None:
        """Reject invalid kind / empty value explicitly (no silent fallback, per I11)."""
        if self.kind not in VALID_FEATURE_KINDS:
            raise ValueError(
                f"FeatureEntry kind must be one of {sorted(VALID_FEATURE_KINDS)}, got {self.kind!r}"
            )
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("FeatureEntry value must be a non-empty string")


@dataclass
class ScheduleSection:
    weekdays: list[str] = field(default_factory=list)
    time: str = "21:00"


@dataclass
class BroadcasterSection:
    publish_bid: Optional[str] = None
    share_card: Optional[ShareCard] = None
    books: list[BookEntry] = field(default_factory=list)
    features: list[FeatureEntry] = field(default_factory=list)
    schedule: ScheduleSection = field(default_factory=ScheduleSection)


@dataclass
class FollowEntry:
    bid: str
    alias: str = ""
    added_at: str = ""


@dataclass
class SubscriberSection:
    follows: list[FollowEntry] = field(default_factory=list)
    pull_interval_hours: int = 6
    initial_lookback_days: int = 7
    auto_download: bool = True


@dataclass
class SubscriptionConfig:
    customname: str = "default"
    mode: str = MODE_BROADCASTER
    broadcaster: BroadcasterSection = field(default_factory=BroadcasterSection)
    subscriber: SubscriberSection = field(default_factory=SubscriberSection)

    def validate(self) -> None:
        """Validate against invariant I1 (mode is enum single-select)."""
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"subscription mode must be one of {sorted(VALID_MODES)}, got {self.mode!r}"
            )
        for feature in self.broadcaster.features:
            feature.validate()
