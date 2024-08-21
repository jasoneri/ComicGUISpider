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
