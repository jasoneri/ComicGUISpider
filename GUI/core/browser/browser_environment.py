from __future__ import annotations

from assets import res
from utils import temp_p
from variables import Spider

from .types import BrowserCookieSet, BrowserEnvironmentConfig


def build_browser_environment(browser) -> BrowserEnvironmentConfig:
    gui = browser.gui
    gui_site_runtime = gui.gui_site_runtime
    if gui_site_runtime is None:
        raise RuntimeError("gui_site_runtime unavailable for browser environment")
    env = gui_site_runtime.build_browser_environment(
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
