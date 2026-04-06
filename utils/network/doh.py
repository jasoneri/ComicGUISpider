from __future__ import annotations

import ipaddress
import threading
from typing import Iterable, Optional
from urllib.parse import urlparse

import dns.asyncresolver
import dns.resolver
import dns.rdatatype
import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.sync import SyncBackend
from httpx._config import DEFAULT_LIMITS, Limits, Proxy, create_ssl_context
from httpx._transports.default import (
    AsyncResponseStream,
    ResponseStream,
    SOCKET_OPTION,
    map_httpcore_exceptions,
)

DNS_STUB_HOST = "127.0.0.1"
DNS_STUB_PORT = 53
DOH_WEBENGINE_PROXY_HOST = DOH_CONNECT_PROXY_HOST = "127.0.0.1"
DEFAULT_DOH_URL = "https://cloudflare-dns.com/dns-query"
_DOH_CACHE_SIZE = 4096

_resolver_cache_lock = threading.Lock()
_resolver_caches: dict[str, dns.resolver.LRUCache] = {}


def normalize_doh_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("DoH URL must be a full https://... endpoint")
    return text


def _resolver_cache(doh_url: str) -> dns.resolver.LRUCache:
    with _resolver_cache_lock:
        cache = _resolver_caches.get(doh_url)
        if cache is None:
            cache = dns.resolver.LRUCache(max_size=_DOH_CACHE_SIZE)
            _resolver_caches[doh_url] = cache
        return cache


def create_async_doh_resolver(doh_url: str) -> dns.asyncresolver.Resolver:
    normalized_doh_url = normalize_doh_url(doh_url)
    if not normalized_doh_url:
        raise ValueError("DoH resolver can only be created when DoH is enabled")
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = [normalized_doh_url]
    resolver.cache = _resolver_cache(normalized_doh_url)
    resolver.search = []
    resolver.use_search_by_default = False
    return resolver


def create_sync_doh_resolver(doh_url: str) -> dns.resolver.Resolver:
    normalized_doh_url = normalize_doh_url(doh_url)
    if not normalized_doh_url:
        raise ValueError("DoH resolver can only be created when DoH is enabled")
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [normalized_doh_url]
    resolver.cache = _resolver_cache(normalized_doh_url)
    resolver.search = []
    resolver.use_search_by_default = False
    return resolver


async def resolve_host_via_doh(
    resolver: dns.asyncresolver.Resolver,
    host: str,
    *,
    timeout: Optional[float] = None,
    local_address: Optional[str] = None,
) -> str:
    text = str(host or "").strip()
    if not text:
        raise httpcore.ConnectError("DoH resolution received an empty host")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    if text.casefold() == "localhost":
        return DNS_STUB_HOST

    lifetime = timeout if timeout and timeout > 0 else 5.0
    family_order = [dns.rdatatype.A, dns.rdatatype.AAAA]
    if local_address and ":" in local_address:
        family_order = [dns.rdatatype.AAAA, dns.rdatatype.A]
    last_error: Optional[Exception] = None
    for rdtype in family_order:
        try:
            answer = await resolver.resolve(text, rdtype, search=False, lifetime=lifetime)
        except dns.resolver.NoAnswer:
            continue
        except dns.resolver.NXDOMAIN as exc:
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            continue
        if len(answer) > 0:
            candidate = answer[0]
            address = getattr(candidate, "address", None)
            if address:
                return address
            return candidate.to_text()
    if last_error is not None:
        raise httpcore.ConnectError(f"DoH resolution failed for {text}: {last_error}") from last_error
    raise httpcore.ConnectError(f"DoH resolution returned no A/AAAA record for {text}")


def resolve_host_via_sync_doh(
    resolver: dns.resolver.Resolver,
    host: str,
    *,
    timeout: Optional[float] = None,
    local_address: Optional[str] = None,
) -> str:
    text = str(host or "").strip()
    if not text:
        raise httpcore.ConnectError("DoH resolution received an empty host")
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        pass
    if text.casefold() == "localhost":
        return DNS_STUB_HOST

    lifetime = timeout if timeout and timeout > 0 else 5.0
    family_order = [dns.rdatatype.A, dns.rdatatype.AAAA]
    if local_address and ":" in local_address:
        family_order = [dns.rdatatype.AAAA, dns.rdatatype.A]
    last_error: Optional[Exception] = None
    for rdtype in family_order:
        try:
            answer = resolver.resolve(text, rdtype, search=False, lifetime=lifetime)
        except dns.resolver.NoAnswer:
            continue
        except dns.resolver.NXDOMAIN as exc:
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            continue
        if len(answer) > 0:
            candidate = answer[0]
            address = getattr(candidate, "address", None)
            if address:
                return address
            return candidate.to_text()
    if last_error is not None:
        raise httpcore.ConnectError(f"DoH resolution failed for {text}: {last_error}") from last_error
    raise httpcore.ConnectError(f"DoH resolution returned no A/AAAA record for {text}")


def is_doh_enabled(doh_url: object) -> bool:
    return bool(normalize_doh_url(doh_url))


def dns_stub_server(doh_url: object) -> str:
    return DNS_STUB_HOST if is_doh_enabled(doh_url) else ""


def dns_stub_endpoint(doh_url: object) -> str:
    return f"{DNS_STUB_HOST}:{DNS_STUB_PORT}" if is_doh_enabled(doh_url) else ""


class DoHNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, doh_url: str):
        self._doh_url = normalize_doh_url(doh_url)
        self._resolver = create_async_doh_resolver(self._doh_url)
        self._backend = AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ):
        target_host = await self._resolve_host(host, timeout=timeout, local_address=local_address)
        return await self._backend.connect_tcp(
            host=target_host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ):
        return await self._backend.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)

    async def _resolve_host(
        self,
        host: str,
        *,
        timeout: Optional[float],
        local_address: Optional[str],
    ) -> str:
        return await resolve_host_via_doh(
            self._resolver,
            host,
            timeout=timeout,
            local_address=local_address,
        )


class SyncDoHNetworkBackend(SyncBackend):
    def __init__(self, doh_url: str):
        super().__init__()
        self._doh_url = normalize_doh_url(doh_url)
        self._resolver = create_sync_doh_resolver(self._doh_url)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ):
        target_host = resolve_host_via_sync_doh(
            self._resolver,
            host,
            timeout=timeout,
            local_address=local_address,
        )
        return super().connect_tcp(
            host=target_host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class DoHHTTPTransport(httpx.HTTPTransport):
    def __init__(
        self,
        *,
        network_backend: httpcore.NetworkBackend,
        verify=True,
        cert=None,
        limits: Limits = DEFAULT_LIMITS,
        trust_env: bool = True,
        proxy=None,**kw
    ) -> None:
        ssl_context = create_ssl_context(verify=verify, cert=cert, trust_env=trust_env)
        proxy = Proxy(url=proxy) if isinstance(proxy, (str, httpx.URL)) else proxy

        if proxy is None:
            self._pool = httpcore.ConnectionPool(
                ssl_context=ssl_context,
                max_connections=limits.max_connections,
                max_keepalive_connections=limits.max_keepalive_connections,
                keepalive_expiry=limits.keepalive_expiry,
                network_backend=network_backend, **kw
            )
        elif proxy.url.scheme in ("http", "https"):
            self._pool = httpcore.HTTPProxy(
                proxy_url=httpcore.URL(
                    scheme=proxy.url.raw_scheme,
                    host=proxy.url.raw_host,
                    port=proxy.url.port,
                    target=proxy.url.raw_path,
                ),
                proxy_auth=proxy.raw_auth,
                proxy_headers=proxy.headers.raw,
                ssl_context=ssl_context,
                proxy_ssl_context=proxy.ssl_context,
                max_connections=limits.max_connections,
                max_keepalive_connections=limits.max_keepalive_connections,
                keepalive_expiry=limits.keepalive_expiry,
                network_backend=network_backend, **kw
            )
        else:
            raise ValueError("DoH transport only supports direct or HTTP/HTTPS proxy connections")


class DoHAsyncHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        *,
        network_backend: httpcore.AsyncNetworkBackend,
        verify=True,
        cert=None,
        http1: bool = True,
        http2: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        trust_env: bool = True,
        proxy=None,
        uds: Optional[str] = None,
        local_address: Optional[str] = None,
        retries: int = 0,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ) -> None:
        ssl_context = create_ssl_context(verify=verify, cert=cert, trust_env=trust_env)
        proxy = Proxy(url=proxy) if isinstance(proxy, (str, httpx.URL)) else proxy

        if proxy is None:
            self._pool = httpcore.AsyncConnectionPool(
                ssl_context=ssl_context,
                max_connections=limits.max_connections,
                max_keepalive_connections=limits.max_keepalive_connections,
                keepalive_expiry=limits.keepalive_expiry,
                http1=http1,
                http2=http2,
                uds=uds,
                local_address=local_address,
                retries=retries,
                socket_options=socket_options,
                network_backend=network_backend,
            )
        elif proxy.url.scheme in ("http", "https"):
            self._pool = httpcore.AsyncHTTPProxy(
                proxy_url=httpcore.URL(
                    scheme=proxy.url.raw_scheme,
                    host=proxy.url.raw_host,
                    port=proxy.url.port,
                    target=proxy.url.raw_path,
                ),
                proxy_auth=proxy.raw_auth,
                proxy_headers=proxy.headers.raw,
                ssl_context=ssl_context,
                proxy_ssl_context=proxy.ssl_context,
                max_connections=limits.max_connections,
                max_keepalive_connections=limits.max_keepalive_connections,
                keepalive_expiry=limits.keepalive_expiry,
                http1=http1,
                http2=http2,
                retries=retries,
                local_address=local_address,
                uds=uds,
                socket_options=socket_options,
                network_backend=network_backend,
            )
        else:
            raise ValueError("DoH transport only supports direct or HTTP/HTTPS proxy connections")

    async def __aenter__(self):
        await self._pool.__aenter__()
        return self

    async def __aexit__(self, exc_type=None, exc_value=None, traceback=None) -> None:
        with map_httpcore_exceptions():
            await self._pool.__aexit__(exc_type, exc_value, traceback)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        req = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with map_httpcore_exceptions():
            resp = await self._pool.handle_async_request(req)
        return httpx.Response(
            status_code=resp.status,
            headers=resp.headers,
            stream=AsyncResponseStream(resp.stream),
            extensions=resp.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


def build_http_transport(
    proxy_policy: str,
    proxies: list[str],
    *,
    doh_url: str,
    is_async: bool,
    retries: int = 0,
    verify=True,
    cert=None,
    limits=None,
    http1: bool = True,
    http2: bool = False,
) -> tuple[httpx.BaseTransport | httpx.AsyncBaseTransport, bool]:
    normalized_doh_url = normalize_doh_url(doh_url) if str(doh_url or "").strip() else ""
    if not normalized_doh_url:
        transport_kw = {
            "retries": retries,
            "verify": verify,
            "http1": http1,
            "http2": http2,
        }
        if cert is not None:
            transport_kw["cert"] = cert
        if limits is not None:
            transport_kw["limits"] = limits
        from utils.website.core import build_proxy_transport

        return build_proxy_transport(
            proxy_policy,
            proxies,
            is_async=is_async,
            **transport_kw,
        )

    proxy = None
    effective_retries = retries
    if proxy_policy != "direct" and proxies:
        proxy = f"http://{proxies[0]}"
        effective_retries += 1

    doh_limits = limits or DEFAULT_LIMITS
    if is_async:
        transport = DoHAsyncHTTPTransport(
            verify=verify,
            cert=cert,
            limits=doh_limits,
            trust_env=False,
            proxy=proxy,
            retries=effective_retries,
            http1=http1,
            http2=http2,
            network_backend=DoHNetworkBackend(normalized_doh_url),
        )
    else:
        transport = DoHHTTPTransport(
            verify=verify,
            cert=cert,
            limits=doh_limits,
            trust_env=False,
            proxy=proxy,
            retries=effective_retries,
            http1=http1,
            http2=http2,
            network_backend=SyncDoHNetworkBackend(normalized_doh_url),
        )
    return transport, False
