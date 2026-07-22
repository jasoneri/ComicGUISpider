from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil
from typing import Optional


class PageNavTier(str, Enum):
    SMALL = "T0"
    MEDIUM = "T1"
    LARGE = "T2"
    HOME = "T3"


@dataclass(frozen=True, slots=True)
class PageNavState:
    current_page: int
    total_count: Optional[int]
    total_pages: Optional[int]
    query_is_empty: bool
    page_size: int = 30
    site_cap: int = 1000
    loading: bool = False

    @classmethod
    def from_counts(
        cls,
        *,
        current_page: int,
        total_count: Optional[int],
        query_is_empty: bool,
        page_size: int = 30,
        site_cap: int = 1000,
        loading: bool = False,
    ) -> "PageNavState":
        total_pages: Optional[int] = None
        if total_count is not None and total_count >= 0 and page_size > 0:
            raw_pages = max(1, ceil(int(total_count) / page_size)) if total_count > 0 else 1
            total_pages = min(raw_pages, site_cap)
        return cls(
            current_page=max(1, int(current_page or 1)),
            total_count=total_count,
            total_pages=total_pages,
            query_is_empty=bool(query_is_empty),
            page_size=page_size,
            site_cap=site_cap,
            loading=bool(loading),
        )


@dataclass(frozen=True, slots=True)
class JumpDecision:
    accepted: bool
    target_page: Optional[int]
    reason: str
