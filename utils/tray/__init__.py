from __future__ import annotations

from utils.tray.event_log import TrayEventLog
from utils.tray.subscription_scheduler import (
    ScheduleDecision,
    ScheduleStatus,
    SubscriptionScheduler,
    schedule_run_scope,
)

__all__ = [
    "TrayEventLog",
    "ScheduleDecision",
    "ScheduleStatus",
    "SubscriptionScheduler",
    "schedule_run_scope",
    "SubscriptionRunner",
    "SubscriptionRunSummary",
]


def __getattr__(name: str):
    if name in {"SubscriptionRunner", "SubscriptionRunSummary"}:
        from utils.tray.subscription_runner import SubscriptionRunner, SubscriptionRunSummary

        return {
            "SubscriptionRunner": SubscriptionRunner,
            "SubscriptionRunSummary": SubscriptionRunSummary,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
