from __future__ import annotations

from assets import res
from utils import temp_p
from utils.website.runtime_context import PreviewRuntimeContext
from utils.website.registry import resolve_site_gateway
from variables import Spider

from .types import BrowserCookieSet, BrowserEnvironmentConfig


def build_browser_environment(browser) -> BrowserEnvironmentConfig:
    gui = browser.gui
    snapshot = gui.search_context
    runtime_context = PreviewRuntimeContext.from_snapshot(snapshot)
    site_index = snapshot.site_index if snapshot is not None else gui.chooseBox.currentIndex()
    gateway = resolve_site_gateway(site_index)
    env = gateway.build_browser_environment(
        runtime_context,
        site_index=site_index,
        lang=res.lang,
        cn_proxy_indexes=Spider.cn_proxy(),
    )

    return BrowserEnvironmentConfig(
        proxy=env.proxy,
        referer_url=env.referer_url,
        cookie_sets=tuple(
            BrowserCookieSet(values=item.values, domain=item.domain, url=item.url)
            for item in env.cookie_sets
        ),
    )


def peek_snapshot_domain(site_utils) -> str | None:
    if hasattr(site_utils, "peek_snapshot_domain"):
        return site_utils.peek_snapshot_domain()
    cachef = getattr(site_utils, "cachef", None)
    cached = getattr(cachef, "val", None) if cachef else None
    if isinstance(cached, str) and cached.strip():
        return cached.strip()

    cache_name = getattr(site_utils, "name", "")
    if cache_name:
        cache_path = temp_p.joinpath(f"{cache_name}_domain.txt")
        if cache_path.exists():
            if cached := cache_path.read_text(encoding="utf-8").strip():
                return cached

    fallback = (
        site_utils._fallback_domain()
        if hasattr(site_utils, "_fallback_domain")
        else getattr(site_utils, "domain", None)
    )
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return None
