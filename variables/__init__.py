#!/usr/bin/python
# -*- coding: utf-8 -*-
from enum import IntEnum
from assets import res

VER = "v2.9.11"

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

    @property
    def spider_name(self): return self.name.lower()

    @classmethod
    def specials(cls):  return frozenset({cls.JM, cls.WNACG, cls.EHENTAI, cls.HITOMI, cls.H_COMIC})
    @classmethod
    def mangas(cls):    return frozenset({cls.MANGA_COPY, cls.MANGABZ})
    @classmethod
    def cn_proxy(cls):  return frozenset({cls.WNACG, cls.EHENTAI, cls.HITOMI, cls.H_COMIC})
    @classmethod
    def aggr(cls):      return frozenset({cls.JM, cls.WNACG, cls.EHENTAI, cls.H_COMIC})   # AggrSearchThread._async_run
    @classmethod
    def clip(cls):      return frozenset({cls.JM, cls.WNACG, cls.EHENTAI})                # ClipTasksThread._async_run


SPIDERS: dict[int, str] = {s.value: s.spider_name for s in Spider}
COOKIES_SUPPORT = {
    'jm': set(),
    'ehentai': {"igneous","ipb_member_id","ipb_pass_hash"}
}
COOKIES_PLACEHOLDER = {
    k: f"{res.GUI.Uic.confDia_cookies_placeholder}{', '.join(v)}"
    for k, v in COOKIES_SUPPORT.items()
}

DEFAULT_COMPLETER = {  # only take effect when init (mean value[completer] of conf.yml is null or not exist)
    1: ['更新', '排名日', '排名周', '排名月', '排名总'],
    2: ['C107', '更新周', '更新月', '点击周', '点击月', '评分周', '评分月', '评论周', '评论月', '收藏周', '收藏月'],
    3: ['C107', '更新', '汉化'],
    4: [res.EHentai.MAPPINGS_POPULAR, res.EHentai.MAPPINGS_INDEX, 'C107'],
    5: ['更新', '人气'],
    6: ['index-all', 'popular/week-all', 'popular/month-all'],
    7: [],
    8: []
}
STATUS_TIP = {
    0: None,
    1: f"manga_copy: {res.GUI.SearchInputStatusTip.manga_copy}",
    2: f"jm: {res.GUI.SearchInputStatusTip.jm}",
    3: f"wnacg: {res.GUI.SearchInputStatusTip.wnacg}",
    4: f"ehentai: {res.GUI.SearchInputStatusTip.ehentai}",
    5: f"mangabz: {res.GUI.SearchInputStatusTip.mangabz}",
    6: f"hitomi: {res.GUI.SearchInputStatusTip.hitomi}",
    8: f"h_comic: {res.GUI.SearchInputStatusTip.h_comic}"
}

PYPI_SOURCE = {
    0: "https://pypi.org/simple",
    1: "https://pypi.tuna.tsinghua.edu.cn/simple/",
    2: "https://mirrors.aliyun.com/pypi/simple/",
    3: "https://repo.huaweicloud.com/repository/pypi/simple/",
}
CGS_DOC = "https://cgs.101114105.xyz"
