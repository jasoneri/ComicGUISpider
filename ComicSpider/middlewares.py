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
