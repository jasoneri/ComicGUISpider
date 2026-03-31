# -*- coding: utf-8 -*-
import re

from utils.website import MangabzUtils
from utils.website.schema import MbBody as Body, MbSearchBody as SearchBody, mb_curr_time_format as curr_time_format
from .basecomicspider import FormReqBaseComicSpider, ComicspiderItem

domain = MangabzUtils.domain


class MangabzSpider(FormReqBaseComicSpider):
    name = 'mangabz'
    ua = MangabzUtils.ua
    num_of_row = 50
    domain = domain
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.MangabzUAMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlAllProxyMiddleware': 6},
        "ITEM_PIPELINES": {'ComicSpider.pipelines.MangabzComicPipeline': 50}
    }
    search_url_head = f"https://{domain}/pager.ashx"
    mappings = {"更新": ["manga-list-0-0-2", "2"],
                "人气": ["manga-list", "10"],
                }
    body = Body()
    _enable_episode_dispatch = True

    def frame_book(self, response):
        frame_results = {}
        targets = response.json() if isinstance(self.body, SearchBody) \
            else response.json().get('UpdateComicItems')
        books = self.ut.parser.parse_search_targets(targets, self.body, domain=self.domain)
        for book in books:
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, url=response.url)

    def frame_section(self, response):
        book = response.meta.get("book")
        episodes = self.ut.parser.parse_episodes(response, book, domain)
        frame_results = {ep.idx: ep for ep in episodes}
        return self.say.frame_section_print(frame_results)

    def parse_fin_page(self, response):
        ep = response.meta['ep']
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        img_list = self.ut.parser.parse_page_urls_from_html(response.text)
        group_infos = {'title':book.name,'section':ep.name,'uuid':uid,'uuid_md5':u_md5}
        ep.pages = len(img_list)
        self.set_task(ep)
        for img_url in img_list:
            item = ComicspiderItem()
            item.update(**group_infos)
            page = int(re.search(r'/(\d+)_\d+\.', img_url).group(1))
            item['page'] = page
            item['image_urls'] = [img_url]
            self.total += 1
            yield item
        self._emit_process('fin')
