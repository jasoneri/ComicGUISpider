# -*- coding: utf-8 -*-
import scrapy

from utils.website.providers.rumanhua import RumanhuaUtils
from .basecomicspider import BaseComicSpider, ComicspiderItem


class RumanhuaSpider(BaseComicSpider):
    name = "rumanhua"
    image_ua = RumanhuaUtils.image_ua
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "ComicSpider.middlewares.RefererMiddleware": 10,
            "ComicSpider.middlewares.FakeMiddleware": 30,
        }
    }

    def _build_episode_items(self, ep, page_urls, *, chapter_referer):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {"title": book.name, "section": ep.name, "uuid": uid, "uuid_md5": u_md5}
        ep.pages = len(page_urls)
        self.set_task(ep)
        if not hasattr(self, "_chapter_referers"):
            self._chapter_referers = {}
        self._chapter_referers[u_md5] = chapter_referer
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
        page_urls = list(getattr(ep, "page_urls", None) or [])
        chapter_referer = getattr(ep, "chapter_referer", None) or ep.url
        if not page_urls or not chapter_referer:
            missing = "page_urls" if not page_urls else "chapter_referer"
            raise ValueError(f"rumanhua episode requires {missing}: {ep!r}")
        for item in self._build_episode_items(ep, page_urls, chapter_referer=chapter_referer):
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{item["image_urls"][0]}',
                callback=self.process_item,
                meta={"item": item, "referer": chapter_referer},
                dont_filter=True,
            )
        self._emit_process("fin")

    def image_request_meta(self, *, url, item):
        referer = getattr(self, "_chapter_referers", {}).get(item.get("uuid_md5"))
        return {"referer": referer} if referer else {}

    def process_item(self, response):
        yield response.meta["item"]
