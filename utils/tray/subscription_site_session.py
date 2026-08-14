# -*- coding: utf-8 -*-
"""Per-site preview runtime session for subscription tray runs.

Patterns:
- Chain of Responsibility: domain sources tried in order until one binds
- Async context manager: open ThreadSiteRuntime + httpx client, always aclose
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional, Protocol

from utils import conf
from utils.config.qc import cgs_cfg
from utils.subscription.site_proxy import effective_proxies, resolve_provider_proxy_policy
from utils.website.registry import resolve_provider_descriptor_by_site
from utils.website.runtime_context import PreviewSiteConfig
from utils.website.site_runtime import ThreadSiteRuntime


class DomainSource(Protocol):
    """One link in the domain-resolution chain."""

    async def resolve(self, provider_name: str, provider_cls: Any) -> Optional[str]:
        ...


class PeekCachedDomainSource:
    async def resolve(self, provider_name: str, provider_cls: Any) -> Optional[str]:
        if provider_cls is None:
            return None
        peek = getattr(provider_cls, "peek_cached_domain", None)
        if not callable(peek):
            return None
        try:
            cached = peek()
        except Exception:
            return None
        value = str(cached or "").strip()
        return value or None


class GetDomainSource:
    async def resolve(self, provider_name: str, provider_cls: Any) -> Optional[str]:
        if provider_cls is None:
            return None
        get_domain = getattr(provider_cls, "get_domain", None)
        if not callable(get_domain):
            return None
        try:
            cached = await asyncio.to_thread(get_domain)
        except Exception:
            return None
        value = str(cached or "").strip()
        return value or None


class StaticDomainSource:
    async def resolve(self, provider_name: str, provider_cls: Any) -> Optional[str]:
        if provider_cls is None:
            return None
        value = str(getattr(provider_cls, "domain", None) or "").strip()
        return value or None


class DomainBinder:
    """Fallback chain when conf.domains lacks the provider: peek → get_domain → static."""

    def __init__(self, sources: list[DomainSource] | None = None) -> None:
        self._sources = list(sources) if sources is not None else []

    @classmethod
    def default(cls) -> DomainBinder:
        # conf.domains is applied by the caller before bind; chain is fallback only.
        return cls(
            [
                PeekCachedDomainSource(),
                GetDomainSource(),
                StaticDomainSource(),
            ]
        )

    async def bind(self, domains: dict, provider_name: str, provider_cls: Any) -> dict:
        bound = dict(domains)
        if str(bound.get(provider_name) or "").strip():
            return bound
        for source in self._sources:
            value = await source.resolve(provider_name, provider_cls)
            if value:
                bound[provider_name] = value
                break
        return bound


class SiteRuntimeSession:
    """Async CM: build PreviewSiteConfig + ThreadSiteRuntime for one site_key."""

    def __init__(self, site_key: str, *, site_proxy: Optional[dict] = None) -> None:
        self.site_key = str(site_key or "").strip()
        self.site_proxy = dict(site_proxy or {})
        self.runtime: Optional[ThreadSiteRuntime] = None

    async def __aenter__(self) -> ThreadSiteRuntime:
        descriptor = resolve_provider_descriptor_by_site(self.site_key)
        provider_name = str(descriptor.provider_name or self.site_key).strip()
        provider_cls = getattr(descriptor, "provider_cls", None)
        domains = dict(getattr(conf, "domains", None) or {})
        # JM (and similar) need a bound preview domain before ThreadSiteRuntime builds
        # the httpx client. Prefer conf.domains, then provider domain cache / get_domain.
        domains = await DomainBinder.default().bind(domains, provider_name, provider_cls)
        proxy_policy = resolve_provider_proxy_policy(self.site_key)
        session_proxies = effective_proxies(
            self.site_key,
            site_proxy=self.site_proxy,
            conf_proxies=getattr(conf, "proxies", None),
            proxy_policy=proxy_policy,
        )
        site_config = PreviewSiteConfig.create(
            provider_name,
            cookies_by_site=conf.cookies,
            domains=domains,
            custom_map=conf.custom_map,
            proxies=session_proxies,
            doh_url=cgs_cfg.doh.get_url(),
        )
        self.runtime = ThreadSiteRuntime(descriptor, site_config=site_config, conf_state=conf)
        self.runtime.get_async_preview_client()
        return self.runtime

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.runtime is not None:
            await self.runtime.aclose()
            self.runtime = None
