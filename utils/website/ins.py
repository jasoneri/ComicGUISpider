from utils.website.providers import *
from utils.website.providers.hcomic import HComicParseError  # noqa: F401
from . import registry

registry.spider_utils_map.update({
    1: KaobeiUtils, 2: JmUtils, 3: WnacgUtils, 4: EHentaiKits, 5: MangabzUtils,
    6: HitomiUtils, 8: HComicUtils,
    'manga_copy': KaobeiUtils, 'jm': JmUtils, 'wnacg': WnacgUtils, 'ehentai': EHentaiKits, 'mangabz': MangabzUtils,
    'hitomi': HitomiUtils, 'h_comic': HComicUtils
})
