# -*- coding: utf-8 -*-
import scrapy


class ComicspiderMasterItem(scrapy.Item):
    urls = scrapy.Field()   # 1话里包含的urls


class ComicspiderSlaveItem(scrapy.Item):
    title = scrapy.Field()
    section = scrapy.Field()
    page = scrapy.Field()
    image_urls = scrapy.Field()
    images = scrapy.Field()
    images_base64_content = scrapy.Field()
