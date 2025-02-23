# -*- coding: utf-8 -*-
import scrapy


class ComicspiderItem(scrapy.Item):
    title = scrapy.Field()
    section = scrapy.Field()
    page = scrapy.Field()
    image_urls = scrapy.Field()
    images = scrapy.Field()
    uuid = scrapy.Field()
    uuid_md5 = scrapy.Field()  # 相当于group_id，并非此item的唯一标识

    @classmethod
    def get_group_infos(cls, resp_meta) -> dict:
        return {
            'title': resp_meta.get('title'),
            'section': resp_meta.get('section') or 'meaningless',
            'uuid': resp_meta.get('uuid'),
            'uuid_md5': resp_meta.get('uuid_md5'),
        }
