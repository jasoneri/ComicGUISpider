# -*- coding: utf-8 -*-
import scrapy


class ComicspiderItem(scrapy.Item):
    title = scrapy.Field()
    section = scrapy.Field()
    page = scrapy.Field()
    image_urls = scrapy.Field()
    images = scrapy.Field()
    referer = scrapy.Field()
