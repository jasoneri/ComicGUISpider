# -*- coding: utf-8 -*-
import scrapy

from utils import PresetHtmlEl
from utils.website import JComicUtils
from .basecomicspider import BaseComicSpider, ComicspiderItem


class JComicSpider(BaseComicSpider):
    name = "jcomic"
    domain = JComicUtils.domain
    search_url_head = JComicUtils.search_url_head
    book_id_url = JComicUtils.book_id_url
    mappings = dict(JComicUtils.mappings)
    image_ua = JComicUtils.headers
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "ComicSpider.middlewares.ComicDlAllProxyMiddleware": 5,
            "ComicSpider.middlewares.UAMiddleware": 6,
            "ComicSpider.middlewares.RefererMiddleware": 10,
            "ComicSpider.middlewares.FakeMiddleware": 30,
        }
    }
    _image_referers = None

    @property
    def ua(self):
        return JComicUtils.headers

    def _process_book(self, book):
        url = book.url if book.url and book.url.startswith("http") else self.book_id_url % book.id
        yield scrapy.Request(
            url=url,
            callback=self.parse_book_pages, headers={**self.ua, "Referer": self.request_referer(url)}, meta={"book": book},
            dont_filter=True
        )

    def parse_book_pages(self, response):
        self._emit_process("parse section")
        book = response.meta["book"]
        parsed = self.spider_site_runtime.parser.parse_book(response.text, request_url=response.url, domain=self.domain)
        page_links = list(getattr(parsed, "page_links", None) or [])
        book.name = parsed.name or book.name
        book.artist = parsed.artist or book.artist
        book.tags = parsed.tags or book.tags
        book.img_preview = parsed.img_preview or book.img_preview
        book.public_date = parsed.public_date or book.public_date
        book.preview_url = parsed.preview_url or book.preview_url
        book.url = parsed.url or book.url
        book.pages = parsed.pages or book.pages
        if not page_links:
            raise ValueError(f"jcomic book has no page links: {book!r}")
        self._assert_task_not_downloaded(book)
        self.set_task(book)
        self.say(f"📜 《{book.display_title}》")
        meta = {"book": book, "page_links": page_links, "next_link_index": 0, "global_page": 1, "task_validated": True}
        yield from self._request_next_page(meta)

    def _request_next_page(self, meta):
        page_links = meta["page_links"]
        next_link_index = int(meta["next_link_index"])
        if next_link_index >= len(page_links):
            return
        page_link = page_links[next_link_index]
        meta = dict(meta)
        meta["next_link_index"] = next_link_index + 1
        meta["section_name"] = page_link["name"]
        yield scrapy.Request(
            url=page_link["url"],
            callback=self.parse_page_images, headers={**self.ua, "Referer": self.request_referer(page_link["url"])}, meta=meta,
            dont_filter=True
        )

    def parse_page_images(self, response):
        meta = response.meta
        book = meta["book"]
        section_name = meta.get("section_name")
        page_urls = self.spider_site_runtime.parser.parse_page_urls_from_html(response.text)
        global_page = int(meta["global_page"])
        for image_url in page_urls:
            if self._should_download_page(book, global_page):
                item = ComicspiderItem()
                item["title"] = PresetHtmlEl.sub(book.name)
                item["page"] = str(global_page)
                item["section"] = section_name
                item["image_urls"] = [image_url]
                item["uuid"], item["uuid_md5"] = book.id_and_md5()
                if self.job_context:
                    self.job_context.total += 1
                self.total += 1
                if self._image_referers is None:
                    self._image_referers = {}
                self._image_referers[image_url] = response.url
                yield scrapy.Request(
                    url=f"https://fakefakefa.com/{image_url}",
                    callback=self.process_item, meta={"item": item, "referer": response.url}, dont_filter=True
                )
            global_page += 1
        meta = dict(meta)
        meta["global_page"] = global_page
        yield from self._request_next_page(meta)

    def image_request_meta(self, *, url, item):
        referer = (self._image_referers or {}).get(url)
        return {"referer": referer} if referer else {"referer": self.request_referer()}

    def process_item(self, response):
        yield response.meta["item"]
