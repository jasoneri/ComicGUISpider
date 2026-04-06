from __future__ import annotations

from typing import Optional

from lxml import html as lxml_html

from utils.script.motrix import HTTPX_USER_AGENT

from .constants import (
    AUTOCOMPLETE_PATH,
    DANBOORU_AUTOCOMPLETE_LIMIT,
    DANBOORU_BASE_URL,
    DANBOORU_PAGE_SIZE,
)
from .http import DanbooruResponseInspector, create_async_http_client
from .models import (
    DanbooruAutocompleteCandidate,
    DanbooruAutocompleteResult,
    DanbooruPost,
    DanbooruRuntimeConfig,
    DanbooruSearchQuery,
)


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
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
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
        DanbooruResponseInspector.raise_for_status(response)
        return probe_image_size_from_bytes(response.content)


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
        DanbooruResponseInspector.log(f"json path={path} params={params}", response)
        DanbooruResponseInspector.raise_for_status(response)
        return response.json()

    async def search_posts(
        self,
        tags: str,
        *,
        order: Optional[str] = None,
        page: int = 1,
        limit: Optional[int] = None,
    ) -> list[DanbooruPost]:
        search_query = DanbooruSearchQuery(tags, order or "")
        payload = await self._get_json(
            "/posts.json",
            params=search_query.params(page=page, limit=limit or self.page_size),
        )
        return [DanbooruPost.from_api_payload(item, canonical_term=search_query.folder_term) for item in payload]

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
        value = DanbooruSearchQuery.normalize(item.get("data-autocomplete-value") or "")
        if not value or value in seen_values:
            continue
        candidates.append(
            DanbooruAutocompleteCandidate(
                value=value,
                antecedent=DanbooruSearchQuery.normalize(
                    "".join(item.xpath(".//span[contains(@class, 'autocomplete-antecedent')]//text()"))
                ),
                autocomplete_type=DanbooruSearchQuery.normalize(item.get("data-autocomplete-type") or ""),
                category=_parse_danbooru_autocomplete_category(item.get("data-autocomplete-category")),
                proper_name=DanbooruSearchQuery.normalize(item.get("data-autocomplete-proper-name") or ""),
                post_count_text=DanbooruSearchQuery.normalize(
                    "".join(item.xpath(".//span[contains(@class, 'post-count')]//text()"))
                ),
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
    canonical_term = DanbooruSearchQuery.normalize(term)
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
        DanbooruResponseInspector.log(f"autocomplete term={canonical_term} limit={limit}", response)
        DanbooruResponseInspector.raise_for_status(response)
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
        DanbooruResponseInspector.raise_for_status(response)
        return response.content
