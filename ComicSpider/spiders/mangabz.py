# -*- coding: utf-8 -*-
import re

import scrapy

from .basecomicspider import BaseComicSpider, ComicspiderItem


class MangabzSpider(BaseComicSpider):
    name = 'mangabz'
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.ComicDlAllProxyMiddleware': 6,
                                   'ComicSpider.middlewares.FakeMiddleware': 30},
        "ITEM_PIPELINES": {'ComicSpider.pipelines.MangabzComicPipeline': 50}
    }

    def _build_episode_items(self, ep, page_urls):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title':book.name,'section':ep.name,'uuid':uid,'uuid_md5':u_md5}
        ep.pages = len(page_urls)
        self.set_task(ep)
        for idx, img_url in enumerate(page_urls, start=1):
            item = ComicspiderItem()
            item.update(**group_infos)
            matched = re.search(r'/(\d+)_\d+\.', img_url)
            page = int(matched.group(1)) if matched else idx
            item['page'] = page
            item['image_urls'] = [img_url]
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item

    def _process_episode(self, ep):
        if not getattr(ep, 'page_urls', None):
            raise ValueError(f"mangabz episode requires page_urls: {ep!r}")
        for item in self._build_episode_items(ep, list(ep.page_urls)):
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{item["image_urls"][0]}', callback=self.process_item,
                meta={'item': item}, dont_filter=True,
            )
        self._emit_process('fin')

    def process_item(self, response):
        yield response.meta['item']
