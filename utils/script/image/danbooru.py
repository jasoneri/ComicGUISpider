#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import html
import pathlib as p
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional
from urllib.parse import quote

import httpx
from lxml import html as lxml_html

from utils import get_httpx_verify
from utils.script import conf, AioRClient, folder_sub
from utils.script.motrix import HTTPX_USER_AGENT, MotrixRPC
from utils.sql import SqlRecorder
from utils.website.core import build_proxy_transport

SUPPORTED_MEDIA_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
UNSUPPORTED_MEDIA_EXTENSIONS = {"mp4", "webm", "zip"}
DANBOORU_SQL_TABLE = "danbooru_md5_table"
_WHITESPACE_RE = re.compile(r"\s+")
_ORDER_TOKEN_CAPTURE_RE = re.compile(r"(?:^|\s)(order:[^\s]+)")
_ORDER_TOKEN_STRIP_RE = re.compile(r"(?:^|\s)order:[^\s]+")
DEFAULT_DOWNLOAD_CONCURRENCY = 3
MOTRIX_POLL_INTERVAL = 1.2
DANBOORU_PAGE_SIZE = 30
DEFAULT_DANBOORU_SAVE_PATH = "D:/pic/danbooru"
DANBOORU_SAVE_TYPE_SEARCH_TAG = "search_tag"
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
MOEGIRL_PAGE_HOST = "https://zh.moegirl.org.cn"
_MOEGIRL_LATIN_PREFIX_RE = re.compile(
    r"(?:(?:^|\n)\s*(?:英|英文名|English|平文式罗马字|罗马字|罗马音)[:：]\s*)([A-Za-z][A-Za-z0-9 ._'/+-]*)",
    re.IGNORECASE,
)
_MOEGIRL_LATIN_PAREN_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9 ._'/+-]*)\)")
_MOEGIRL_PLAIN_LATIN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ._'/+-]*$")
_MOEGIRL_LABEL_PRIORITY = ("外文名", "英文名", "本名", "罗马字", "平文式罗马字")


def create_async_http_client(
    *,
    base_url: str = "",
    headers: Optional[dict] = None,
    timeout: float = 30.0,
    follow_redirects: bool = False,
    proxy_policy: str = "proxy",
    retries: int = 2,
    **kwargs,
) -> httpx.AsyncClient:
    transport, trust_env = build_proxy_transport(
        proxy_policy,
        getattr(conf, "proxies", None) or [],
        is_async=True,
        retries=retries,
        verify=get_httpx_verify(),
    )
    return httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        follow_redirects=follow_redirects,
        transport=transport,
        trust_env=trust_env,
        **kwargs,
    )


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


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(filter(None, values)))


def _normalize_moegirl_ascii_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = text.strip().strip("()[]{}")
    text = text.replace("&", " and ")
    text = text.replace("’", "'")
    text = re.sub(r"[']", "", text)
    text = re.sub(r"\s+", "_", text.lower())
    text = re.sub(r"[^a-z0-9_:/+-]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _html_fragment_text(node) -> str:
    fragment = lxml_html.tostring(node, encoding="unicode")
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = lxml_html.fromstring(fragment).text_content()
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _extract_moegirl_ascii_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in _MOEGIRL_LATIN_PREFIX_RE.findall(text):
        candidates.append(match.strip())
    for match in _MOEGIRL_LATIN_PAREN_RE.findall(text):
        candidates.append(match.strip())
    for line in (item.strip() for item in text.splitlines()):
        if _MOEGIRL_PLAIN_LATIN_RE.fullmatch(line):
            candidates.append(line)
    return _dedupe_keep_order(candidates)


def _iter_moegirl_label_texts(page_html: str, label: str) -> Iterable[str]:
    document = lxml_html.fromstring(page_html)
    for span in document.xpath(f"//span[normalize-space()='{label}']"):
        label_div = span.getparent()
        while label_div is not None and label_div.tag != "div":
            label_div = label_div.getparent()
        if label_div is None:
            continue
        value_div = label_div.getnext()
        if value_div is None or value_div.tag != "div":
            continue
        text = _html_fragment_text(value_div)
        if text:
            yield text


def extract_moegirl_danbooru_tag(page_html: str) -> Optional[str]:
    for label in _MOEGIRL_LABEL_PRIORITY:
        for label_text in _iter_moegirl_label_texts(page_html, label):
            for candidate in _extract_moegirl_ascii_candidates(label_text):
                normalized = _normalize_moegirl_ascii_name(candidate)
                if normalized:
                    return normalized
    page_text = lxml_html.fromstring(page_html).text_content()
    for candidate in _MOEGIRL_LATIN_PREFIX_RE.findall(page_text):
        normalized = _normalize_moegirl_ascii_name(candidate)
        if normalized:
            return normalized
    return None


def _build_moegirl_page_url(title: str) -> str:
    return f"{MOEGIRL_PAGE_HOST}/{quote(title, safe='/:()')}"


def extract_moegirl_page_candidates(payload: object) -> list[tuple[str, str]]:
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        return []
    urls = payload[3] if len(payload) >= 4 and isinstance(payload[3], list) else []
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(payload[1]):
        title = canonicalize_search_term(item) if isinstance(item, str) else ""
        if not title or title in seen:
            continue
        page_url = urls[index] if index < len(urls) and isinstance(urls[index], str) and urls[index] else _build_moegirl_page_url(title)
        candidates.append((title, page_url))
        seen.add(title)
    return candidates


def select_moegirl_page_candidate(canonical_term: str, candidates: Iterable[tuple[str, str]]) -> Optional[tuple[str, str]]:
    candidate_list = list(candidates)
    if not candidate_list:
        return None
    exact_matches = [item for item in candidate_list if item[0].casefold() == canonical_term.casefold()]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(candidate_list) == 1:
        return candidate_list[0]
    return None


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
        response.raise_for_status()
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

    @classmethod
    def from_conf(cls) -> "DanbooruRuntimeConfig":
        raw = getattr(conf, "danbooru", {}) or {}
        save_type = raw.get("save_type")
        if save_type not in {None, DANBOORU_SAVE_TYPE_SEARCH_TAG}:
            raise ValueError(f"Unsupported Danbooru save_type: {save_type}")
        return cls(
            save_path=raw.get("save_path", DEFAULT_DANBOORU_SAVE_PATH),
            save_type=save_type,
            download_concurrency=int(raw.get("download_concurrency", DEFAULT_DOWNLOAD_CONCURRENCY)),
        )


@dataclass(slots=True)
class MoegirlConversionResult:
    success: bool
    canonical_term: str
    converted_term: Optional[str] = None
    reason: Optional[str] = None
    candidates: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DownloadPlan:
    deduped_skipped: list[DanbooruPost] = field(default_factory=list)
    to_submit: list[DanbooruPost] = field(default_factory=list)
    failed_pre_submit: list[DanbooruPost] = field(default_factory=list)
    submission_errors: list[str] = field(default_factory=list)


class DanbooruClient:
    base_url = "https://danbooru.donmai.us"

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
        response.raise_for_status()
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


class MoegirlConverter:
    endpoint = "https://moegirl.org.cn/api.php"

    def __init__(self, *, timeout: float = 20.0):
        self.session = create_async_http_client(
            headers={"User-Agent": HTTPX_USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    async def aclose(self):
        await self.session.aclose()

    async def convert(self, term: str) -> MoegirlConversionResult:
        canonical_term = canonicalize_search_term(term)
        if not canonical_term:
            return MoegirlConversionResult(False, canonical_term, reason="empty_term")
        response = await self.session.get(
            self.endpoint,
            params={
                "action": "opensearch",
                "search": canonical_term,
                "limit": 10,
                "namespace": 0,
                "format": "json",
            },
        )
        response.raise_for_status()
        page_candidates = extract_moegirl_page_candidates(response.json())
        if not page_candidates:
            return MoegirlConversionResult(False, canonical_term, reason="no_result")
        selected_page = select_moegirl_page_candidate(canonical_term, page_candidates)
        if selected_page is None:
            return MoegirlConversionResult(
                False,
                canonical_term,
                reason="ambiguous",
                candidates=[title for title, _ in page_candidates],
            )
        _page_title, page_url = selected_page
        page_response = await self.session.get(page_url)
        page_response.raise_for_status()
        converted_term = extract_moegirl_danbooru_tag(page_response.text)
        if not converted_term:
            return MoegirlConversionResult(
                False,
                canonical_term,
                reason="no_convertible_term",
                candidates=[title for title, _ in page_candidates],
            )
        return MoegirlConversionResult(
            True,
            canonical_term=canonical_term,
            converted_term=converted_term,
            candidates=[converted_term],
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


async def convert_moegirl_term(term: str, *, timeout: float = 20.0) -> MoegirlConversionResult:
    async with MoegirlConverter(timeout=timeout) as converter:
        return await converter.convert(term)


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
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
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
