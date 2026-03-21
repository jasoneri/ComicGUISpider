#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import pathlib as p
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
from lxml import html as lxml_html
from loguru import logger as lg

from utils import get_httpx_verify
from utils.script import conf, AioRClient, folder_sub
from utils.script.motrix import HTTPX_USER_AGENT, MotrixRPC, build_motrix_dns_options
from utils.sql import SqlRecorder
from .danbooru_dns import (
    DANBOORU_DNS_STUB_HOST,
    DANBOORU_DNS_STUB_PORT,
    build_danbooru_async_transport,
    ensure_danbooru_dns_stub_started_async,
    normalize_doh_url,
)

SUPPORTED_MEDIA_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
UNSUPPORTED_MEDIA_EXTENSIONS = {"mp4", "webm", "zip"}
DANBOORU_SQL_TABLE = "danbooru_md5_table"
DANBOORU_BASE_URL = "https://danbooru.donmai.us"
AUTOCOMPLETE_PATH = "/autocomplete"
_WHITESPACE_RE = re.compile(r"\s+")
_ORDER_TOKEN_CAPTURE_RE = re.compile(r"(?:^|\s)(order:[^\s]+)")
_ORDER_TOKEN_STRIP_RE = re.compile(r"(?:^|\s)order:[^\s]+")
DEFAULT_DOWNLOAD_CONCURRENCY = 3
MOTRIX_POLL_INTERVAL = 1.2
DANBOORU_PAGE_SIZE = 30
DANBOORU_AUTOCOMPLETE_LIMIT = 20
DEFAULT_DANBOORU_SAVE_PATH = "D:/pic/danbooru"
DANBOORU_SAVE_TYPE_SEARCH_TAG = "search_tag"
_DANBOORU_CHALLENGE_MARKERS = (
    "cf-mitigated",
    "challenge-form",
    "cf-browser-verification",
    "just a moment",
    "__cf_chl_",
)
DANBOORU_OFFICIAL_ORDER_VALUES = frozenset(
    {
        "active_child_count", "active_children", "active_children_asc", "active_comment_count", "active_comments", "active_comments_asc", 
        "active_note_count", "active_notes", "active_notes_asc", "active_pool_count", "active_pools",
        "active_pools_asc", "appeal_count", "appeals", "appeals_asc", "approval_count", "approvals", "approvals_asc", "artcomm", 
        "artcomm_asc", "arttags", "arttags_asc", "change", "change_asc", "chartags", "chartags_asc", "child_count", "children", 
        "children_asc", "collection_pool_count", "collection_pools", "collection_pools_asc", "comment", "comment_asc", 
        "comment_bumped", "comment_bumped_asc", "comment_count", "comments", "comments_asc", "copytags", "copytags_asc", 
        "created_at", "created_at_asc", "custom", "deleted_child_count",
        "deleted_children", "deleted_children_asc", "deleted_comment_count", "deleted_comments", "deleted_comments_asc", 
        "deleted_note_count", "deleted_notes", "deleted_notes_asc", "deleted_pool_count", "deleted_pools", "deleted_pools_asc", 
        "disapproved", "disapproved_asc", "downvotes", "downvotes_asc", "duration", "duration_asc", "favcount", "favcount_asc", 
        "filesize", "filesize_asc", "flag_count", "flags", "flags_asc", "gentags", "gentags_asc", "id", "id_desc", "landscape", 
        "md5", "md5_asc", "metatags", "metatags_asc", "modqueue", "mpixels", "mpixels_asc", "none", "note", "note_asc", "note_count", 
        "notes", "notes_asc", "pool_count", "pools", "pools_asc", "portrait", "random", "rank", "replacement_count", "replacements", 
        "replacements_asc", "score", "score_asc", "series_pool_count",
        "series_pools", "series_pools_asc", "tagcount", "tagcount_asc", "upvotes", "upvotes_asc",
    }
)
DANBOORU_SORT_OPTIONS = (
    ("默认", ""),
    ("评分", "score"),
    ("最旧", "id"),
)
_danbooru_browser_session_lock = threading.Lock()


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


_danbooru_browser_session = DanbooruBrowserSession()


class DanbooruChallengeRequired(Exception):
    def __init__(self, *, verify_url: str, status_code: int, detail: str = ""):
        message = detail or "Danbooru request requires browser verification"
        super().__init__(message)
        self.verify_url = str(verify_url or DANBOORU_BASE_URL)
        self.status_code = int(status_code)


def _normalize_browser_cookie(cookie: object) -> DanbooruBrowserCookie:
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


def _verification_url_from_response(response: httpx.Response) -> str:
    request = getattr(response, "request", None)
    if request is None or getattr(request, "url", None) is None:
        return DANBOORU_BASE_URL
    parsed = urlsplit(str(request.url))
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def get_danbooru_browser_session() -> DanbooruBrowserSession:
    with _danbooru_browser_session_lock:
        return _danbooru_browser_session


def clear_danbooru_browser_session() -> None:
    global _danbooru_browser_session
    with _danbooru_browser_session_lock:
        _danbooru_browser_session = DanbooruBrowserSession()


def set_danbooru_browser_session(
    *,
    cookies: Iterable[object] = (),
    user_agent: object = "",
) -> DanbooruBrowserSession:
    global _danbooru_browser_session
    normalized_cookies = tuple(_normalize_browser_cookie(cookie) for cookie in cookies)
    session = DanbooruBrowserSession(
        cookies=normalized_cookies,
        user_agent=str(user_agent or "").strip(),
    )
    with _danbooru_browser_session_lock:
        _danbooru_browser_session = session
    return session


def apply_danbooru_browser_session(client: httpx.AsyncClient) -> DanbooruBrowserSession:
    session = get_danbooru_browser_session()
    if session.user_agent:
        client.headers["User-Agent"] = session.user_agent
    for cookie in session.cookies:
        client.cookies.set(
            cookie.name,
            cookie.value,
            domain=cookie.domain or None,
            path=cookie.path or "/",
        )
    return session


def is_danbooru_challenge_response(response: httpx.Response) -> bool:
    status_code = getattr(response, "status_code", None)
    if status_code not in {403, 429, 503}:
        return False
    headers = getattr(response, "headers", {}) or {}
    mitigated = str(headers.get("cf-mitigated", "")).strip().casefold()
    if mitigated == "challenge":
        return True
    content_type = str(headers.get("content-type", "")).casefold()
    if "html" not in content_type and status_code != 403:
        return False
    try:
        text = str(getattr(response, "text", "") or "")[:4096].casefold()
    except Exception:
        return False
    return any(marker in text for marker in _DANBOORU_CHALLENGE_MARKERS)


def raise_for_danbooru_response(response: httpx.Response) -> None:
    if is_danbooru_challenge_response(response):
        raise DanbooruChallengeRequired(
            verify_url=_verification_url_from_response(response),
            status_code=response.status_code,
            detail=f"Danbooru request blocked by browser verification ({response.status_code})",
        )
    response.raise_for_status()


def create_async_http_client(
    *,
    base_url: str = "",
    headers: Optional[dict] = None,
    timeout: float = 30.0,
    follow_redirects: bool = False,
    proxy_policy: str = "proxy",
    retries: int = 2,
    runtime_config: Optional["DanbooruRuntimeConfig"] = None,
    **kwargs,
) -> httpx.AsyncClient:
    config = runtime_config or DanbooruRuntimeConfig.from_conf()
    transport, trust_env = build_danbooru_async_transport(
        proxy_policy,
        getattr(conf, "proxies", None) or [],
        doh_url=config.doh_url,
        retries=retries,
        verify=get_httpx_verify(),
    )
    client = httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        follow_redirects=follow_redirects,
        transport=transport,
        trust_env=trust_env,
        **kwargs,
    )
    apply_danbooru_browser_session(client)
    return client


def canonicalize_search_term(term: str) -> str:
    return _WHITESPACE_RE.sub(" ", (term or "").strip())


def extract_danbooru_order_token(term: str) -> str:
    matches = _ORDER_TOKEN_CAPTURE_RE.findall(canonicalize_search_term(term))
    return matches[-1] if matches else ""


def strip_danbooru_order_tokens(term: str) -> str:
    return canonicalize_search_term(_ORDER_TOKEN_STRIP_RE.sub(" ", canonicalize_search_term(term)))


def build_danbooru_search_tags(term: str, order: Optional[str] = None) -> str:
    canonical_term = canonicalize_search_term(term)
    base_term = strip_danbooru_order_tokens(canonical_term)
    canonical_order = canonicalize_search_term(order or "")
    effective_order = canonical_order or extract_danbooru_order_token(canonical_term)
    if not effective_order:
        return base_term
    order_token = effective_order if effective_order.startswith("order:") else f"order:{effective_order}"
    return " ".join(part for part in (base_term, order_token) if part)


def build_danbooru_search_params(
    tags: str,
    *,
    order: Optional[str] = None,
    page: int = 1,
    limit: Optional[int] = None,
) -> dict:
    return {
        "tags": build_danbooru_search_tags(tags, order),
        "page": page,
        "limit": limit or DANBOORU_PAGE_SIZE,
    }


def is_official_danbooru_order_value(order: str) -> bool:
    normalized = canonicalize_search_term(order).removeprefix("order:")
    return normalized in DANBOORU_OFFICIAL_ORDER_VALUES


def normalize_file_ext(file_ext: Optional[str]) -> str:
    return (file_ext or "").strip().lower().lstrip(".")


def is_supported_media_type(file_ext: Optional[str]) -> bool:
    return normalize_file_ext(file_ext) in SUPPORTED_MEDIA_EXTENSIONS


def is_unsupported_media_type(file_ext: Optional[str]) -> bool:
    return normalize_file_ext(file_ext) in UNSUPPORTED_MEDIA_EXTENSIONS


def probe_image_size_from_bytes(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

    if len(data) >= 10 and data[:3] == b"GIF":
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")

    if len(data) >= 30 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if chunk == b"VP8L" and len(data) >= 25:
            b0, b1, b2, b3 = data[21:25]
            width = ((b1 & 0x3F) << 8 | b0) + 1
            height = (((b3 & 0x0F) << 10) | (b2 << 2) | (b1 >> 6)) + 1
            return width, height
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(data[26:28], "little"), int.from_bytes(data[28:30], "little")

    if len(data) >= 4 and data.startswith(b"\xff\xd8"):
        offset = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if marker == 0xDA or offset + 2 > len(data):
                break
            segment_length = int.from_bytes(data[offset:offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(data):
                break
            if marker in sof_markers and segment_length >= 7:
                height = int.from_bytes(data[offset + 3:offset + 5], "big")
                width = int.from_bytes(data[offset + 5:offset + 7], "big")
                return width, height
            offset += segment_length

    return None


async def fetch_remote_image_size(
    url: str,
    *,
    timeout: float = 12.0,
    proxy_policy: str = "proxy",
    probe_bytes: int = 262143,
) -> Optional[tuple[int, int]]:
    async with create_async_http_client(
        headers={
            "User-Agent": HTTPX_USER_AGENT,
            "Accept": "*/*",
            "Range": f"bytes=0-{probe_bytes}",
        },
        timeout=timeout,
        follow_redirects=True,
        proxy_policy=proxy_policy,
    ) as client:
        response = await client.get(url)
        raise_for_danbooru_response(response)
        return probe_image_size_from_bytes(response.content)


@dataclass(slots=True)
class DanbooruPost:
    post_id: int
    md5: str
    canonical_term: str = ""
    file_url: Optional[str] = None
    large_file_url: Optional[str] = None
    preview_file_url: Optional[str] = None
    source: Optional[str] = None
    rating: Optional[str] = None
    file_ext: str = ""
    tag_string: str = ""
    tag_string_general: str = ""
    tag_string_character: str = ""
    tag_string_copyright: str = ""
    tag_string_artist: str = ""
    tag_string_meta: str = ""
    image_width: int = 0
    image_height: int = 0
    preview_width: int = 0
    preview_height: int = 0
    score: int = 0

    @property
    def is_supported(self) -> bool:
        return is_supported_media_type(self.file_ext)

    @property
    def filename(self) -> str:
        ext = normalize_file_ext(self.file_ext)
        if not ext:
            raise ValueError("file_ext is required for filename derivation")
        return f"{self.post_id}_{self.md5}.{ext}"

    @classmethod
    def from_api_payload(cls, payload: dict, canonical_term: str = "") -> "DanbooruPost":
        return cls(
            post_id=int(payload["id"]),
            md5=payload.get("md5") or "",
            canonical_term=canonical_term,
            file_url=payload.get("file_url"),
            large_file_url=payload.get("large_file_url"),
            preview_file_url=payload.get("preview_file_url"),
            source=payload.get("source"),
            rating=payload.get("rating"),
            file_ext=normalize_file_ext(payload.get("file_ext")),
            tag_string=payload.get("tag_string") or "",
            tag_string_general=payload.get("tag_string_general") or "",
            tag_string_character=payload.get("tag_string_character") or "",
            tag_string_copyright=payload.get("tag_string_copyright") or "",
            tag_string_artist=payload.get("tag_string_artist") or "",
            tag_string_meta=payload.get("tag_string_meta") or "",
            image_width=int(payload.get("image_width") or 0),
            image_height=int(payload.get("image_height") or 0),
            preview_width=int(payload.get("preview_width") or 0),
            preview_height=int(payload.get("preview_height") or 0),
            score=int(payload.get("score") or 0),
        )

    def with_canonical_term(self, canonical_term: str) -> "DanbooruPost":
        self.canonical_term = canonicalize_search_term(canonical_term)
        return self


@dataclass(frozen=True, slots=True)
class DanbooruRuntimeConfig:
    save_path: str
    save_type: Optional[str] = None
    download_concurrency: int = DEFAULT_DOWNLOAD_CONCURRENCY
    doh_url: str = ""
    motrix_aria2_conf_path: str = ""

    def __post_init__(self):
        if self.save_type not in {None, DANBOORU_SAVE_TYPE_SEARCH_TAG}:
            raise ValueError(f"Unsupported Danbooru save_type: {self.save_type}")
        object.__setattr__(self, "save_path", str(self.save_path or DEFAULT_DANBOORU_SAVE_PATH))
        object.__setattr__(self, "download_concurrency", int(self.download_concurrency or DEFAULT_DOWNLOAD_CONCURRENCY))
        raw_doh_url = str(self.doh_url or "").strip()
        object.__setattr__(self, "doh_url", normalize_doh_url(raw_doh_url) if raw_doh_url else "")
        object.__setattr__(self, "motrix_aria2_conf_path", str(self.motrix_aria2_conf_path or "").strip())

    @classmethod
    def from_mapping(cls, raw: Optional[dict]) -> "DanbooruRuntimeConfig":
        data = raw or {}
        return cls(
            save_path=data.get("save_path", DEFAULT_DANBOORU_SAVE_PATH),
            save_type=data.get("save_type"),
            download_concurrency=data.get("download_concurrency", DEFAULT_DOWNLOAD_CONCURRENCY),
            doh_url=data.get("doh_url", ""),
            motrix_aria2_conf_path=data.get("motrix_aria2_conf_path", ""),
        )

    @classmethod
    def from_conf(cls) -> "DanbooruRuntimeConfig":
        return cls.from_mapping(getattr(conf, "danbooru", {}) or {})

    def is_doh_enabled(self) -> bool:
        return bool(self.doh_url)

    def motrix_add_uri_options(self) -> dict[str, str]:
        return build_motrix_dns_options(dns_server=self.stub_dns_server())

    def stub_dns_server(self) -> str:
        return DANBOORU_DNS_STUB_HOST if self.is_doh_enabled() else ""

    def stub_dns_endpoint(self) -> str:
        return f"{DANBOORU_DNS_STUB_HOST}:{DANBOORU_DNS_STUB_PORT}" if self.is_doh_enabled() else ""

    def request_dns_summary(self) -> str:
        return f"DoH -> {self.doh_url}" if self.is_doh_enabled() else "系统 DNS"

    def motrix_dns_summary(self) -> str:
        return f"Motrix: async-dns-server={self.stub_dns_server()}" if self.is_doh_enabled() else "Motrix: 默认 DNS"

    def network_label(self) -> str:
        return f"请求 {self.request_dns_summary()} | {self.motrix_dns_summary()}"

    def network_tooltip(self) -> str:
        if self.is_doh_enabled():
            request_text = f"Danbooru 请求通过 dnspython DoH resolver 解析，当前端点为 {self.doh_url}。"
            motrix_text = f"Danbooru 会启动本地 DNS stub {self.stub_dns_endpoint()}，Motrix 通过 async-dns-server={self.stub_dns_server()} 使用同一上游。"
            if self.motrix_aria2_conf_path:
                motrix_text += " 设置页保存时还会同步 aria2.conf。"
            return f"{request_text}\n{motrix_text}"
        request_text = "Danbooru 请求使用系统或代理链路的默认 DNS 解析。"
        motrix_text = "Motrix 不启用 Danbooru 本地 DNS stub。"
        if self.motrix_aria2_conf_path:
            motrix_text += " 设置页保存时会清空 aria2.conf 里的 Danbooru DNS 覆写。"
        return f"{request_text}\n{motrix_text}"

@dataclass(frozen=True, slots=True)
class DanbooruAutocompleteCandidate:
    value: str
    antecedent: str = ""
    autocomplete_type: str = ""
    category: Optional[int] = None
    proper_name: str = ""
    post_count_text: str = ""

    @property
    def menu_text(self) -> str:
        display = self.antecedent or self.proper_name or self.value
        if display.casefold() != self.value.casefold():
            display = f"{display} -> {self.value}"
        if self.post_count_text:
            display = f"{display} ({self.post_count_text})"
        return display


@dataclass(slots=True)
class DanbooruAutocompleteResult:
    canonical_term: str
    matches: list[DanbooruAutocompleteCandidate] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def is_single_match(self) -> bool:
        return len(self.matches) == 1

    @property
    def has_matches(self) -> bool:
        return bool(self.matches)

    @property
    def selected_term(self) -> Optional[str]:
        return self.matches[0].value if self.is_single_match else None


@dataclass(slots=True)
class DownloadPlan:
    deduped_skipped: list[DanbooruPost] = field(default_factory=list)
    to_submit: list[DanbooruPost] = field(default_factory=list)
    failed_pre_submit: list[DanbooruPost] = field(default_factory=list)
    submission_errors: list[str] = field(default_factory=list)


class DanbooruClient:
    base_url = DANBOORU_BASE_URL

    def __init__(self, *, timeout: float = 30.0, runtime_config: Optional[DanbooruRuntimeConfig] = None):
        self.runtime_config = runtime_config or DanbooruRuntimeConfig.from_conf()
        self.session = create_async_http_client(
            base_url=self.base_url,
            headers={
                "User-Agent": HTTPX_USER_AGENT,
                "Accept": "application/json",
            },
            timeout=timeout,
            follow_redirects=True,
            runtime_config=self.runtime_config,
        )
        self.page_size = DANBOORU_PAGE_SIZE

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    async def aclose(self):
        await self.session.aclose()

    async def _get_json(self, path: str, *, params: Optional[dict] = None):
        response = await self.session.get(path, params=params)
        raise_for_danbooru_response(response)
        return response.json()

    async def search_posts(
        self,
        tags: str,
        *,
        order: Optional[str] = None,
        page: int = 1,
        limit: Optional[int] = None,
    ) -> list[DanbooruPost]:
        canonical_term = canonicalize_search_term(tags)
        params = build_danbooru_search_params(
            canonical_term,
            order=order,
            page=page,
            limit=limit or self.page_size,
        )
        payload = await self._get_json(
            "/posts.json",
            params=params,
        )
        folder_term = strip_danbooru_order_tokens(canonical_term)
        return [DanbooruPost.from_api_payload(item, canonical_term=folder_term) for item in payload]

    async def get_post(self, post_id: int) -> DanbooruPost:
        payload = await self._get_json(f"/posts/{post_id}.json")
        return DanbooruPost.from_api_payload(payload)


def _parse_danbooru_autocomplete_category(value: Optional[str]) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def extract_danbooru_autocomplete_candidates(payload: str) -> list[DanbooruAutocompleteCandidate]:
    if not (payload or "").strip():
        return []
    document = lxml_html.fromstring(payload)
    candidates: list[DanbooruAutocompleteCandidate] = []
    seen_values: set[str] = set()
    for item in document.xpath("//li[contains(@class, 'ui-menu-item')][@data-autocomplete-value]"):
        value = canonicalize_search_term(item.get("data-autocomplete-value") or "")
        if not value or value in seen_values:
            continue
        antecedent = canonicalize_search_term(
            "".join(item.xpath(".//span[contains(@class, 'autocomplete-antecedent')]//text()"))
        )
        post_count_text = canonicalize_search_term(
            "".join(item.xpath(".//span[contains(@class, 'post-count')]//text()"))
        )
        candidates.append(
            DanbooruAutocompleteCandidate(
                value=value,
                antecedent=antecedent,
                autocomplete_type=canonicalize_search_term(item.get("data-autocomplete-type") or ""),
                category=_parse_danbooru_autocomplete_category(item.get("data-autocomplete-category")),
                proper_name=canonicalize_search_term(item.get("data-autocomplete-proper-name") or ""),
                post_count_text=post_count_text,
            )
        )
        seen_values.add(value)
    return candidates


async def autocomplete_danbooru_tags(
    term: str,
    *,
    timeout: float = 15.0,
    limit: int = DANBOORU_AUTOCOMPLETE_LIMIT,
) -> DanbooruAutocompleteResult:
    canonical_term = canonicalize_search_term(term)
    if not canonical_term:
        return DanbooruAutocompleteResult(canonical_term=canonical_term, reason="empty_term")
    async with create_async_http_client(
        base_url=DANBOORU_BASE_URL,
        headers={"User-Agent": HTTPX_USER_AGENT, "Accept": "text/html, */*;q=0.9"},
        timeout=timeout,
        follow_redirects=True,
        runtime_config=DanbooruRuntimeConfig.from_conf(),
    ) as client:
        response = await client.get(
            AUTOCOMPLETE_PATH,
            params={
                "search[query]": canonical_term,
                "search[type]": "tag",
                "version": 3,
                "limit": limit,
            },
        )
        raise_for_danbooru_response(response)
    matches = extract_danbooru_autocomplete_candidates(response.text)
    return DanbooruAutocompleteResult(
        canonical_term=canonical_term,
        matches=matches,
        reason=None if matches else "no_match",
    )


async def search_danbooru_posts(
    tags: str,
    *,
    order: Optional[str] = None,
    page: int = 1,
    limit: Optional[int] = None,
    timeout: float = 30.0,
) -> list[DanbooruPost]:
    async with DanbooruClient(timeout=timeout) as client:
        return await client.search_posts(tags, order=order, page=page, limit=limit)


async def fetch_remote_bytes(
    url: str,
    *,
    timeout: float = 20.0,
    headers: Optional[dict] = None,
    proxy_policy: str = "proxy",
) -> bytes:
    async with create_async_http_client(
        headers=headers or {"User-Agent": HTTPX_USER_AGENT, "Accept": "*/*"},
        timeout=timeout,
        follow_redirects=True,
        proxy_policy=proxy_policy,
        runtime_config=DanbooruRuntimeConfig.from_conf(),
    ) as client:
        response = await client.get(url)
        raise_for_danbooru_response(response)
        return response.content


def create_danbooru_sql_recorder() -> SqlRecorder:
    return SqlRecorder(table=DANBOORU_SQL_TABLE)


def plan_downloads(posts: Iterable[DanbooruPost], sql_recorder: Optional[SqlRecorder] = None) -> DownloadPlan:
    post_list = list(posts)
    plan = DownloadPlan()
    if not post_list:
        return plan
    recorder = sql_recorder or create_danbooru_sql_recorder()
    md5s = [post.md5 for post in post_list if post.md5]
    duplicated = recorder.batch_check_dupe(md5s)
    for post in post_list:
        if not post.file_url or not post.md5 or not post.is_supported:
            plan.failed_pre_submit.append(post)
        elif post.md5 in duplicated:
            plan.deduped_skipped.append(post)
        else:
            plan.to_submit.append(post)
    return plan


class DanbooruDownloadSubmitter:
    def __init__(
        self,
        *,
        runtime_config: Optional[DanbooruRuntimeConfig] = None,
        sql_recorder: Optional[SqlRecorder] = None,
        motrix_client: Optional[MotrixRPC] = None,
    ):
        self.runtime_config = runtime_config or DanbooruRuntimeConfig.from_conf()
        self.sql_recorder = sql_recorder or create_danbooru_sql_recorder()
        self.motrix_client = motrix_client

    async def submit(
        self,
        posts: Iterable[DanbooruPost],
        *,
        completion_callback: Optional[Callable[[str, bool], None]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> DownloadPlan:
        plan = plan_downloads(posts, sql_recorder=self.sql_recorder)
        if not plan.to_submit:
            return plan

        submit_candidates = list(plan.to_submit)
        plan.to_submit = []

        rpc = self.motrix_client or MotrixRPC()
        own_rpc = self.motrix_client is None
        sem = asyncio.Semaphore(self.runtime_config.download_concurrency)
        motrix_options = self.runtime_config.motrix_add_uri_options()
        if self.runtime_config.is_doh_enabled():
            await ensure_danbooru_dns_stub_started_async(self.runtime_config.doh_url)
            lg.info(
                f"[DanbooruDNS] runtime doh={self.runtime_config.doh_url} stub={self.runtime_config.stub_dns_endpoint()} motrix={self.runtime_config.stub_dns_server()}"
            )
        else:
            lg.info("[DanbooruDNS] runtime doh=disabled motrix=system")

        async def run_rpc_task(post: DanbooruPost) -> tuple[DanbooruPost, Optional[str]]:
            async with sem:
                try:
                    target_path = derive_download_path(post, runtime_config=self.runtime_config)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    gid = await rpc.add_uri(
                        post.file_url,
                        target_dir=target_path.parent,
                        out=post.filename,
                        task_id=f"danbooru-{post.post_id}",
                        options=motrix_options,
                    )
                    while True:
                        status_payload = await rpc.tell_status(gid)
                        status = status_payload.get("status")
                        if status == "complete":
                            if completion_callback is not None:
                                completion_callback(post.md5, True)
                            return post, None
                        if status in {"error", "removed"}:
                            err = status_payload.get("errorMessage") or status_payload.get("errorCode") or status or "unknown"
                            return post, err
                        if progress_callback is not None:
                            progress_callback(f"等待 Motrix 完成 {post.post_id}: {status or 'unknown'}")
                        await asyncio.sleep(MOTRIX_POLL_INTERVAL)
                except Exception as exc:
                    return post, str(exc)

        try:
            tasks = [asyncio.create_task(run_rpc_task(post)) for post in submit_candidates]
            for future in asyncio.as_completed(tasks):
                post, error = await future
                if error:
                    plan.failed_pre_submit.append(post)
                    plan.submission_errors.append(f"{post.post_id}: {error}")
                    continue
                plan.to_submit.append(post)
        finally:
            if own_rpc:
                await rpc.aclose()

        if plan.submission_errors and not plan.to_submit:
            raise RuntimeError("Motrix submission failed: " + "; ".join(plan.submission_errors[:3]))
        return plan


def derive_download_path(
    post: DanbooruPost,
    base_path: Optional[str] = None,
    runtime_config: Optional[DanbooruRuntimeConfig] = None,
) -> p.Path:
    config = runtime_config or DanbooruRuntimeConfig.from_conf()
    root = p.Path(base_path or config.save_path)
    if config.save_type == DANBOORU_SAVE_TYPE_SEARCH_TAG:
        canonical_term = canonicalize_search_term(post.canonical_term)
        if not canonical_term:
            raise ValueError("canonical_term is required when Danbooru save_type is 'search_tag'")
        root = root.joinpath(folder_sub.sub("-", canonical_term))
    return root.joinpath(post.filename)


def get_download_concurrency() -> int:
    return DanbooruRuntimeConfig.from_conf().download_concurrency


async def submit_downloads(
    posts: Iterable[DanbooruPost],
    redis_client: Optional[AioRClient] = None,
    motrix_client: Optional[MotrixRPC] = None,
    completion_callback: Optional[Callable[[str, bool], None]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> DownloadPlan:
    _ = redis_client
    submitter = DanbooruDownloadSubmitter(motrix_client=motrix_client)
    return await submitter.submit(
        posts,
        completion_callback=completion_callback,
        progress_callback=progress_callback,
    )
