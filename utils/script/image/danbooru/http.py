from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger as lg

from utils import get_httpx_verify
from utils.network.doh import build_http_transport
from utils.script import conf as script_conf

from .constants import DANBOORU_BASE_URL, DANBOORU_CHALLENGE_MARKERS
from .debug import append_danbooru_debug_event, debug_shrink_text
from .session import DanbooruBrowserSession, danbooru_browser_session_store

if TYPE_CHECKING:
    from .models import DanbooruRuntimeConfig


class DanbooruChallengeRequired(Exception):
    def __init__(self, *, verify_url: str, status_code: int, detail: str = ""):
        message = detail or "Danbooru request requires browser verification"
        super().__init__(message)
        self.verify_url = str(verify_url or DANBOORU_BASE_URL)
        self.status_code = int(status_code)


class DanbooruResponseInspector:
    @staticmethod
    def _verification_url(response: httpx.Response) -> str:
        request = getattr(response, "request", None)
        if request is None or getattr(request, "url", None) is None:
            return DANBOORU_BASE_URL
        parsed = urlsplit(str(request.url))
        return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))

    @staticmethod
    def contains_challenge_markers(payload: object) -> bool:
        text = str(payload or "").casefold()
        return any(marker in text for marker in DANBOORU_CHALLENGE_MARKERS)

    @classmethod
    def is_verification_completion_url(cls, url: str) -> bool:
        parsed = urlsplit(str(url or ""))
        base = urlsplit(DANBOORU_BASE_URL)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc.casefold() != base.netloc.casefold():
            return False
        return not cls.contains_challenge_markers(url)

    @classmethod
    def is_challenge_response(cls, response: httpx.Response) -> bool:
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
        return cls.contains_challenge_markers(text)

    @classmethod
    def classify(cls, response: httpx.Response) -> str:
        if cls.is_challenge_response(response):
            return "challenge"
        content_type = str(getattr(response, "headers", {}).get("content-type", "")).casefold()
        if "json" in content_type:
            return "json"
        if "html" in content_type:
            return "html"
        return content_type or "unknown"

    @classmethod
    def log(cls, scope: str, response: httpx.Response) -> None:
        request = getattr(response, "request", None)
        if request is None:
            return
        cookie_header = request.headers.get("Cookie", "")
        request_cookie_names = DanbooruBrowserSession.cookie_names_from_header(cookie_header)
        request_header_names = sorted(request.headers.keys())
        browser_session = danbooru_browser_session_store.current()
        lg.info(
            f"[DanbooruHTTP] {scope} method={request.method} url={request.url} "
            f"status={response.status_code} content_type={response.headers.get('content-type', '')} "
            f"classification={cls.classify(response)} "
            f"user_agent={request.headers.get('User-Agent', '')} "
            f"referer={request.headers.get('Referer', '')} "
            f"request_header_names={request_header_names} "
            f"request_cookie_names={request_cookie_names} "
            f"{browser_session.summary()}"
        )
        append_danbooru_debug_event(
            "http.response",
            scope=scope,
            method=request.method,
            url=str(request.url),
            status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            classification=cls.classify(response),
            user_agent=request.headers.get("User-Agent", ""),
            referer=request.headers.get("Referer", ""),
            request_header_names=request_header_names,
            request_cookie_names=request_cookie_names,
            response_head=debug_shrink_text(getattr(response, "text", "") or ""),
            browser_session=browser_session.summary(),
        )

    @classmethod
    def raise_for_status(cls, response: httpx.Response) -> None:
        if cls.is_challenge_response(response):
            append_danbooru_debug_event(
                "http.challenge_detected",
                verify_url=cls._verification_url(response),
                status=response.status_code,
                url=str(getattr(getattr(response, "request", None), "url", "")),
            )
            raise DanbooruChallengeRequired(
                verify_url=cls._verification_url(response),
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
    from .models import DanbooruRuntimeConfig

    config = runtime_config or DanbooruRuntimeConfig.from_conf()
    transport, trust_env = build_http_transport(
        proxy_policy,
        getattr(script_conf, "proxies", None) or [],
        doh_url=config.doh_url,
        is_async=True,
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
    danbooru_browser_session_store.apply_to(client)
    return client
