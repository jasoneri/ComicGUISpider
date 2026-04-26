# ruff: noqa: F401,F403,F405
from __future__ import annotations

from utils.website.providers import *
from utils.website.providers.hcomic import HComicParseError  

from . import registry
from .site_runtime import ProviderDescriptor

provider_map = {
    1: KaobeiUtils, 2: JmUtils, 3: WnacgUtils, 4: EHentaiKits, 5: MangabzUtils,
    6: HitomiUtils, 8: HComicUtils,
    'manga_copy': KaobeiUtils, 'kaobei': KaobeiUtils, 'jm': JmUtils, 'wnacg': WnacgUtils, 'ehentai': EHentaiKits, 'mangabz': MangabzUtils,
    'hitomi': HitomiUtils, 'h_comic': HComicUtils
}


def _provider_site_indexes() -> dict[type, int]:
    site_indexes = {}
    for site_key, provider_cls in provider_map.items():
        if isinstance(site_key, int) and provider_cls not in site_indexes:
            site_indexes[provider_cls] = site_key
    return site_indexes


def _bootstrap_provider_descriptors():
    registry.clear_provider_descriptors()
    site_indexes = _provider_site_indexes()
    descriptor_cache: dict[type, ProviderDescriptor] = {}
    for site_key, provider_cls in provider_map.items():
        descriptor = descriptor_cache.setdefault(
            provider_cls,
            ProviderDescriptor.create(provider_cls, site_index=site_indexes.get(provider_cls)),
        )
        registry.register_provider_descriptor(site_key, descriptor)
        registry.register_provider_spider_alias(descriptor.spider_name, descriptor)
        if isinstance(site_key, str):
            registry.register_provider_spider_alias(site_key, descriptor)


_bootstrap_provider_descriptors()
