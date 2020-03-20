# -*- coding: utf-8 -*-
import logging
import time

from scrapy import signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from utils import get_proxy
import random


class ComicspiderDownloaderMiddleware(RetryMiddleware):
    logger = logging.getLogger(__name__)

    def __init__(self, setting):
        super(ComicspiderDownloaderMiddleware, self).__init__(setting)
        self.USER_AGENTS = setting.get('UA')

    def guise_proxy(self, request, *args):
        request.meta['proxy'] = f"{request.url.split(':')[0]}://{get_proxy()}"
        self.logger.info(f"switch proxy : {request.meta['proxy']} net error url>>{request.url}")
        return request

    # @classmethod
    # def from_crawler(cls, crawler):  # if not base on object then need to define this toget spider setting
    #     # This method is used by Scrapy to create your spiders.
    #     USER_AGENTS = crawler.settings.get('UA')
    #     s = cls(USER_AGENTS)
    #     crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
    #     return s

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.
        if response.status != 200:
            user_agent = random.choice(self.USER_AGENTS)
            request.headers['User-Agent'] = user_agent
            return self.guise_proxy(request)
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.
        if '10061' in str(exception) or '10060' in str(exception):
            request = self.guise_proxy(request)

        if isinstance(exception, self.EXCEPTIONS_TO_RETRY) and not request.meta.get('dont_retry', False):
            time.sleep(random.randint(1, 3))
            self.logger.warning('连接异常,进行重试......')
            return self._retry(request, exception, spider)
