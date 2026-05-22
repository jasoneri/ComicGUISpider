from __future__ import annotations

import asyncio
import re
from urllib.parse import quote

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.info import Episode, Mh1234BookInfo


class _Mh1234Contract:
    name = "mh1234"
    proxy_policy = "direct"
    domain = "m.wmh1234.com"
    index = f"https://{domain}"
    popular = f"{index}/category/order/hits"
    update = f"{index}/category/order/addtime"
    search_url_head = f"{index}/search/"
    mappings = {
        res.SPIDER.Completer.index: popular,
        res.SPIDER.Completer.popular: popular,
        res.SPIDER.Completer.update: update,
    }
    ua_value = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    )
    headers = {
        "User-Agent": ua_value,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    }
    book_hea = headers
    image_ua = {
        "User-Agent": headers["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": headers["Accept-Language"],
    }


class Mh1234Parser(_Mh1234Contract, Previewer):
    # Cross-checked with Keiyoushi zh/mh1234 MH1234.kt, Apache-2.0, commit 5d33d04c61b7ad4da05f148feecbab169f54dc64.
    _book_id_re = re.compile(r"/comic/(?P<book_id>\d+)\.html")
    _episode_id_re = re.compile(r"/comic/(?P<book_id>\d+)/(?P<episode_id>\d+)\.html")
    _status_xpath = (
        "//*[contains(@class,'stat-item')][.//*[contains(text(),'状态')]]"
        "//*[contains(@class,'stat-value')]/text()"
    )

    @classmethod
    def normalize_site_resource(cls, value: str | None, *, domain: str | None = None) -> str | None:
        return cls.normalize_preview_resource(value, domain=domain or cls.domain)

    @staticmethod
    def _clean_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def _clean_node_text(cls, node, xpath: str = ".//text()") -> str:
        return cls._clean_text("".join(node.xpath(xpath).getall()))

    @classmethod
    def parse_book_id(cls, url: str) -> str:
        matched = cls._book_id_re.search(url or "")
        if not matched:
            raise ValueError(f"mh1234 book url missing /comic/<id>.html shape: {url!r}")
        return matched.group("book_id")

    @classmethod
    def parse_episode_id(cls, url: str) -> str:
        matched = cls._episode_id_re.search(url or "")
        if not matched:
            raise ValueError(f"mh1234 episode url missing /comic/<book>/<chapter>.html shape: {url!r}")
        return f"{matched.group('book_id')}-{matched.group('episode_id')}"

    @classmethod
    def _new_book(cls, *, idx: int, url: str) -> Mh1234BookInfo:
        return Mh1234BookInfo(idx=idx, render_keys=["name", "latest_sec"], url=url, preview_url=url)

    @classmethod
    def parse_list_item(cls, node, *, idx: int, domain: str) -> Mh1234BookInfo:
        href = node.css("a.comic-card__link::attr(href)").get()
        if not href:
            raise ValueError(f"mh1234 list card missing href: idx={idx}")
        url = cls.normalize_site_resource(href, domain=domain)
        book = cls._new_book(idx=idx, url=url)
        book.id = cls.parse_book_id(url)
        book.name = cls._clean_node_text(node, ".//*[contains(@class,'comic-card__title')]//text()")
        if not book.name:
            raise ValueError(f"mh1234 list card missing title: idx={idx} href={href!r}")
        latest = cls._clean_node_text(node, ".//*[contains(@class,'comic-card__chapter')]//text()")
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        image = node.css("img.comic-card__image")
        cover = image.css("::attr(data-src)").get() or image.css("::attr(src)").get()
        book.img_preview = cls.normalize_site_resource(cover, domain=domain) if cover else None
        return book

    @classmethod
    def parse_list_document(cls, html_text: str, *, domain: str) -> list[Mh1234BookInfo]:
        sel = Selector(text=html_text)
        cards = sel.css(".comic-card")
        if len(cards) == 0:
            raise ValueError("mh1234 list page missing .comic-card results")
        return [cls.parse_list_item(card, idx=idx, domain=domain) for idx, card in enumerate(cards, start=1)]

    @classmethod
    def parse_search_document(cls, html_text: str, *, domain: str) -> list[Mh1234BookInfo]:
        sel = Selector(text=html_text)
        cards = sel.css(".comic-card")
        if len(cards) == 0 and not sel.css(".search, .search-result, .comic-grid").get():
            raise ValueError("mh1234 search page missing result container")
        return [cls.parse_list_item(card, idx=idx, domain=domain) for idx, card in enumerate(cards, start=1)]

    @classmethod
    def parse_book(cls, html_text: str, book: Mh1234BookInfo, *, domain: str) -> Mh1234BookInfo:
        sel = Selector(text=html_text)
        title = cls._clean_text(sel.css(".comic-hero__title::text, h1::text").get())
        if not title:
            raise ValueError(f"mh1234 book page missing title: url={book.url}")
        book.name = title
        meta = [cls._clean_text(text) for text in sel.css(".comic-hero__meta .meta-item::text").getall()]
        meta = [text for text in meta if text]
        if meta:
            book.artist = meta[0]
        if len(meta) > 1:
            book.tags = meta[1:]
        status = cls._clean_text(sel.xpath(cls._status_xpath).get())
        if status:
            book.btype = status
        description = cls._clean_text(sel.css("#comicDesc::text").get())
        if description:
            book.description = description
        cover = sel.css(".comic-hero__cover img::attr(src), .comic-hero__bg::attr(data-bg)").get()
        book.img_preview = cls.normalize_site_resource(cover, domain=domain) if cover else book.img_preview
        book.episodes = cls.parse_episodes(html_text, book, domain=domain)
        return book

    @classmethod
    def parse_episodes(cls, html_text: str, book: Mh1234BookInfo, *, domain: str) -> list[Episode]:
        sel = Selector(text=html_text)
        rows = sel.css(".chapter-list a.chapter-item[href]")
        episodes = []
        for row in rows:
            href = row.css("::attr(href)").get()
            if not href or not cls._episode_id_re.search(href):
                continue
            name = cls._clean_node_text(row, ".//*[contains(@class,'chapter-title')]//text()")
            if not name:
                raise ValueError(f"mh1234 chapter row missing title: book={book.url} href={href!r}")
            url = cls.normalize_site_resource(href, domain=domain)
            episode = Episode(from_book=book, id=cls.parse_episode_id(url), idx=len(episodes) + 1, url=url, name=name)
            episode.chapter_referer = url
            episodes.append(episode)
        if not episodes:
            raise ValueError(f"mh1234 chapter list returned no readable chapters: book={book.url}")
        return episodes

    @classmethod
    def parse_page_urls_from_html(cls, html_text: str, *, section_url: str, domain: str) -> list[str]:
        sel = Selector(text=html_text)
        urls = []
        for image in sel.css("img.reader-image"):
            raw_url = image.css("::attr(data-src)").get() or image.css("::attr(src)").get()
            url = cls.normalize_site_resource(raw_url, domain=domain)
            if url and "placeholder.svg" not in url:
                urls.append(url)
        if not urls:
            raise ValueError(f"mh1234 reader page returned no img.reader-image urls: url={section_url}")
        return urls


class Mh1234Reqer(_Mh1234Contract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def build_search_url(cls, keyword: str, *, domain: str, custom_map: dict | None = None, page: int = 1) -> str:
        keyword = keyword.strip()
        page = max(1, int(page or 1))
        mappings = Previewer.merge_search_mappings(cls.mappings, custom_map)
        if keyword in mappings:
            url = Previewer.normalize_preview_resource(mappings[keyword], domain=domain)
        else:
            url = f"https://{domain}/search/{quote(keyword)}"
        return url if page == 1 else f"{url}/page/{page}"

    @classmethod
    def is_mapped_search_keyword(cls, keyword: str, *, custom_map: dict | None = None) -> bool:
        return keyword.strip() in Previewer.merge_search_mappings(cls.mappings, custom_map)

    def test_index(self):
        try:
            resp = self.cli.head(self.index, headers=self.headers, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    async def _fetch_text(self, url: str, *, headers: dict | None = None):
        resp = await self.ensure_preview_client().get(url, headers=headers or self.headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return resp

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        custom_map = site_kw.get("custom_map")
        url = self.build_search_url(keyword, domain=domain, custom_map=custom_map, page=page)
        resp = await self._fetch_text(url)
        mapped_keyword = self.is_mapped_search_keyword(keyword, custom_map=custom_map)
        parser = owner.parser.parse_list_document if mapped_keyword else owner.parser.parse_search_document
        return await asyncio.to_thread(parser, resp.text, domain=domain)

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        domain = self.preview_site_kwargs().get("domain") or getattr(self, "domain", None) or type(owner).domain
        resp = await self._fetch_text(book.url)
        parsed = await asyncio.to_thread(owner.parser.parse_book, resp.text, book, domain=domain)
        return parsed.episodes

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        domain = self.preview_site_kwargs().get("domain") or getattr(self, "domain", None) or type(owner).domain
        referer = getattr(episode.from_book, "preview_url", None) or getattr(episode.from_book, "url", None) or self.index
        resp = await self._fetch_text(episode.url, headers={**self.headers, "Referer": referer})
        urls = await asyncio.to_thread(owner.parser.parse_page_urls_from_html, resp.text, section_url=str(resp.url), domain=domain)
        episode.pages = len(urls)
        episode.page_urls = list(urls)
        episode.chapter_referer = str(resp.url)
        return urls


class Mh1234Utils(_Mh1234Contract, Utils, Previewer):
    parser = Mh1234Parser
    reqer_cls = Mh1234Reqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def get_uuid(cls, info, only_id=False):
        try:
            identity = cls.parser.parse_book_id(str(info))
        except ValueError:
            identity = str(info).strip()
        return identity if only_id else f"{cls.name}-{identity}"

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": cls.headers}
