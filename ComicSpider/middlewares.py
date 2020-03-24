# -*- coding: utf-8 -*-
import logging
from asyncio import sleep
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from ComicSpider.utils import get_proxy
import random


class ComicspiderUAMiddleware(object):
    logger = logging.getLogger(__name__)

    def __init__(self, crawler):
        super(ComicspiderUAMiddleware, self).__init__()
        self.UA = crawler.settings.get('USER_AGENT')

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request, spider):
        agent = random.choice(self.UA)
        request.headers["User-Agent"] = agent


class ComicspiderProxyMiddleware(RetryMiddleware):
    logger = logging.getLogger(__name__)

    def proxy_guise(self, request, *args):
        request.meta['proxy'] = f"{request.url.split(':')[0]}://{get_proxy()}"
        self.logger.info(f"switch proxy : {request.meta['proxy']} net url>>{request.url}")
        return request

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.
        if response.status != 200:
            return self.proxy_guise(request)
        return response

    def process_exception(self, request, exception, spider):
        # if '10061' in str(exception) or '10060' in str(exception):
        #     request = self.proxy_guise(request)

        if isinstance(exception, self.EXCEPTIONS_TO_RETRY) and not request.meta.get('dont_retry', False):
            sleep(random.randint(1, 2))
            self.logger.warning('connection exception occur, retrying ......')
            return self._retry(self.proxy_guise(request), exception, spider)
