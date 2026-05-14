from __future__ import annotations

import asyncio
import codecs
import re
import time
from urllib.parse import urlencode, urlparse

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.info import Dm5BookInfo, Episode


class _Dm5Contract:
    name = "dm5"
    proxy_policy = "direct"
    domain = "www.dm5.com"
    index = f"https://{domain}/"
    search_path = "/search"
    search_url_head = f"{index.rstrip('/')}{search_path}?"
    update_page = f"https://{domain}/manhua-new/"
    update_api = f"https://{domain}/manhua-new/dm5.ashx?action=getupdatecomics"
    mappings = {
        res.SPIDER.Completer.update: {"kind": "update", "day": 0},
    }
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }
    headers = ua
    book_hea = ua
    image_ua = {
        "User-Agent": ua["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": ua["Accept-Language"],
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }


class _Dm5ReaderDecoder:
    _packed_re = re.compile(
        r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(?P<source>.*)',(?P<radix>\d+),(?P<count>\d+),'(?P<dictionary>.*)'\.split\('\|'\),0,\{\}\)\)",
        re.S,
    )
    _cid_re = re.compile(r"\bvar\s+cid\s*=\s*(?P<value>\d+)\s*;", re.S)
    _pix_re = re.compile(r"\bvar\s+pix\s*=\s*(?P<value>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')\s*;", re.S)
    _pvalue_re = re.compile(r"\bvar\s+pvalue\s*=\s*\[(?P<body>.*?)\]\s*;", re.S)
    _suffix_re = re.compile(
        r"pvalue\s*\[\s*i\s*\]\s*=\s*pix\s*\+\s*pvalue\s*\[\s*i\s*\]\s*\+\s*(?P<value>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')\s*;",
        re.S,
    )
    _string_literal_re = re.compile(r"\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'", re.S)
    _page_no_re = re.compile(r"/(?P<page>\d+)_")

    @staticmethod
    def _decode_js_string_literal(raw: str) -> str:
        normalized = str(raw or "").strip()
        if len(normalized) < 2 or normalized[0] not in {'"', "'"} or normalized[-1] != normalized[0]:
            raise ValueError(f"dm5 reader invalid js string literal: {raw!r}")
        return codecs.decode(normalized[1:-1], "unicode_escape")

    @classmethod
    def _encode_unpack_token(cls, index: int, radix: int) -> str:
        if index == 0:
            return "0"
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        token = ""
        while index:
            index, remainder = divmod(index, radix)
            token = (chr(remainder + 29) if remainder > 35 else chars[remainder]) + token
        return token

    @classmethod
    def _unpack_script(cls, script_text: str, *, request_url: str) -> str:
        matched = cls._packed_re.search(script_text)
        if not matched:
            if "dm5imagefun" in script_text and "pvalue" in script_text:
                return script_text
            raise ValueError(f"dm5 chapterfun response missing packed eval payload: url={request_url}")
        source = codecs.decode(matched.group("source"), "unicode_escape")
        radix = int(matched.group("radix"))
        count = int(matched.group("count"))
        dictionary = codecs.decode(matched.group("dictionary"), "unicode_escape").split("|")
        for index in range(count - 1, -1, -1):
            if index >= len(dictionary) or not dictionary[index]:
                continue
            token = cls._encode_unpack_token(index, radix)
            source = re.sub(r"\b" + re.escape(token) + r"\b", dictionary[index], source)
        return source

    @classmethod
    def decode_page_urls(
        cls,
        script_text: str,
        *,
        request_url: str,
        expected_cid: str | None = None,
    ) -> list[tuple[int, str]]:
        unpacked = cls._unpack_script(script_text, request_url=request_url)
        cid_match = cls._cid_re.search(unpacked)
        if not cid_match:
            raise ValueError(f"dm5 decoded reader payload missing cid: url={request_url}")
        cid = cid_match.group("value")
        if expected_cid is not None and str(expected_cid) != cid:
            raise ValueError(f"dm5 decoded reader cid mismatch: expected={expected_cid} actual={cid} url={request_url}")

        pix_match = cls._pix_re.search(unpacked)
        if not pix_match:
            raise ValueError(f"dm5 decoded reader payload missing pix: url={request_url}")
        pix = cls._decode_js_string_literal(pix_match.group("value"))

        pvalue_match = cls._pvalue_re.search(unpacked)
        if not pvalue_match:
            raise ValueError(f"dm5 decoded reader payload missing pvalue array: url={request_url}")
        paths = [
            cls._decode_js_string_literal(matched.group(0))
            for matched in cls._string_literal_re.finditer(pvalue_match.group("body"))
        ]
        if not paths:
            raise ValueError(f"dm5 decoded reader payload returned empty pvalue array: url={request_url}")

        suffix_match = cls._suffix_re.search(unpacked)
        if not suffix_match:
            raise ValueError(f"dm5 decoded reader payload missing image query suffix: url={request_url}")
        suffix = cls._decode_js_string_literal(suffix_match.group("value"))

        page_urls = []
        for path in paths:
            page_match = cls._page_no_re.search(path)
            if not page_match:
                raise ValueError(f"dm5 decoded reader path missing page index: path={path!r} url={request_url}")
            page_urls.append((int(page_match.group("page")), f"{pix}{path}{suffix}"))
        return page_urls


class Dm5Parser(_Dm5Contract, Previewer):
    _reader_decoder = _Dm5ReaderDecoder()
    _style_url_re = re.compile(r"url\((['\"]?)(?P<url>.+?)\1\)", re.I)
    _book_path_re = re.compile(r"/manhua-(?P<slug>[^/?#]+)/?", re.I)
    _chapter_id_re = re.compile(r"/m(?P<cid>\d+)(?:-p\d+)?/?", re.I)
    _page_count_re = re.compile(r"(\d+)\s*P", re.I)
    _onclick_mid_re = re.compile(r"(?:GetFirstChapterUrl|SetBookmarker)\([^\d]*(?P<mid>\d+)")

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def _extract_style_url(cls, value: str | None) -> str | None:
        matched = cls._style_url_re.search(str(value or ""))
        if matched:
            return cls._normalize_text(matched.group("url"))
        return None

    @classmethod
    def _new_book(cls, *, idx: int, url: str) -> Dm5BookInfo:
        return Dm5BookInfo(idx=idx, render_keys=["name", "latest_sec"], url=url, preview_url=url)

    @classmethod
    def _book_url(cls, slug_or_url: str, *, domain: str) -> str:
        raw_value = cls._normalize_text(slug_or_url)
        if not raw_value:
            raise ValueError("dm5 book slug/url is required")
        if raw_value.startswith("http") or raw_value.startswith("/"):
            normalized = cls.normalize_preview_resource(raw_value, domain=domain)
            if not normalized:
                raise ValueError(f"dm5 book url normalization failed: {slug_or_url!r}")
            return normalized
        return f"https://{domain}/manhua-{raw_value.strip('/')}/"

    @classmethod
    def _extract_book_mid(cls, node) -> str | None:
        for value in node.xpath(".//@onclick").getall():
            if matched := cls._onclick_mid_re.search(str(value or "")):
                return matched.group("mid")
        return None

    @classmethod
    def _clean_latest_chapter(cls, value: str | None, *, title: str | None = None) -> str:
        cleaned = cls._normalize_text(value)
        normalized_title = cls._normalize_text(title)
        if normalized_title and cleaned.startswith(normalized_title):
            cleaned = cls._normalize_text(cleaned[len(normalized_title):].lstrip(" :-"))
        if cleaned in {"开始阅读", "阅读"}:
            return ""
        return cleaned

    @classmethod
    def _apply_latest(cls, book: Dm5BookInfo, value: str | None) -> str:
        latest = cls._clean_latest_chapter(value, title=book.name)
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        return latest

    @classmethod
    def _apply_artists(cls, book: Dm5BookInfo, values: list[str]) -> None:
        artists = [cls._normalize_text(value) for value in values]
        artists = [value for value in artists if value]
        if artists:
            book.artist = " ".join(artists)

    @classmethod
    def _parse_html_card(cls, node, *, idx: int, domain: str) -> Dm5BookInfo | None:
        href = cls._normalize_text(
            node.xpath(".//h2[contains(@class,'title')]//a[1]/@href").get()
            or node.xpath(".//p[contains(@class,'title')]//a[1]/@href").get()
            or node.xpath(".//a[contains(@href,'/manhua-')][1]/@href").get()
        )
        if not href:
            return None
        title = cls._normalize_text(
            node.xpath(".//h2[contains(@class,'title')]//a[1]/@title").get()
            or node.xpath(".//h2[contains(@class,'title')]//a[1]/text()").get()
            or node.xpath(".//p[contains(@class,'title')]//a[1]/@title").get()
            or node.xpath(".//p[contains(@class,'title')]//a[1]/text()").get()
        )
        if not title:
            return None
        book_url = cls._book_url(href, domain=domain)
        book = cls._new_book(idx=idx, url=book_url)
        book.name = title
        book.id = cls._extract_book_mid(node) or ""
        latest = cls._normalize_text(
            node.xpath(".//p[contains(@class,'chapter')]//a[1]/@title").get()
            or node.xpath(".//p[contains(@class,'chapter')]//a[1]/text()").get()
        )
        cls._apply_latest(book, latest)
        cls._apply_artists(
            book,
            node.xpath(".//p[contains(@class,'author')]//a/text()").getall()
            or node.xpath(".//p[contains(@class,'subtitle')]//a/text()").getall()
            or node.xpath(".//p[contains(@class,'zl')][span[contains(.,'作者')]]//a/text()").getall(),
        )
        cover = cls._extract_style_url(node.xpath(".//p[contains(@class,'mh-cover')][1]/@style").get())
        if cover:
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
        return book

    @classmethod
    def _parse_featured_search_card(cls, node, *, idx: int, domain: str) -> Dm5BookInfo | None:
        href = cls._normalize_text(node.xpath(".//p[contains(@class,'title')]//a[1]/@href").get())
        title = cls._normalize_text(
            node.xpath(".//p[contains(@class,'title')]//a[1]/@title").get()
            or node.xpath(".//p[contains(@class,'title')]//a[1]/text()").get()
        )
        if not href or not title:
            return None
        book = cls._new_book(idx=idx, url=cls._book_url(href, domain=domain))
        book.name = title
        book.id = cls._extract_book_mid(node) or ""
        cls._apply_artists(book, node.xpath(".//p[contains(@class,'subtitle')]//a/text()").getall())
        latest = cls._normalize_text(node.xpath(".//a[contains(@class,'btn-2')][1]/@title").get())
        cls._apply_latest(book, latest)
        cover = cls._normalize_text(node.xpath(".//div[contains(@class,'cover')]//img[1]/@src").get())
        if cover:
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
        return book

    @classmethod
    def parse_html_books(cls, html_text: str, *, domain: str) -> list[Dm5BookInfo]:
        sel = Selector(text=html_text)
        books: list[Dm5BookInfo] = []
        seen_urls = set()

        def _append(book: Dm5BookInfo | None):
            if book is None:
                return
            if book.url in seen_urls:
                return
            seen_urls.add(book.url)
            book.idx = len(books) + 1
            books.append(book)

        for node in sel.css("div.banner_detail_form"):
            _append(cls._parse_featured_search_card(node, idx=len(books) + 1, domain=domain))
        for node in sel.css("div.mh-item"):
            _append(cls._parse_html_card(node, idx=len(books) + 1, domain=domain))
        return books

    @classmethod
    def parse_search_document(cls, html_text: str, *, domain: str) -> list[Dm5BookInfo]:
        return cls.parse_html_books(html_text, domain=domain)

    @classmethod
    def parse_update_payload(cls, payload, *, domain: str) -> list[Dm5BookInfo]:
        if not isinstance(payload, dict):
            raise TypeError(f"dm5 update payload must be object, got {type(payload).__name__}")
        items = payload.get("UpdateComicItems")
        if not isinstance(items, list):
            raise ValueError("dm5 update payload missing UpdateComicItems list")
        books = []
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise TypeError(f"dm5 update item must be object, got {type(item).__name__}")
            slug = cls._normalize_text(item.get("UrlKey"))
            title = cls._normalize_text(item.get("Title"))
            if not slug or not title:
                continue
            book = cls._new_book(idx=idx, url=cls._book_url(slug, domain=domain))
            book.id = cls._normalize_text(str(item.get("ID") or ""))
            book.name = title
            cls._apply_latest(book, item.get("ShowLastPartName"))
            authors = item.get("Author") if isinstance(item.get("Author"), list) else []
            cls._apply_artists(book, [str(value) for value in authors])
            book.public_date = cls._normalize_text(item.get("LastUpdateTime")) or None
            cover = cls._normalize_text(item.get("ShowPicUrlB") or item.get("ShowConver") or item.get("Logo"))
            if cover:
                book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
            books.append(book)
        return books

    @classmethod
    def _extract_js_var(cls, text: str, name: str):
        matched = re.search(rf"\b{name}\s*=\s*(?P<value>\"[^\"]*\"|'[^']*'|\d+)\s*;", text)
        if not matched:
            raise ValueError(f"dm5 html missing js variable: {name}")
        value = matched.group("value").strip()
        if value[:1] in {'"', "'"}:
            return value[1:-1]
        return value

    @classmethod
    def parse_book_details(cls, html_text: str, *, request_url: str) -> dict:
        sel = Selector(text=html_text)
        title = cls._normalize_text(
            "".join(sel.xpath("//div[contains(@class,'banner_detail_form')]//p[contains(@class,'title')][1]/text()[normalize-space()]").getall())
        )
        if not title:
            raise ValueError(f"dm5 book page missing title: url={request_url}")
        cover = cls._normalize_text(
            sel.xpath("//div[contains(@class,'banner_detail_form')]//div[contains(@class,'cover')]//img[1]/@src").get()
        )
        artists = [cls._normalize_text(text) for text in sel.xpath("//p[contains(@class,'subtitle')]//a/text()").getall()]
        tags = [cls._normalize_text(text) for text in sel.xpath("//p[contains(@class,'tip')]//a//span/text()").getall()]
        latest = cls._normalize_text(sel.xpath("//div[contains(@class,'detail-list-title')]//span[contains(@class,'s')]//a[1]/text()").get())
        return {
            "id": cls._extract_js_var(html_text, "DM5_COMIC_MID"),
            "title": title,
            "cover": cover or None,
            "artist": " ".join(filter(None, artists)) or None,
            "tags": [tag for tag in tags if tag],
            "latest_sec": latest or None,
        }

    @classmethod
    def apply_book_details(cls, book: Dm5BookInfo, details: dict, *, domain: str) -> None:
        if details.get("id"):
            book.id = str(details["id"])
        if details.get("title"):
            book.name = cls._normalize_text(details["title"])
        cover = cls._normalize_text(details.get("cover"))
        if cover:
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
        artist = cls._normalize_text(details.get("artist"))
        if artist:
            book.artist = artist
        tags = list(details.get("tags") or [])
        if tags:
            book.tags = tags
        cls._apply_latest(book, details.get("latest_sec") or book.latest_sec)

    @classmethod
    def parse_chapter_id(cls, url: str) -> str:
        matched = cls._chapter_id_re.search(str(url or ""))
        if not matched:
            raise ValueError(f"dm5 chapter url missing /m<cid>/ shape: {url!r}")
        return matched.group("cid")

    @classmethod
    def parse_episodes(cls, html_text: str, book: Dm5BookInfo, *, domain: str) -> list[Episode]:
        sel = Selector(text=html_text)
        rows = list(sel.css("div#chapterlistload ul.view-win-list a[href*='/m']"))
        if not rows:
            raise ValueError(f"dm5 book page returned no chapter rows: book={book.url}")
        episodes = []
        seen_urls = set()
        for row in reversed(rows):
            href = cls._normalize_text(row.xpath("./@href").get())
            if not href:
                continue
            chapter_url = cls.normalize_preview_resource(href, domain=domain)
            if chapter_url in seen_urls:
                continue
            seen_urls.add(chapter_url)
            name = cls._normalize_text("".join(row.xpath("./text()").getall()))
            if not name:
                raise ValueError(f"dm5 chapter row missing title: href={href}")
            episode = Episode(
                from_book=book,
                id=cls.parse_chapter_id(chapter_url),
                idx=len(episodes) + 1,
                url=chapter_url,
                name=name,
            )
            page_text = cls._normalize_text("".join(row.xpath("./span/text()").getall()))
            if matched := cls._page_count_re.search(page_text):
                episode.pages = int(matched.group(1))
            episode.chapter_referer = chapter_url
            episodes.append(episode)
        return episodes

    @classmethod
    def parse_reader_context(cls, html_text: str, *, chapter_url: str) -> dict:
        image_count = int(cls._extract_js_var(html_text, "DM5_IMAGE_COUNT"))
        if image_count < 1:
            raise ValueError(f"dm5 chapter page returned invalid DM5_IMAGE_COUNT: url={chapter_url}")
        request_domain = urlparse(chapter_url).netloc or cls.domain
        dm5_curl = str(cls._extract_js_var(html_text, "DM5_CURL"))
        canonical_chapter_url = cls.normalize_preview_resource(dm5_curl, domain=request_domain) or chapter_url
        chapterfun_url = f"{canonical_chapter_url.rstrip('/')}/chapterfun.ashx"
        sel = Selector(text=html_text)
        dm5_key = cls._normalize_text(sel.xpath("//input[@id='dm5_key']/@value").get())
        return {
            "DM5_CURL": dm5_curl,
            "DM5_MID": str(cls._extract_js_var(html_text, "DM5_MID")),
            "DM5_CID": str(cls._extract_js_var(html_text, "DM5_CID")),
            "DM5_IMAGE_COUNT": image_count,
            "DM5_PAGEINDEX": int(cls._extract_js_var(html_text, "DM5_PAGEINDEX")),
            "DM5_VIEWSIGN": str(cls._extract_js_var(html_text, "DM5_VIEWSIGN")),
            "DM5_VIEWSIGN_DT": str(cls._extract_js_var(html_text, "DM5_VIEWSIGN_DT")),
            "DM5_KEY": dm5_key,
            "DM5_LANGUAGE": "1",
            "DM5_GTK": "6",
            "DM5_CHAPTERFUN_URL": chapterfun_url,
            "DM5_CHAPTER_URL": canonical_chapter_url,
        }

    @classmethod
    def build_chapterfun_request(
        cls,
        reader_context: dict,
        *,
        page: int,
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        chapter_url = str(reader_context["DM5_CHAPTER_URL"])
        return (
            str(reader_context["DM5_CHAPTERFUN_URL"]),
            {
                **cls.ua,
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": chapter_url,
            },
            {
                "cid": str(reader_context["DM5_CID"]),
                "page": str(max(1, int(page))),
                "key": str(reader_context.get("DM5_KEY", "")),
                "language": str(reader_context.get("DM5_LANGUAGE", "1")),
                "gtk": str(reader_context.get("DM5_GTK", "6")),
                "_cid": str(reader_context["DM5_CID"]),
                "_mid": str(reader_context["DM5_MID"]),
                "_dt": str(reader_context["DM5_VIEWSIGN_DT"]),
                "_sign": str(reader_context["DM5_VIEWSIGN"]),
            },
        )

    @classmethod
    def decode_chapterfun_page_urls(
        cls,
        script_text: str,
        *,
        request_url: str,
        expected_cid: str | None = None,
    ) -> list[tuple[int, str]]:
        return cls._reader_decoder.decode_page_urls(script_text, request_url=request_url, expected_cid=expected_cid)

    @classmethod
    def build_image_headers(cls, *, referer_url: str | None = None) -> dict[str, str]:
        headers = dict(cls.image_ua)
        if referer_url:
            headers["Referer"] = referer_url
        return headers

    @classmethod
    def build_page_urls(cls, chunks: list[list[tuple[int, str]]], *, total: int, request_url: str) -> list[str]:
        page_map: dict[int, str] = {}
        for chunk in chunks:
            for page_no, url in chunk:
                if not 1 <= int(page_no) <= int(total):
                    raise ValueError(f"dm5 decoded page index out of range: page={page_no} total={total} url={request_url}")
                previous = page_map.get(page_no)
                if previous is not None and previous != url:
                    raise ValueError(f"dm5 decoded page url conflict: page={page_no} url={request_url}")
                page_map[page_no] = url
        missing = [page for page in range(1, int(total) + 1) if page not in page_map]
        if missing:
            preview = ",".join(str(page) for page in missing[:10])
            suffix = "..." if len(missing) > 10 else ""
            raise ValueError(f"dm5 chapterfun payload incomplete: missing={preview}{suffix} total={total} url={request_url}")
        return [page_map[page] for page in range(1, int(total) + 1)]


class Dm5Reqer(_Dm5Contract, Req):
    update_page_size = 140

    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def build_search_url(cls, keyword: str, *, domain: str, page: int = 1) -> str:
        query = {"title": keyword.strip(), "language": "1"}
        if page > 1:
            query["page"] = str(page)
        return f"https://{domain}{cls.search_path}?{urlencode(query)}"

    @classmethod
    def build_mapping_url(cls, mapping_value, *, domain: str) -> str:
        if isinstance(mapping_value, dict):
            raw_value = mapping_value.get("url") or mapping_value.get("value") or ""
        else:
            raw_value = mapping_value
        url = cls.normalize_preview_resource(str(raw_value or ""), domain=domain)
        if not url:
            raise ValueError("dm5 mapping URL is required")
        return url

    @classmethod
    def is_update_mapping(cls, mapping_value) -> bool:
        return isinstance(mapping_value, dict) and mapping_value.get("kind") == "update"

    @classmethod
    def mapping_update_day(cls, mapping_value) -> int:
        if not isinstance(mapping_value, dict):
            return 0
        return max(0, int(mapping_value.get("day", 0) or 0))

    @classmethod
    def build_update_request(cls, *, domain: str, page: int, day: int = 0) -> tuple[str, dict[str, str], dict[str, str]]:
        stamp = int(time.time() * 1000)
        url = f"https://{domain}/manhua-new/dm5.ashx?action=getupdatecomics&d={stamp}"
        headers = {
            **cls.ua,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": cls.preview_origin(domain),
            "Referer": f"https://{domain}/manhua-new/",
        }
        data = {"page": str(max(1, int(page or 1))), "pagesize": str(cls.update_page_size), "DK": str(day)}
        return url, headers, data

    def test_index(self):
        try:
            resp = self.cli.get(self.index, headers=self.ua, follow_redirects=True, timeout=6)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return bool(resp.text)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or owner_type.domain
        mappings = owner_type.merge_search_mappings(self.mappings, site_kw.get("custom_map"))
        page = max(1, int(page or 1))
        keyword = keyword.strip()

        if keyword in mappings:
            mapping_value = mappings[keyword]
            if self.is_update_mapping(mapping_value):
                url, headers, data = self.build_update_request(domain=domain, page=page, day=self.mapping_update_day(mapping_value))
                resp = await self.ensure_preview_client().post(url, data=data, headers=headers, follow_redirects=True, timeout=12)
                resp.raise_for_status()
                return await asyncio.to_thread(owner.parser.parse_update_payload, resp.json(), domain=domain)
            url = self.build_mapping_url(mapping_value, domain=domain)
            resp = await self.ensure_preview_client().get(url, headers=self.ua, follow_redirects=True, timeout=12)
            resp.raise_for_status()
            html_domain = urlparse(str(resp.url)).netloc or domain
            return await asyncio.to_thread(owner.parser.parse_html_books, resp.text, domain=html_domain)

        resp = await self.ensure_preview_client().get(
            self.build_search_url(keyword, domain=domain, page=page),
            headers=self.ua,
            follow_redirects=True,
            timeout=12,
        )
        resp.raise_for_status()
        html_domain = urlparse(str(resp.url)).netloc or domain
        return await asyncio.to_thread(owner.parser.parse_search_document, resp.text, domain=html_domain)

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        resp = await self.ensure_preview_client().get(book.url, headers=self.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        book.url = str(resp.url)
        actual_domain = urlparse(book.url).netloc or domain
        details = await asyncio.to_thread(owner.parser.parse_book_details, resp.text, request_url=book.url)
        owner.parser.apply_book_details(book, details, domain=actual_domain)
        return await asyncio.to_thread(owner.parser.parse_episodes, resp.text, book, domain=actual_domain)

    async def _fetch_reader_page_urls(self, reader_context: dict) -> list[str]:
        owner = self._require_preview_owner()
        total = int(reader_context["DM5_IMAGE_COUNT"])
        request_url = str(reader_context["DM5_CHAPTERFUN_URL"])
        page_chunks: list[list[tuple[int, str]]] = []
        next_page = 1

        while next_page <= total:
            url, headers, params = owner.parser.build_chapterfun_request(reader_context, page=next_page)
            resp = await self.ensure_preview_client().get(
                url,
                params=params,
                headers=headers,
                follow_redirects=True,
                timeout=12,
            )
            resp.raise_for_status()
            chunk = await asyncio.to_thread(
                owner.parser.decode_chapterfun_page_urls,
                resp.text,
                request_url=str(resp.url),
                expected_cid=str(reader_context["DM5_CID"]),
            )
            if not chunk:
                raise ValueError(f"dm5 chapterfun returned empty image chunk: url={resp.url}")
            page_chunks.append(chunk)
            chunk_last_page = max(page_no for page_no, _url in chunk)
            if chunk_last_page < next_page:
                raise ValueError(f"dm5 chapterfun pagination made no progress: page={next_page} url={resp.url}")
            if chunk_last_page >= total:
                break
            next_page = chunk_last_page + 1

        return owner.parser.build_page_urls(page_chunks, total=total, request_url=request_url)

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        resp = await self.ensure_preview_client().get(episode.url, headers=self.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        episode.url = str(resp.url)
        reader_context = await asyncio.to_thread(owner.parser.parse_reader_context, resp.text, chapter_url=episode.url)
        page_urls = await self._fetch_reader_page_urls(reader_context)
        chapter_referer = str(reader_context["DM5_CHAPTER_URL"])
        for key, value in reader_context.items():
            setattr(episode, key, value)
        episode.dm5_reader_context = dict(reader_context)
        episode.dm5_image_headers = owner.parser.build_image_headers(referer_url=chapter_referer)
        episode.chapter_referer = chapter_referer
        episode.pages = len(page_urls)
        episode.page_urls = list(page_urls)
        return list(episode.page_urls)


class Dm5Utils(_Dm5Contract, Utils, Previewer):
    parser = Dm5Parser
    reqer_cls = Dm5Reqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": cls.ua}
