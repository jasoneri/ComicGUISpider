# -*- coding: utf-8 -*-
import scrapy

from utils.website.providers.kaobei import KaobeiUtils
from utils.website.schema import KbFrameBook as FrameBook
from .basecomicspider import BaseComicSpider, ComicspiderItem


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

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.spider_site_runtime.reqer.get_aes_key()
        return spider

    def _build_episode_items(self, ep, page_urls):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title': book.name, 'section': ep.name, 'uuid': uid, 'uuid_md5': u_md5}
        ep.pages = len(page_urls)
        self.set_task(ep)
        for page, image_url in self._iter_target_page_urls(ep, page_urls):
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
                url=f'https://fakefakefa.com/{item["image_urls"][0]}', callback=self.process_item,
                meta={'item': item}, dont_filter=True,
            )
        self._emit_process('fin')

    def _process_episode(self, ep):
        if not getattr(ep, 'page_urls', None):
            raise ValueError(f"kaobei episode requires page_urls: {ep!r}")
        yield from self._yield_episode_items(ep, list(ep.page_urls))

    def process_item(self, response):
        item = response.meta['item']
        yield item
