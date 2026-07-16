from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Optional
from urllib.parse import quote

import httpx
from lxml import html as lxml_html

from utils.script.motrix import HTTPX_USER_AGENT

from .constants import (
    AUTOCOMPLETE_PATH,
    DANBOORU_AUTOCOMPLETE_LIMIT,
    DANBOORU_BASE_URL,
    DANBOORU_PAGE_SIZE,
)
from .http import DanbooruResponseInspector, create_client
from .models import (
    DanbooruAutocompleteCandidate,
    DanbooruAutocompleteResult,
    DanbooruPost,
    DanbooruRuntimeConfig,
    DanbooruSearchQuery,
)
from .session import danbooru_browser_session_store


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


class DanbooruClient:
    base_url = DANBOORU_BASE_URL

    def __init__(self, *, timeout: float = 30.0, proxy_policy: str = "proxy", runtime_config: Optional[DanbooruRuntimeConfig] = None):
        self.timeout = float(timeout)
        self.proxy_policy = str(proxy_policy or "proxy")
        self.runtime_config = runtime_config or DanbooruRuntimeConfig.from_conf()
        self.page_size = DANBOORU_PAGE_SIZE
        self._lock = threading.Lock()
        self._session_revision: Optional[int] = None
        self._client: Optional[httpx.Client] = None
        self._retired_clients: list[httpx.Client] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        with self._lock:
            clients = [client for client in [self._client, *self._retired_clients] if client is not None]
            self._client = None
            self._retired_clients = []
            self._session_revision = None
        for client in clients:
            client.close()

    def set_runtime_config(self, runtime_config: Optional[DanbooruRuntimeConfig] = None):
        next_config = runtime_config or DanbooruRuntimeConfig.from_conf()
        with self._lock:
            if next_config == self.runtime_config:
                return
            self.runtime_config = next_config
            self._retire_current_client_locked()

    def _retire_current_client_locked(self):
        if self._client is not None:
            self._retired_clients.append(self._client)
            self._client = None
        self._session_revision = None

    def _get_client(self) -> httpx.Client:
        session_revision, _browser_session = danbooru_browser_session_store.current_with_revision()
        with self._lock:
            if self._client is None or self._session_revision != session_revision:
                self._retire_current_client_locked()
                self._client = create_client(
                    mode="sync", base_url=self.base_url, headers={"User-Agent": HTTPX_USER_AGENT}, timeout=self.timeout,
                    follow_redirects=True, proxy_policy=self.proxy_policy, runtime_config=self.runtime_config,
                )
                self._session_revision = session_revision
            return self._client

    def _request(
        self,
        url: str,
        *,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[float] = None,
        log_scope: Optional[str] = None,
    ) -> httpx.Response:
        response = self._get_client().get(url, params=params, headers=headers, timeout=timeout or self.timeout)
        if log_scope:
            DanbooruResponseInspector.log(log_scope, response)
        DanbooruResponseInspector.raise_for_status(response)
        return response

    def _get_json(self, path: str, *, params: Optional[dict] = None, timeout: Optional[float] = None):
        response = self._request(
            path, params=params, headers={"Accept": "application/json"}, timeout=timeout,
            log_scope=f"json path={path} params={params}",
        )
        return response.json()

    def search_posts(
        self,
        tags: str,
        *,
        order: Optional[str] = None,
        page: int = 1,
        limit: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> list[DanbooruPost]:
        search_query = DanbooruSearchQuery(tags, order or "")
        params = search_query.params(page=page, limit=limit or self.page_size)
        payload = self._get_json("/posts.json", timeout=timeout, params=params)
        return [DanbooruPost.from_api_payload(item, canonical_term=search_query.folder_term) for item in payload]

    def get_post(self, post_id: int, *, timeout: Optional[float] = None) -> DanbooruPost:
        return DanbooruPost.from_api_payload(self._get_json(f"/posts/{post_id}.json", timeout=timeout))

    def get_wiki_page(self, title: str, *, timeout: Optional[float] = None) -> Optional[dict]:
        """Exact wiki page by tag title (other_names + body). Uses browser session client."""
        tag_title = str(title or "").strip()
        if not tag_title:
            return None
        encoded = quote(tag_title, safe="")
        try:
            payload = self._get_json(f"/wiki_pages/{encoded}.json", timeout=timeout)
        except Exception:
            payload = self._get_json(
                "/wiki_pages.json",
                params={"search[title]": tag_title, "limit": "1"},
                timeout=timeout,
            )
        record: Optional[dict] = None
        if isinstance(payload, dict):
            record = payload
        elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
            record = payload[0]
        if not record or record.get("is_deleted"):
            return None
        got_title = str(record.get("title") or "").replace(" ", "_").casefold()
        want = tag_title.replace(" ", "_").casefold()
        if got_title and got_title != want and isinstance(payload, list):
            return None
        return record

    def autocomplete_tags(
        self,
        term: str,
        *,
        timeout: float = 15.0,
        limit: int = DANBOORU_AUTOCOMPLETE_LIMIT,
    ) -> DanbooruAutocompleteResult:
        canonical_term = DanbooruSearchQuery.normalize(term)
        if not canonical_term:
            return DanbooruAutocompleteResult(canonical_term=canonical_term, reason="empty_term")
        response = self._request(
            AUTOCOMPLETE_PATH,
            params={
                "search[query]": canonical_term,
                "search[type]": "tag",
                "version": 3,
                "limit": limit,
            },
            headers={"Accept": "text/html, */*;q=0.9"}, timeout=timeout, log_scope=f"autocomplete term={canonical_term} limit={limit}",
        )
        matches = extract_danbooru_autocomplete_candidates(response.text)
        return DanbooruAutocompleteResult(canonical_term=canonical_term, matches=matches, reason=None if matches else "no_match")

    def fetch_remote_bytes(self, url: str, *, timeout: float = 20.0, headers: Optional[dict] = None) -> bytes:
        response = self._request(url, headers=headers or {"Accept": "*/*"}, timeout=timeout)
        return response.content

    def fetch_remote_image_size(self, url: str, *, timeout: float = 12.0, probe_bytes: int = 262143) -> Optional[tuple[int, int]]:
        response = self._request(url, headers={"Accept": "*/*", "Range": f"bytes=0-{probe_bytes}"}, timeout=timeout)
        return probe_image_size_from_bytes(response.content)

    @contextmanager
    def stream_remote(
        self,
        url: str,
        *,
        method: str = "GET",
        timeout: float = 90.0,
        headers: Optional[dict] = None,
        log_scope: Optional[str] = None,
    ):
        request_method = str(method or "GET").upper()
        with self._get_client().stream(request_method, url, headers=headers or {"Accept": "*/*"}, timeout=timeout) as response:
            if log_scope:
                DanbooruResponseInspector.log(log_scope, response)
            DanbooruResponseInspector.raise_for_status(response)
            yield response


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
                post_count_text=DanbooruSearchQuery.normalize("".join(item.xpath(".//span[contains(@class, 'post-count')]//text()"))),
            )
        )
        seen_values.add(value)
    return candidates
