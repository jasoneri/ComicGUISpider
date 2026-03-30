# -*- coding: utf-8 -*-
from utils.website import HComicUtils
from .basecomicspider import BaseComicSpider2, font_color

domain = "h-comic.com"


class HComicSpider(BaseComicSpider2):
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "ComicSpider.middlewares.ComicDlAllProxyMiddleware": 5,
            "ComicSpider.middlewares.UAMiddleware": 6,
            "ComicSpider.middlewares.RefererMiddleware": 10,
        }
    }
    name = "h_comic"
    num_of_row = 4
    domain = domain
    search_url_head = f"https://{domain}/?q="
    turn_page_info = (r"page=\d+",)
    book_id_url = f"https://{domain}/comics/1?id=%s"
    mappings = {}

    @property
    def ua(self):
        return HComicUtils.headers

    def frame_section(self, response):
        book = self.ut.parser.parse_book(response.text)
        pages = int(book.pages or 0)
        if pages <= 0:
            self.say(font_color("未解析到页面信息，请稍后重试", cls="theme-err"))
            return {}
        media_id = getattr(book, "media_id", "")
        comic_source = getattr(book, "comic_source", "")
        image_prefix = self.ut.parser.get_image_prefix(comic_source)
        frame_results = {}
        for page in range(1, pages + 1):
            frame_results[page] = f"{image_prefix}/{media_id}/pages/{page}"
        self.say("📢" + font_color(" 这本已经扔进任务了", cls="theme-tip"))
        return frame_results
