# -*- coding: utf-8 -*-
"""Subscription tray schedule owner.

Patterns:
- ``SchedulerRunState`` — persisted last-fire fingerprint (current schema only).
- ``PrimarySlotPlan`` — match / idempotency / next-occurrence for card CheckSlots.
- ``CatchupPlan`` — tray-global catch-up interval.
- ``SubscriptionScheduler`` — thin evaluate / mark / status façade.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from utils import temp_p
from utils.subscription import PRESET_INTERVAL_HOURS, SubscriptionConfig
from utils.subscription.check_slot import effective_slot
from utils.subscription.library import LocalLibraryStore
from utils.subscription.schema import BookEntry, CheckSlot, format_tz_offset_label, format_weekdays_label
from utils.subscription.store import get_subscription_catchup_preset
from utils.tray.feature_search import supported_features

ConfigLoader = Callable[[], SubscriptionConfig]
NowProvider = Callable[[], datetime]
CatchupLoader = Callable[[], str]
LibraryLoader = Callable[[SubscriptionConfig], list[BookEntry]]

_STATE_ALLOWED_KEYS = frozenset({"last_run_at", "last_primary_slot_key"})


@dataclass(frozen=True)
class ScheduleDecision:
    reason: str
    slot_key: str
    triggered_at: datetime
    matched_books: tuple[BookEntry, ...] = ()


@dataclass(frozen=True)
class ScheduleStatus:
    summary: str
    next_run_at: Optional[datetime]


@dataclass(frozen=True)
class _MatchedPrimary:
    books: tuple[BookEntry, ...]
    slots: tuple[CheckSlot, ...]
    anchor_slot: CheckSlot
    slot_key: str
    reason: str


class SchedulerRunState:
    """Current-schema fire memory only — no dual-shape legacy read."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        self.last_run_at: Optional[datetime] = None
        self.last_primary_slot_key: str = ""
        self.load()

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("subscription scheduler state must be a mapping")
        unknown = set(payload) - _STATE_ALLOWED_KEYS
        if unknown:
            raise ValueError(
                f"subscription scheduler state has unknown keys: {sorted(unknown)}"
            )
        run_at = _optional_text(payload.get("last_run_at"))
        if run_at:
            self.last_run_at = datetime.fromisoformat(run_at)
        self.last_primary_slot_key = str(payload.get("last_primary_slot_key") or "")

    def save(self) -> None:
        if self.path is None:
            return
        payload = {
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_primary_slot_key": self.last_primary_slot_key or "",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    def remember(self, decision: ScheduleDecision) -> None:
        self.last_run_at = decision.triggered_at
        if decision.slot_key.startswith("primary:"):
            self.last_primary_slot_key = decision.slot_key
        self.save()


class PrimarySlotPlan:
    """Card CheckSlot primary path: match-now, fire gate, next occurrence."""

    def __init__(self, cfg: SubscriptionConfig, enabled_entries: list[BookEntry]) -> None:
        self.cfg = cfg
        self.enabled_entries = list(enabled_entries)

    def decision_if_due(
        self,
        now: datetime,
        *,
        last_primary_slot_key: str,
        last_run_at: Optional[datetime],
    ) -> Optional[ScheduleDecision]:
        matched = self._collect_matches(now)
        if matched is None:
            return None
        if not self._may_fire(matched, now, last_primary_slot_key, last_run_at):
            return None
        return ScheduleDecision(
            reason=matched.reason,
            slot_key=matched.slot_key,
            triggered_at=now,
            matched_books=matched.books,
        )

    def next_occurrence(
        self,
        now: datetime,
        *,
        last_primary_slot_key: str,
        last_run_at: Optional[datetime],
    ) -> Optional[datetime]:
        candidates: list[datetime] = []
        for entry in self.enabled_entries:
            slot = effective_slot(entry, self.cfg.check)
            nxt = slot.next_occurrence(now)
            if nxt is None:
                continue
            if self._same_day_already_fired(slot, now, last_primary_slot_key, last_run_at):
                after = nxt + timedelta(minutes=1)
                nxt = slot.next_occurrence(after)
                if nxt is None:
                    continue
            candidates.append(nxt)
        if not candidates:
            return None
        return min(candidates)

    def _collect_matches(self, now: datetime) -> Optional[_MatchedPrimary]:
        matched_books: list[BookEntry] = []
        matched_slots: list[CheckSlot] = []
        for entry in self.enabled_entries:
            slot = effective_slot(entry, self.cfg.check)
            if not slot.matches(now):
                continue
            matched_books.append(entry)
            matched_slots.append(slot)
        if not matched_books:
            return None
        anchor = _earliest_wall_clock_slot(matched_slots)
        local_now = anchor.as_local(now)
        fingerprints = sorted({slot.fingerprint() for slot in matched_slots})
        tz_label = format_tz_offset_label(anchor.tz_offset)
        slot_key = (
            f"primary:{local_now.date().isoformat()}"
            f"@{anchor.time}{tz_label}#{'|'.join(fingerprints)}"
        )
        reason = f"primary_card_slots n={len(matched_books)} @ {anchor.time}{tz_label}"
        return _MatchedPrimary(
            books=tuple(matched_books),
            slots=tuple(matched_slots),
            anchor_slot=anchor,
            slot_key=slot_key,
            reason=reason,
        )

    def _may_fire(
        self,
        matched: _MatchedPrimary,
        now: datetime,
        last_primary_slot_key: str,
        last_run_at: Optional[datetime],
    ) -> bool:
        if matched.slot_key == last_primary_slot_key:
            return False
        if last_run_at is None:
            return True
        anchor = matched.anchor_slot
        local_now = anchor.as_local(now)
        last_local = anchor.as_local(last_run_at)
        if last_local.date() != local_now.date():
            return True
        hour, minute = _parse_time(anchor.time)
        return (last_local.hour, last_local.minute) < (hour, minute)

    @staticmethod
    def _same_day_already_fired(
        slot: CheckSlot,
        now: datetime,
        last_primary_slot_key: str,
        last_run_at: Optional[datetime],
    ) -> bool:
        if last_run_at is None or not last_primary_slot_key:
            return False
        local_now = slot.as_local(now)
        last_local = slot.as_local(last_run_at)
        if last_local.date() != local_now.date():
            return False
        return slot.fingerprint() in last_primary_slot_key


class CatchupPlan:
    """Tray-global catch-up interval (qconfig preset → hours)."""

    def __init__(self, preset_loader: CatchupLoader) -> None:
        self._preset_loader = preset_loader

    def decision_if_due(
        self, now: datetime, *, last_run_at: Optional[datetime]
    ) -> Optional[ScheduleDecision]:
        preset = self._preset_loader()
        hours = PRESET_INTERVAL_HOURS.get(preset)
        if hours is None or last_run_at is None:
            # Cold start waits for first primary; catchup never boots alone.
            return None
        if now < last_run_at + timedelta(hours=hours):
            return None
        return ScheduleDecision(
            reason=f"catchup {preset}",
            slot_key=f"catchup:{preset}:{now.isoformat(timespec='minutes')}",
            triggered_at=now,
            matched_books=(),
        )

    def next_occurrence(
        self, now: datetime, *, last_run_at: Optional[datetime]
    ) -> Optional[datetime]:
        hours = PRESET_INTERVAL_HOURS.get(self._preset_loader())
        if hours is None or last_run_at is None:
            return None
        catchup_at = last_run_at + timedelta(hours=hours)
        return now if catchup_at < now else catchup_at


class SubscriptionScheduler:
    """Primary = any enabled book whose effective CheckSlot matches; catchup = tray qconfig."""

    def __init__(
        self,
        config_loader: ConfigLoader,
        *,
        now_provider: Optional[NowProvider] = None,
        state_path: Optional[Path] = None,
        catchup_loader: Optional[CatchupLoader] = None,
        library_loader: Optional[LibraryLoader] = None,
    ) -> None:
        self._config_loader = config_loader
        self._now_provider = now_provider or datetime.now
        self._catchup_loader = catchup_loader or get_subscription_catchup_preset
        self._library_loader = library_loader or _default_library_entries
        self._state = SchedulerRunState(state_path)

    @property
    def _last_run_at(self) -> Optional[datetime]:
        return self._state.last_run_at

    @_last_run_at.setter
    def _last_run_at(self, value: Optional[datetime]) -> None:
        self._state.last_run_at = value

    @property
    def _last_primary_slot_key(self) -> str:
        return self._state.last_primary_slot_key

    @_last_primary_slot_key.setter
    def _last_primary_slot_key(self, value: str) -> None:
        self._state.last_primary_slot_key = value

    def evaluate(self, now: Optional[datetime] = None) -> Optional[ScheduleDecision]:
        current = now if now is not None else self._now_provider()
        cfg = self._config_loader()
        cfg.validate()
        if not cfg.check.auto_download:
            return None
        enabled = [entry for entry in self._library_loader(cfg) if entry.enabled]
        primary = PrimarySlotPlan(cfg, enabled).decision_if_due(
            current,
            last_primary_slot_key=self._state.last_primary_slot_key,
            last_run_at=self._state.last_run_at,
        )
        if primary is not None:
            return primary
        return CatchupPlan(self._catchup_loader).decision_if_due(
            current, last_run_at=self._state.last_run_at
        )

    def mark_triggered(self, decision: ScheduleDecision) -> None:
        self._state.remember(decision)

    def status(self, now: Optional[datetime] = None) -> ScheduleStatus:
        current = now if now is not None else self._now_provider()
        cfg = self._config_loader()
        cfg.validate()
        entries = self._library_loader(cfg)
        enabled = [entry for entry in entries if entry.enabled]
        features = len(supported_features(cfg.features))
        catchup = self._catchup_loader()
        profile_slot = cfg.check.as_slot()
        tz_label = format_tz_offset_label(profile_slot.tz_offset)
        summary = (
            f"books={len(enabled)} features={features} follows={len(cfg.follows)} "
            f"default={format_weekdays_label(profile_slot.weekdays)} "
            f"@ {profile_slot.time}{tz_label} catchup={catchup}"
        )
        next_run_at = (
            self._next_run_at(cfg, current, enabled) if cfg.check.auto_download else None
        )
        return ScheduleStatus(summary=summary, next_run_at=next_run_at)

    def _next_run_at(
        self,
        cfg: SubscriptionConfig,
        now: datetime,
        enabled_entries: list[BookEntry],
    ) -> Optional[datetime]:
        next_primary = PrimarySlotPlan(cfg, enabled_entries).next_occurrence(
            now,
            last_primary_slot_key=self._state.last_primary_slot_key,
            last_run_at=self._state.last_run_at,
        )
        catchup_at = CatchupPlan(self._catchup_loader).next_occurrence(
            now, last_run_at=self._state.last_run_at
        )
        candidates = [item for item in (next_primary, catchup_at) if item is not None]
        if not candidates:
            return None
        return min(candidates)


def default_scheduler_state_path() -> Path:
    return temp_p / "subscription_scheduler_state.json"


def _default_library_entries(cfg: SubscriptionConfig) -> list[BookEntry]:
    return LocalLibraryStore().book_entries(yaml_books=cfg.books)


def _earliest_wall_clock_slot(slots: list[CheckSlot]) -> CheckSlot:
    anchor = slots[0]
    for candidate in slots[1:]:
        if (candidate.time, candidate.tz_offset) < (anchor.time, anchor.tz_offset):
            anchor = candidate
    return anchor


def _parse_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"check.time must be HH:MM, got {value!r}")
    return hour, minute


def _optional_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
