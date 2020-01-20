# -*- coding: utf-8 -*-
from scrapy import cmdline
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

# 这里是必须引入的
# import robotparser

import scrapy.spiderloader
import scrapy.statscollectors
import scrapy.logformatter
import scrapy.dupefilters
import scrapy.squeues

import scrapy.extensions.spiderstate
import scrapy.extensions.corestats
import scrapy.extensions.telnet
import scrapy.extensions.logstats
import scrapy.extensions.memusage
import scrapy.extensions.memdebug
import scrapy.extensions.feedexport
import scrapy.extensions.closespider
import scrapy.extensions.debug
import scrapy.extensions.httpcache
import scrapy.extensions.statsmailer
import scrapy.extensions.throttle

import scrapy.core.scheduler
import scrapy.core.engine
import scrapy.core.scraper
import scrapy.core.spidermw
import scrapy.core.downloader

import scrapy.downloadermiddlewares.stats
import scrapy.downloadermiddlewares.httpcache
import scrapy.downloadermiddlewares.cookies
import scrapy.downloadermiddlewares.useragent
import scrapy.downloadermiddlewares.httpproxy
import scrapy.downloadermiddlewares.ajaxcrawl
import scrapy.downloadermiddlewares.decompression
import scrapy.downloadermiddlewares.defaultheaders
import scrapy.downloadermiddlewares.downloadtimeout
import scrapy.downloadermiddlewares.httpauth
import scrapy.downloadermiddlewares.httpcompression
import scrapy.downloadermiddlewares.redirect
import scrapy.downloadermiddlewares.retry
import scrapy.downloadermiddlewares.robotstxt

import scrapy.spidermiddlewares.depth
import scrapy.spidermiddlewares.httperror
import scrapy.spidermiddlewares.offsite
import scrapy.spidermiddlewares.referer
import scrapy.spidermiddlewares.urllength

import scrapy.pipelines

import scrapy.core.downloader.handlers.http
import scrapy.core.downloader.contextfactory
import scrapy.pipelines.images

# 自己项目用到的
from ComicSpider.settings import IMAGES_STORE
import json
import time
import os
import re
# requirement.txt

text = ('{:=^70}'.format('message'),'\n此程序可搜索网站的漫画并进行下载\n',
        '{:-^60}'.format('仅为学习使用'),'\n响应出错可参考README.md设置代理IP\n','{:=^70}'.format('message'))


if __name__ == '__main__':
    print(''.join(text))
    _list = ['comic90mh', 'comickukudm']
    # try:while True:
    choose = input('现有两网站 1、90mh网； 2、kuku动漫网\t请进行选择(输入其他视为退出exe)： ')
    spider = _list[int(choose)-1]
    print(f'\nyou choose the """{spider}"""')
    time.sleep(1.5)
    process = CrawlerProcess(get_project_settings())
    process.crawl(spider)
    process.start()
    os.system(f"explorer.exe {IMAGES_STORE}")
    # except Exception as e:
    #     print(f'\n{"="*20} wrong happen "{e}", later will quit')
    #     time.sleep(3)
#     finally：process.stop()

