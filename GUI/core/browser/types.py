from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QSize


@dataclass(frozen=True, slots=True)
class BrowserCookieSet:
    values: dict[str, str]
    domain: str
    url: str


@dataclass(frozen=True, slots=True)
class BrowserEnvironmentConfig:
    proxy: str | None = None
    referer_url: str | None = None
    cookie_sets: tuple[BrowserCookieSet, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserRequestCaptureConfig:
    host_filter: str
    path_filters: tuple[str, ...] = ()
    debug_pickle_path: str = ""
    limit: int = 8


@dataclass(frozen=True, slots=True)
class BrowserChallengeSpec:
    verify_url: str
    domain_filter: str
    source_url: str = ""
    window_title: str = ""
    window_size: QSize | None = None
    doh_url: str = ""
    completion_detector: Callable[[str], bool] | None = None
    request_capture: BrowserRequestCaptureConfig | None = None
    debug_pickle_path: str = ""
    auto_sync_on_load: bool = True


@dataclass(frozen=True, slots=True)
class BrowserChallengeResult:
    snapshot_cookies: tuple[dict[str, str], ...] = ()
    live_cookies: tuple[dict[str, str], ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    user_agent: str = ""
    current_url: str = ""
    source_url: str = ""
    trigger: str = "manual"

    @property
    def has_transfer_state(self) -> bool:
        return bool(self.snapshot_cookies or self.live_cookies or self.headers)
