"""DoH URL/stub policy — pure stdlib, deliberately free of dns/httpx imports.

Split out of ``doh.py`` because ``utils.config.qc`` needs only
``normalize_doh_url``, and importing it from ``doh`` dragged
``dns -> httpx -> httpx._main -> click/pygments/rich`` onto the GUI startup
path (~1.8s cold). Keep this module dependency-free; transports and resolvers
belong in ``doh.py``.
"""
from __future__ import annotations

from urllib.parse import urlparse

DNS_STUB_HOST = "127.0.0.1"
DNS_STUB_PORT = 53
DOH_WEBENGINE_PROXY_HOST = DOH_CONNECT_PROXY_HOST = "127.0.0.1"
DEFAULT_DOH_URL = "https://cloudflare-dns.com/dns-query"


def normalize_doh_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("DoH URL must be a full https://... endpoint")
    return text


def is_doh_enabled(doh_url: object) -> bool:
    return bool(normalize_doh_url(doh_url))


def dns_stub_server(doh_url: object) -> str:
    return DNS_STUB_HOST if is_doh_enabled(doh_url) else ""


def dns_stub_endpoint(doh_url: object) -> str:
    return f"{DNS_STUB_HOST}:{DNS_STUB_PORT}" if is_doh_enabled(doh_url) else ""
