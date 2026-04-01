from __future__ import annotations

import typing as t

import httpx

from utils import conf, get_httpx_verify, temp_p
from utils.network.doh import build_http_transport
from variables import Spider

from .contracts import BrowserCookiePayload, BrowserEnvironmentPayload, PreprocessResult
from .core import Previewer
from .preprocess import run_site_preprocess
from .runtime_context import PreviewRuntimeContext, PreviewSiteConfig


class ProviderSiteGateway:
    BROWSER_IMAGE_ACCEPT = (
        "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5"
    )

    def __init__(self, provider_cls):
        self.provider_cls = provider_cls

    def __call__(self, conf_state=conf):
        return self.create_runtime(conf_state)

    @property
    def name(self) -> str:
        return getattr(self.provider_cls, "name", "")

    @property
    def index(self):
        return getattr(self.provider_cls, "index", None)

    @property
    def publish_url(self) -> str:
        return getattr(self.provider_cls, "publish_url", "")

    @property
    def book_url_regex(self) -> str:
        return getattr(self.provider_cls, "book_url_regex", "")

    @property
    def reqer_cls(self):
        return getattr(self.provider_cls, "reqer_cls", None)

    @property
    def cachef(self):
        return getattr(self.provider_cls, "cachef", None)

    @property
    def domain(self):
        return getattr(self.provider_cls, "domain", None)

    @property
    def test_nozomi(self):
        return getattr(self.provider_cls, "test_nozomi", None)

    @property
    def cover_preload_via_http(self) -> bool:
        return bool(getattr(self.provider_cls, "cover_preload_via_http", True))

    @property
    def supports_test_index(self) -> bool:
        reqer_cls = self.reqer_cls
        return bool(
            hasattr(reqer_cls, "test_index")
            or hasattr(self.provider_cls, "test_index")
        )

    def cache_path(self):
        return temp_p.joinpath(f"{self.name}_domain.txt")

    def create_runtime(self, conf_state=conf):
        return self.provider_cls(conf_state)

    def get_domain(self):
        if hasattr(self.provider_cls, "get_domain"):
            return self.provider_cls.get_domain()
        return getattr(self.provider_cls, "domain", None)

    def test_index(self, conf_state=conf):
        runtime = self.create_runtime(conf_state)
        reqer = getattr(runtime, "reqer", runtime)
        if hasattr(reqer, "test_index"):
            return reqer.test_index()
        if hasattr(self.provider_cls, "test_index"):
            return self.provider_cls.test_index()
        raise AttributeError(f"{self.provider_cls.__name__} does not support test_index")

    def preprocess(
        self,
        site_key: int,
        *,
        conf_state=conf,
        data_client=None,
        progress_callback=None,
    ) -> PreprocessResult:
        return run_site_preprocess(
            site_key,
            gateway=self,
            conf_state=conf_state,
            data_client=data_client,
            progress_callback=progress_callback,
        )

    async def test_aviable_domain(self, domain):
        return await self.provider_cls.test_aviable_domain(domain)

    def build_site_config_from_snapshot(
        self,
        snapshot,
        *,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> PreviewSiteConfig:
        return PreviewSiteConfig.from_snapshot(
            self.name,
            snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )

    def build_site_config_from_conf(
        self,
        *,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> PreviewSiteConfig:
        return PreviewSiteConfig.create(
            self.name,
            cookies_by_site=conf_state.cookies,
            domains=getattr(conf_state, "domains", None),
            custom_map=conf_state.custom_map,
            proxies=conf_state.proxies,
            doh_url=default_doh_url or getattr(conf_state, "doh_url", ""),
        )

    def _ensure_preview_support(self):
        if not issubclass(self.provider_cls, Previewer):
            raise TypeError(f"{self.provider_cls.__name__} does not support preview search")

    def _preview_client_parts(self, site_config: PreviewSiteConfig):
        self._ensure_preview_support()
        site_kw = site_config.as_provider_kwargs()
        client_kw = dict(self.provider_cls.preview_client_config(**site_kw) or {})
        transport_kw = dict(self.provider_cls.preview_transport_config() or {})
        policy = getattr(self.provider_cls, "proxy_policy", "proxy")
        return site_kw, client_kw, transport_kw, policy

    def create_async_preview_client(
        self,
        *,
        snapshot=None,
        site_config: PreviewSiteConfig | None = None,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> httpx.AsyncClient:
        site_config = site_config or self.build_site_config_from_snapshot(
            snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )
        _site_kw, client_kw, transport_kw, policy = self._preview_client_parts(site_config)
        transport, trust_env = build_http_transport(
            policy,
            list(site_config.transport.proxies),
            doh_url=site_config.transport.doh_url,
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

    async def preview_search(
        self,
        keyword: str,
        client,
        *,
        page: int = 1,
        snapshot=None,
        site_config: PreviewSiteConfig | None = None,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> list:
        site_config = site_config or self.build_site_config_from_snapshot(
            snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )
        return await self.provider_cls.preview_search(
            keyword,
            client,
            page=page,
            **site_config.as_provider_kwargs(),
        )

    async def preview_fetch_episodes(
        self,
        book,
        client,
        *,
        snapshot=None,
        site_config: PreviewSiteConfig | None = None,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> list:
        site_config = site_config or self.build_site_config_from_snapshot(
            snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )
        return await self.provider_cls.preview_fetch_episodes(
            book,
            client,
            **site_config.as_provider_kwargs(),
        )

    async def preview_fetch_pages(
        self,
        episode,
        client,
        *,
        snapshot=None,
        site_config: PreviewSiteConfig | None = None,
        conf_state=conf,
        default_doh_url: str | None = None,
    ) -> list:
        site_config = site_config or self.build_site_config_from_snapshot(
            snapshot,
            conf_state=conf_state,
            default_doh_url=default_doh_url,
        )
        return await self.provider_cls.preview_fetch_pages(
            episode,
            client,
            **site_config.as_provider_kwargs(),
        )

    def download_cover_bytes(
        self,
        tasks_obj,
        *,
        snapshot,
        browser_headers: dict[str, str] | None = None,
        conf_state=conf,
    ) -> bytes:
        site_config = self.build_site_config_from_snapshot(snapshot, conf_state=conf_state)
        site_kw, client_kw, transport_kw, policy = self._preview_client_parts(site_config)
        provider_headers = dict(client_kw.pop("headers", {}) or {})
        transport_verify = transport_kw.pop("verify", get_httpx_verify())
        transport, trust_env = build_http_transport(
            policy,
            list(site_config.transport.proxies),
            doh_url=site_config.transport.doh_url,
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

    def build_browser_environment(
        self,
        runtime_context: PreviewRuntimeContext,
        *,
        site_index: int,
        lang: str,
        cn_proxy_indexes: t.Container[int],
    ) -> BrowserEnvironmentPayload:
        proxy_value = (runtime_context.transport.proxies or (None,))[0]
        proxy = proxy_value if lang != "zh-CN" or site_index in cn_proxy_indexes else None
        cookie_sets: list[BrowserCookiePayload] = []
        referer_url = None

        if site_index == Spider.JM:
            domain = self._resolve_snapshot_domain(runtime_context, "jm")
            referer_url = f"https://{domain}"
            if cookies := runtime_context.site_cookies("jm"):
                cookie_sets.append(
                    BrowserCookiePayload(values=cookies, domain=domain, url=referer_url)
                )
        elif site_index == Spider.WNACG:
            referer_url = f"https://{self._resolve_snapshot_domain(runtime_context, 'wnacg')}"
        elif site_index == Spider.EHENTAI:
            if cookies := runtime_context.site_cookies("ehentai"):
                domain = runtime_context.site_domain("ehentai") or self.domain
                cookie_sets.append(
                    BrowserCookiePayload(values=cookies, domain=domain, url=f"https://{domain}/")
                )
        elif site_index == Spider.HITOMI:
            referer_url = str(getattr(self.provider_cls, "index", ""))
            if not referer_url:
                raise ValueError("hitomi site index unavailable")

        return BrowserEnvironmentPayload(
            proxy=proxy,
            referer_url=referer_url,
            cookie_sets=tuple(cookie_sets),
        )

    def _resolve_snapshot_domain(
        self,
        runtime_context: PreviewRuntimeContext,
        snapshot_key: str,
    ) -> str:
        if domain := runtime_context.site_domain(snapshot_key):
            return domain.rstrip("/")
        if domain := self.peek_snapshot_domain():
            return domain.rstrip("/")
        if hasattr(self.provider_cls, "get_domain"):
            domain = self.provider_cls.get_domain()
        else:
            domain = getattr(self.provider_cls, "domain", None)
        if not domain:
            raise ValueError(f"{snapshot_key} site domain unavailable")
        return str(domain).strip().rstrip("/")

    def peek_snapshot_domain(self) -> str | None:
        cachef = getattr(self.provider_cls, "cachef", None)
        cached = getattr(cachef, "val", None) if cachef else None
        if isinstance(cached, str) and cached.strip():
            return cached.strip()

        cache_path = self.cache_path()
        if cache_path.exists():
            cached_text = cache_path.read_text(encoding="utf-8").strip()
            if cached_text:
                return cached_text

        if hasattr(self.provider_cls, "_fallback_domain"):
            fallback = self.provider_cls._fallback_domain()
        else:
            fallback = getattr(self.provider_cls, "domain", None)
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return None
