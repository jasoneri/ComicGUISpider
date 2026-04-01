# -*- coding: utf-8 -*-
import re

from utils.processed_class import Url
from utils.website import KaobeiUtils
from utils.website.schema import KbFrameBook as FrameBook
from .basecomicspider import BaseComicSpider, ComicspiderItem, conf


class KaobeiSpider(BaseComicSpider):
    name = 'manga_copy'
    ua = headers = KaobeiUtils.ua
    ua_mapi = KaobeiUtils.ua_mapi
    domain = KaobeiUtils.api_domain
    pc_domain = KaobeiUtils.pc_domain
    proxy_domains = [domain, pc_domain]  # 需要代理的域名列表
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.UAKaobeiMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlProxyMiddleware': 6},
        "REFERER_ENABLED": False
    }
    search_url_head = ''
    preset_book_frame = FrameBook(domain)
    turn_page_info = (r"offset=\d+", None, 30)
    section_limit = 300
    _enable_episode_dispatch = True

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        KaobeiUtils.reqer_cls.get_aes_key()
        return super().from_crawler(crawler, *args, **kwargs)

    def frame_book(self, response):
        frame_results = {}
        targets = response.json().get('results', {}).get('list', [])
        books = self.site.parser.parse_search_targets(targets, self.preset_book_frame)
        for book in books:
            frame_results[book.idx] = book
        return self.say.frame_book_print(
            frame_results, url=response.url,
            extra=" →_→ 拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算")

    def frame_section(self, response):
        book = response.meta.get("book")
        episodes = self.site.parser.parse_episodes(
            response.json()['results'], book, url=response.url, 
            aes_key=self.site.reqer_cls.get_aes_key(), show_dhb=conf.kbShowDhb,
        )
        frame_results = {ep.idx: ep for ep in episodes}
        self.say.frame_section_print(frame_results)

    def mk_page_tasks(self, **kw):
        return [kw['url']]

    def parse_fin_page(self, response):
        ep = response.meta['ep']
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title':book.name,'section':ep.name,'uuid':uid,'uuid_md5':u_md5}
        imageData = self.site.parser.parse_page_urls_from_html(
            response.text, url=response.url, aes_key=self.site.reqer_cls.get_aes_key(),
        )
        ep.pages = len(imageData)
        self.set_task(ep)
        for page, url_item in enumerate(imageData):
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page + 1
            item['image_urls'] = [url_item['url']]
            self.total += 1
            yield item
        self._emit_process('fin')
