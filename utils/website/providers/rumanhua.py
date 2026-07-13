from __future__ import annotations

import asyncio
import base64
import codecs
import json
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.info import Episode, RumanhuaBookInfo


@dataclass(frozen=True, slots=True)
class _ChapterCandidate:
    url: str
    name: str


class _PackedScriptDecoder:
    _packed_re = re.compile(
        r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(?P<source>.*?)',(?P<radix>\d+),(?P<count>\d+),"
        r"'(?P<dictionary>.*?)'\.split\('\|'\),0,\{\}\)\)",
        re.S,
    )

    def __init__(self, html_text: str, *, chapter_url: str):
        self.html_text = html_text
        self.chapter_url = chapter_url

    @staticmethod
    def _decode_js_string(value: str) -> str:
        return codecs.decode(value, "unicode_escape")

    @staticmethod
    def _encode_unpack_token(index: int, radix: int) -> str:
        if index == 0:
            return "0"
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        token = ""
        while index:
            index, remainder = divmod(index, radix)
            token = (chr(remainder + 29) if remainder > 35 else chars[remainder]) + token
        return token

    def unpack(self) -> str:
        match = self._packed_re.search(self.html_text)
        if not match:
            raise ValueError(f"rumanhua chapter page missing packed eval payload: url={self.chapter_url}")
        source = self._decode_js_string(match.group("source"))
        radix = int(match.group("radix"))
        count = int(match.group("count"))
        dictionary_text = self._decode_js_string(match.group("dictionary"))
        dictionary = dictionary_text.split("|")
        unpacked = source
        for index in range(count - 1, -1, -1):
            if index < len(dictionary) and dictionary[index]:
                token = self._encode_unpack_token(index, radix)
                unpacked = re.sub(r"\b" + re.escape(token) + r"\b", dictionary[index], unpacked)
        return unpacked


class _ReaderPageDecoder:
    _reader_id_re = re.compile(r'data-id="(?P<reader_id>\d+)"')
    _payload_re = re.compile(r'var\s+__c0rst96="(?P<payload>[^"]+)"')
    _keys = {
        0: "smkhy258",
        1: "smkd95fv",
        2: "md496952",
        3: "cdcsdwq",
        4: "vbfsa256",
        5: "cawf151c",
        6: "cd56cvda",
        7: "8kihnt9",
        8: "dso15tlo",
        9: "5ko6plhy",
    }

    def __init__(self, html_text: str, *, chapter_url: str):
        self.html_text = html_text
        self.chapter_url = chapter_url

    def _reader_key(self) -> bytes:
        matched = self._reader_id_re.search(self.html_text)
        if not matched:
            raise ValueError(f"rumanhua chapter page missing readerContainer data-id: url={self.chapter_url}")
        reader_id = int(matched.group("reader_id"))
        key = self._keys.get(reader_id)
        if key is None:
            raise ValueError(f"rumanhua chapter page uses unsupported reader key index {reader_id}: url={self.chapter_url}")
        return key.encode()

    def _encrypted_payload(self) -> str:
        unpacked = _PackedScriptDecoder(self.html_text, chapter_url=self.chapter_url).unpack()
        matched = self._payload_re.search(unpacked)
        if not matched:
            raise ValueError(f"rumanhua unpacked reader script missing __c0rst96 payload: url={self.chapter_url}")
        return matched.group("payload")

    def decode(self) -> list[str]:
        key = self._reader_key()
        payload = bytearray(base64.b64decode(self._encrypted_payload()))
        for index in range(len(payload)):
            payload[index] ^= key[index % len(key)]
        decoded = base64.b64decode(bytes(payload)).decode("utf-8")
        image_urls = json.loads(decoded)
        if not isinstance(image_urls, list) or not image_urls:
            raise TypeError(f"rumanhua reader payload must be a non-empty list, got {type(image_urls).__name__}")
        normalized = [str(url).strip() for url in image_urls]
        if not all(normalized):
            raise ValueError(f"rumanhua reader payload contains empty image urls: url={self.chapter_url}")
        return normalized


class _RumanhuaContract:
    # Cross-checked with Keiyoushi zh/rumanhua + lib-multisrc/mmlook, Apache-2.0,
    # commit bc300198a7746b21bcf43040da41cfcd7421e1c1.
    name = "rumanhua"
    proxy_policy = "direct"
    domain = "www.rumanhua2.com"
    mobile_domain = "m.rumanhua2.com"
    index = f"https://{domain}/"
    popular = f"https://{domain}/rank/1"
    update = f"https://{domain}/rank/5"
    search_url = f"https://{domain}/s"
    morechapter_url = f"https://{domain}/morechapter"
    mappings = {
        res.SPIDER.Completer.index: popular,
        res.SPIDER.Completer.update: update,
    }
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    headers = ua
    book_hea = ua
    image_ua = {
        "User-Agent": ua["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": ua["Accept-Language"],
    }


class RumanhuaParser(_RumanhuaContract, Previewer):
    @staticmethod
    def _clean_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def _clean_node_text(cls, node, xpath: str = ".//text()") -> str:
        return cls._clean_text("".join(node.xpath(xpath).getall()))

    @classmethod
    def normalize_book_resource(cls, value: str | None) -> str | None:
        return cls.normalize_preview_resource(value, domain=cls.domain)

    @classmethod
    def normalize_chapter_resource(cls, value: str | None) -> str | None:
        return cls.normalize_preview_resource(value, domain=cls.mobile_domain)

    @classmethod
    def parse_book_slug(cls, url: str) -> str:
        parts = [part for part in urlparse(str(url or "")).path.split("/") if part]
        if not parts:
            raise ValueError(f"rumanhua url missing book slug: {url!r}")
        return parts[0]

    @classmethod
    def parse_chapter_id(cls, url: str) -> str:
        parts = [part for part in urlparse(str(url or "")).path.split("/") if part]
        if len(parts) < 2 or not parts[1].endswith(".html"):
            raise ValueError(f"rumanhua url missing chapter id: {url!r}")
        return parts[1].removesuffix(".html")

    @classmethod
    def _new_book(cls, *, idx: int, url: str, render_keys: list[str] | None = None) -> RumanhuaBookInfo:
        return RumanhuaBookInfo(
            idx=idx,
            render_keys=render_keys or ["name", "latest_sec"],
            url=url,
            preview_url=url,
            source=cls.name,
        )

    @classmethod
    def _apply_latest(cls, book: RumanhuaBookInfo, value: str | None):
        latest = cls._clean_text(value)
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        return latest

    @classmethod
    def _rank_books(cls, html_text: str) -> list[RumanhuaBookInfo]:
        sel = Selector(text=html_text)
        cards = sel.css("div.wholike div.likedata")
        if len(cards) == 0:
            raise ValueError("rumanhua rank page returned no likedata cards")
        books = []
        for idx, card in enumerate(cards, start=1):
            href = cls._clean_text(card.xpath(".//div[contains(@class,'likeimg')]//a[1]/@href").get())
            if not href:
                raise ValueError(f"rumanhua rank card missing href: idx={idx}")
            book_url = cls.normalize_book_resource(href)
            book = cls._new_book(idx=idx, url=book_url)
            book.id = cls.parse_book_slug(book_url)
            book.name = cls._clean_text(card.xpath(".//p[contains(@class,'le-t')][1]/text()").get())
            if not book.name:
                raise ValueError(f"rumanhua rank card missing title: idx={idx} href={href}")
            author_text = cls._clean_text(card.xpath(".//div[contains(@class,'likeinfo')]/p[1]/text()").get())
            latest_text = cls._clean_text(card.xpath(".//div[contains(@class,'likeinfo')]/p[2]/text()").get())
            if author_text.startswith("作者："):
                book.artist = cls._clean_text(author_text.removeprefix("作者：")) or None
            if latest_text.startswith("最新："):
                cls._apply_latest(book, latest_text.removeprefix("最新："))
            cover = cls._clean_text(card.xpath(".//img[1]/@data-src").get() or card.xpath(".//img[1]/@src").get())
            book.img_preview = cls.normalize_book_resource(cover) if cover else None
            description = cls._clean_text(card.xpath(".//p[contains(@class,'le-j')][1]/text()").get())
            if description:
                book.description = description
            books.append(book)
        return books

    @classmethod
    def parse_index_books(cls, html_text: str) -> list[RumanhuaBookInfo]:
        return cls._rank_books(html_text)

    @classmethod
    def parse_update_books(cls, html_text: str) -> list[RumanhuaBookInfo]:
        return cls._rank_books(html_text)

    @classmethod
    def parse_search_document(cls, html_text: str) -> list[RumanhuaBookInfo]:
        sel = Selector(text=html_text)
        cards = sel.css("div.item-data div.col-auto")
        if len(cards) == 0 and not sel.xpath("//*[contains(text(), '相关') and contains(text(), '结果')]").get():
            raise ValueError("rumanhua search page missing result container")
        books = []
        for idx, card in enumerate(cards, start=1):
            href = cls._clean_text(card.xpath("./a[1]/@href").get())
            if not href:
                raise ValueError(f"rumanhua search card missing href: idx={idx}")
            book_url = cls.normalize_book_resource(href)
            book = cls._new_book(idx=idx, url=book_url, render_keys=["name", "artist"])
            book.id = cls.parse_book_slug(book_url)
            book.name = cls._clean_text(card.xpath(".//p[contains(@class,'e-title')][1]/text()").get())
            if not book.name:
                raise ValueError(f"rumanhua search card missing title: idx={idx} href={href}")
            book.artist = cls._clean_text(card.xpath(".//p[contains(@class,'tip')][1]/text()").get()) or None
            cover = cls._clean_text(card.xpath(".//img[1]/@data-src").get() or card.xpath(".//img[1]/@src").get())
            book.img_preview = cls.normalize_book_resource(cover) if cover else None
            books.append(book)
        return books

    @classmethod
    def parse_book_state(cls, html_text: str, book: RumanhuaBookInfo, *, request_url: str):
        sel = Selector(text=html_text)
        title = cls._clean_text(sel.css("div.comicInfo h1.name_mh::text").get())
        if not title:
            raise ValueError(f"rumanhua book page missing title: url={request_url}")
        book.id = cls.parse_book_slug(request_url)
        book.url = request_url
        book.preview_url = request_url
        book.name = title
        cover = cls._clean_text(
            sel.css("div.comicInfo div.mhcover img::attr(data-src)").get()
            or sel.css("div.comicInfo div.mhcover img::attr(src)").get()
        )
        if cover:
            book.img_preview = cls.normalize_book_resource(cover)
        for span in sel.css("div.comicInfo div.detinfo span"):
            text = cls._clean_node_text(span)
            if text.startswith("作 者："):
                book.artist = cls._clean_text(text.removeprefix("作 者：")) or None
            elif text.startswith("更新时间："):
                book.public_date = cls._clean_text(text.removeprefix("更新时间：")) or None
            elif text.startswith("标 签："):
                tags_text = cls._clean_text(text.removeprefix("标 签："))
                book.tags = [tag for tag in tags_text.split(" ") if tag]
            elif text.startswith("状 态："):
                book.btype = cls._clean_text(text.removeprefix("状 态：")) or None
        description = cls._clean_text(sel.css("div.comicInfo p.content::text").get())
        if description:
            book.description = description
        latest = cls._clean_text(sel.css("meta[property='og:novel:latest_chapter_name']::attr(content)").get())
        if not latest:
            latest = cls._clean_text(sel.css("div.comicInfo div.himg a::text").get())
        cls._apply_latest(book, latest)
        chapters = []
        for row in sel.css("div.chapterlistload ul a[href]"):
            href = cls._clean_text(row.xpath("./@href").get())
            if not href:
                raise ValueError(f"rumanhua chapter row missing href: url={request_url}")
            chapter_url = cls.normalize_chapter_resource(href)
            name = cls._clean_text(row.xpath("./@title").get()) or cls._clean_node_text(row)
            if not name:
                raise ValueError(f"rumanhua chapter row missing title: href={href}")
            chapters.append(_ChapterCandidate(url=chapter_url, name=name))
        if not chapters:
            raise ValueError(f"rumanhua book page returned no initial chapter rows: url={request_url}")
        return {
            "slug": cls.parse_book_slug(request_url),
            "chapters": chapters,
            "has_more": bool(sel.css("div.chapterlistload div.chaplist-more button")),
        }

    @classmethod
    def parse_more_chapter_payload(cls, payload: str, *, slug: str) -> list[_ChapterCandidate]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("rumanhua morechapter payload is not valid JSON") from exc
        if str(data.get("code")) != "200":
            raise ValueError(f"rumanhua morechapter payload returned unexpected code: {data.get('code')!r}")
        rows = data.get("data")
        if not isinstance(rows, list):
            raise TypeError(f"rumanhua morechapter payload data must be list, got {type(rows).__name__}")
        chapters = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise TypeError(f"rumanhua morechapter row must be dict, got {type(row).__name__}")
            chapter_id = cls._clean_text(str(row.get("chapterid") or ""))
            chapter_name = cls._clean_text(str(row.get("chaptername") or ""))
            if not chapter_id or not chapter_name:
                raise ValueError(f"rumanhua morechapter row missing chapter fields: idx={idx} row={row!r}")
            chapters.append(_ChapterCandidate(url=cls.normalize_chapter_resource(f"/{slug}/{chapter_id}.html"), name=chapter_name))
        return chapters

    @classmethod
    def build_episodes(cls, book: RumanhuaBookInfo, chapters: list[_ChapterCandidate]) -> list[Episode]:
        deduped = []
        seen_urls = set()
        for chapter in chapters:
            if chapter.url in seen_urls:
                continue
            seen_urls.add(chapter.url)
            deduped.append(chapter)
        episodes = []
        for idx, chapter in enumerate(reversed(deduped), start=1):
            chapter_id = cls.parse_chapter_id(chapter.url)
            episode = Episode(
                from_book=book,
                id=f"{book.id}-{chapter_id}",
                idx=idx,
                url=chapter.url,
                name=chapter.name,
            )
            episode.chapter_referer = chapter.url
            episodes.append(episode)
        return episodes

    @classmethod
    def parse_page_urls_from_html(cls, html_text: str, *, chapter_url: str) -> list[str]:
        return _ReaderPageDecoder(html_text, chapter_url=chapter_url).decode()


class RumanhuaReqer(_RumanhuaContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf, verify=False)

    def test_index(self):
        try:
            resp = self.cli.get(self.index, headers=self.headers, follow_redirects=True, timeout=6)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return bool(resp.text)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        keyword = keyword.strip()
        page = max(1, int(page or 1))
        if page > 1:
            return []
        mappings = owner_type.merge_search_mappings(self.mappings, self.preview_site_kwargs().get("custom_map"))
        client = self.ensure_preview_client()
        if keyword in mappings:
            url = owner.parser.normalize_book_resource(mappings[keyword])
            resp = await client.get(url, headers=self.headers, follow_redirects=True, timeout=12)
            resp.raise_for_status()
            parser = owner.parser.parse_index_books if keyword == res.SPIDER.Completer.index else owner.parser.parse_update_books
            return await asyncio.to_thread(parser, resp.text)
        resp = await client.post(
            self.search_url,
            headers=self.headers,
            data={"k": keyword[:12]},
            follow_redirects=True,
            timeout=12,
        )
        resp.raise_for_status()
        return await asyncio.to_thread(owner.parser.parse_search_document, resp.text)

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        client = self.ensure_preview_client()
        resp = await client.get(book.url, headers=self.headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        state = await asyncio.to_thread(owner.parser.parse_book_state, resp.text, book, request_url=str(resp.url))
        chapters = list(state["chapters"])
        if state["has_more"]:
            more_resp = await client.post(
                self.morechapter_url,
                headers={**self.headers, "Referer": str(resp.url)},
                data={"id": state["slug"]},
                follow_redirects=True,
                timeout=12,
            )
            more_resp.raise_for_status()
            chapters.extend(await asyncio.to_thread(owner.parser.parse_more_chapter_payload, more_resp.text, slug=state["slug"]))
        episodes = await asyncio.to_thread(owner.parser.build_episodes, book, chapters)
        book.episodes = episodes
        return episodes

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        client = self.ensure_preview_client()
        referer = getattr(episode.from_book, "preview_url", None) or getattr(episode.from_book, "url", None) or self.index
        resp = await client.get(episode.url, headers={**self.headers, "Referer": referer}, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        urls = await asyncio.to_thread(owner.parser.parse_page_urls_from_html, resp.text, chapter_url=str(resp.url))
        episode.url = str(resp.url)
        episode.pages = len(urls)
        episode.page_urls = list(urls)
        episode.chapter_referer = str(resp.url)
        return urls


class RumanhuaUtils(_RumanhuaContract, Utils, Previewer):
    parser = RumanhuaParser
    reqer_cls = RumanhuaReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def get_uuid(cls, info, only_id=False):
        try:
            identity = cls.parser.parse_book_slug(str(info))
        except ValueError:
            identity = str(info).strip()
        return identity if only_id else f"{cls.name}-{identity}"

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": cls.headers}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"verify": False}
