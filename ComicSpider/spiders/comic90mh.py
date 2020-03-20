# -*- coding: utf-8 -*-
import asyncio
import aiohttp
from loguru import logger
import re
from lxml import etree
from ComicSpider.items import ComicspiderItem
from scrapy.http import Request
from scrapy_redis.spiders import RedisSpider
import base64


# class Comic90mhSpider(scrapy.Spider):
class Comic90mhSpider(RedisSpider):
    name = 'comic90mh'
    allowed_domains = ['m.90mh.com']
    cs_exp_txt = ('\n''{:=^70}'.format('another book dividing line'),)
    # start_urls = ['http://m.90mh.com/search/?keywords=eros', ]
    # redis_key = "comic_queue"

    def __init__(self, *args, **kwargs):
        super(Comic90mhSpider, self).__init__(*args, **kwargs)
        self.loop = asyncio.get_event_loop()
        self.__book = [1,5,8]
        self.__section = []
        # self.__section = [60]

    @logger.catch
    def parse(self, response):
        c_b = self.choose_book(response)
        i_b = self.__book
        try:
            if len(i_b):
                for i in i_b:
                    yield Request(c_b[i][1], callback=self.parse_book, meta={'title': c_b[i][0]})
            else:
                for i in list(c_b.keys()):
                    yield Request(c_b[i][1], callback=self.parse_book, meta={'title': c_b[i][0]})
        except Exception as e:
            logger.error(f'parse 出错：{e.args}')

    def choose_book(self, response):
        c_b = {}
        targets = response.xpath('//div[@class="itemBox"]')  # sign -*-
        for x in range(len(targets)):
            title = targets[x].xpath('.//a[@class="title"]/text()').get().strip()
            url = targets[x].xpath('.//a[@class="title"]/@href').get()
            c_b[x + 1] = [title, url]
        return c_b

    @logger.catch
    def parse_book(self, response):
        title = response.meta.get('title')
        c_s = self.choose_section(response, title)
        i_s = self.__section
        try:
            if len(i_s):
                for i in i_s:
                    yield Request(c_s[i][1], callback=self.parse_page, meta={'info': [title, c_s[i][0]]})
            else:
                for i in list(c_s.keys()):
                    section, section_url = c_s[i]
                    pic_urls = self.loop.run_until_complete(self.find_urls(url=section_url))
                    logger.debug(f"yield《{title}》's section：{section}")
                    for url in pic_urls:
                        yield Request(url, callback=self.parse_page, meta={'info': [title, section]})
        except Exception as e:
            logger.error(f'parse section 出错：{e.args}')

    async def find_urls(self, url):
        async def pic_fetch(session, url):
            async with session.get(url) as resp:
                return await resp.text()
        async with aiohttp.ClientSession() as session:
            html = await pic_fetch(session, url)
            total_page = int(etree.HTML(html).xpath('//span[@id="k_total"]/text()')[0])  # sign -*-
            compile = re.compile(r'(-[\d])*\.html')
            url_list = list(map(lambda x: compile.sub(f'-{x}.html', url), range(total_page + 1)[1:]))
        return url_list

    def choose_section(self, response, *args):
        targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
        c_s = {}
        for x in range(len(targets)):
            section_url = targets[x].xpath('./a/@href').get()
            section = targets[x].xpath('.//span/text()').get()
            c_s[x + 1] = [section, section_url]
        logger.debug(f'section dict info: {c_s}')
        return c_s

    @logger.catch
    def parse_page(self, response):
        item = ComicspiderItem()
        target = response.xpath('//div[@class="UnderPage"]/div/mip-link')  # sign -*-
        # next_url = target.xpath('./@href').get()
        item['title'] = response.meta.get('info')[0]
        item['section'] = response.meta.get('info')[1]
        item['page'] = response.xpath('//span[@id="k_page"]/text()').get()
        image_url = target.xpath('.//mip-img/@src').get()
        item['image_urls'] = image_url

        item = self.loop.run_until_complete(self.pic_content_download(item))    # -*- run_until_complete -*-
        yield item
        # print(f'self.loop.is_closed: {self.loop.is_closed()}')

    async def pic_content_download(self, item):
        async def pic_fetch(session, url):
            async with session.get(url) as resp:
                return await resp.read()
        async with aiohttp.ClientSession() as session:
            resp_content = await pic_fetch(session, item['image_urls'])
            base_content = base64.b64encode(resp_content)
            item['images_base64_content'] = base_content
        return item

    def close(spider, reason):
        spider.loop.stop()
        spider.loop.close()

