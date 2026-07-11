from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from utils import temp_p
from utils.subscription import MODE_BROADCASTER, MODE_SUBSCRIBER, SubscriptionConfig

ConfigLoader = Callable[[], SubscriptionConfig]
NowProvider = Callable[[], datetime]

@dataclass(frozen=True)
class ScheduleDecision:
    mode: str
    reason: str
    slot_key: str
    triggered_at: datetime


@dataclass(frozen=True)
class ScheduleStatus:
    mode: str
    summary: str
    next_run_at: Optional[datetime]


class SubscriptionScheduler:
    """In-process due-time calculator for the tray subscription loop."""

    def __init__(
        self,
        config_loader: ConfigLoader,
        *,
        now_provider: Optional[NowProvider] = None,
        state_path: Optional[Path] = None,
    ) -> None:
        self._config_loader = config_loader
        self._now_provider = now_provider or datetime.now
        self._last_broadcaster_slot: Optional[str] = None
        self._last_subscriber_run_at: Optional[datetime] = None
        self._state_path = Path(state_path) if state_path is not None else None
        self._load_state()

    def evaluate(self, now: Optional[datetime] = None) -> Optional[ScheduleDecision]:
        current = now if now is not None else self._now_provider()
        cfg = self._config_loader()
        cfg.validate()
        if cfg.mode == MODE_BROADCASTER:
            return self._broadcaster_decision(cfg, current)
        if cfg.mode == MODE_SUBSCRIBER:
            return self._subscriber_decision(cfg, current)
        raise ValueError(f"unsupported subscription mode: {cfg.mode!r}")

    def mark_triggered(self, decision: ScheduleDecision) -> None:
        if decision.mode == MODE_BROADCASTER:
            self._last_broadcaster_slot = decision.slot_key
            self._save_state()
            return
        if decision.mode == MODE_SUBSCRIBER:
            self._last_subscriber_run_at = decision.triggered_at
            self._save_state()
            return
        raise ValueError(f"unsupported subscription mode: {decision.mode!r}")

    def status(self, now: Optional[datetime] = None) -> ScheduleStatus:
        current = now if now is not None else self._now_provider()
        cfg = self._config_loader()
        cfg.validate()
        if cfg.mode == MODE_BROADCASTER:
            enabled = len([entry for entry in cfg.broadcaster.books if entry.enabled])
            publish_bid = str(cfg.broadcaster.publish_bid or "").strip() or "-"
            return ScheduleStatus(
                mode=MODE_BROADCASTER,
                summary=f"mode=broadcaster bid={publish_bid} books={enabled}",
                next_run_at=self._next_broadcaster_run_at(cfg, current),
            )
        if cfg.mode == MODE_SUBSCRIBER:
            follows = len(cfg.subscriber.follows)
            return ScheduleStatus(
                mode=MODE_SUBSCRIBER,
                summary=f"mode=subscriber follows={follows} auto_download={cfg.subscriber.auto_download}",
                next_run_at=self._next_subscriber_run_at(cfg, current),
            )
        raise ValueError(f"unsupported subscription mode: {cfg.mode!r}")

    def _broadcaster_decision(self, cfg: SubscriptionConfig, now: datetime) -> Optional[ScheduleDecision]:
        schedule = cfg.broadcaster.schedule
        weekdays = _parse_weekdays(schedule.weekdays)
        if not weekdays or now.weekday() not in weekdays:
            return None

        hour, minute = _parse_time(schedule.time)
        if now.hour != hour or now.minute != minute:
            return None

        slot_key = f"broadcaster:{now.date().isoformat()}T{hour:02d}:{minute:02d}"
        if slot_key == self._last_broadcaster_slot:
            return None
        return ScheduleDecision(
            mode=MODE_BROADCASTER, reason=f"broadcaster schedule {schedule.time}", slot_key=slot_key, triggered_at=now
        )

    def _subscriber_decision(self, cfg: SubscriptionConfig, now: datetime) -> Optional[ScheduleDecision]:
        subscriber = cfg.subscriber
        if not subscriber.auto_download or not subscriber.follows:
            return None

        interval_hours = int(subscriber.pull_interval_hours)
        if interval_hours <= 0:
            raise ValueError("subscriber.pull_interval_hours must be positive")
        if self._last_subscriber_run_at is not None:
            next_run_at = self._last_subscriber_run_at + timedelta(hours=interval_hours)
            if now < next_run_at:
                return None

        slot_key = f"subscriber:{now.isoformat(timespec='minutes')}"
        return ScheduleDecision(
            mode=MODE_SUBSCRIBER, reason=f"subscriber pull interval {interval_hours}h", slot_key=slot_key, triggered_at=now
        )

    def _next_broadcaster_run_at(self, cfg: SubscriptionConfig, now: datetime) -> Optional[datetime]:
        schedule = cfg.broadcaster.schedule
        weekdays = _parse_weekdays(schedule.weekdays)
        if not weekdays:
            return None
        hour, minute = _parse_time(schedule.time)
        for day_offset in range(8):
            candidate_day = now.date() + timedelta(days=day_offset)
            candidate = datetime.combine(candidate_day, datetime.min.time()).replace(hour=hour, minute=minute)
            if candidate.weekday() not in weekdays or candidate < now.replace(second=0, microsecond=0):
                continue
            slot_key = f"broadcaster:{candidate.date().isoformat()}T{hour:02d}:{minute:02d}"
            if slot_key == self._last_broadcaster_slot:
                continue
            return candidate
        return None

    def _next_subscriber_run_at(self, cfg: SubscriptionConfig, now: datetime) -> Optional[datetime]:
        subscriber = cfg.subscriber
        if not subscriber.auto_download or not subscriber.follows:
            return None
        interval_hours = int(subscriber.pull_interval_hours)
        if interval_hours <= 0:
            raise ValueError("subscriber.pull_interval_hours must be positive")
        if self._last_subscriber_run_at is None:
            return now.replace(second=0, microsecond=0)
        return self._last_subscriber_run_at + timedelta(hours=interval_hours)

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        with open(self._state_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        if not isinstance(payload, dict):
            raise ValueError("subscription scheduler state must be a mapping")
        self._last_broadcaster_slot = _optional_text(payload.get("last_broadcaster_slot"))
        subscriber_run_at = _optional_text(payload.get("last_subscriber_run_at"))
        if subscriber_run_at:
            self._last_subscriber_run_at = datetime.fromisoformat(subscriber_run_at)

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        payload = {
            "last_broadcaster_slot": self._last_broadcaster_slot,
            "last_subscriber_run_at": self._last_subscriber_run_at.isoformat() if self._last_subscriber_run_at else None,
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))


def default_scheduler_state_path() -> Path:
    return temp_p / "subscription_scheduler_state.json"


def _parse_weekdays(values: list[str]) -> set[int]:
    return {int(value) - 1 for value in values}


def _parse_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"schedule.time must be HH:MM, got {value!r}")
    return hour, minute


def _optional_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
