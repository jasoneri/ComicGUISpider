# -*- coding: utf-8 -*-
"""Layer-C learning state stores (retained; due gating is optional / disabled by product)."""
from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from utils import temp_p
from utils.subscription.schema import PRESET_INTERVAL_HOURS

DEFAULT_INTERVAL_DAYS = 7.0
MIN_INTERVAL_DAYS = 1.0
MAX_INTERVAL_DAYS = 28.0
MAX_HIT_DATES = 10
DORMANCY_MISS_STREAK = 10
DUE_WINDOW = timedelta(days=1)


@dataclass
class BookCheckState:
    key: str
    last_check: str = ""
    next_check: str = ""
    calc_interval_days: float = DEFAULT_INTERVAL_DAYS
    hit_dates: list[str] = field(default_factory=list)
    miss_streak: int = 0

    def advance(
        self,
        *,
        found_new: bool,
        now: datetime,
        catchup_interval_days: Optional[float] = None,
    ) -> "BookCheckState":
        if found_new:
            hit_dates = self._append_hit(self.hit_dates, now.date())
            miss_streak = 0
        else:
            hit_dates = list(self.hit_dates)
            miss_streak = self.miss_streak + 1

        interval = self._derive_interval(hit_dates, miss_streak)
        if not found_new and catchup_interval_days is not None and catchup_interval_days > 0:
            interval = self._clamp(min(interval, float(catchup_interval_days)))
            anchor = now
        else:
            anchor = self._latest_hit_at(hit_dates) or now
        return BookCheckState(
            key=self.key,
            last_check=self._iso_z(now),
            next_check=self._iso_z(self._advance(anchor, interval, now)),
            calc_interval_days=interval,
            hit_dates=hit_dates,
            miss_streak=miss_streak,
        )

    def is_due(self, now: datetime) -> bool:
        if not self.next_check:
            return True
        return self._parse_iso_z(self.next_check) <= now + DUE_WINDOW

    @staticmethod
    def _append_hit(hit_dates: list[str], hit_day: date) -> list[str]:
        merged = sorted(set(hit_dates) | {hit_day.isoformat()})
        return merged[-MAX_HIT_DATES:]

    @staticmethod
    def _derive_interval(hit_dates: list[str], miss_streak: int) -> float:
        if len(hit_dates) >= 3:
            days = sorted(date.fromisoformat(value) for value in hit_dates)
            gaps = [(later - earlier).days for earlier, later in zip(days, days[1:])]
            interval = float(statistics.median(gaps))
        else:
            interval = DEFAULT_INTERVAL_DAYS
        if miss_streak > DORMANCY_MISS_STREAK:
            interval *= 2
        return BookCheckState._clamp(interval)

    @staticmethod
    def _clamp(value: float) -> float:
        return min(max(value, MIN_INTERVAL_DAYS), MAX_INTERVAL_DAYS)

    @staticmethod
    def _latest_hit_at(hit_dates: list[str]) -> Optional[datetime]:
        if not hit_dates:
            return None
        return datetime.combine(date.fromisoformat(max(hit_dates)), time.min, tzinfo=timezone.utc)

    @staticmethod
    def _advance(anchor: datetime, interval_days: float, now: datetime) -> datetime:
        step = timedelta(days=interval_days)
        if anchor >= now:
            return anchor + step
        return anchor + step * (int((now - anchor) / step) + 1)

    @staticmethod
    def _iso_z(moment: datetime) -> str:
        return moment.isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _parse_iso_z(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


def recalculate(
    state: BookCheckState,
    *,
    found_new: bool,
    now: datetime,
    catchup_interval_days: Optional[float] = None,
    **_ignored,
) -> BookCheckState:
    return state.advance(
        found_new=found_new,
        now=now,
        catchup_interval_days=catchup_interval_days,
    )


def is_due(state: BookCheckState, now: datetime) -> bool:
    return state.is_due(now)


class CheckStateStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else temp_p / "subscription_check_state.json"

    def load(self) -> dict[str, BookCheckState]:
        if not self.path.exists():
            return {}
        with open(self.path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("subscription check state must be a mapping")
        return {key: self._from_payload(key, entry) for key, entry in payload.items()}

    def save(self, states: dict[str, BookCheckState]) -> None:
        payload = {key: asdict(state) for key, state in states.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _from_payload(key: str, entry: object) -> BookCheckState:
        if not isinstance(entry, dict):
            raise ValueError(f"check state entry for {key!r} must be a mapping")
        allowed = {item.name for item in fields(BookCheckState)}
        unknown = set(entry) - allowed
        if unknown:
            raise ValueError(f"unknown check state fields for {key!r}: {sorted(unknown)}")
        return BookCheckState(**{**entry, "key": key})


@dataclass
class CheckinSiteState:
    site: str
    last_checkin: str = ""


def is_checkin_due(state: Optional[CheckinSiteState], preset: str, now: datetime) -> bool:
    if preset in ("never", "manual"):
        return False
    if preset not in PRESET_INTERVAL_HOURS:
        raise ValueError(f"unknown checkin interval preset: {preset!r}")
    hours = PRESET_INTERVAL_HOURS[preset]
    if hours is None:
        return False
    if state is None or not state.last_checkin:
        return True
    return BookCheckState._parse_iso_z(state.last_checkin) + timedelta(hours=hours) <= now


def mark_checkin(states: dict[str, CheckinSiteState], site: str, now: datetime) -> None:
    states[site] = CheckinSiteState(site=site, last_checkin=BookCheckState._iso_z(now))


class CheckinStateStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else temp_p / "subscription_checkin_state.json"

    def load(self) -> dict[str, CheckinSiteState]:
        if not self.path.exists():
            return {}
        with open(self.path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("subscription checkin state must be a mapping")
        return {site: self._from_payload(site, entry) for site, entry in payload.items()}

    def save(self, states: dict[str, CheckinSiteState]) -> None:
        payload = {site: asdict(state) for site, state in states.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _from_payload(site: str, entry: object) -> CheckinSiteState:
        if not isinstance(entry, dict):
            raise ValueError(f"checkin state entry for {site!r} must be a mapping")
        allowed = {item.name for item in fields(CheckinSiteState)}
        unknown = set(entry) - allowed
        if unknown:
            raise ValueError(f"unknown checkin state fields for {site!r}: {sorted(unknown)}")
        return CheckinSiteState(**{**entry, "site": site})
