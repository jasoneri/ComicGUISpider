from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field, replace
import typing as t

import httpx

from utils import conf, temp_p

from .core import DomainUtils
from .preprocess import run_site_preprocess
from .runtime_context import PreviewRuntimeContext, PreviewSiteConfig
from .contracts import BrowserEnvironmentPayload, PreprocessResult


def _normalize_domain_value(value: t.Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().rstrip("/")
    return normalized or None


def _pick_bound_domain(*values: t.Any) -> str | None:
    for value in values:
        if normalized := _normalize_domain_value(value):
            return normalized
    return None


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

    def _bind_runtime_domain(self, domain: str) -> str:
        normalized = _normalize_domain_value(domain)
        if not normalized:
            raise ValueError(f"{self.provider_cls.__name__} runtime domain must be a non-empty string")
        self.provider.domain = normalized
        self.reqer.domain = normalized
        return normalized

    def _require_runtime_domain(self) -> str:
        domain = _pick_bound_domain(
            getattr(self.provider, "domain", None),
            getattr(self.reqer, "domain", None),
            getattr(self.provider_cls, "domain", None),
        )
        if domain is None:
            raise RuntimeError(
                f"{self.provider_cls.__name__} spider runtime requires a bound domain on provider/reqer runtime state "
                "or static provider config"
            )
        return self._bind_runtime_domain(domain)

    def _require_reqer_method(self, method_name: str, *, purpose: str):
        method = getattr(self.reqer, method_name, None)
        if callable(method):
            return method
        raise RuntimeError(f"{self.provider_cls.__name__} reqer.{method_name}() is required for {purpose}")

    def resolve_domain(self):
        return self._require_runtime_domain()

    def close(self):
        seen = set()
        for owner in (self.provider, self.reqer):
            cli = getattr(owner, "cli", None)
            close = getattr(cli, "close", None)
            if cli is None or not callable(close) or id(cli) in seen:
                continue
            close()
            seen.add(id(cli))


class SpiderSiteRuntime(_ProviderRuntimeBase):
    pass


class ThreadSiteRuntime(_ProviderRuntimeBase):
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
        self._bind_preview_state(preview_client=preview_client)

    def _bind_preview_state(self, *, preview_client: httpx.AsyncClient | None = None):
        if self.site_config.domain:
            self.provider.domain = self.site_config.domain
        self.provider.site_config = self.site_config
        if self.site_config.cookies:
            self.provider.cookies = copy.deepcopy(self.site_config.cookies)
        if self.site_config.custom_map:
            self.provider.custom_map = copy.deepcopy(self.site_config.custom_map)
        self.reqer.preview_client = preview_client
        bind_preview_runtime = self._require_reqer_method("bind_preview_runtime", purpose="preview runtime binding")
        self._require_reqer_method("aclose_preview_client", purpose="preview runtime cleanup")
        bind_preview_runtime(owner=self.provider, site_config=self.site_config, preview_client=preview_client)
        if preview_client is None:
            ensure_preview_client = self._require_reqer_method("ensure_preview_client", purpose="preview runtime client bootstrap")
            ensure_preview_client()

    def preview_batch_limit(self, stage: str, default: int) -> int:
        return self.provider_descriptor.preview_batch_limit(stage, default)

    async def preview_search(self, keyword: str, *, page: int = 1) -> list:
        preview_search = self._require_reqer_method("preview_search", purpose="preview worker search")
        return await preview_search(keyword, page=page)

    async def preview_fetch_episodes(self, book) -> list:
        preview_fetch_episodes = self._require_reqer_method("preview_fetch_episodes", purpose="preview episode fetch")
        return await preview_fetch_episodes(book)

    async def preview_fetch_pages(self, item) -> list:
        preview_fetch_pages = self._require_reqer_method("preview_fetch_pages", purpose="preview page fetch")
        return await preview_fetch_pages(item)

    async def download_cover_bytes(self, tasks_obj, *, browser_headers: dict[str, str] | None = None) -> bytes:
        download_cover_bytes = self._require_reqer_method("download_cover_bytes", purpose="task-panel cover preload")
        return await download_cover_bytes(tasks_obj, browser_headers=browser_headers)

    async def aclose(self):
        await self.reqer.aclose_preview_client()
        super().close()

    def close(self):
        if self.reqer.preview_client is not None:
            try:
                asyncio.run(self.aclose())
            except RuntimeError as exc:
                raise RuntimeError("ThreadSiteRuntime with preview_client must be closed via await aclose() inside an active event loop") from exc
            return
        super().close()


@dataclass(slots=True)
class GuiSiteRuntime:
    provider_descriptor: ProviderDescriptor
    site_index: int
    runtime_context: PreviewRuntimeContext
    conf_state: t.Any = field(default_factory=lambda: conf)

    @classmethod
    def create(
        cls, provider_descriptor: ProviderDescriptor, *, site_index: int, conf_state=conf,
        default_doh_url: str | None = None,
    ) -> "GuiSiteRuntime":
        runtime_context = PreviewRuntimeContext.from_conf_state(conf_state=conf_state, default_doh_url=default_doh_url)
        cookies_by_site = {}
        cookies_owner = getattr(conf_state, "cookies", None)
        if cookies_owner is not None:
            if isinstance(cookies_owner, dict):
                site_cookies = cookies_owner.get(provider_descriptor.provider_name)
            else:
                get_site_cookies = getattr(cookies_owner, "get", None)
                site_cookies = get_site_cookies(provider_descriptor.provider_name) if callable(get_site_cookies) else None
            if site_cookies:
                cookies_by_site[provider_descriptor.provider_name] = copy.deepcopy(dict(site_cookies))
        domains = {}
        if domain := cls._peek_cached_domain_for(provider_descriptor):
            domains[provider_descriptor.provider_name] = domain
        runtime_context = replace(runtime_context, cookies_by_site=cookies_by_site, domains=domains)
        return cls(
            provider_descriptor=provider_descriptor,
            site_index=site_index,
            runtime_context=runtime_context,
            conf_state=conf_state,
        )

    @property
    def provider_cls(self):
        return self.provider_descriptor.provider_cls

    @property
    def name(self) -> str:
        return self.provider_descriptor.provider_name

    def _uses_dynamic_domain(self) -> bool:
        return issubclass(self.provider_cls, DomainUtils)

    def _cached_domain(self) -> str | None:
        if not self._uses_dynamic_domain():
            return None
        return _normalize_domain_value(self.provider_cls.peek_cached_domain())

    def _static_domain(self) -> str | None:
        return _normalize_domain_value(getattr(self.provider_cls, "domain", None))

    def _resolved_gui_domain(self) -> str | None:
        return _pick_bound_domain(self.runtime_context.site_domain(self.name), self._cached_domain(), self._static_domain())

    def _require_bound_gui_domain(self) -> str:
        domain = self._resolved_gui_domain()
        if domain is None:
            raise RuntimeError(
                f"{self.provider_cls.__name__} gui runtime requires a bound domain in runtime_context, cache, "
                "or static provider config"
            )
        return domain

    def get_domain(self) -> str | None:
        if domain := _normalize_domain_value(self.runtime_context.site_domain(self.name)):
            return domain
        if self._uses_dynamic_domain():
            return _normalize_domain_value(self.provider_cls.get_domain())
        return self._static_domain()

    def domain_cache_path(self):
        return temp_p.joinpath(f"{self.name}_domain.txt")

    def build_site_config(self) -> PreviewSiteConfig:
        return PreviewSiteConfig(
            cookies=self.runtime_context.site_cookies(self.name),
            domain=self._require_bound_gui_domain(),
            custom_map=copy.deepcopy(self.runtime_context.custom_map),
            transport=self.runtime_context.transport,
        )

    def build_cover_headers(self, tasks_obj) -> dict[str, str]:
        site_config = self.build_site_config()
        client_config = dict(self.provider_cls.preview_client_config(**site_config.as_provider_kwargs()) or {})
        headers = dict(client_config.get("headers", {}) or {})
        referer = self.provider_cls.build_referer_url(
            getattr(tasks_obj, "title_url", None),
            request_url=getattr(tasks_obj, "cover_url", None),
        )
        if referer:
            headers = {k: v for k, v in headers.items() if k.casefold() != "referer"}
            headers["Referer"] = referer
        return headers

    def create_thread_site_runtime(self, *, preview_client: httpx.AsyncClient | None = None) -> ThreadSiteRuntime:
        return ThreadSiteRuntime(
            self.provider_descriptor,
            site_config=self.build_site_config(),
            conf_state=self.conf_state,
            preview_client=preview_client,
        )

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

    def persist_domain(self, domain: str) -> "GuiSiteRuntime":
        normalized = _normalize_domain_value(domain)
        if not normalized:
            raise ValueError(f"{self.provider_cls.__name__} domain cache requires a non-empty domain")
        self.domain_cache_path().write_text(normalized, encoding="utf-8")
        return self.with_domain(normalized)

    def preprocess(self, *, conf_state=conf, data_client=None, progress_callback=None) -> PreprocessResult:
        return run_site_preprocess(
            self.site_index, gui_site_runtime=self, conf_state=conf_state, data_client=data_client, progress_callback=progress_callback
        )

    def build_browser_environment(self, *, lang: str, cn_proxy_indexes: t.Container[int]) -> BrowserEnvironmentPayload:
        def _browser_domain_required() -> bool:
            referer_mode = getattr(self.provider_cls, "browser_referer_mode", None)
            return referer_mode in {"domain_origin", "domain_origin_slash"} or bool(
                getattr(self.provider_cls, "browser_cookie_set_enabled", False)
            )
        def _require_browser_domain() -> str:
            domain = self._resolved_gui_domain()
            if domain is None:
                raise RuntimeError(
                    f"{self.provider_cls.__name__} browser environment requires a bound domain in runtime_context, cache, "
                    "or static provider config"
                )
            return domain
        site_config = self.build_site_config()
        proxy_value = (site_config.transport.proxies or (None,))[0]
        proxy = proxy_value if lang != "zh-CN" or self.site_index in cn_proxy_indexes else None
        domain = None
        if _browser_domain_required():
            domain = _require_browser_domain()
        referer_url = self.provider_cls.build_browser_referer_url(domain=domain)
        cookie_sets = self.provider_cls.build_browser_cookie_sets(cookies=site_config.cookies, domain=domain, referer_url=referer_url)
        return BrowserEnvironmentPayload(
            proxy=proxy, doh_url=site_config.transport.doh_url, referer_url=referer_url, cookie_sets=cookie_sets,
        )

    def peek_cached_domain(self) -> str | None:
        return self._cached_domain()

    @staticmethod
    def _peek_cached_domain_for(provider_descriptor: ProviderDescriptor) -> str | None:
        if not issubclass(provider_descriptor.provider_cls, DomainUtils):
            return None
        cache_path = temp_p.joinpath(f"{provider_descriptor.provider_name}_domain.txt")
        if cache_path.exists():
            cached_text = cache_path.read_text(encoding="utf-8").strip()
            if cached_text:
                return cached_text
        return None
