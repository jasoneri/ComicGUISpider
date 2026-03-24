from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

import httpx

from utils.script.motrix import HTTPX_USER_AGENT

from .constants import DANBOORU_BASE_URL, _DANBOORU_BROWSER_HEADER_DROP
from .debug import append_danbooru_debug_event


@dataclass(frozen=True, slots=True)
class DanbooruBrowserCookie:
    name: str
    value: str
    domain: str = ""
    path: str = "/"


@dataclass(frozen=True, slots=True)
class DanbooruBrowserSession:
    cookies: tuple[DanbooruBrowserCookie, ...] = ()
    user_agent: str = ""
    headers: tuple[tuple[str, str], ...] = ()
    source_url: str = ""

    @staticmethod
    def cookie_names_from_header(cookie_header: object) -> list[str]:
        return sorted(
            {
                part.split("=", 1)[0].strip()
                for part in str(cookie_header or "").split(";")
                if "=" in part and part.split("=", 1)[0].strip()
            }
        )

    @staticmethod
    def _normalize_text(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _source_host(source_url: str) -> str:
        parsed = urlsplit(str(source_url or DANBOORU_BASE_URL))
        return str(parsed.hostname or urlsplit(DANBOORU_BASE_URL).hostname or "").strip()

    @staticmethod
    def _normalize_cookie(cookie: object) -> DanbooruBrowserCookie:
        if isinstance(cookie, DanbooruBrowserCookie):
            return cookie
        if not isinstance(cookie, dict):
            raise TypeError("Danbooru browser cookie payload must be a mapping")
        name = str(cookie.get("name") or "").strip()
        if not name:
            raise ValueError("Danbooru browser cookie name is required")
        return DanbooruBrowserCookie(
            name=name,
            value=str(cookie.get("value") or ""),
            domain=str(cookie.get("domain") or "").strip(),
            path=str(cookie.get("path") or "/").strip() or "/",
        )

    @classmethod
    def _normalize_headers(cls, headers: object) -> tuple[tuple[str, str], ...]:
        if headers is None:
            return ()
        raw_items = headers.items() if isinstance(headers, dict) else headers
        normalized: dict[str, tuple[str, str]] = {}
        for raw_name, raw_value in raw_items:
            name = cls._normalize_text(raw_name)
            value = cls._normalize_text(raw_value)
            if not name or not value or name.casefold() in _DANBOORU_BROWSER_HEADER_DROP:
                continue
            normalized[name.casefold()] = (name, value)
        return tuple(normalized.values())

    @classmethod
    def _cookies_from_header(
        cls,
        cookie_header: object,
        *,
        source_url: str = "",
    ) -> tuple[DanbooruBrowserCookie, ...]:
        host = cls._source_host(source_url)
        cookies: list[DanbooruBrowserCookie] = []
        for chunk in str(cookie_header or "").split(";"):
            if "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            normalized_name = cls._normalize_text(name)
            if not normalized_name:
                continue
            cookies.append(
                DanbooruBrowserCookie(
                    name=normalized_name,
                    value=value.strip(),
                    domain=host,
                    path="/",
                )
            )
        return tuple(cookies)

    @classmethod
    def merge_cookies(cls, *cookie_groups: Iterable[object]) -> tuple[DanbooruBrowserCookie, ...]:
        merged: dict[tuple[str, str, str], DanbooruBrowserCookie] = {}
        for cookie_group in cookie_groups:
            for raw_cookie in cookie_group:
                cookie = cls._normalize_cookie(raw_cookie)
                merged[(cookie.name, cookie.domain, cookie.path)] = cookie
        return tuple(merged.values())

    @classmethod
    def from_browser_capture(
        cls,
        *,
        cookies: Iterable[object] = (),
        user_agent: object = "",
        headers: object = (),
        source_url: object = "",
    ) -> "DanbooruBrowserSession":
        normalized_headers = cls._normalize_headers(headers)
        effective_source_url = cls._normalize_text(source_url)
        cookie_header = next(
            (value for name, value in normalized_headers if name.casefold() == "cookie"),
            "",
        )
        return cls(
            cookies=cls.merge_cookies(
                cookies,
                cls._cookies_from_header(cookie_header, source_url=effective_source_url),
            ),
            user_agent=cls._normalize_text(user_agent),
            headers=normalized_headers,
            source_url=effective_source_url,
        )

    def header_value(self, name: str, default: str = "") -> str:
        normalized_name = str(name or "").casefold()
        return next(
            (value for current_name, value in self.headers if current_name.casefold() == normalized_name),
            default,
        )

    @property
    def cookie_names(self) -> list[str]:
        return sorted({cookie.name for cookie in self.cookies if cookie.name})

    @property
    def header_names(self) -> list[str]:
        return sorted({name for name, _value in self.headers if name})

    def cookie_header(self) -> str:
        return "; ".join(f"{cookie.name}={cookie.value}" for cookie in self.cookies if cookie.name)

    def cookie_header_names(self) -> list[str]:
        return self.cookie_names_from_header(self.header_value("Cookie"))

    def resolved_user_agent(self, default: str = "") -> str:
        return self.user_agent or default

    def referer(self, default: str = "") -> str:
        return self.header_value("Referer") or self.source_url or default

    def summary(self) -> str:
        return (
            f"browser_cookies={len(self.cookies)} "
            f"cookie_names={self.cookie_names} "
            f"header_names={self.header_names} "
            f"cookie_header_names={self.cookie_header_names()} "
            f"user_agent={self.user_agent or '<default>'} "
            f"source_url={self.source_url or '<unknown>'}"
        )

    def motrix_headers(self, *, default_user_agent: str = HTTPX_USER_AGENT) -> list[str]:
        headers = [
            f"User-Agent: {self.resolved_user_agent(default_user_agent)}",
            "Accept: */*",
        ]
        referer = self.referer(f"{DANBOORU_BASE_URL}/")
        if referer:
            headers.append(f"Referer: {referer}")
        cookie_header = self.cookie_header()
        if cookie_header:
            headers.append(f"Cookie: {cookie_header}")
        return headers

    def apply_to_client(self, client: httpx.AsyncClient) -> "DanbooruBrowserSession":
        if self.user_agent:
            client.headers["User-Agent"] = self.user_agent
        for name, value in self.headers:
            if self.user_agent and name.casefold() == "user-agent":
                continue
            client.headers[name] = value
        for cookie in self.cookies:
            client.cookies.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain or None,
                path=cookie.path or "/",
            )
        return self


class DanbooruBrowserSessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._session = DanbooruBrowserSession()

    def current(self) -> DanbooruBrowserSession:
        with self._lock:
            return self._session

    def clear(self) -> None:
        with self._lock:
            self._session = DanbooruBrowserSession()

    def update(
        self,
        *,
        cookies: Iterable[object] = (),
        user_agent: object = "",
        headers: object = (),
        source_url: object = "",
    ) -> DanbooruBrowserSession:
        session = DanbooruBrowserSession.from_browser_capture(
            cookies=cookies,
            user_agent=user_agent,
            headers=headers,
            source_url=source_url,
        )
        with self._lock:
            self._session = session
        append_danbooru_debug_event(
            "session.set",
            cookies=len(session.cookies),
            cookie_names=session.cookie_names,
            user_agent=session.user_agent,
            header_names=session.header_names,
            cookie_header_names=session.cookie_header_names(),
            source_url=session.source_url,
        )
        return session

    def apply_to(self, client: httpx.AsyncClient) -> DanbooruBrowserSession:
        session = self.current().apply_to_client(client)
        append_danbooru_debug_event(
            "session.apply",
            cookies=len(session.cookies),
            cookie_names=session.cookie_names,
            user_agent=client.headers.get("User-Agent", ""),
            base_url=str(getattr(client, "base_url", "")),
            header_names=session.header_names,
            cookie_header_names=session.cookie_header_names(),
            source_url=session.source_url,
        )
        return session


danbooru_browser_session_store = DanbooruBrowserSessionStore()
