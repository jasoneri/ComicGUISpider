# -*- coding: utf-8 -*-
import asyncio
import aiohttp
from loguru import logger
import re
from ComicSpider.items import ComicspiderItem
from scrapy.http import Request
from scrapy_redis.spiders import RedisSpider
import base64


# class Comic90mhSpider(scrapy.Spider):
class Comic90mhSpider(RedisSpider):
    name = 'comic90mh'
    allowed_domains = ['m.90mh.com']
    cs_exp_txt = ('\n',
                  '{:=^70}'.format('message'),
                  '\n{:-^63}\n'.format('关于输入移步参考[1图流示例.jpg]\n'
                                       '用‘-’号识别的，别漏了打！ \t用‘-’号识别的，别漏了打！ \t用‘-’号识别的，别漏了打！ \t'),
                  '{:=^70}'.format('message'),)

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
                    section = c_s[i][0]
                    logger.debug(f'爬的《{title}》的章节：{section}')
                    yield Request(c_s[i][1], callback=self.parse_page, meta={'info': [title, section]})
        except Exception as e:
            logger.error(f'parse book 出错：{e.args}')

    def choose_section(self, response, *args):
        targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
        c_s = {}
        for x in range(len(targets)):
            section_url = targets[x].xpath('./a/@href').get()
            section = targets[x].xpath('.//span/text()').get()
            c_s[x + 1] = [section, section_url]
        logger.debug(''.join(self.cs_exp_txt))
        return c_s

    @logger.catch
    def parse_page(self, response):
        item = ComicspiderItem()
        target = response.xpath('//div[@class="UnderPage"]/div/mip-link')  # sign -*-
        next_url = target.xpath('./@href').get()
        item['title'] = response.meta.get('info')[0]
        item['section'] = response.meta.get('info')[1]
        item['page'] = response.xpath('//span[@id="k_page"]/text()').get()
        image_url = target.xpath('.//mip-img/@src').get()
        item['image_urls'] = image_url

        item = self.loop.run_until_complete(self.download(item))

        yield item
        # print(f'self.loop.is_closed: {self.loop.is_closed()}')
        if re.match(r'.*?-[\d]+\.html', next_url):
            yield response.follow(next_url, callback=self.parse_page, meta={'info': [item['title'], item['section']]})

    async def fetch(self, session, url):
        async with session.get(url) as resp:
            return await resp.read()

    async def download(self, item):
        async with aiohttp.ClientSession() as session:
            resp_content = await self.fetch(session, item['image_urls'])
            base_content = base64.b64encode(resp_content)
            item['images_base64_content'] = base_content
        return item

    def close(spider, reason):
        spider.loop.stop()
        spider.loop.close()
