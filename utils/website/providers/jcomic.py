# -*- coding: utf-8 -*-
import asyncio
import re
from urllib.parse import quote

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import EroUtils, Previewer, Req
from utils.website.info import JComicBookInfo


class JComicParseError(ValueError):
    pass


class _JComicContract:
    name = "jcomic"
    domain = "jcomic.net"
    index = "https://jcomic.net"
    proxy_policy = "proxy"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
    }
    book_hea = headers
    search_url_head = f"{index}/search/"
    mappings = {
        res.SPIDER.Completer.index: f"{index}/cat/隨機/1",
        res.SPIDER.Completer.popular: f"{index}/cat/隨機/1",
        res.SPIDER.Completer.update: f"{index}/cat/最近更新/1",
        "隨機": f"{index}/cat/隨機/1",
        "最近更新": f"{index}/cat/最近更新/1",
    }
    turn_page_info = (r"/\d+$",)
    turn_page_search = r"/\d+$"
    book_id_url = f"{index}/eps/%s"
    uuid_regex = re.compile(r"/(?:eps|page)/([^/?#]+)")
    page_count_regex = re.compile(r"\((\d+)\)\s*$")
    book_url_regex = r"^https://jcomic\.net/(?:eps|page)/.+"


class JComicParser(_JComicContract, Previewer):
    @classmethod
    def _selector(cls, html_text: str) -> Selector:
        return Selector(text=html_text)

    @classmethod
    def _strip_title_count(cls, title: str) -> tuple[str, int | None]:
        raw_title = str(title or "").strip()
        match = cls.page_count_regex.search(raw_title)
        if not match:
            return raw_title, None
        return cls.page_count_regex.sub("", raw_title).strip(), int(match.group(1))

    @classmethod
    def _normalize_url(cls, value: str, *, domain: str | None = None) -> str:
        normalized = cls.normalize_preview_resource(value, domain=domain or cls.domain)
        if not isinstance(normalized, str) or not normalized:
            raise JComicParseError("jcomic URL 解析失败")
        return normalized

    @classmethod
    def _book_url_from_href(cls, href: str, *, domain: str | None = None) -> str:
        normalized = cls._normalize_url(href, domain=domain)
        return normalized.replace("/page/", "/eps/", 1)

    @classmethod
    def _page_url_from_href(cls, href: str, *, domain: str | None = None) -> str:
        normalized = cls._normalize_url(href, domain=domain)
        return normalized.replace("/eps/", "/page/", 1)

    @classmethod
    def parse_search_item(cls, target, *, domain: str | None = None):
        href = target.xpath("./a[1]/@href").get()
        title_text = target.xpath(".//*[contains(@class, 'comic-title')]/text()").get()
        cover = target.xpath(".//*[contains(@class, 'comic-thumb')]/@src").get()
        date_text = target.xpath(".//*[contains(@class, 'comic-date')]/text()").get()
        list_links = target.xpath(".//*[contains(@class, 'list-content')]/a")
        if not href or not title_text:
            raise JComicParseError("jcomic 列表条目缺少标题或链接")
        title, pages = cls._strip_title_count(title_text)
        tags = [text.strip() for text in list_links.xpath("string(.)").getall() if text.strip()]
        artist = tags[0] if tags else None
        return JComicBookInfo(
            name=title, preview_url=cls._book_url_from_href(href, domain=domain), url=cls._book_url_from_href(href, domain=domain),
            pages=pages, artist=artist, tags=tags[1:],
            public_date=str(date_text or "").replace("最後更新:", "").strip() or None,
            img_preview=cls._normalize_url(cover, domain=domain) if cover else None,
        ).get_id(href)

    @classmethod
    def parse_preview_books(cls, html_text: str, *, domain: str | None = None) -> list[JComicBookInfo]:
        card_xpath = (
            "//div[contains(@class, 'container')]"
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' col-lg-4 ')]"
        )
        targets = cls._selector(html_text).xpath(card_xpath)
        if not targets:
            raise JComicParseError("jcomic 列表页未解析到作品卡片")
        books = []
        for idx, target in enumerate(targets, start=1):
            book = cls.parse_search_item(target, domain=domain)
            book.idx = idx
            books.append(book)
        return books

    @classmethod
    def parse_book(cls, html_text: str, *, request_url: str | None = None, domain: str | None = None) -> JComicBookInfo:
        doc = cls._selector(html_text)
        title_text = doc.xpath("normalize-space(//p[contains(@class, 'comic-title')][1])").get()
        if not title_text:
            title_text = doc.xpath("normalize-space(//h1[1])").get()
        if not title_text:
            raise JComicParseError("jcomic 书页未解析到标题")
        title, pages = cls._strip_title_count(title_text)
        cover = doc.xpath("(//img[contains(@class, 'comic-thumb')]/@src)[1]").get()
        tag_texts = doc.xpath("//p[contains(@class, 'comic-category')]/following-sibling::a/text()").getall()
        tags = [text.strip() for text in tag_texts if text.strip()]
        artist = doc.xpath("normalize-space(//p[contains(@class, 'comic-author')]/following-sibling::a[1])").get() or None
        page_links = cls.parse_chapter_links(html_text, domain=domain)
        url = cls._book_url_from_href(request_url or doc.xpath("(//a[contains(@href, '/eps/')]/@href)[1]").get(), domain=domain)
        return JComicBookInfo(
            name=title, preview_url=url, url=url, pages=pages, artist=artist, tags=tags,
            img_preview=cls._normalize_url(cover, domain=domain) if cover else None, page_links=page_links,
        ).get_id(url)

    @classmethod
    def parse_chapter_links(cls, html_text: str, *, domain: str | None = None) -> list[dict]:
        doc = cls._selector(html_text)
        anchors = doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' col-md-6 ')][2]//a[contains(@href, '/page/')]")
        if not anchors:
            page_href = doc.xpath("(//a[contains(@href, '/eps/')]/@href)[1]").get()
            if page_href and doc.xpath("//img[contains(@class, 'comic-thumb')]/@src").getall():
                return [{"url": cls._page_url_from_href(page_href, domain=domain), "name": "单章节"}]
            raise JComicParseError("jcomic 书页未解析到章节链接")
        links = []
        for anchor in anchors:
            href = anchor.xpath("./@href").get()
            name = anchor.xpath("normalize-space(.)").get()
            if not href:
                raise JComicParseError("jcomic 章节条目缺少链接")
            links.append({"url": cls._page_url_from_href(href, domain=domain), "name": name or "未命名章节"})
        return links

    @classmethod
    def parse_page_urls_from_html(cls, html_text: str) -> list[str]:
        doc = cls._selector(html_text)
        image_srcs = doc.xpath("//div[contains(@class, 'container')]//img[contains(@class, 'comic-thumb')]/@src").getall()
        urls = [url.strip() for url in image_srcs if url.strip()]
        urls = [url for url in urls if "jcomic-content" in url or "cloudflarestorage.com" in url]
        if not urls:
            raise JComicParseError("jcomic 图片页未解析到图片 URL")
        return urls

    @classmethod
    def build_search_url(cls, keyword: str, *, page: int = 1, domain: str | None = None, mappings: dict | None = None) -> str:
        page = max(1, int(page or 1))
        merged = cls.merge_search_mappings(cls.mappings, mappings)
        if keyword in merged:
            base = cls.normalize_preview_resource(merged[keyword], domain=domain or cls.domain)
            return re.sub(r"/\d+$", f"/{page}", str(base))
        return f"{cls.preview_origin(domain or cls.domain)}/search/{quote(keyword, safe='')}/{page}"


class JComicReqer(_JComicContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf, follow_redirects=True, timeout=12, verify=False)

    def test_index(self):
        try:
            resp = self.cli.get(self.index, timeout=6)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        url = owner.parser.build_search_url(keyword, page=page, domain=domain, mappings=site_kw.get("custom_map"))
        resp = await self.ensure_preview_client().get(url, headers=self.headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(owner.parser.parse_preview_books, resp.text, domain=domain)

    async def preview_fetch_episodes(self, book):
        return [book]


class JComicUtils(_JComicContract, EroUtils, Previewer):
    parser = JComicParser
    reqer_cls = JComicReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": cls.headers, "follow_redirects": True}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"verify": False, "retries": 1}
