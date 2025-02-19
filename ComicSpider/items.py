# -*- coding: utf-8 -*-
import scrapy


class ComicspiderItem(scrapy.Item):
    title = scrapy.Field()
    section = scrapy.Field()
    page = scrapy.Field()
    image_urls = scrapy.Field()
    images = scrapy.Field()
    identity = scrapy.Field()
    identity_md5 = scrapy.Field()  # 相当于group_id，并非此item的唯一标识
