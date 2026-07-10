from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from utils.subscript.schema import FEATURE_KIND_ARTIST, FEATURE_KIND_TAG, FeatureEntry


@dataclass(frozen=True)
class FeatureSearchCapability:
    site: str
    kind: str
    label: str


SUPPORTED_FEATURE_CAPABILITIES: dict[tuple[str, str], FeatureSearchCapability] = {
    ("jm", FEATURE_KIND_ARTIST): FeatureSearchCapability(site="jm", kind=FEATURE_KIND_ARTIST, label="jm artist"),
}


def feature_capability(entry: FeatureEntry) -> FeatureSearchCapability | None:
    return SUPPORTED_FEATURE_CAPABILITIES.get((str(entry.site or "").strip(), str(entry.kind or "").strip()))


def is_supported_feature(entry: FeatureEntry) -> bool:
    return feature_capability(entry) is not None


def supported_features(entries: Iterable[FeatureEntry]) -> list[FeatureEntry]:
    return [entry for entry in entries if entry.enabled and is_supported_feature(entry)]


def unsupported_features(entries: Iterable[FeatureEntry]) -> list[FeatureEntry]:
    return [entry for entry in entries if entry.enabled and not is_supported_feature(entry)]


def filter_feature_books(entry: FeatureEntry, books: Iterable) -> list:
    return [book for book in books if _matches_feature(entry, book)]


def feature_status(entry: FeatureEntry) -> str:
    if not entry.enabled:
        return "disabled"
    return "enabled" if is_supported_feature(entry) else "unsupported"


def feature_label(entry: FeatureEntry) -> str:
    capability = feature_capability(entry)
    if capability is not None:
        return capability.label
    site = str(entry.site or "").strip() or "unknown"
    kind = str(entry.kind or "").strip() or "feature"
    return f"{site} {kind}"


def unsupported_feature_summary(entries: Iterable[FeatureEntry], *, limit: int = 3) -> str:
    labels = [f"{feature_label(entry)}:{entry.value}" for entry in unsupported_features(entries)]
    if len(labels) > limit:
        return ", ".join(labels[:limit]) + f" plus {len(labels)} total"
    return ", ".join(labels)


def _matches_feature(entry: FeatureEntry, book) -> bool:
    value = _normalize(entry.value)
    if entry.kind == FEATURE_KIND_ARTIST:
        return _normalize(getattr(book, "artist", "")) == value
    if entry.kind == FEATURE_KIND_TAG:
        return value in {_normalize(tag) for tag in (getattr(book, "tags", None) or [])}
    return False


def _normalize(value) -> str:
    return " ".join(str(value or "").split()).casefold()
