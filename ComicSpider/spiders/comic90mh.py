# -*- coding: utf-8 -*-
import re
import base64
import asyncio
import aiohttp
from loguru import logger
from lxml import etree
from scrapy import Spider
from ComicSpider.items import ComicspiderMasterItem, ComicspiderSlaveItem
from scrapy.http import Request
from scrapy_redis.spiders import RedisSpider


class BaseComicSpider(Spider):     # Base
    def __init__(self, *args, **kwargs):
        super(BaseComicSpider, self).__init__(*args, **kwargs)
        self.loop = asyncio.get_event_loop()
        self.book = []
        self.section = []

    @logger.catch
    def parse(self, response):
        book_frame = self.choose_book(response)
        seclected = self.book if len(self.book) else list(book_frame.keys())
        # try:
        for i in seclected:
            book, book_url = book_frame[i]
            yield Request(book_url, callback=self.parse_section, meta={'title': book})
        # except Exception as e:
        #     logger.error(f'parse error occur：{e.args}')

    def choose_book(self, response):
        """
        choose方法均为解耦，便于后续扩展，在此方法上写对应网站目标
        :return cust_frame
        """
        url = response.xpath('.//a[@class="title"]/@href').get()
        cust_frame_demo = ['title', url]
        raise NotImplementedError

    @logger.catch
    def parse_section(self, response):
        async def get_urls(url):
            async def picFetch(_session, _url):
                async with _session.get(_url) as resp:
                    return await resp.text()

            async with aiohttp.ClientSession() as session:
                html = await picFetch(session, url)
                url_list = self.parse_urls(url, html)
            return url_list

        item = ComicspiderMasterItem()
        title = response.meta.get('title')
        section_frame = self.choose_section(response, title)
        seclected = self.section if len(self.section) else list(section_frame.keys())
        # try:
        for i in seclected:
            section, section_url = section_frame[i]
            pic_urls = self.loop.run_until_complete(get_urls(url=section_url))
            logger.debug(f"selected 《{title}》's section：{section}")
            item['urls'] = pic_urls
            yield item
        # except Exception as e:
        #     logger.error(f'parse section error occur：{e.args}')

    def choose_section(self, response, *args):
        """
        choose方法均为解耦，便于后续扩展
        在此方法上写对应网站目标
        """
        raise NotImplementedError

    def parse_urls(self, url, html):
        """
        parse html，combine url --> urls
        :param url:
        :param html: list(urls)
        """
        raise NotImplementedError

    async def pic_content_download(self, url):
        """
        :param url: pic_url
        :return: b64encode(resp.content)
        """
        async def pic_fetch(session, _url):
            async with session.get(_url) as resp:
                return await resp.read()
        async with aiohttp.ClientSession() as session:
            resp_content = await pic_fetch(session, url)
            base64_content = base64.b64encode(resp_content)
        return base64_content

    @staticmethod
    def close(spider, reason):
        spider.loop.stop()
        spider.loop.close()


# class Comic90mhSpider(BaseComicSpider):  # Master
#     name = 'comic90mh'
#     allowed_domains = ['m.90mh.com']
#     start_urls = ['http://m.90mh.com/search/?keywords=异世界', ]
#
#     def __init__(self, *args, **kwargs):
#         super(Comic90mhSpider, self).__init__(*args, **kwargs)
#         self.book = [1,5]
#         self.section = []
#
#     def choose_book(self, response):
#         book_frame = {}
#         targetsSection = response.xpath('//div[@class="itemBox"]')  # sign -*-
#         for x in range(len(targetsSection)):
#             title = targetsSection[x].xpath('.//a[@class="title"]/text()').get().strip()
#             url = targetsSection[x].xpath('.//a[@class="title"]/@href').get()
#             book_frame[x + 1] = [title, url]
#         return book_frame
#
#     def choose_section(self, response, *args):
#         targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
#         section_frame = {}
#         for x in range(len(targets)):
#             section_url = targets[x].xpath('./a/@href').get()
#             section = targets[x].xpath('.//span/text()').get()
#             section_frame[x + 1] = [section, section_url]
#         logger.debug(f'section dict info: {section_frame}')
#         return section_frame
#
#     def parse_urls(self, url, html):
#         total_page = int(etree.HTML(html).xpath('//span[@id="k_total"]/text()')[0])  # sign -*-
#         compile = re.compile(r'(-[\d])*\.html')
#         url_list = list(map(lambda x: compile.sub(f'-{x}.html', url), range(total_page + 1)[1:]))
#         return url_list


class Comic90mhSpider(RedisSpider, BaseComicSpider):    # Slave
    name = 'comic90mh'
    redis_key = "comic90mh:start_urls"
    # redis_encoding = 'utf-8'

    from ComicSpider.CUST import settings
    custom_settings = settings

    def __init__(self, *args, **kwargs):
        domain = kwargs.pop('domain', '')
        self.allowed_domains = filter(None, domain.split(','))
        super(Comic90mhSpider, self).__init__(*args, **kwargs)

    @logger.catch
    def parse(self, response):
        item = ComicspiderSlaveItem()
        item['title'] = response.xpath('//div[contains(@class, "title")]//a/text()').get()
        section = response.xpath('//div[contains(@class,"p10")]/h1/span/text()').get()
        item['section'] = re.sub("[^0-9A-Za-z\u4e00-\u9fa5]", "", section)
        item['page'] = response.xpath('//span[@id="k_page"]/text()').get()
        image_url = response.xpath('//div[@class="UnderPage"]/div/mip-link/mip-img/@src').get()
        item['image_urls'] = image_url
        content = self.loop.run_until_complete(self.pic_content_download(image_url))  # -*- run_until_complete -*-
        item['images_base64_content'] = content
        yield item
