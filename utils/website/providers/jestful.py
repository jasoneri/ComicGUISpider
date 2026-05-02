from __future__ import annotations

import asyncio
import json
import re
import secrets
import string
from urllib.parse import urlencode, urlparse

import httpx
from scrapy import Selector

from utils.website.core import Previewer, Req, Utils
from utils.website.info import Episode, JestfulBookInfo


class _JestfulContract:
    name = "jestful"
    proxy_policy = "direct"
    domain = "jestful.net"
    index = f"https://{domain}/"
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
        "Connection": "keep-alive",
    }
    book_hea = ua
    image_ua = {
        "User-Agent": ua["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": ua["Accept-Language"],
        "Connection": "keep-alive",
    }
    _search_sort = "views"
    _search_sort_type = "DESC"
    _random_alphabet = string.ascii_letters + string.digits


class JestfulParser(_JestfulContract, Previewer):
    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def _new_book(cls, *, idx: int, url: str) -> JestfulBookInfo:
        return JestfulBookInfo(
            idx=idx,
            render_keys=["name", "latest_sec"],
            url=url,
            preview_url=url,
        )

    @classmethod
    def parse_search_document(cls, html_text: str, *, domain: str) -> list[JestfulBookInfo]:
        sel = Selector(text=html_text)
        cards = sel.css("div.thumb-wrapper[data-id]")
        books = []
        for idx, card in enumerate(cards, start=1):
            href = card.xpath("./a[@href][1]/@href").get()
            if not href:
                raise ValueError(f"jestful search card missing owner href: idx={idx}")
            book_url = cls.normalize_preview_resource(href, domain=domain)
            book = cls._new_book(idx=idx, url=book_url)
            book.id = cls._normalize_text(card.xpath("./@data-id").get())
            book.name = cls._normalize_text(
                card.xpath("../div[contains(@class,'series-title')][1]//h3[contains(@class,'title-thumb')]/text()").get()
            )
            if not book.name:
                raise ValueError(f"jestful search card missing title: idx={idx} href={href}")
            latest_text = cls._normalize_text(card.xpath(".//a[contains(@class,'btn-danger')]/text()").get())
            book.latest_sec = latest_text
            cover = cls._normalize_text(card.xpath(".//div[contains(@class,'content')]/@data-bg").get())
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain) if cover else None
            books.append(book)
        return books

    @staticmethod
    def _suggest_book_path(onclick_text: str) -> str:
        matched = re.search(r"/(hwms-[^'\"/?#]+\.html)", onclick_text or "")
        if not matched:
            raise ValueError(f"jestful suggest item onclick missing owner path: onclick={onclick_text!r}")
        return matched.group(1)

    @classmethod
    def parse_search_suggest(cls, payload: str, *, domain: str) -> list[JestfulBookInfo]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("jestful search suggest payload is not valid JSON") from exc
        if not isinstance(data, list):
            raise TypeError(f"jestful search suggest payload must be list, got {type(data).__name__}")

        books = []
        for group in data:
            if not isinstance(group, dict):
                raise TypeError(f"jestful search suggest group must be dict, got {type(group).__name__}")
            entries = group.get("data", [])
            if not isinstance(entries, list):
                raise TypeError(f"jestful search suggest group.data must be list, got {type(entries).__name__}")
            for item in entries:
                if not isinstance(item, dict):
                    raise TypeError(f"jestful search suggest item must be dict, got {type(item).__name__}")
                book_path = cls._suggest_book_path(str(item.get("onclick") or ""))
                book_url = cls.normalize_preview_resource(book_path, domain=domain)
                book = cls._new_book(idx=len(books) + 1, url=book_url)
                book.name = cls._normalize_text(str(item.get("primary") or ""))
                if not book.name:
                    raise ValueError(f"jestful suggest item missing primary: {item!r}")
                book.latest_sec = cls._normalize_text(str(item.get("secondary") or ""))
                cover = cls._normalize_text(str(item.get("image") or ""))
                book.img_preview = cls.normalize_preview_resource(cover, domain=domain) if cover else None
                books.append(book)
        return books

    @classmethod
    def parse_book_owner_state(cls, html_text: str, *, owner_url: str) -> dict:
        data_l_match = re.search(r"""var\s+dataL\s*=\s*["']([^"']+)["']""", html_text)
        if not data_l_match:
            raise ValueError(f"jestful book owner page missing dataL: url={owner_url}")
        loader_slug = cls._normalize_text(data_l_match.group(1))
        if not loader_slug:
            raise ValueError(f"jestful book owner page returned empty dataL: url={owner_url}")

        sel = Selector(text=html_text)
        latest_href = sel.css("a.btn.btn-danger.btn-md[target='_blank']::attr(href)").get()
        latest_sec = cls._normalize_text(sel.css("a.btn.btn-danger.btn-md[target='_blank']::text").get())
        manga_id_match = re.search(r"cont\.pop\.php\?action=pop&id=(\d+)", html_text)

        return {
            "loader_slug": loader_slug,
            "latest_href": latest_href,
            "latest_sec": latest_sec,
            "manga_id": manga_id_match.group(1) if manga_id_match else None,
            "has_chapter_panel": bool(sel.css("#list-chapter")),
        }

    @classmethod
    def parse_episodes_from_list_html(cls, html_text: str, book: JestfulBookInfo, *, domain: str) -> list[Episode]:
        sel = Selector(text=html_text)
        rows = sel.css("a.chapter[href]")
        if not rows:
            raise ValueError(f"jestful chapter-list payload returned no chapters: book={book.url}")
        episodes = []
        for idx, row in enumerate(rows, start=1):
            href = cls._normalize_text(row.xpath("./@href").get())
            if not href:
                raise ValueError(f"jestful chapter-list row missing href: idx={idx} book={book.url}")
            ep_url = cls.normalize_preview_resource(href, domain=domain)
            name = cls._normalize_text("".join(row.xpath(".//text()").getall())) or cls._normalize_text(
                row.xpath("./@title").get()
            )
            if not name:
                raise ValueError(f"jestful chapter-list row missing chapter title: idx={idx} href={href}")
            ep = Episode(
                from_book=book,
                id=href.strip("/"),
                idx=idx,
                url=ep_url,
                name=name,
            )
            ep.chapter_referer = ep.url
            episodes.append(ep)
        return episodes

    @staticmethod
    def parse_chapter_image_cid(html_text: str, *, chapter_url: str) -> str:
        target = re.search(
            r"""load_image\(\s*['"]?([^,'"()\s]+)['"]?\s*,\s*['"]list-imga['"]\s*\)""",
            html_text,
        )
        if not target:
            raise ValueError(f"jestful chapter page missing load_image(cid, 'list-imga'): url={chapter_url}")
        cid = str(target.group(1)).strip()
        if not cid:
            raise ValueError(f"jestful chapter page returned empty cid: url={chapter_url}")
        return cid

    @classmethod
    def parse_iog_image_urls(cls, html_text: str, *, request_url: str) -> list[str]:
        sel = Selector(text=html_text)
        urls = []
        for raw_url in sel.css("img.chapter-img::attr(src)").getall():
            normalized = cls._normalize_text(raw_url)
            if normalized:
                urls.append(normalized)
        if not urls:
            raise ValueError(f"jestful iog payload returned no img.chapter-img urls: url={request_url}")
        return urls


class JestfulReqer(_JestfulContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @staticmethod
    def _split_domain(domain: str | None) -> tuple[str, str]:
        candidate = (domain or "").strip()
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = (parsed.netloc or parsed.path).strip().rstrip("/")
        if not host:
            raise ValueError("jestful domain is required")
        origin = f"{parsed.scheme or 'https'}://{host}"
        return host, origin

    def _preview_domain(self) -> tuple[str, str]:
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        return self._split_domain(domain)

    @classmethod
    def _random_token(cls, length: int) -> str:
        return "".join(secrets.choice(cls._random_alphabet) for _ in range(length))

    @classmethod
    def build_search_document_url(cls, keyword: str, *, page: int, domain: str) -> str:
        if page <= 1:
            return f"https://{domain}/manga-list.html?name={keyword}"
        params = {
            "listType": "pagination",
            "page": str(page),
            "artist": "",
            "author": "",
            "group": "",
            "m_status": "",
            "name": keyword,
            "genre": "",
            "ungenre": "",
            "sort": cls._search_sort,
            "sort_type": cls._search_sort_type,
        }
        return f"https://{domain}/manga-list.html?{urlencode(params)}"

    @staticmethod
    def build_search_suggest_url(keyword: str, *, domain: str) -> str:
        return f"https://{domain}/app/manga/controllers/search.single.php?q={keyword}"

    @classmethod
    def build_lstc_url(cls, slug: str, *, domain: str) -> str:
        return f"https://{domain}/{cls._random_token(25)}.lstc?slug={slug}"

    @classmethod
    def build_iog_url(cls, cid: str, *, domain: str) -> str:
        return f"https://{domain}/{cls._random_token(30)}.iog?cid={cid}"

    @classmethod
    def build_lstc_headers(cls, *, referer: str) -> dict[str, str]:
        return {
            **cls.ua,
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        }

    @classmethod
    def build_iog_headers(cls, *, referer: str) -> dict[str, str]:
        return {
            **cls.ua,
            "Accept": "*/*",
            "Referer": referer,
        }

    @classmethod
    def build_suggest_headers(cls, *, origin: str) -> dict[str, str]:
        return {
            **cls.ua,
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{origin}/",
        }

    def test_index(self):
        try:
            _, origin = self._split_domain(getattr(self, "domain", None) or self.domain)
            resp = self.cli.head(
                f"{origin}/",
                headers={"User-Agent": self.ua["User-Agent"]},
                follow_redirects=True,
                timeout=3.5,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        domain, origin = self._preview_domain()
        page = max(1, int(page or 1))

        doc_url = self.build_search_document_url(keyword.strip(), page=page, domain=domain)
        resp = await self.ensure_preview_client().get(
            doc_url,
            headers=self.ua,
            follow_redirects=True,
            timeout=12,
        )
        resp.raise_for_status()
        books = await asyncio.to_thread(owner.parser.parse_search_document, resp.text, domain=domain)
        if books or page > 1:
            return books

        suggest_url = self.build_search_suggest_url(keyword.strip(), domain=domain)
        suggest_resp = await self.ensure_preview_client().get(
            suggest_url,
            headers=self.build_suggest_headers(origin=origin),
            follow_redirects=True,
            timeout=12,
        )
        suggest_resp.raise_for_status()
        return await asyncio.to_thread(owner.parser.parse_search_suggest, suggest_resp.text, domain=domain)

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        domain, _ = self._preview_domain()

        owner_resp = await self.ensure_preview_client().get(
            book.url,
            headers=self.ua,
            follow_redirects=True,
            timeout=12,
        )
        owner_resp.raise_for_status()
        owner_url = str(owner_resp.url)
        owner_state = await asyncio.to_thread(owner.parser.parse_book_owner_state, owner_resp.text, owner_url=owner_url)
        book.loader_slug = owner_state["loader_slug"]
        book.manga_id = owner_state["manga_id"]
        if owner_state.get("latest_sec"):
            book.latest_sec = owner_state["latest_sec"]

        chapter_url = self.build_lstc_url(owner_state["loader_slug"], domain=domain)
        chapter_resp = await self.ensure_preview_client().get(
            chapter_url,
            headers=self.build_lstc_headers(referer=owner_url),
            follow_redirects=True,
            timeout=12,
        )
        chapter_resp.raise_for_status()
        return await asyncio.to_thread(
            owner.parser.parse_episodes_from_list_html,
            chapter_resp.text,
            book,
            domain=domain,
        )

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        domain, _ = self._preview_domain()

        chapter_resp = await self.ensure_preview_client().get(
            episode.url,
            headers=self.ua,
            follow_redirects=True,
            timeout=12,
        )
        chapter_resp.raise_for_status()
        chapter_url = str(chapter_resp.url)
        cid = await asyncio.to_thread(owner.parser.parse_chapter_image_cid, chapter_resp.text, chapter_url=chapter_url)

        iog_url = self.build_iog_url(cid, domain=domain)
        iog_resp = await self.ensure_preview_client().get(
            iog_url,
            headers=self.build_iog_headers(referer=chapter_url),
            follow_redirects=True,
            timeout=12,
        )
        iog_resp.raise_for_status()
        urls = await asyncio.to_thread(owner.parser.parse_iog_image_urls, iog_resp.text, request_url=str(iog_resp.url))
        episode.pages = len(urls)
        episode.page_urls = list(urls)
        episode.chapter_referer = chapter_url
        return urls


class JestfulUtils(_JestfulContract, Utils, Previewer):
    parser = JestfulParser
    reqer_cls = JestfulReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {
            "headers": cls.ua,
        }
