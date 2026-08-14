# -*- coding: utf-8 -*-
"""CheckSlot helpers: D-w1 weekday defaults (value methods live on schema.CheckSlot)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from utils.subscription.schema import CheckSlot, BookEntry, CheckSection

__all__ = [
    "CheckSlot",
    "effective_slot",
    "resolve_default_weekdays",
]

_DATE_YMD_RE = re.compile(
    r"(?P<year>20\d{2}|19\d{2})[./\-年](?P<month>\d{1,2})[./\-月](?P<day>\d{1,2})"
)
_DATE_MDY_RE = re.compile(
    r"(?P<month>\d{1,2})[./\-](?P<day>\d{1,2})[./\-](?P<year>20\d{2}|19\d{2})"
)
_ISO_PREFIX_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})")
_UPDATE_SIGNAL_ATTRS = ("datetime_updated", "updated_at", "public_date")


def effective_slot(book: BookEntry, profile_check: CheckSection | CheckSlot) -> CheckSlot:
    return book.effective_slot(profile_check)


class DefaultWeekdayResolver:
    """D-w1: site update signal → library-added moment → unset."""

    def resolve(self, book_info: Any, *, added_at: Any = None) -> list[str]:
        for attr_name in _UPDATE_SIGNAL_ATTRS:
            raw = getattr(book_info, attr_name, None) if book_info is not None else None
            if raw is None and isinstance(book_info, dict):
                raw = book_info.get(attr_name)
            weekday = self._weekday_from_update_signal(raw)
            if weekday is not None:
                return [weekday]
        anchor = added_at if added_at is not None else datetime.now()
        weekday = self._weekday_from_moment_or_text(anchor)
        if weekday is not None:
            return [weekday]
        return []

    def _weekday_from_update_signal(self, raw: Any) -> Optional[str]:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return CheckSlot.weekday_id(raw)
        text = str(raw).strip()
        if not text or self._looks_like_chapter_title(text):
            return None
        parsed = self._parse_date_text(text)
        if parsed is None:
            return None
        return CheckSlot.weekday_id(parsed)

    def _weekday_from_moment_or_text(self, raw: Any) -> Optional[str]:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return CheckSlot.weekday_id(raw)
        text = str(raw).strip()
        if not text:
            return None
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return CheckSlot.weekday_id(moment)
        except ValueError:
            pass
        parsed = self._parse_date_text(text)
        if parsed is None:
            return None
        return CheckSlot.weekday_id(parsed)

    @staticmethod
    def _looks_like_chapter_title(text: str) -> bool:
        stripped = text.strip()
        if re.fullmatch(r"第?\s*\d+\s*[话話章卷節节]", stripped):
            return True
        if re.fullmatch(r"(ch\.?|chapter)\s*\d+", stripped, flags=re.IGNORECASE):
            return True
        return False

    @staticmethod
    def _parse_date_text(text: str) -> Optional[datetime]:
        stripped = text.strip()
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            pass
        iso_match = _ISO_PREFIX_RE.match(stripped)
        if iso_match:
            try:
                return datetime(
                    int(iso_match.group("year")),
                    int(iso_match.group("month")),
                    int(iso_match.group("day")),
                )
            except ValueError:
                pass
        ymd = _DATE_YMD_RE.search(stripped)
        if ymd:
            try:
                return datetime(
                    int(ymd.group("year")),
                    int(ymd.group("month")),
                    int(ymd.group("day")),
                )
            except ValueError:
                pass
        mdy = _DATE_MDY_RE.search(stripped)
        if mdy:
            try:
                return datetime(
                    int(mdy.group("year")),
                    int(mdy.group("month")),
                    int(mdy.group("day")),
                )
            except ValueError:
                pass
        return None


def resolve_default_weekdays(book_info: Any, *, added_at: Any = None) -> list[str]:
    return DefaultWeekdayResolver().resolve(book_info, added_at=added_at)
