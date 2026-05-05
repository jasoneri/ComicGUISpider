# -*- coding: utf-8 -*-
from utils.website import NhentaiUtils

from .basecomicspider import BaseComicSpider2, font_color


class NhentaiSpider(BaseComicSpider2):
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "ComicSpider.middlewares.ComicDlAllProxyMiddleware": 5,
            "ComicSpider.middlewares.UAMiddleware": 6,
            "ComicSpider.middlewares.RefererMiddleware": 10,
        }
    }
    name = "nhentai"
    num_of_row = 4
    domain = NhentaiUtils.domain
    search_url_head = NhentaiUtils.search_url_head
    turn_page_info = NhentaiUtils.turn_page_info
    book_id_url = NhentaiUtils.gallery_api_url_template
    mappings = dict(NhentaiUtils.mappings)

    @property
    def ua(self):
        return dict(NhentaiUtils.headers)

    def frame_section(self, response):
        detail = self.spider_site_runtime.parser.parse_book(response.text)
        book = response.meta.get("book") or detail
        if book is not detail:
            self.spider_site_runtime.parser.apply_detail(book, detail)
        frame_results = self.spider_site_runtime.parser.build_page_image_map(book)
        if not frame_results:
            raise ValueError("nhentai gallery detail produced empty image map")
        self.say("📢" + font_color(" 这本已经扔进任务了", cls="theme-tip"))
        return frame_results
