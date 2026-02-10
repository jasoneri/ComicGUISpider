# -*- coding: utf-8 -*-
from utils.website import HComicUtils
from .basecomicspider import BaseComicSpider2, font_color

domain = "h-comic.com"


class HComicSpider(BaseComicSpider2):
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
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

    def frame_book(self, response):
        frame_results = {}
        self.say(self.say_fm.format("序号", "漫画名") + "<br>")
        books = self.ut.parse_search(response.text)
        for idx, book in enumerate(books, 1):
            book.idx = idx
            frame_results[idx] = book
        return self.say.frame_book_print(frame_results, url=response.url, make_preview=True)

    def frame_section(self, response):
        book = self.ut.parse_book(response.text)
        pages = int(book.pages or 0)
        if pages <= 0:
            self.say(font_color("未解析到页面信息，请稍后重试", cls="theme-err"))
            return {}
        media_id = getattr(book, "media_id", "")
        comic_source = getattr(book, "comic_source", "")
        image_prefix = HComicUtils._get_image_prefix(comic_source)
        frame_results = {}
        for page in range(1, pages + 1):
            frame_results[page] = f"{image_prefix}/{media_id}/pages/{page}"
        self.say("📢" + font_color(" 这本已经扔进任务了", cls="theme-tip"))
        return frame_results
