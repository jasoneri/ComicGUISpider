from __future__ import annotations

from assets import res
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
        doh_url=env.doh_url,
        referer_url=env.referer_url,
        cookie_sets=tuple(
            BrowserCookieSet(values=item.values, domain=item.domain, url=item.url)
            for item in env.cookie_sets
        ),
    )
