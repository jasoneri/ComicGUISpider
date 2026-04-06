from __future__ import annotations

from dataclasses import dataclass, field
import typing as t


@dataclass(frozen=True, slots=True)
class BrowserCookiePayload:
    values: dict[str, str]
    domain: str
    url: str


@dataclass(frozen=True, slots=True)
class BrowserEnvironmentPayload:
    proxy: str | None = None
    referer_url: str | None = None
    cookie_sets: tuple[BrowserCookiePayload, ...] = ()


@dataclass(frozen=True, slots=True)
class PreprocessResult:
    ready: bool = True
    block_search: bool = False
    domain: str | None = None
    runtime_ready: bool = False
    messages: tuple[dict[str, t.Any], ...] = ()
    actions: tuple[dict[str, t.Any], ...] = ()
    state_flags: dict[str, t.Any] = field(default_factory=dict)
