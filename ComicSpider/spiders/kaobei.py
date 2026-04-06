# -*- coding: utf-8 -*-
import re

import scrapy

from utils.processed_class import Url
from utils.website import KaobeiUtils
from utils.website.schema import KbFrameBook as FrameBook
from .basecomicspider import BaseComicSpider, ComicspiderItem, conf


class KaobeiSpider(BaseComicSpider):
    name = 'manga_copy'
    ua = KaobeiUtils.ua
    headers = KaobeiUtils.headers
    page_headers = {**KaobeiUtils.ua_mapi, **KaobeiUtils.headers}
    ua_mapi = KaobeiUtils.ua_mapi
    domain = KaobeiUtils.api_domain
    pc_domain = KaobeiUtils.pc_domain
    proxy_domains = [domain, pc_domain]  # 需要代理的域名列表
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.UAKaobeiMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlProxyMiddleware': 6,
                                   'ComicSpider.middlewares.FakeMiddleware': 30},
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

    def _build_episode_items(self, ep, page_urls):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title': book.name, 'section': ep.name, 'uuid': uid, 'uuid_md5': u_md5}
        ep.pages = len(page_urls)
        self.set_task(ep)
        for page, image_url in enumerate(page_urls, start=1):
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page
            item['image_urls'] = [image_url]
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item

    def _yield_episode_items(self, ep, page_urls):
        for item in self._build_episode_items(ep, page_urls):
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{item["image_urls"][0]}',
                callback=self.process_item,
                meta={'item': item},
                dont_filter=True,
            )
        self._emit_process('fin')

    def _process_episode(self, ep):
        if getattr(ep, 'page_urls', None):
            yield from self._yield_episode_items(ep, list(ep.page_urls))
            return
        yield from super()._process_episode(ep)

    def parse_fin_page(self, response):
        ep = response.meta['ep']
        imageData = self.site.parser.parse_page_urls_from_html(
            response.text, url=response.url, aes_key=self.site.reqer_cls.get_aes_key(),
        )
        for item in self._build_episode_items(ep, [url_item['url'] for url_item in imageData]):
            yield item
        self._emit_process('fin')

    def process_item(self, response):
        item = response.meta['item']
        yield item
