# ruff: noqa: F401,F403,F405
from __future__ import annotations

from utils.website.providers import *
from utils.website.providers.hcomic import HComicParseError  
from utils.website.providers.jcomic import JComicParseError
from variables import Spider

from . import registry
from .site_runtime import ProviderDescriptor


def _build_provider_map():
    _PROVIDER_BINDINGS = {
        Spider.MANGA_COPY: KaobeiUtils, Spider.JM: JmUtils, Spider.WNACG: WnacgUtils, 
        Spider.EHENTAI: EHentaiKits, Spider.MANGABZ: MangabzUtils, Spider.HITOMI: HitomiUtils, 
        Spider.H_COMIC: HComicUtils, Spider.NHENTAI: NhentaiUtils, Spider.JESTFUL: JestfulUtils,
        Spider.MANHUAGUI: ManhuaguiUtils, Spider.DM5: Dm5Utils, Spider.COMICABC: ComicabcUtils,
        Spider.MH1234: Mh1234Utils, Spider.JCOMIC: JComicUtils, Spider.RUMANHUA: RumanhuaUtils,
    }
    _PROVIDER_ALIASES = {
        Spider.MANGA_COPY: ("kaobei",), Spider.JESTFUL: ("jf",), Spider.DM5: ("dm",),
        Spider.RUMANHUA: ("rmh",),
    }
    binding_map = {}
    for spider in sorted(Spider, key=int):
        provider_cls = _PROVIDER_BINDINGS[spider]
        binding_map[spider.value] = provider_cls
        binding_map[spider.spider_name] = provider_cls
        for alias in _PROVIDER_ALIASES.get(spider, ()):
            binding_map[alias] = provider_cls
    return binding_map


provider_map = _build_provider_map()


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
