#!/usr/bin/python
# -*- coding: utf-8 -*-
from assets import res

VER = "v2.8.5"

LANG = {
    "en_US": "English",
    "zh_CN": "简体中文"
}

SPIDERS = {
    1: 'manga_copy',    # 🇨🇳 
    2: 'jm',            # 🇨🇳 🔞
    3: 'wnacg',         # 🇨🇳 🔞
    4: 'ehentai',       # 🌎 🔞
    5: 'mangabz',       # 🇨🇳
    6: 'hitomi',        # 🌎 🔞
    8: 'h_comic',       # 🌎 🔞
}
SPECIAL_WEBSITES = ['wnacg', 'jm', 'ehentai', 'hitomi', 'h_comic']
COOKIES_SUPPORT = {
    'jm': set(), 
    'ehentai': {"igneous","ipb_member_id","ipb_pass_hash"}
}
COOKIES_PLACEHOLDER = {
    k: f"{res.GUI.Uic.confDia_cookies_placeholder}{', '.join(v)}"
    for k, v in COOKIES_SUPPORT.items()
}
SPECIAL_WEBSITES_IDXES = [2, 3, 4, 6, 8]

# GUI feat/behaviors
CN_PREVIEW_NEED_PROXIES_IDXES = [3, 4, 6, 8]
AGGR_SEARCH_IDXES = [2, 3, 4, 8]    # AggrSearchThread._async_run
CLIP_IDXES = [2, 3, 4]              # ClipTasksThread._async_run

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
