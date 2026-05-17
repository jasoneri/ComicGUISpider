#!/usr/bin/python
# -*- coding: utf-8 -*-
from enum import IntEnum
from assets import res

VER = "v2.10.1-beta"

LANG = {
    "en_US": "English",
    "zh_CN": "简体中文"
}

class Spider(IntEnum):
    MANGA_COPY = 1   # 🇨🇳
    JM = 2           # 🇨🇳 🔞
    WNACG = 3        # 🇨🇳 🔞
    EHENTAI = 4      # 🌎 🔞
    MANGABZ = 5      # 🇨🇳
    HITOMI = 6       # 🌎 🔞
    H_COMIC = 8      # 🌎 🔞
    NHENTAI = 9     # 🌎 🔞
    JESTFUL = 10      # 🌎
    MANHUAGUI = 11    # 🇨🇳
    DM5 = 12          # 🇨🇳

    @property
    def spider_name(self): return self.name.lower()

    @classmethod
    def specials(cls):  return frozenset({cls.JM, cls.WNACG, cls.EHENTAI, cls.HITOMI, cls.H_COMIC, cls.NHENTAI})
    @classmethod
    def mangas(cls):    return frozenset({cls.MANGA_COPY, cls.MANGABZ, cls.JESTFUL, cls.MANHUAGUI, cls.DM5})
    @classmethod
    def cn_proxy(cls):  return frozenset({cls.WNACG, cls.EHENTAI, cls.HITOMI, cls.H_COMIC, cls.NHENTAI, cls.MANHUAGUI})
    @classmethod
    def aggr(cls):      return frozenset({cls.JM, cls.WNACG, cls.EHENTAI, cls.H_COMIC, cls.NHENTAI})   # AggrSearchThread._async_run
    @classmethod
    def clip(cls):      return frozenset({cls.JM, cls.WNACG, cls.EHENTAI})                             # ClipTasksThread._async_run


SPIDERS: dict[int, str] = {s.value: s.spider_name for s in Spider}
SCRIPT_SITE_INDEX = 7
SCRIPT_SITE_NAME = "Script"

def _map_spider_values(values_by_spider):
    return {spider.value: values_by_spider[spider] for spider in Spider}

def _label(s: Spider) -> str:  
    """site name show by chooseBox, ⚠️ notice site in Spider.specials will add 🔞(suffix) by MitmMainWindow.apply_translations"""
    match s.spider_name:
        case "manga_copy":
            return f"{s.value}、拷贝漫画"
        case "dm5":
            return f"{s.value}、动漫屋"
        case _:
            return f"{s.value}、{s.spider_name}"

SPIDERS_LABELS = dict(sorted({
    **{spider.value: _label(spider) for spider in Spider},
    SCRIPT_SITE_INDEX: f"{SCRIPT_SITE_INDEX}、{SCRIPT_SITE_NAME}",
}.items()))

COOKIES_SUPPORT = {     # only when login required
    'jm': set(),
    'ehentai': {"igneous","ipb_member_id","ipb_pass_hash"}
}
COOKIES_PLACEHOLDER = {
    k: f"{res.GUI.Uic.confDia_cookies_placeholder}{', '.join(v)}"
    for k, v in COOKIES_SUPPORT.items()
}

DEFAULT_COMPLETER = dict(sorted({  # only take effect when init (mean value[completer] of conf.yml is null or not exist)
    **_map_spider_values({
        Spider.MANGA_COPY: ['更新', '排名日', '排名周', '排名月', '排名总'],
        Spider.JM: ['C107', '更新周', '更新月', '点击周', '点击月', '评分周', '评分月', '评论周', '评论月', '收藏周', '收藏月'],
        Spider.WNACG: ['C107', '更新', '汉化'],
        Spider.EHENTAI: [res.SPIDER.Completer.popular, res.SPIDER.Completer.index, 'C107'],
        Spider.MANGABZ: ['更新', '人气'],
        Spider.HITOMI: ['index-all', 'popular/week-all', 'popular/month-all'],
        Spider.H_COMIC: ['更新'],
        Spider.NHENTAI: [res.SPIDER.Completer.update],
        Spider.JESTFUL: [res.SPIDER.Completer.index,res.SPIDER.Completer.update],
        Spider.MANHUAGUI: [res.SPIDER.Completer.index,res.SPIDER.Completer.update],
        Spider.DM5: [res.SPIDER.Completer.update],
    }),
    SCRIPT_SITE_INDEX: [],
}.items()))
STATUS_TIP = dict(sorted({
    0: None,
    **_map_spider_values({
        Spider.MANGA_COPY: f"manga_copy: {res.GUI.SearchInputStatusTip.manga_copy}",
        Spider.JM: f"jm: {res.GUI.SearchInputStatusTip.jm}",
        Spider.WNACG: f"wnacg: {res.GUI.SearchInputStatusTip.wnacg}",
        Spider.EHENTAI: f"ehentai: {res.GUI.SearchInputStatusTip.common}",
        Spider.MANGABZ: f"mangabz: {res.GUI.SearchInputStatusTip.common}",
        Spider.HITOMI: f"hitomi: {res.GUI.SearchInputStatusTip.hitomi}",
        Spider.H_COMIC: f"h_comic: {res.GUI.SearchInputStatusTip.common}",
        Spider.NHENTAI: f"nhentai: {res.GUI.SearchInputStatusTip.common}",
        Spider.JESTFUL: f"jestful: {res.GUI.SearchInputStatusTip.common}",
        Spider.MANHUAGUI: f"manhuagui: {res.GUI.SearchInputStatusTip.common}",
        Spider.DM5: f"dm5: {res.GUI.SearchInputStatusTip.dm5}",
    }),
}.items()))

PYPI_SOURCE = {
    0: "https://pypi.org/simple",
    1: "https://pypi.tuna.tsinghua.edu.cn/simple/",
    2: "https://mirrors.aliyun.com/pypi/simple/",
    3: "https://repo.huaweicloud.com/repository/pypi/simple/",
}
CGS_DOC = "https://cgs.101114105.xyz"
CGS_DISCORD_SHARE_API = "https://cgs-share.101114105.xyz"
