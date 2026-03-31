from __future__ import annotations

import copy
from dataclasses import dataclass
import typing as t

from utils import conf
from utils.config.qc import cgs_cfg

@dataclass(frozen=True, slots=True)
class PreviewTransportConfig:
    proxies: tuple[str, ...] = ()
    doh_url: str = ""

    @classmethod
    def create(
        cls,
        *,
        proxies: t.Iterable[str] | None = None,
        doh_url: str = "",
    ) -> "PreviewTransportConfig":
        return cls(
            proxies=tuple(proxies or ()),
            doh_url=str(doh_url or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class PreviewRuntimeContext:
    cookies_by_site: dict[str, dict[str, str]]
    domains: dict[str, str]
    custom_map: dict[str, t.Any]
    transport: PreviewTransportConfig

    @classmethod
    def from_snapshot(
        cls,
        snapshot,
        *,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> "PreviewRuntimeContext":
        fallback_doh = (
            default_doh_url
            if default_doh_url is not None
            else getattr(conf_state, "doh_url", "") or cgs_cfg.get_doh_url()
        )
        if snapshot is None:
            return cls(
                cookies_by_site=copy.deepcopy(dict(getattr(conf_state, "cookies", None) or {})),
                domains=copy.deepcopy(dict(getattr(conf_state, "domains", None) or {})),
                custom_map=copy.deepcopy(dict(getattr(conf_state, "custom_map", None) or {})),
                transport=PreviewTransportConfig.create(
                    proxies=getattr(conf_state, "proxies", None),
                    doh_url=fallback_doh,
                ),
            )
        return cls(
            cookies_by_site=copy.deepcopy(dict(getattr(snapshot, "cookies", None) or {})),
            domains=copy.deepcopy(dict(getattr(snapshot, "domains", None) or {})),
            custom_map=copy.deepcopy(dict(getattr(snapshot, "custom_map", None) or {})),
            transport=PreviewTransportConfig.create(
                proxies=getattr(snapshot, "proxies", None) or getattr(conf_state, "proxies", None),
                doh_url=getattr(snapshot, "doh_url", "") or fallback_doh,
            ),
        )

    @staticmethod
    def _provider_key(provider_name: str) -> str:
        provider_key = str(provider_name or "").strip()
        if not provider_key:
            raise ValueError("provider_name is required")
        return provider_key

    def site_cookies(self, provider_name: str) -> dict[str, str]:
        return copy.deepcopy(dict(self.cookies_by_site.get(self._provider_key(provider_name)) or {}))

    def site_domain(self, provider_name: str) -> str | None:
        domain = self.domains.get(self._provider_key(provider_name))
        return str(domain).strip() if domain else None


@dataclass(frozen=True, slots=True)
class PreviewSiteConfig:
    cookies: dict[str, str]
    domain: str | None
    custom_map: dict[str, t.Any]
    transport: PreviewTransportConfig

    @classmethod
    def create(
        cls,
        provider_name: str,
        *,
        cookies_by_site: t.Mapping[str, t.Mapping[str, str]] | None = None,
        domains: t.Mapping[str, str] | None = None,
        custom_map: t.Mapping[str, t.Any] | None = None,
        proxies: t.Iterable[str] | None = None,
        doh_url: str = "",
    ) -> "PreviewSiteConfig":
        provider_key = str(provider_name or "").strip()
        if not provider_key:
            raise ValueError("provider_name is required")
        site_cookies = (cookies_by_site or {}).get(provider_key)
        site_domain = (domains or {}).get(provider_key)
        return cls(
            cookies=copy.deepcopy(dict(site_cookies or {})),
            domain=str(site_domain).strip() if site_domain else None,
            custom_map=copy.deepcopy(dict(custom_map or {})),
            transport=PreviewTransportConfig.create(
                proxies=proxies,
                doh_url=doh_url,
            ),
        )

    def as_provider_kwargs(self) -> dict[str, t.Any]:
        kwargs = {}
        if self.cookies:
            kwargs["cookies"] = copy.deepcopy(self.cookies)
        if self.domain:
            kwargs["domain"] = self.domain
        if self.custom_map:
            kwargs["custom_map"] = copy.deepcopy(self.custom_map)
        return kwargs

    @classmethod
    def from_snapshot(
        cls,
        provider_name: str,
        snapshot,
        *,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> "PreviewSiteConfig":
        runtime_context = PreviewRuntimeContext.from_snapshot(
            snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )
        return cls(
            cookies=runtime_context.site_cookies(provider_name),
            domain=runtime_context.site_domain(provider_name),
            custom_map=copy.deepcopy(runtime_context.custom_map),
            transport=runtime_context.transport,
        )
