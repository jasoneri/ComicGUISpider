from __future__ import annotations

from GUI.types import SearchContextSnapshot
from assets import res
from utils import conf, temp_p
from utils.website import EHentaiKits, spider_utils_map
from variables import Spider

from .types import BrowserCookieSet, BrowserEnvironmentConfig


def build_browser_environment(gui, snapshot: SearchContextSnapshot | None) -> BrowserEnvironmentConfig:
    site_index = snapshot.site_index if snapshot is not None else gui.chooseBox.currentIndex()
    proxy = _resolve_proxy(site_index, snapshot)
    cookie_sets: list[BrowserCookieSet] = []
    referer_url = ""

    if site_index == Spider.JM:
        if cookie_set := _resolve_jm_cookie_set(site_index, snapshot):
            cookie_sets.append(cookie_set)
    elif site_index == Spider.EHENTAI:
        if cookie_set := _resolve_ehentai_cookie_set(snapshot):
            cookie_sets.append(cookie_set)
    elif site_index == Spider.HITOMI:
        referer_url = _resolve_hitomi_referer(site_index)

    return BrowserEnvironmentConfig(
        proxy=proxy,
        referer_url=referer_url or None,
        cookie_sets=tuple(cookie_sets),
    )


def _resolve_proxy(site_index: int, snapshot: SearchContextSnapshot | None) -> str | None:
    conf_proxy = (
        (snapshot.proxies or [None])[0]
        if snapshot is not None else (conf.proxies or [None])[0]
    )
    if res.lang == "zh-CN":
        return conf_proxy if site_index in Spider.cn_proxy() else None
    return conf_proxy or None


def _resolve_ehentai_cookie_set(snapshot: SearchContextSnapshot | None) -> BrowserCookieSet | None:
    cookies = (
        snapshot.cookies.get("ehentai", {})
        if snapshot is not None else conf.cookies.get("ehentai", {})
    )
    if not cookies:
        return None
    domain = (snapshot.domains.get("ehentai") if snapshot is not None else None) or EHentaiKits.domain
    return BrowserCookieSet(values=dict(cookies), domain=domain, url=f"https://{domain}/")


def _resolve_jm_cookie_set(site_index: int, snapshot: SearchContextSnapshot | None) -> BrowserCookieSet | None:
    cookies = (
        snapshot.cookies.get("jm", {})
        if snapshot is not None else conf.cookies.get("jm", {})
    )
    if not cookies:
        return None
    domain = snapshot.domains.get("jm") if snapshot is not None else None
    if not domain:
        site_cls = spider_utils_map.get(site_index)
        if site_cls is None:
            raise ValueError("jm site utils unavailable")
        domain = site_cls.get_domain()
    return BrowserCookieSet(values=dict(cookies), domain=domain, url=f"https://{domain}")


def _resolve_hitomi_referer(site_index: int) -> str:
    site_cls = spider_utils_map.get(site_index)
    if site_cls is None or not getattr(site_cls, "index", None):
        raise ValueError("hitomi site index unavailable")
    return str(site_cls.index)


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
