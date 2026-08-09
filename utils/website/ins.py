# ruff: noqa: F401
from __future__ import annotations

from variables import Spider

from . import registry
from .site_runtime import ProviderDescriptor

# Declarative "module:ClassName" refs -- importing this module must not import a
# single provider module, otherwise the whole scrapy / twisted / cryptography /
# lxml stack lands on the GUI startup path. Providers load on first use, via
# ProviderDescriptor.provider_cls.
_PROVIDER_REFS = {
    Spider.MANGA_COPY: "utils.website.providers.kaobei:KaobeiUtils",
    Spider.JM: "utils.website.providers.jm:JmUtils",
    Spider.WNACG: "utils.website.providers.wnacg:WnacgUtils",
    Spider.EHENTAI: "utils.website.providers.ehentai:EHentaiKits",
    Spider.MANGABZ: "utils.website.providers.mangabz:MangabzUtils",
    Spider.HITOMI: "utils.website.hitomi:HitomiUtils",
    Spider.H_COMIC: "utils.website.providers.hcomic:HComicUtils",
    Spider.NHENTAI: "utils.website.nhentai:NhentaiUtils",
    Spider.JESTFUL: "utils.website.providers.jestful:JestfulUtils",
    Spider.MANHUAGUI: "utils.website.providers.manhuagui:ManhuaguiUtils",
    Spider.DM5: "utils.website.dm5:Dm5Utils",
    Spider.COMICABC: "utils.website.providers.comicabc:ComicabcUtils",
    Spider.MH1234: "utils.website.providers.mh1234:Mh1234Utils",
    Spider.JCOMIC: "utils.website.providers.jcomic:JComicUtils",
    Spider.RUMANHUA: "utils.website.providers.rumanhua:RumanhuaUtils",
}
_PROVIDER_ALIASES = {
    Spider.MANGA_COPY: ("kaobei",), Spider.JESTFUL: ("jf",), Spider.DM5: ("dm",),
    Spider.RUMANHUA: ("rmh",),
}


def _build_provider_map():
    binding_map = {}
    for spider in sorted(Spider, key=int):
        provider_ref = _PROVIDER_REFS[spider]
        binding_map[spider.value] = provider_ref
        binding_map[spider.spider_name] = provider_ref
        for alias in _PROVIDER_ALIASES.get(spider, ()):
            binding_map[alias] = provider_ref
    return binding_map


provider_map = _build_provider_map()


def _provider_site_indexes() -> dict[str, int]:
    site_indexes = {}
    for site_key, provider_ref in provider_map.items():
        if isinstance(site_key, int) and provider_ref not in site_indexes:
            site_indexes[provider_ref] = site_key
    return site_indexes


def _bootstrap_provider_descriptors():
    registry.clear_provider_descriptors()
    site_indexes = _provider_site_indexes()
    spider_names = {_PROVIDER_REFS[spider]: spider.spider_name for spider in Spider}
    descriptor_cache: dict[str, ProviderDescriptor] = {}
    for site_key, provider_ref in provider_map.items():
        descriptor = descriptor_cache.setdefault(
            provider_ref,
            ProviderDescriptor.from_ref(
                provider_ref,
                provider_name=spider_names[provider_ref],
                site_index=site_indexes.get(provider_ref),
            ),
        )
        registry.register_provider_descriptor(site_key, descriptor)
        registry.register_provider_spider_alias(descriptor.spider_name, descriptor)
        if isinstance(site_key, str):
            registry.register_provider_spider_alias(site_key, descriptor)


_bootstrap_provider_descriptors()
