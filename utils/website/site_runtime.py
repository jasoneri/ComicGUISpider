from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
import typing as t

import httpx

from utils import conf, get_httpx_verify, temp_p
from utils.network.doh import build_http_transport
from variables import Spider

from .contracts import BrowserCookiePayload, BrowserEnvironmentPayload, PreprocessResult
from .core import Previewer
from .runtime_context import PreviewRuntimeContext, PreviewSiteConfig


def _normalize_domain_value(value: t.Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().rstrip("/")
    return normalized or None


def _raise_runtime_owner_todo(provider_cls: type, detail: str) -> t.NoReturn:
    raise NotImplementedError(f"TODO(site-runtime-owner): {provider_cls.__name__} {detail}")


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """
    Value object holding static provider identity and factory reference.

    Static config like publish_url, book_url_regex should be read directly
    from provider_cls when needed, not cached as forwarding properties.
    """
    provider_cls: type
    provider_name: str
    spider_name: str
    site_index: int | None = None

    @classmethod
    def create(cls, provider_cls, *, site_index: int | None = None, spider_name: str | None = None) -> "ProviderDescriptor":
        provider_name = str(getattr(provider_cls, "name", "") or spider_name or "")
        return cls(
            provider_cls=provider_cls,
            provider_name=provider_name,
            spider_name=str(spider_name or provider_name),
            site_index=site_index,
        )

    def get_uuid(self, *args, **kwargs):
        return self.provider_cls.get_uuid(*args, **kwargs)

    def preview_batch_limit(self, stage: str, default: int) -> int:
        """
        Read preview batch limit from provider_cls directly.
        No caching, no property forwarding.
        """
        raw_limits = getattr(self.provider_cls, "preview_batch_limits", None)
        if callable(raw_limits):
            raw_limits = raw_limits()
        if isinstance(raw_limits, dict):
            raw_value = raw_limits.get(stage, default)
        else:
            raw_value = getattr(self.provider_cls, f"preview_{stage}_batch_limit", default)
        try:
            limit = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"{self.provider_cls.__name__} preview batch limit must be int-compatible: "
                f"stage={stage!r} value={raw_value!r}"
            ) from exc
        if limit < 1:
            raise ValueError(f"{self.provider_cls.__name__} preview batch limit must be >= 1: stage={stage!r} value={limit}")
        return limit


class _ProviderRuntimeBase:
    def __init__(self, provider_descriptor: ProviderDescriptor, *, conf_state=conf):
        self.provider_descriptor = provider_descriptor
        self.conf_state = conf_state
        self.provider = provider_descriptor.provider_cls(conf_state)
        try:
            self.reqer = self.provider.reqer
        except AttributeError as exc:
            raise RuntimeError(f"{self.provider_cls.__name__} must expose provider.reqer for site runtime ownership") from exc
        try:
            self.parser = self.provider.parser
        except AttributeError as exc:
            raise RuntimeError(f"{self.provider_cls.__name__} must expose provider.parser for site runtime ownership") from exc

    @property
    def provider_cls(self):
        return self.provider_descriptor.provider_cls

    @property
    def name(self) -> str:
        return self.provider_descriptor.provider_name

    @property
    def spider_name(self) -> str:
        return self.provider_descriptor.spider_name

    @property
    def site_index(self) -> int | None:
        return self.provider_descriptor.site_index

    def get_uuid(self, *args, **kwargs):
        return self.provider_descriptor.get_uuid(*args, **kwargs)

    def resolve_domain(self):
        for candidate in (getattr(self.provider, "domain", None), getattr(self.reqer, "domain", None)):
            if normalized := _normalize_domain_value(candidate):
                return normalized
        if static_domain := _normalize_domain_value(getattr(self.provider_cls, "domain", None)):
            return static_domain
        _raise_runtime_owner_todo(
            self.provider_cls,
            "must bind domain on provider/reqer runtime state before spider flow; "
            "provider_cls.get_domain() fallback was removed",
        )

    def close(self):
        seen = set()
        for owner in (self.provider, self.reqer, self.parser):
            cli = getattr(owner, "cli", None)
            close = getattr(cli, "close", None)
            if cli is None or not callable(close) or id(cli) in seen:
                continue
            close()
            seen.add(id(cli))


class SpiderSiteRuntime(_ProviderRuntimeBase):
    pass


class ThreadSiteRuntime(_ProviderRuntimeBase):
    BROWSER_IMAGE_ACCEPT = (
        "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5"
    )

    def __init__(
        self,
        provider_descriptor: ProviderDescriptor,
        *,
        site_config: PreviewSiteConfig,
        conf_state=conf,
        preview_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(provider_descriptor, conf_state=conf_state)
        self.site_config = site_config
        self._preview_client = preview_client
        self._bind_preview_state()

    def _bind_preview_state(self):
        if self.site_config.domain:
            setattr(self.provider, "domain", self.site_config.domain)
        setattr(self.provider, "site_config", self.site_config)
        for owner in (self.provider, self.reqer):
            if not hasattr(owner, "__dict__"):
                continue
            setattr(owner, "site_config", self.site_config)
            setattr(owner, "transport", self.site_config.transport)
            if self.site_config.domain:
                setattr(owner, "domain", self.site_config.domain)
            if self.site_config.cookies:
                setattr(owner, "cookies", copy.deepcopy(self.site_config.cookies))
            if self.site_config.custom_map:
                setattr(owner, "custom_map", copy.deepcopy(self.site_config.custom_map))
        if self._preview_client is not None:
            self.attach_preview_client(self._preview_client)

    def attach_preview_client(self, preview_client: httpx.AsyncClient | None):
        self._preview_client = preview_client
        if preview_client is not None and hasattr(self.reqer, "__dict__"):
            setattr(self.reqer, "preview_client", preview_client)
        return preview_client

    def _ensure_preview_support(self):
        if not issubclass(self.provider_cls, Previewer):
            raise TypeError(f"{self.provider_cls.__name__} does not support preview search")

    def _preview_client_parts(self):
        self._ensure_preview_support()
        site_kw = self.site_config.as_provider_kwargs()
        client_kw = dict(self.provider_cls.preview_client_config(**site_kw) or {})
        transport_kw = dict(self.provider_cls.preview_transport_config() or {})
        policy = getattr(self.provider_cls, "proxy_policy", "proxy")
        return site_kw, client_kw, transport_kw, policy

    def create_async_preview_client(self) -> httpx.AsyncClient:
        _site_kw, client_kw, transport_kw, policy = self._preview_client_parts()
        transport, trust_env = build_http_transport(
            policy,
            list(self.site_config.transport.proxies),
            doh_url=self.site_config.transport.doh_url,
            is_async=True,
            **transport_kw,
        )
        base_kw = {
            "transport": transport,
            "follow_redirects": True,
            "trust_env": trust_env,
            "headers": None,
        }
        base_kw.update(client_kw)
        return httpx.AsyncClient(**base_kw)

    def get_async_preview_client(self) -> httpx.AsyncClient:
        if self._preview_client is None:
            self.attach_preview_client(self.create_async_preview_client())
        return self._preview_client

    def preview_batch_limit(self, stage: str, default: int) -> int:
        return self.provider_descriptor.preview_batch_limit(stage, default)

    async def preview_search(self, keyword: str, *, page: int = 1) -> list:
        self.get_async_preview_client()
        return await self.reqer.preview_search(keyword, page=page)

    async def preview_fetch_episodes(self, book) -> list:
        self.get_async_preview_client()
        return await self.reqer.preview_fetch_episodes(book)

    async def preview_fetch_pages(self, item) -> list:
        self.get_async_preview_client()
        return await self.reqer.preview_fetch_pages(item)

    def download_cover_bytes(self, tasks_obj, *, browser_headers: dict[str, str] | None = None) -> bytes:
        _site_kw, client_kw, transport_kw, policy = self._preview_client_parts()
        provider_headers = dict(client_kw.pop("headers", {}) or {})
        transport_verify = transport_kw.pop("verify", get_httpx_verify())
        transport, trust_env = build_http_transport(
            policy,
            list(self.site_config.transport.proxies),
            doh_url=self.site_config.transport.doh_url,
            is_async=False,
            verify=transport_verify,
            **transport_kw,
        )
        with httpx.Client(
            headers=getattr(self.provider_cls, "book_hea", None) or getattr(self.provider_cls, "headers", {}),
            transport=transport,
            trust_env=trust_env,
            follow_redirects=True,
            timeout=15,
            **client_kw,
        ) as cli:
            headers = httpx.Headers(cli.headers)
            headers.update(provider_headers)
            headers.update(dict(browser_headers or {}))
            if "accept" not in headers or "image/" not in headers.get("accept", ""):
                headers["Accept"] = self.BROWSER_IMAGE_ACCEPT
            referer_url = Previewer.build_referer_url(
                getattr(tasks_obj, "title_url", None),
                request_url=getattr(tasks_obj, "cover_url", None),
            )
            if referer_url and "referer" not in headers:
                headers["Referer"] = referer_url
            resp = cli.get(tasks_obj.cover_url, headers=headers)
            resp.raise_for_status()
            return resp.content

    async def aclose(self):
        preview_client = self._preview_client
        self._preview_client = None
        if preview_client is not None:
            await preview_client.aclose()
        self.close()


@dataclass(slots=True)
class GuiSiteRuntime:
    provider_descriptor: ProviderDescriptor
    site_index: int
    runtime_context: PreviewRuntimeContext
    conf_state: t.Any = field(default_factory=lambda: conf)

    @classmethod
    def create(
        cls, provider_descriptor: ProviderDescriptor, *, site_index: int, snapshot=None, conf_state=conf,
        default_doh_url: str | None = None,
    ) -> "GuiSiteRuntime":
        runtime_context = cls._build_runtime_context(
            provider_descriptor,
            snapshot=snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )
        return cls(
            provider_descriptor=provider_descriptor,
            site_index=site_index,
            runtime_context=runtime_context,
            conf_state=conf_state,
        )

    @classmethod
    def _build_runtime_context(
        cls,
        provider_descriptor: ProviderDescriptor,
        *,
        snapshot,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> PreviewRuntimeContext:
        if snapshot is not None:
            return PreviewRuntimeContext.from_snapshot(snapshot, conf_state=conf_state, default_doh_url=default_doh_url)
        runtime_context = PreviewRuntimeContext.from_snapshot(None, conf_state=conf_state, default_doh_url=default_doh_url)
        cookies_by_site = {}
        raw_cookies = dict(getattr(conf_state, "cookies", {}) or {})
        if site_cookies := raw_cookies.get(provider_descriptor.provider_name):
            cookies_by_site[provider_descriptor.provider_name] = copy.deepcopy(dict(site_cookies))
        domains = {}
        if domain := cls._peek_cached_domain_for(provider_descriptor):
            domains[provider_descriptor.provider_name] = domain
        return replace(runtime_context, cookies_by_site=cookies_by_site, domains=domains)

    @property
    def provider_cls(self):
        return self.provider_descriptor.provider_cls

    @property
    def name(self) -> str:
        return self.provider_descriptor.provider_name

    @property
    def publish_url(self) -> str:
        """Read directly from provider_cls, not cached."""
        return getattr(self.provider_cls, "publish_url", "")

    @property
    def book_url_regex(self) -> str:
        """Read directly from provider_cls, not cached."""
        return getattr(self.provider_cls, "book_url_regex", "")

    @property
    def index(self):
        return getattr(self.provider_cls, "index", None)

    @property
    def domain(self):
        return getattr(self.provider_cls, "domain", None)

    def cache_path(self):
        return temp_p.joinpath(f"{self.name}_domain.txt")

    def build_site_config(self) -> PreviewSiteConfig:
        domain = self.runtime_context.site_domain(self.name)
        if not domain:
            domain = self.peek_snapshot_domain() or self.get_domain()
        return PreviewSiteConfig(
            cookies=self.runtime_context.site_cookies(self.name),
            domain=domain,
            custom_map=copy.deepcopy(self.runtime_context.custom_map),
            transport=self.runtime_context.transport,
        )

    def create_thread_site_runtime(self, *, preview_client: httpx.AsyncClient | None = None) -> ThreadSiteRuntime:
        return ThreadSiteRuntime(
            self.provider_descriptor,
            site_config=self.build_site_config(),
            conf_state=self.conf_state,
            preview_client=preview_client,
        )

    def create_runtime(self, conf_state=conf):
        return self.provider_cls(conf_state)

    def get_domain(self):
        if domain := _normalize_domain_value(self.runtime_context.site_domain(self.name)):
            return domain
        if domain := _normalize_domain_value(self.peek_snapshot_domain()):
            return domain
        if domain := _normalize_domain_value(getattr(self.provider_cls, "domain", None)):
            return domain
        _raise_runtime_owner_todo(
            self.provider_cls,
            "must bind domain through runtime_context or static provider config; "
            "provider_cls.get_domain() fallback was removed",
        )

    def test_index(self, conf_state=conf):
        runtime = self.create_runtime(conf_state)
        reqer = runtime.reqer
        try:
            return reqer.test_index()
        finally:
            reqer.cli.close()

    async def test_aviable_domain(self, domain):
        return await self.provider_cls.test_aviable_domain(domain)

    def with_domain(self, domain: str | None) -> "GuiSiteRuntime":
        if not domain:
            return self
        normalized = str(domain).strip()
        if not normalized:
            return self
        next_domains = copy.deepcopy(self.runtime_context.domains)
        if next_domains.get(self.name) == normalized:
            return self
        next_domains[self.name] = normalized
        return GuiSiteRuntime(
            provider_descriptor=self.provider_descriptor,
            site_index=self.site_index,
            runtime_context=replace(self.runtime_context, domains=next_domains),
            conf_state=self.conf_state,
        )

    def preprocess(self, *, conf_state=conf, data_client=None, progress_callback=None) -> PreprocessResult:
        from .preprocess import run_site_preprocess

        return run_site_preprocess(
            self.site_index,
            runtime_owner=self,
            conf_state=conf_state,
            data_client=data_client,
            progress_callback=progress_callback,
        )

    def build_browser_environment(self, *, lang: str, cn_proxy_indexes: t.Container[int]) -> BrowserEnvironmentPayload:
        """
        Build browser environment payload for the current site.

        FIXME: This is transitional hardcoded site logic.
        Each site should implement reqer.build_browser_environment() instead.
        The hardcoded if/elif chain below should be replaced by:
        - JM: reqer should own cookie injection and referer logic
        - WNACG: reqer should own referer logic
        - EHENTAI: reqer should own cookie and referer logic
        - HITOMI: reqer should own index URL validation
        """
        site_config = self.build_site_config()
        proxy_value = (site_config.transport.proxies or (None,))[0]
        proxy = proxy_value if lang != "zh-CN" or self.site_index in cn_proxy_indexes else None
        cookie_sets: list[BrowserCookiePayload] = []
        referer_url = None

        if self.site_index == Spider.JM:
            domain = self._resolve_site_domain(site_config, "jm")
            referer_url = f"https://{domain}"
            if site_config.cookies:
                cookie_sets.append(BrowserCookiePayload(values=site_config.cookies, domain=domain, url=referer_url))
        elif self.site_index == Spider.WNACG:
            referer_url = f"https://{self._resolve_site_domain(site_config, 'wnacg')}"
        elif self.site_index == Spider.EHENTAI:
            domain = site_config.domain or self.domain
            referer_url = f"https://{domain}/"
            if site_config.cookies:
                cookie_sets.append(BrowserCookiePayload(values=site_config.cookies, domain=domain, url=referer_url))
        elif self.site_index == Spider.HITOMI:
            referer_url = str(getattr(self.provider_cls, "index", ""))
            if not referer_url:
                raise ValueError("hitomi site index unavailable")

        return BrowserEnvironmentPayload(proxy=proxy, referer_url=referer_url, cookie_sets=tuple(cookie_sets))

    def _resolve_site_domain(self, site_config: PreviewSiteConfig, snapshot_key: str) -> str:
        if domain := _normalize_domain_value(site_config.domain):
            return domain
        if domain := _normalize_domain_value(self.peek_snapshot_domain()):
            return domain
        if domain := _normalize_domain_value(getattr(self.provider_cls, "domain", None)):
            return domain
        _raise_runtime_owner_todo(
            self.provider_cls,
            f"must bind domain before building {snapshot_key} browser environment; "
            "provider_cls.get_domain() fallback was removed",
        )

    def peek_snapshot_domain(self) -> str | None:
        return self._peek_cached_domain_for(self.provider_descriptor)

    @staticmethod
    def _peek_cached_domain_for(provider_descriptor: ProviderDescriptor) -> str | None:
        provider_cls = provider_descriptor.provider_cls
        cachef = getattr(provider_cls, "cachef", None)
        cached = getattr(cachef, "val", None) if cachef else None
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
        cache_path = temp_p.joinpath(f"{provider_descriptor.provider_name}_domain.txt")
        if cache_path.exists():
            cached_text = cache_path.read_text(encoding="utf-8").strip()
            if cached_text:
                return cached_text
        return None
