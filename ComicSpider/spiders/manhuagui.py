# -*- coding: utf-8 -*-
import scrapy

from utils.website.providers.manhuagui import ManhuaguiUtils
from .basecomicspider import BaseComicSpider, ComicspiderItem


class ManhuaguiSpider(BaseComicSpider):
    name = "manhuagui"
    image_ua = ManhuaguiUtils.image_ua
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "ComicSpider.middlewares.ComicDlAllProxyMiddleware": 6,
            "ComicSpider.middlewares.FakeMiddleware": 30,
        }
    }

    def _build_episode_items(self, ep, page_urls):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {"title": book.name, "section": ep.name, "uuid": uid, "uuid_md5": u_md5}
        ep.pages = len(page_urls)
        self.set_task(ep)
        for page, image_url in self._iter_target_page_urls(ep, page_urls):
            item = ComicspiderItem()
            item.update(**group_infos)
            item["page"] = page
            item["image_urls"] = [image_url]
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item

    def _process_episode(self, ep):
        if not getattr(ep, "page_urls", None):
            raise ValueError(f"manhuagui episode requires page_urls: {ep!r}")
        for item in self._build_episode_items(ep, list(ep.page_urls)):
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{item["image_urls"][0]}', callback=self.process_item,
                meta={"item": item}, dont_filter=True,
            )
        self._emit_process("fin")

    def process_item(self, response):
        yield response.meta["item"]
