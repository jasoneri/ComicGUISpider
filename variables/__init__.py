#!/usr/bin/python
# -*- coding: utf-8 -*-
SPIDERS = {
    1: 'manga_copy',
    2: 'jm',
    3: 'wnacg',
    4: 'ehentai'
}
SPECIAL_WEBSITES = ['wnacg', 'jm', 'ehentai']
SPECIAL_WEBSITES_IDXES = [2, 3, 4]
SPIDERS_NEED_PROXIES_IDXES = [3, 4]

DEFAULT_COMPLETER = {  # only take effect when init (mean value[completer] of conf.yml is null or not exist)
    1: ['更新', '排名日', '排名周', '排名月', '排名总'],
    2: ['C104', '更新周', '更新月', '点击周', '点击月', '评分周', '评分月', '评论周', '评论月', '收藏周', '收藏月'],
    3: ['C104', '更新', '汉化'],
    4: ['C104']
}
STATUS_TIP = {
    0: None,
    1: '拷贝漫画：（1）输入【搜索词】返回搜索结果（2）按空格弹出预设（2.1）规则补充：排名+日/周/月/总+轻小说/男/女，例如"排名轻小说月"',
    2: r'jm：（1）输入【搜索词】返回搜索结果（2）按空格弹出预设（2.1）规则补充：时间维度可选 日/周/月/总，例如"收藏总"（3）翻页规则："&page=\d+"',
    3: r'wnacg：（1）输入【搜索词】返回搜索结果（2）按空格弹出预设（3）翻页规则：搜索是"&p=\d+" 导航页是"-page-\d+" 如不满足请联系开发者',
    4: 'ehentai：（1）输入【搜索词】返回搜索结果（2）按空格弹出预设'
}
