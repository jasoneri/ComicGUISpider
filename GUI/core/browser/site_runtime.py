from __future__ import annotations

from assets import res
from utils import conf, temp_p
from utils.website import EHentaiKits, spider_utils_map
from variables import Spider

from .types import BrowserCookieSet, BrowserEnvironmentConfig


def build_browser_environment(browser) -> BrowserEnvironmentConfig:
    gui = browser.gui
    snapshot = gui.search_context
    site_index = snapshot.site_index if snapshot is not None else gui.chooseBox.currentIndex()
    conf_proxy = (
        (snapshot.proxies or [None])[0]
        if snapshot is not None else (conf.proxies or [None])[0]
    )
    proxy = conf_proxy if res.lang != "zh-CN" or site_index in Spider.cn_proxy() else None
    cookie_sets: list[BrowserCookieSet] = []
    referer_url = None

    if site_index == Spider.JM:
        domain = _resolve_site_domain(site_index, "jm", snapshot)
        referer_url = f"https://{domain}"
        cookies = snapshot.cookies.get("jm", {}) if snapshot is not None else conf.cookies.get("jm", {})
        if cookies:
            cookie_sets.append(BrowserCookieSet(values=dict(cookies), domain=domain, url=referer_url))
    elif site_index == Spider.WNACG:
        referer_url = f"https://{_resolve_site_domain(site_index, 'wnacg', snapshot)}"
    elif site_index == Spider.EHENTAI:
        cookies = snapshot.cookies.get("ehentai", {}) if snapshot is not None else conf.cookies.get("ehentai", {})
        if cookies:
            domain = (snapshot.domains.get("ehentai") if snapshot is not None else None) or EHentaiKits.domain
            cookie_sets.append(BrowserCookieSet(values=dict(cookies), domain=domain, url=f"https://{domain}/"))
    elif site_index == Spider.HITOMI:
        site_cls = spider_utils_map.get(site_index)
        if site_cls is None or not getattr(site_cls, "index", None):
            raise ValueError("hitomi site index unavailable")
        referer_url = str(site_cls.index)

    return BrowserEnvironmentConfig(
        proxy=proxy,
        referer_url=referer_url,
        cookie_sets=tuple(cookie_sets),
    )


def _resolve_site_domain(site_index: int, snapshot_key: str, snapshot) -> str:
    domain = snapshot.domains.get(snapshot_key) if snapshot is not None else None
    if domain:
        return str(domain).strip().rstrip("/")
    site_cls = spider_utils_map.get(site_index)
    if site_cls is None:
        raise ValueError(f"site utils unavailable for {snapshot_key}")
    domain = peek_snapshot_domain(site_cls)
    if not domain and hasattr(site_cls, "get_domain"):
        domain = site_cls.get_domain()
    if not domain:
        domain = getattr(site_cls, "domain", None)
    if not domain:
        raise ValueError(f"{snapshot_key} site domain unavailable")
    return str(domain).strip().rstrip("/")


def peek_snapshot_domain(site_utils) -> str | None:
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

    fallback = site_utils._fallback_domain() if hasattr(site_utils, "_fallback_domain") else getattr(site_utils, "domain", None)
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return None
