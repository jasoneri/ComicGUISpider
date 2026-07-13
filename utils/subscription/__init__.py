"""Subscription config primitives for ComicGUISpider.

Backend module owning:
- `subscription_<customname>.yml` schema and roundtrip (broadcaster/subscriber mode-driven)
"""
from utils.subscription.schema import (
    BookEntry,
    BroadcasterSection,
    FEATURE_KIND_ARTIST,
    FEATURE_KIND_TAG,
    FeatureEntry,
    FollowEntry,
    MODE_BROADCASTER,
    MODE_SUBSCRIBER,
    ScheduleSection,
    ShareCard,
    SubscriberSection,
    SubscriptionConfig,
    VALID_FEATURE_KINDS,
    VALID_MODES,
)
from utils.subscription.store import (
    DEFAULT_CUSTOMNAME,
    SUBSCRIPTION_DIR,
    SubscriptionStore,
)

__all__ = [
    "BookEntry",
    "BroadcasterSection",
    "FEATURE_KIND_ARTIST",
    "FEATURE_KIND_TAG",
    "FeatureEntry",
    "FollowEntry",
    "MODE_BROADCASTER",
    "MODE_SUBSCRIBER",
    "ScheduleSection",
    "ShareCard",
    "SubscriberSection",
    "SubscriptionConfig",
    "SubscriptionStore",
    "VALID_FEATURE_KINDS",
    "VALID_MODES",
    "DEFAULT_CUSTOMNAME",
    "SUBSCRIPTION_DIR",
]
