# -*- coding: utf-8 -*-
import re

# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals
import random


class ComicspiderDownloaderMiddleware(object):
    def __init__(self, USER_AGENTS, PROXIES):
        self.USER_AGENTS = USER_AGENTS
        self.PROXIES = PROXIES

    @classmethod
    def from_crawler(cls, crawler):
        USER_AGENTS, PROXIES = crawler.settings.get('UA'), crawler.settings.get('PROXY_CUST')
        s = cls(USER_AGENTS, PROXIES)
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.
        if response.status != 200:
            request.headers['User-Agent'] = random.choice(self.USER_AGENTS)
            proxy = random.choice(self.PROXIES)
            request.meta['proxy'] = f"{request.url.split(':')[0]}://{proxy}"
            return request
        return response

    def process_exception(self, request, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info(f'Spider opened: 【{spider.name}】')


class KaobeiMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        request.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip",
            "Content-Encoding": "gzip",
            "platform": "1",
            "version": "2024.01.08",
            "webp": "1",
            "region": "1",
            "Origin": "https://www.mangacopy.com",
        })
        return None


class JmMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        request.headers.update({
            'Host': spider.domain,
            'User-Agent': 'Mozilla/5.0(WindowsNT10.0;Win64;x64;rv:127.0)Gecko/20100101Firefox/127.0',
            'Accept': 'image/webp;application/xml;q=0.9;image/avif;application/xhtml+xml;text/html;*/*;q=0.8',
            'Accept-Language': 'zh;q=0.8;en;q=0.2;zh-CN;zh-TW;q=0.7;zh-HK;q=0.5;en-US;q=0.3',
            'Accept-Encoding': 'br;zstd;deflate;gzip',
            'Alt-Used': spider.domain,
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1', 'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-User': '?1',
            'Priority': 'u=1', 'Pragma': 'no-cache', 'Cache-Control': 'no-cache', 'TE': 'trailers'
        })
        return None


class ComicDlProxyMiddleware(ComicspiderDownloaderMiddleware):
    """使用情况是“通常页需要over wall访问”，“图源cn就能访问”... 因此domain的都使用代理"""
    domain_regex: re.Pattern = None

    @classmethod
    def from_crawler(cls, crawler):
        _ = super(ComicDlProxyMiddleware, cls).from_crawler(crawler)
        _.domain_regex = re.compile(crawler.spider.domain)
        return _

    def process_request(self, request, spider):
        if bool(self.domain_regex.search(request.url)):
            proxy = random.choice(self.PROXIES)
            request.meta['proxy'] = f"http://{proxy}"
