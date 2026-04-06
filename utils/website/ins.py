from utils.website.providers import *
from utils.website.providers.hcomic import HComicParseError  # noqa: F401
from . import registry
from .adapter import ProviderSpiderAdapter
from .gateway import ProviderSiteGateway

provider_map = {
    1: KaobeiUtils, 2: JmUtils, 3: WnacgUtils, 4: EHentaiKits, 5: MangabzUtils,
    6: HitomiUtils, 8: HComicUtils,
    'manga_copy': KaobeiUtils, 'kaobei': KaobeiUtils, 'jm': JmUtils, 'wnacg': WnacgUtils, 'ehentai': EHentaiKits, 'mangabz': MangabzUtils,
    'hitomi': HitomiUtils, 'h_comic': HComicUtils
}

gateway_cache = {}
adapter_cache = {}
for site_key, provider_cls in provider_map.items():
    registry.site_gateway_map[site_key] = gateway_cache.setdefault(
        provider_cls,
        ProviderSiteGateway(provider_cls),
    )
    registry.spider_adapter_map[site_key] = adapter_cache.setdefault(
        provider_cls,
        ProviderSpiderAdapter(provider_cls),
    )
