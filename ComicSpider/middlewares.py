# -*- coding: utf-8 -*-
import re
import random
import traceback
# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals
from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.http import HtmlResponse


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
        if exception:
            spider.crawler.stats.inc_value('process_exception/count')
            spider.crawler.stats.set_value('process_exception/last_exception', 
                f"[{type(exception).__name__}]{str(exception).replace('<', '')}")
        return None

    def spider_opened(self, spider):
        spider.logger.info(f'Spider opened: 【{spider.name}】')


class GlobalErrorHandlerMiddleware:
    """全局错误处理中间件 - 基于scrapy信号机制"""

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        # 连接spider_error信号
        crawler.signals.connect(s.spider_error, signal=signals.spider_error)
        return s

    def spider_error(self, failure, response, spider):
        error_msg = str(failure.value)
        spider.logger.error(f"Traceback: {failure.getTraceback()}")
        spider.crawler.engine.close_spider(spider, reason=f"[error]{error_msg}")

    def process_spider_exception(self, response, exception, spider):
        """处理spider回调函数中的异常"""
        error_msg = str(exception)
        spider.logger.error(f"Traceback: {traceback.format_exc()}")
        network_exceptions = ('ConnectionError', 'TimeoutError', 'ImageException')
        if any(ex_type in type(exception).__name__ for ex_type in network_exceptions):
            spider.crawler.stats.inc_value('process_exception/count')
            spider.crawler.stats.set_value('process_exception/last_exception', 
                f"[{type(exception).__name__}]{str(exception).replace('<', '')}")
            return []
        spider.crawler.engine.close_spider(spider, reason=f"[error]{error_msg}")
        return []


class UAMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        request.headers.update(getattr(spider, 'ua', {}))
        return None


class UAKaobeiMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        if request.url.find(spider.pc_domain) != -1:
            ua = getattr(spider, 'ua', {})
            if request.url.endswith('/chapters'):
                ua.update({'Referer': f'https://{spider.pc_domain}/comic/{request.url.split("/")[-2]}'})
            else:
                ua.update({'Referer': "/".join(request.url.split("/")[:-2])})
            request.headers.update(ua)
        else:
            request.headers.update(getattr(spider, 'ua_mapi', {}))
        return None


class MangabzUAMiddleware(UAMiddleware):
    def process_request(self, request, spider):
        if request.method == "POST":
            request.headers.update({
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                "Accept-Encoding": "gzip, deflate, br",
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


class DisableSystemProxyMiddleware(HttpProxyMiddleware):
    def _get_proxy(self, scheme, *args, **kwargs):
        return None, None


class RefererMiddleware(ComicspiderDownloaderMiddleware):
    def process_request(self, request, spider):
        request.headers['Referer'] = spider.domain
        return None


class FakeMiddleware:
    def process_request(self, request, spider):
        if request.url.startswith('https://fakefakefa.com'):
            fake_resp = HtmlResponse(url=request.url, request=request, body=b'fake')
            return fake_resp
        return None
