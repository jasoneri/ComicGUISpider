# -*- coding: utf-8 -*-
import scrapy

from utils.website import JestfulUtils
from .basecomicspider import BaseComicSpider, ComicspiderItem


class JestfulSpider(BaseComicSpider):
    name = "jestful"
    ua = JestfulUtils.ua
    image_ua = JestfulUtils.image_ua
    domain = JestfulUtils.domain
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "ComicSpider.middlewares.UAMiddleware": 5,
            "ComicSpider.middlewares.RefererMiddleware": 10,
            "ComicSpider.middlewares.FakeMiddleware": 30,
        }
    }
    _enable_episode_dispatch = True

    def frame_section(self, response):
        reqer = self.spider_site_runtime.reqer
        parser = self.spider_site_runtime.parser
        book = response.meta.get("book")
        if book is None:
            raise ValueError("jestful frame_section requires response.meta['book']")
        owner_state = parser.parse_book_owner_state(response.text, owner_url=response.url)
        chapter_url = reqer.build_lstc_url(owner_state["loader_slug"], domain=self.domain)
        chapter_resp = reqer.cli.get(
            chapter_url,
            headers=reqer.build_lstc_headers(referer=response.url),
            follow_redirects=True,
            timeout=12,
        )
        chapter_resp.raise_for_status()
        episodes = parser.parse_episodes_from_list_html(chapter_resp.text, book, domain=self.domain)
        frame_results = {ep.idx: ep for ep in episodes}
        return self.say.frame_section_print(frame_results)

    def _build_episode_items(self, ep, page_urls, *, chapter_referer):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {"title": book.name, "section": ep.name, "uuid": uid, "uuid_md5": u_md5}
        ep.pages = len(page_urls)
        self.set_task(ep)
        if not hasattr(self, "_chapter_referers"):
            self._chapter_referers = {}
        self._chapter_referers[u_md5] = chapter_referer
        for page, image_url in enumerate(page_urls, start=1):
            item = ComicspiderItem()
            item.update(**group_infos)
            item["page"] = page
            item["image_urls"] = [image_url]
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item

    def _yield_episode_items(self, ep, page_urls, *, chapter_referer):
        for item in self._build_episode_items(ep, page_urls, chapter_referer=chapter_referer):
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{item["image_urls"][0]}',
                callback=self.process_item,
                meta={'item': item},
                dont_filter=True,
            )
        self._emit_process("fin")

    def _process_episode(self, ep):
        if getattr(ep, "page_urls", None):
            chapter_referer = getattr(ep, "chapter_referer", None) or ep.url
            yield from self._yield_episode_items(ep, list(ep.page_urls), chapter_referer=chapter_referer)
            return
        yield from super()._process_episode(ep)

    def parse_fin_page(self, response):
        parser = self.spider_site_runtime.parser
        reqer = self.spider_site_runtime.reqer
        ep = response.meta["ep"]
        chapter_referer = response.url
        cid = parser.parse_chapter_image_cid(response.text, chapter_url=chapter_referer)
        iog_url = reqer.build_iog_url(cid, domain=self.domain)
        yield scrapy.Request(
            url=iog_url,
            callback=self.parse_iog_page,
            headers=reqer.build_iog_headers(referer=chapter_referer),
            meta={"ep": ep, "chapter_referer": chapter_referer},
            dont_filter=True,
        )

    def parse_iog_page(self, response):
        parser = self.spider_site_runtime.parser
        ep = response.meta["ep"]
        chapter_referer = response.meta.get("chapter_referer") or ep.url
        page_urls = parser.parse_iog_image_urls(response.text, request_url=response.url)
        for item in self._build_episode_items(ep, page_urls, chapter_referer=chapter_referer):
            yield item
        self._emit_process("fin")

    def image_request_meta(self, *, url, item):
        referer = getattr(self, "_chapter_referers", {}).get(item.get("uuid_md5"))
        return {"referer": referer} if referer else {}

    def process_item(self, response):
        yield response.meta["item"]
