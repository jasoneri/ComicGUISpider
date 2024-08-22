#!/usr/bin/python
# -*- coding: utf-8 -*-
SPIDERS = {
    1: 'manga_copy',
    2: 'jm',
    3: 'wnacg'
}
SPECIAL_WEBSITES = ['wnacg', 'jm']
SPECIAL_WEBSITES_IDXES = [2, 3]

DEFAULT_COMPLETER = {  # only take effect when init (mean value[completer] of conf.yml is null or not exist)
    1: ['更新', '排名日', '排名周', '排名月', '排名总'],
    2: ['C104', '更新周', '更新月', '点击周', '点击月', '评分周', '评分月', '评论周', '评论月', '收藏周', '收藏月'],
    3: ['C104', '更新', '汉化']
}
STATUS_TIP = {
    0: None,
    1: '拷贝漫画：（1）输入【搜索词】返回搜索结果（2）按空格即可选择预设（2.1）规则补充：排名+日/周/月/总+轻小说/男/女，例如"排名轻小说月"',
    2: 'jm：（1）输入【搜索词】返回搜索结果（2）按空格即可选择预设（2.1）规则补充：时间维度可选 日/周/月/总，例如"收藏总"（3）翻页：最后加上"&page=2" 等页数',
    3: 'wnacg：（1）输入【搜索词】返回搜索结果（2）按空格即可选择预设（3）翻页：搜索词翻页加入"&p=2" 例如 "C104&p=2" 固定页面如更新页则使用映射'
}
