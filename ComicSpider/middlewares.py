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
            if self.PROXIES:
                proxy = random.choice(self.PROXIES)
                request.meta['proxy'] = f"{request.url.split(':')[0]}://{proxy}"
            return request
        return response

    def process_exception(self, request, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info(f'Spider opened: 【{spider.name}】')


class UAMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        request.headers.update(getattr(spider, 'ua', {}))
        return None


class MangabzUAMiddleware(UAMiddleware):
    def process_request(self, request, spider):
        if request.method == "POST":
            request.headers.update({
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://www.mangabz.com",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "TE": "trailers"
            })
        else:
            request.headers.update(getattr(spider, 'ua', {}))
        return None


class ComicDlAllProxyMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        if self.PROXIES:
            proxy = random.choice(self.PROXIES)
            request.meta['proxy'] = f"http://{proxy}"


class ComicDlProxyMiddleware(ComicspiderDownloaderMiddleware):
    """使用情况是“通常页需要over wall访问”，“图源cn就能访问”... 因此domain的都使用代理"""
    domain_regex: re.Pattern = None

    @classmethod
    def from_crawler(cls, crawler):
        _ = super(ComicDlProxyMiddleware, cls).from_crawler(crawler)
        _.domain_regex = re.compile(crawler.spider.domain)
        return _

    def process_request(self, request, spider):
        if bool(self.domain_regex.search(request.url)) and self.PROXIES:
            proxy = random.choice(self.PROXIES)
            request.meta['proxy'] = f"http://{proxy}"
