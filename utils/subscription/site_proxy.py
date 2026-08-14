# -*- coding: utf-8 -*-
"""Per-profile site_proxy flags + conf.proxies address SSoT."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Optional

_SOURCE_ALIASES = {
    "kaobei": "manga_copy",
    "manga-copy": "manga_copy",
    "copymanga": "manga_copy",
}


class SiteProxyMap:
    """Normalized site_key -> bool owner for subscription binding."""

    def __init__(self, flags: Mapping[str, bool] | None = None) -> None:
        self._flags = self._normalize(flags)

    @classmethod
    def from_mapping(cls, raw: Mapping | None) -> "SiteProxyMap":
        return cls(raw)

    def as_dict(self) -> dict[str, bool]:
        return dict(self._flags)

    def is_enabled(self, site_key: str, *, proxy_policy: str | None) -> bool:
        policy = self._policy(proxy_policy)
        if policy == "direct":
            return False
        key = self.normalize_key(site_key)
        if not key:
            return self.default_enabled(policy)
        if key in self._flags:
            return bool(self._flags[key])
        return self.default_enabled(policy)

    def effective_proxies(
        self,
        site_key: str,
        *,
        conf_proxies: Iterable[str] | None,
        proxy_policy: str | None,
    ) -> list[str]:
        policy = self._policy(proxy_policy)
        if policy == "direct" or not self.is_enabled(site_key, proxy_policy=policy):
            return []
        return [str(item).strip() for item in (conf_proxies or ()) if str(item).strip()]

    @staticmethod
    def normalize_key(site_key: str | None) -> str:
        text = str(site_key or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        return _SOURCE_ALIASES.get(lowered, lowered)

    @staticmethod
    def default_enabled(proxy_policy: str | None) -> bool:
        return SiteProxyMap._policy(proxy_policy) != "direct"

    @staticmethod
    def resolve_provider_policy(site_key: str) -> str:
        key = SiteProxyMap.normalize_key(site_key)
        if not key:
            return "proxy"
        try:
            from utils.website.registry import (
                resolve_provider_descriptor_by_site,
                resolve_provider_descriptor_by_spider,
            )
        except Exception:
            return "proxy"
        descriptor = None
        try:
            descriptor = resolve_provider_descriptor_by_spider(key)
        except Exception:
            descriptor = None
        if descriptor is None:
            try:
                descriptor = resolve_provider_descriptor_by_site(key)
            except Exception:
                descriptor = None
        if descriptor is None:
            return "proxy"
        provider_cls = getattr(descriptor, "provider_cls", None)
        policy = getattr(provider_cls, "proxy_policy", None) if provider_cls is not None else None
        text = str(policy or "proxy").strip().lower() or "proxy"
        return text if text in {"direct", "proxy"} else "proxy"

    @staticmethod
    def _policy(proxy_policy: str | None) -> str:
        return str(proxy_policy or "proxy").strip().lower() or "proxy"

    @classmethod
    def _normalize(cls, raw: Mapping | None) -> dict[str, bool]:
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ValueError(f"site_proxy must be a mapping, got {type(raw).__name__}")
        out: dict[str, bool] = {}
        for raw_key, raw_value in raw.items():
            key = cls.normalize_key(str(raw_key))
            if key:
                out[key] = bool(raw_value)
        return out


def normalize_site_proxy_key(site_key: str | None) -> str:
    return SiteProxyMap.normalize_key(site_key)


def default_site_proxy_enabled(proxy_policy: str | None) -> bool:
    return SiteProxyMap.default_enabled(proxy_policy)


def site_proxy_enabled(
    site_key: str,
    site_proxy: Mapping[str, bool] | None,
    *,
    proxy_policy: str | None,
) -> bool:
    return SiteProxyMap.from_mapping(site_proxy).is_enabled(site_key, proxy_policy=proxy_policy)


def effective_proxies(
    site_key: str,
    *,
    site_proxy: Mapping[str, bool] | None,
    conf_proxies: Iterable[str] | None,
    proxy_policy: str | None,
) -> list[str]:
    return SiteProxyMap.from_mapping(site_proxy).effective_proxies(
        site_key,
        conf_proxies=conf_proxies,
        proxy_policy=proxy_policy,
    )


def resolve_provider_proxy_policy(site_key: str) -> str:
    return SiteProxyMap.resolve_provider_policy(site_key)


def normalize_site_proxy_map(raw: Mapping | None) -> dict[str, bool]:
    return SiteProxyMap.from_mapping(raw).as_dict()


def effective_proxies_for_site(
    site_key: str,
    *,
    site_proxy: Mapping[str, bool] | None = None,
    conf_proxies: Iterable[str] | None = None,
    proxy_policy: Optional[str] = None,
) -> list[str]:
    policy = proxy_policy if proxy_policy is not None else resolve_provider_proxy_policy(site_key)
    return effective_proxies(
        site_key,
        site_proxy=site_proxy,
        conf_proxies=conf_proxies,
        proxy_policy=policy,
    )
