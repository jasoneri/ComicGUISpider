from __future__ import annotations

import asyncio
import codecs
import json
import re
from typing import TypedDict
from urllib.parse import quote, urlparse

import httpx
from lzstring import decompress_from_base64
from scrapy import Selector

from assets import res
from utils.website.core import Cookies, Previewer, Req, Utils
from utils.website.info import Episode, ManhuaguiBookInfo


class _ManhuaguiContract:
    name = "manhuagui"
    proxy_policy = "proxy"
    domain = "www.manhuagui.com"
    index = f"https://{domain}/"
    update = f"{index}update/"
    mappings = {res.SPIDER.Completer.index: index, res.SPIDER.Completer.update: update}
    default_cookies = {"country": "CN"}
    browser_referer_mode = "provider_index"
    browser_cookie_set_enabled = True
    ua = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
        "Connection": "keep-alive",
    }
    headers = ua
    book_hea = ua
    image_ua = {
        "User-Agent": ua["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": ua["Accept-Language"],
        "Referer": index,
        "Connection": "keep-alive",
    }


class _BookDetails(TypedDict):
    title: str
    other_name: str | None
    cover: str | None
    artist: str | None
    tags: list[str]
    aliases: list[str]
    public_date: str | None
    latest_sec: str | None


class _ReaderDecoder:
    _packed_re = re.compile(
        r"function\(p,a,c,k,e,d\).*?\}\('(?P<source>.*?)',(?P<radix>\d+),(?P<count>\d+),"
        r"'(?P<dictionary>.*?)'\['\\x73\\x70\\x6c\\x69\\x63'\]\('\\x7c'\)",
        re.S,
    )
    _payload_re = re.compile(r"SMH\.imgData\((?P<payload>\{.*\})\)\.preInit\(\);?", re.S)
    _picserv_hosts = {
        "auto": (("i", 0.1), ("eu", 4), ("eu1", 4), ("eu2", 4), ("us", 1), ("us1", 1), ("us2", 1), ("us3", 1)),
        "telecom": (("eu", 1), ("eu1", 1), ("eu2", 1)),
        "unicom": (("us", 1), ("us1", 1), ("us2", 1), ("us3", 1)),
    }

    @classmethod
    def _unpack_script(cls, match: re.Match[str]) -> str:
        def _decode_js_string(value: str) -> str:
            return codecs.decode(value, "unicode_escape")
        def _encode_unpack_token(index: int, radix: int) -> str:
            if index == 0:
                return "0"
            chars = "0123456789abcdefghijklmnopqrstuvwxyz"
            token = ""
            while index:
                index, remainder = divmod(index, radix)
                token = (chr(remainder + 29) if remainder > 35 else chars[remainder]) + token
            return token
        def _decode_dictionary_text(value: str) -> str:
            try:
                dictionary_text = decompress_from_base64(value)
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                raise ValueError("manhuagui reader compressed dictionary is not valid LZString Base64") from exc
            if not dictionary_text:
                raise ValueError("manhuagui reader compressed dictionary decompressed to empty or invalid text")
            return dictionary_text
        source = _decode_js_string(match.group("source"))
        radix = int(match.group("radix"))
        count = int(match.group("count"))
        dictionary_text = _decode_dictionary_text(_decode_js_string(match.group("dictionary")))
        dictionary = dictionary_text.split("|")
        for index in range(count - 1, -1, -1):
            if index < len(dictionary) and dictionary[index]:
                source = re.sub(r"\b" + re.escape(_encode_unpack_token(index, radix)) + r"\b", dictionary[index], source)
        return source

    def decode_page_urls(self, chapter_html: str, *, cookies: dict[str, str] | None = None, image_host: str | None = None) -> list[str]:
        def extract_payload(chapter_html: str) -> dict[str, object]:
            for match in self._packed_re.finditer(chapter_html):
                unpacked = self._unpack_script(match)
                payload_match = self._payload_re.search(unpacked)
                if payload_match:
                    payload = json.loads(payload_match.group("payload"))
                    if not isinstance(payload, dict):
                        raise TypeError(f"manhuagui reader payload must be a JSON object: {type(payload).__name__}")
                    return payload
            raise ValueError("manhuagui reader html missing packed SMH.imgData payload")
        def _select_image_host(image_host: str | None = None) -> str:
            valid_hosts = {host for group in self._picserv_hosts.values() for host, weight in group if weight > 0}
            if image_host:
                if image_host not in valid_hosts:
                    raise ValueError(f"manhuagui image host is not in SMH.picserv host groups: {image_host!r}")
                return image_host
            for host, weight in self._picserv_hosts["auto"]:
                if weight == 4:
                    return host
            raise ValueError("manhuagui SMH.picserv auto group has no usable image host")
        def _payload_query(payload: dict[str, object]) -> str:
            sl = payload.get("sl")
            if not isinstance(sl, dict):
                raise TypeError("manhuagui reader payload field 'sl' must be an object")
            return "&".join(f"{key}={value}" for key, value in sl.items())
        payload = extract_payload(chapter_html)
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise TypeError("manhuagui reader payload field 'files' must be a non-empty list")
        normalized_files = [str(file).strip() for file in files]
        if not all(normalized_files):
            raise ValueError("manhuagui reader payload field 'files' contains empty entries")
        total = payload.get("len")
        if not isinstance(total, int) or total != len(normalized_files):
            raise ValueError(f"manhuagui reader payload length mismatch: len={total!r} files={len(normalized_files)}")
        path = payload.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            raise TypeError(f"manhuagui reader payload field 'path' must be an absolute URL path: {path!r}")
        query = _payload_query(payload)
        suffix = f"?{query}" if query else ""
        host = _select_image_host(image_host)
        return [f"https://{host}.hamreus.com{path}{file}{suffix}" for file in normalized_files]


class ManhuaguiParser(_ManhuaguiContract, Previewer):
    _book_id_re = re.compile(r"/comic/(?P<book_id>\d+)/")
    _date_re = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?")

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def apply_latest_chapter(cls, book: ManhuaguiBookInfo, value: str | None) -> str:
        def _clean_latest_chapter() -> str:
            cleaned = cls._normalize_text(value)
            if not cleaned:
                return ""
            for prefix in ("更新至", "更新到", "连载至", "共"):
                if cleaned.startswith(prefix):
                    cleaned = cls._normalize_text(cleaned[len(prefix):])
                    break
            cleaned = cleaned.replace("[全]", "").strip()
            if cleaned and cleaned[0].isdigit():
                return f"第{cleaned}"
            return ""
        latest = _clean_latest_chapter()
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        return latest

    @classmethod
    def _new_book(cls, *, idx: int, url: str) -> ManhuaguiBookInfo:
        return ManhuaguiBookInfo(idx=idx, render_keys=["name", "latest_sec"], url=url, preview_url=url)

    @classmethod
    def parse_book_id(cls, url: str) -> str:
        matched = cls._book_id_re.search(url or "")
        if not matched:
            raise ValueError(f"manhuagui book url missing /comic/<id>/ shape: {url!r}")
        return matched.group("book_id")

    @classmethod
    def _extract_cover(cls, target, *xpaths: str) -> str | None:
        for xpath in xpaths:
            cover = cls._normalize_text(target.xpath(xpath).get())
            if cover:
                return cover
        return None

    @classmethod
    def _parse_cover_books(cls, html_text: str, *, domain: str, card_selector: str, empty_message: str) -> list[ManhuaguiBookInfo]:
        sel = Selector(text=html_text)
        books: list[ManhuaguiBookInfo] = []
        seen_urls = set()
        for card in sel.css(card_selector):
            href = cls._normalize_text(card.xpath("./@href").get())
            if not href:
                continue
            book_url = cls.normalize_preview_resource(href, domain=domain)
            if book_url in seen_urls:
                continue
            seen_urls.add(book_url)
            book = cls._new_book(idx=len(books) + 1, url=book_url)
            book.id = cls.parse_book_id(book_url)
            book.name = cls._normalize_text(card.xpath("./@title").get()) or cls._normalize_text(card.xpath(".//img/@alt").get())
            if not book.name:
                continue
            cls.apply_latest_chapter(book, "".join(card.css("span.tt::text").getall()))
            cover = cls._extract_cover(card, ".//img/@src", ".//img/@data-src")
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain) if cover else None
            books.append(book)
        if not books:
            raise ValueError(empty_message)
        return books

    @classmethod
    def parse_index_books(cls, html_text: str, *, domain: str) -> list[ManhuaguiBookInfo]:
        return cls._parse_cover_books(
            html_text, domain=domain, card_selector="a.bcover[href*='/comic/']",
            empty_message="manhuagui homepage returned no featured cover cards",
        )

    @classmethod
    def parse_update_books(cls, html_text: str, *, domain: str) -> list[ManhuaguiBookInfo]:
        return cls._parse_cover_books(
            html_text, domain=domain, card_selector="div.latest-list a.cover[href*='/comic/']",
            empty_message="manhuagui update page returned no update cover cards",
        )

    @classmethod
    def parse_search_document(cls, html_text: str, *, domain: str) -> list[ManhuaguiBookInfo]:
        sel = Selector(text=html_text)
        rows = list(sel.css("div.book-result > ul > li.cf"))
        if not rows:
            return []
        books: list[ManhuaguiBookInfo] = []
        for idx, row in enumerate(rows, start=1):
            href = cls._normalize_text(row.css("dt a::attr(href)").get())
            if not href:
                raise ValueError(f"manhuagui search row missing book href: idx={idx}")
            book_url = cls.normalize_preview_resource(href, domain=domain)
            book = cls._new_book(idx=idx, url=book_url)
            book.id = cls.parse_book_id(book_url)
            book.name = cls._normalize_text(row.css("dt a::text").get())
            if not book.name:
                raise ValueError(f"manhuagui search row missing title: idx={idx} href={href}")
            latest_sec = cls._normalize_text(row.css("dd.tags.status a.blue::text").get())
            if latest_sec:
                cls.apply_latest_chapter(book, latest_sec)
            cover = cls._extract_cover(
                row, ".//a[contains(@class,'bcover')]//img[1]/@src",
                ".//a[contains(@class,'bcover')]//img[1]/@data-src",
            )
            if cover:
                book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
            book.artist = cls._normalize_text(" ".join(row.xpath(".//dd[contains(@class,'tags')][3]//a/text()").getall())) or None
            tags = [cls._normalize_text(tag) for tag in row.xpath(".//dd[contains(@class,'tags')][2]//a/text()").getall()]
            book.tags = [tag for tag in tags if tag]
            status_text = cls._normalize_text(" ".join(row.css("dd.tags.status *::text").getall()))
            if matched := cls._date_re.search(status_text):
                book.public_date = matched.group(0)
            books.append(book)
        return books

    @classmethod
    def parse_book_details(cls, html_text: str, *, request_url: str) -> _BookDetails:
        sel = Selector(text=html_text)
        title = cls._normalize_text(sel.css("div.book-title h1::text").get())
        if not title:
            raise ValueError(f"manhuagui book page missing title: url={request_url}")
        other_name = cls._normalize_text(sel.css("div.book-title h2::text").get())
        cover = cls._normalize_text(sel.css("div.book-cover img::attr(src)").get())
        artists = [cls._normalize_text(tag) for tag in sel.xpath("//li/span[strong[contains(., '漫画作者')]]//a/text()").getall()]
        tags = [cls._normalize_text(tag) for tag in sel.xpath("//li/span[strong[contains(., '漫画剧情')]]//a/text()").getall()]
        aliases = [cls._normalize_text(tag) for tag in sel.xpath("//li/span[strong[contains(., '漫画别名')]]//a/text()").getall()]
        status_text = cls._normalize_text(" ".join(sel.css("li.status *::text").getall()))
        public_date = cls._date_re.search(status_text)
        latest_sec = cls._normalize_text(sel.css("li.status a.blue::text").get())
        return {
            "title": title,
            "other_name": other_name or None,
            "cover": cover or None,
            "artist": " ".join(filter(None, artists)) or None,
            "tags": [tag for tag in tags if tag],
            "aliases": [alias for alias in aliases if alias],
            "public_date": public_date.group(0) if public_date else None,
            "latest_sec": latest_sec or None,
        }

    @classmethod
    def apply_book_details(cls, book: ManhuaguiBookInfo, details: _BookDetails, *, domain: str) -> None:
        book.name = cls._normalize_text(details["title"] or book.name)
        cover = cls._normalize_text(details["cover"])
        if cover:
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
        book.artist = cls._normalize_text(details["artist"]) or book.artist
        book.tags = list(details["tags"] or book.tags or [])
        book.public_date = details["public_date"] or book.public_date
        cls.apply_latest_chapter(book, details["latest_sec"] or book.latest_sec)
        if aliases := list(details["aliases"]):
            book.other_names = aliases
            book.other_name_raw = ", ".join(aliases)
        elif other_name := cls._normalize_text(details["other_name"]):
            book.other_names = [other_name]
            book.other_name_raw = other_name

    @classmethod
    def parse_episodes(cls, html_text: str, book: ManhuaguiBookInfo, *, domain: str) -> list[Episode]:
        sel = Selector(text=html_text)
        rows = list(sel.css("div.chapter-list ul li a[href]"))
        if not rows:
            raise ValueError(f"manhuagui book page returned no chapter rows: book={book.url}")
        episodes: list[Episode] = []
        seen_urls = set()
        for row in reversed(rows):
            href = cls._normalize_text(row.xpath("./@href").get())
            if not href:
                raise ValueError(f"manhuagui chapter row missing href: book={book.url}")
            chapter_url = cls.normalize_preview_resource(href, domain=domain)
            if chapter_url in seen_urls:
                continue
            seen_urls.add(chapter_url)
            chapter_name = cls._normalize_text(row.xpath("./@title").get()) or cls._normalize_text("".join(row.xpath(".//text()").getall()))
            if not chapter_name:
                raise ValueError(f"manhuagui chapter row missing title: href={href}")
            episodes.append(
                Episode(
                    from_book=book, id=href.strip("/").split("/")[-1].replace(".html", ""), idx=len(episodes) + 1,
                    url=chapter_url, name=chapter_name,
                )
            )
        return episodes


class ManhuaguiReqer(_ManhuaguiContract, Req, Cookies, Previewer):
    def __init__(self, _conf):
        self.conf = _conf
        self.cli = self.get_cli(_conf)
        self.reader_decoder = _ReaderDecoder()

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        cli = super().get_cli(_conf, is_async=is_async, **kwargs)
        cli.headers = {**cls.book_hea, "Cookie": cls.to_str_(_conf.cookies.get(cls.name))}
        return cli

    @classmethod
    def normalize_cookies(cls, cookies: dict | None = None) -> dict[str, str]:
        merged = {key: value for key, value in cls.default_cookies.items() if value not in (None, "")}
        for key, value in (cookies or {}).items():
            if value in (None, ""):
                continue
            merged[str(key)] = str(value)
        return merged

    def _configured_cookies(self) -> dict[str, str]:
        cookies_owner = getattr(self.conf, "cookies", None)
        if cookies_owner is None:
            return {}
        if isinstance(cookies_owner, dict):
            return dict(cookies_owner.get(self.name) or {})
        getter = getattr(cookies_owner, "get", None)
        return dict(getter(self.name) or {}) if callable(getter) else {}

    def resolved_cookies(self, cookies: dict | None = None) -> dict[str, str]:
        return self.normalize_cookies(cookies if cookies is not None else (getattr(self, "cookies", None) or self._configured_cookies()))

    @classmethod
    def preview_headers(cls, domain: str, cookies: dict | None = None) -> dict[str, str]:
        return cls.build_site_headers(
            domain, cls.headers, referer_url=cls.index, cookies=cls.normalize_cookies(cookies),
            cookie_serializer=cls.to_str_,
        )

    @classmethod
    def build_search_url(cls, keyword: str, *, domain: str, page: int = 1) -> str:
        encoded = quote(keyword.strip(), safe="")
        if page <= 1:
            return f"https://{domain}/s/{encoded}.html"
        return f"https://{domain}/s/{encoded}_p{page}.html"

    @classmethod
    def decode_reader_page_urls(cls, chapter_html: str, *, image_host: str | None = None) -> list[str]:
        return _ReaderDecoder().decode_page_urls(chapter_html, cookies=cls.default_cookies, image_host=image_host)

    async def decode_page_urls_async(self, chapter_html: str, *, cookies: dict[str, str]) -> list[str]:
        return await asyncio.to_thread(self.reader_decoder.decode_page_urls, chapter_html, cookies=cookies)

    def decode_page_urls_sync(self, chapter_html: str, *, cookies: dict[str, str], image_host: str | None = None) -> list[str]:
        return self.reader_decoder.decode_page_urls(chapter_html, cookies=cookies, image_host=image_host)

    def test_index(self):
        try:
            resp = self.cli.get(
                self.index, headers=self.preview_headers(self.domain, self.resolved_cookies()), follow_redirects=True,
                timeout=6,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return bool(resp.text)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or self.domain
        cookies = self.resolved_cookies(site_kw.get("cookies"))
        mappings = owner_type.merge_search_mappings(self.mappings, site_kw.get("custom_map"))
        keyword = keyword.strip()
        if keyword in mappings:
            if int(page or 1) > 1:
                return []
            mapping_value = mappings[keyword]
            url = owner_type.normalize_mapping_url(domain, mapping_value)
            resp = await self.ensure_preview_client().get(
                url, headers=self.preview_headers(domain, cookies), follow_redirects=True, timeout=12,
            )
            resp.raise_for_status()
            if not urlparse(str(mapping_value)).path.rstrip("/"):
                return await asyncio.to_thread(owner.parser.parse_index_books, resp.text, domain=domain)
            return await asyncio.to_thread(owner.parser.parse_update_books, resp.text, domain=domain)
        resp = await self.ensure_preview_client().get(
            self.build_search_url(keyword, domain=domain, page=max(1, int(page or 1))), headers=self.preview_headers(domain, cookies),
            follow_redirects=True, timeout=12,
        )
        resp.raise_for_status()
        return await asyncio.to_thread(owner.parser.parse_search_document, resp.text, domain=domain)

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or self.domain
        cookies = self.resolved_cookies(site_kw.get("cookies"))
        resp = await self.ensure_preview_client().get(
            book.url, headers=self.preview_headers(domain, cookies), follow_redirects=True, timeout=12,
        )
        resp.raise_for_status()
        book.url = str(resp.url)
        details = await asyncio.to_thread(owner.parser.parse_book_details, resp.text, request_url=book.url)
        owner.parser.apply_book_details(book, details, domain=domain)
        return await asyncio.to_thread(owner.parser.parse_episodes, resp.text, book, domain=domain)

    async def preview_fetch_pages(self, episode) -> list[str]:
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or self.domain
        cookies = self.resolved_cookies(site_kw.get("cookies"))
        resp = await self.ensure_preview_client().get(
            episode.url, headers=self.preview_headers(domain, cookies), follow_redirects=True, timeout=12,
        )
        resp.raise_for_status()
        episode.url = str(resp.url)
        urls = await self.decode_page_urls_async(resp.text, cookies=cookies)
        episode.pages = len(urls)
        episode.page_urls = list(urls)
        return urls


class ManhuaguiUtils(_ManhuaguiContract, Utils, Cookies, Previewer):
    parser = ManhuaguiParser
    reqer_cls = ManhuaguiReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        domain = context.get("domain") or cls.domain
        return {"headers": cls.reqer_cls.preview_headers(domain, context.get("cookies"))}

    @classmethod
    def build_browser_cookie_sets(cls, *, cookies: dict[str, str], domain: str | None = None, referer_url: str | None = None):
        return super().build_browser_cookie_sets(cookies=cls.reqer_cls.normalize_cookies(cookies), domain=domain, referer_url=referer_url)
