from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlparse

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.core.err import Dm5Resp
from utils.website.info import Dm5BookInfo, Episode

from .reader_decoder import Dm5ReaderDecoder

class _Dm5Contract:
    name = "dm5"
    proxy_policy = "direct"
    domain = "www.dm5.com"
    index = f"https://{domain}/"
    search_path = "/search"
    search_url_head = f"{index.rstrip('/')}{search_path}?"
    update_page = f"https://{domain}/manhua-new/"
    update_api = f"https://{domain}/manhua-new/dm5.ashx?action=getupdatecomics"
    rank_path = "/manhua-rank/"
    rank_url_head = f"https://{domain}{rank_path}"
    rank_types = {
        1: "国漫榜",2: "日漫榜",3: "综合榜",4: "人气榜",5: "收藏榜",6: "评论榜",7: "上升榜",8: "完结榜",
        9: "少年漫画榜",10: "少女漫画榜",11: "热血冒险榜",12: "幻想脑洞榜",13: "恋爱后宫榜",
    }
    rank_period_labels = ("周", "月", "总")
    rank_default_period = rank_period_labels[0]
    mappings = {res.SPIDER.Completer.update: {"kind": "update", "day": 0}}
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


@dataclass(frozen=True, slots=True)
class _Dm5PreviewRoute:
    kind: str
    method: str
    url: str
    headers: dict[str, str]
    parser_name: str
    response_format: str = "html"
    data: dict[str, str] | None = None
    parser_kwargs: dict[str, object] = field(default_factory=dict)


class Dm5Parser(_Dm5Contract, Previewer):
    _reader_decoder = Dm5ReaderDecoder()
    _style_url_re = re.compile(r"url\((['\"]?)(?P<url>.+?)\1\)", re.I)
    _book_path_re = re.compile(r"/manhua-(?P<slug>[^/?#]+)/?", re.I)
    _chapter_id_re = re.compile(r"/m(?P<cid>\d+)(?:-p\d+)?/?", re.I)
    _page_count_re = re.compile(r"(\d+)\s*P", re.I)
    _onclick_mid_re = re.compile(r"(?:GetFirstChapterUrl|SetBookmarker)\([^\d]*(?P<mid>\d+)")
    _rank_type_re = re.compile(r"[?&]t=(?P<rank_type>\d+)")
    _title_link_xpath = "(.//h2[contains(@class,'title')]//a | .//p[contains(@class,'title')]//a)[1]"
    _chapter_title_xpath = "(.//p[contains(@class,'chapter')]//a/@title | .//p[contains(@class,'chapter')]//a/text())[1]"

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def parse_rank_periods(cls, html_text: str) -> list[str]:
        sel = Selector(text=html_text)
        periods = [cls._normalize_text(value) for value in sel.css("p.top-type a::text").getall()]
        return [value for value in periods if value]

    @classmethod
    def parse_active_rank_period(cls, html_text: str) -> str | None:
        sel = Selector(text=html_text)
        return cls._normalize_text(sel.css("p.top-type a.active::text").get())

    @classmethod
    def parse_rank_menu(cls, html_text: str) -> dict[int, str]:
        sel = Selector(text=html_text)
        rank_menu = {}
        for node in sel.css("figure.top-menu a[href*='/manhua-rank/?t=']"):
            href = cls._normalize_text(node.xpath("./@href").get())
            label = cls._normalize_text("".join(node.xpath("./text()").getall()))
            if not href or not label:
                continue
            if matched := cls._rank_type_re.search(href):
                rank_menu[int(matched.group("rank_type"))] = label
        return rank_menu

    @classmethod
    def parse_active_rank_type(cls, html_text: str) -> int | None:
        sel = Selector(text=html_text)
        href = cls._normalize_text(sel.css("figure.top-menu a.active::attr(href)").get())
        if not href:
            return None
        if matched := cls._rank_type_re.search(href):
            return int(matched.group("rank_type"))
        return None

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
        slug = raw_value.strip("/")
        if slug.startswith("manhua-"):
            return f"https://{domain}/{slug}/"
        return f"https://{domain}/manhua-{slug}/"

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
    def _append_unique_book(cls, books: list[Dm5BookInfo], seen_urls: set[str], book: Dm5BookInfo | None) -> None:
        if book is None:
            return
        if book.url in seen_urls:
            return
        seen_urls.add(book.url)
        book.idx = len(books) + 1
        books.append(book)

    @classmethod
    def _parse_html_card(cls, node, *, idx: int, domain: str) -> Dm5BookInfo | None:
        title_link = node.xpath(cls._title_link_xpath)
        href = cls._normalize_text(
            title_link.xpath("./@href").get()
            or node.xpath(".//a[contains(@href,'/manhua-')][1]/@href").get()
        )
        title = cls._normalize_text(title_link.xpath("./@title").get() or title_link.xpath("normalize-space(string())").get())
        if not href or not title:
            return None
        book_url = cls._book_url(href, domain=domain)
        book = cls._new_book(idx=idx, url=book_url)
        book.name = title
        book.id = cls._extract_book_mid(node) or ""
        cls._apply_latest(book, node.xpath(cls._chapter_title_xpath).get())
        cls._apply_artists(
            book,
            node.xpath("./div[contains(@class,'mh-item-detali')]//p[contains(@class,'subtitle')]//a/text()").getall()
            or node.xpath("./div[contains(@class,'mh-item-detali')]//p[contains(@class,'zl')][span[contains(.,'作者')]]//a/text()").getall()
            or node.xpath(".//div[contains(@class,'mh-item-tip-detali')]//p[contains(@class,'author')]//a/text()").getall(),
        )
        cover = cls._extract_style_url(node.xpath(".//p[contains(@class,'mh-cover')][1]/@style").get())
        if cover:
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
        return book

    @classmethod
    def _parse_featured_search_card(cls, node, *, idx: int, domain: str) -> Dm5BookInfo | None:
        title_link = node.xpath(cls._title_link_xpath)
        href = cls._normalize_text(title_link.xpath("./@href").get())
        title = cls._normalize_text(title_link.xpath("./@title").get() or title_link.xpath("normalize-space(string())").get())
        if not href or not title:
            return None
        book = cls._new_book(idx=idx, url=cls._book_url(href, domain=domain))
        book.name = title
        book.id = cls._extract_book_mid(node) or ""
        cls._apply_artists(book, node.xpath(".//p[contains(@class,'subtitle')]//a/text()").getall())
        cls._apply_latest(book, node.xpath("(.//a[contains(@class,'btn-2')][1]/@title | .//a[contains(@class,'btn-2')][1]/text())[1]").get())
        cover = cls._normalize_text(node.xpath(".//div[contains(@class,'cover')]//img[1]/@src").get())
        if cover:
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain)
        return book

    @classmethod
    def parse_html_books(cls, html_text: str, *, domain: str) -> list[Dm5BookInfo]:
        sel = Selector(text=html_text)
        books: list[Dm5BookInfo] = []
        seen_urls: set[str] = set()

        for node in sel.css("div.banner_detail_form"):
            cls._append_unique_book(books, seen_urls, cls._parse_featured_search_card(node, idx=len(books) + 1, domain=domain))
        for node in sel.css("div.mh-item"):
            cls._append_unique_book(books, seen_urls, cls._parse_html_card(node, idx=len(books) + 1, domain=domain))
        return books

    @classmethod
    def parse_rank_books(cls, html_text: str, *, domain: str, period: str | None = None) -> list[Dm5BookInfo]:
        sel = Selector(text=html_text)
        panels = list(sel.css("ul.mh-list.top-cat"))
        if not panels:
            return cls.parse_html_books(html_text, domain=domain)

        labels = cls.parse_rank_periods(html_text)
        requested_period = cls._normalize_text(period) or cls.parse_active_rank_period(html_text) or cls.rank_default_period
        if requested_period not in cls.rank_period_labels:
            raise ValueError(f"dm5 rank period must be one of {','.join(cls.rank_period_labels)}, got {requested_period!r}")

        period_index = labels.index(requested_period) if requested_period in labels else cls.rank_period_labels.index(requested_period)
        if period_index >= len(panels):
            raise ValueError(
                f"dm5 rank period panel missing: period={requested_period} panels={len(panels)} labels={labels or list(cls.rank_period_labels)}"
            )

        books: list[Dm5BookInfo] = []
        seen_urls: set[str] = set()
        for node in panels[period_index].css("div.mh-item"):
            cls._append_unique_book(books, seen_urls, cls._parse_html_card(node, idx=len(books) + 1, domain=domain))
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
        Dm5Resp.catch(html_text)
        rows = list(sel.css("div#chapterlistload a[href*='/m']"))
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
        return _ChapterfunSession.from_reader_html(cls, html_text, chapter_url=chapter_url).to_reader_context()

    @classmethod
    def build_chapterfun_request(
        cls,
        reader_context: dict,
        *,
        page: int,
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        return _ChapterfunSession.from_reader_context(reader_context).build_request(page=page).as_tuple()

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
        return _ChapterfunSession.aggregate_page_urls(chunks, total=total, request_url=request_url)


@dataclass(frozen=True, slots=True)
class _ChapterfunRequest:
    page: int
    url: str
    headers: dict[str, str]
    params: dict[str, str]

    def as_tuple(self) -> tuple[str, dict[str, str], dict[str, str]]:
        return self.url, self.headers, self.params


@dataclass(slots=True)
class _ChapterfunSession:
    curl: str
    chapter_url: str
    chapterfun_url: str
    cid: str
    mid: str
    image_count: int
    pageindex: int
    viewsign: str
    viewsign_dt: str
    key: str
    language: str = "1"
    gtk: str = "6"
    next_page: int = 1
    page_chunks: list[list[tuple[int, str]]] = field(default_factory=list)

    @classmethod
    def from_reader_html(cls, parser: type[Dm5Parser], html_text: str, *, chapter_url: str) -> _ChapterfunSession:
        image_count = int(parser._extract_js_var(html_text, "DM5_IMAGE_COUNT"))
        if image_count < 1:
            raise ValueError(f"dm5 chapter page returned invalid DM5_IMAGE_COUNT: url={chapter_url}")
        request_domain = urlparse(chapter_url).netloc or parser.domain
        dm5_curl = str(parser._extract_js_var(html_text, "DM5_CURL"))
        canonical_chapter_url = parser.normalize_preview_resource(dm5_curl, domain=request_domain) or chapter_url
        sel = Selector(text=html_text)
        return cls(
            curl=dm5_curl,
            chapter_url=canonical_chapter_url,
            chapterfun_url=f"{canonical_chapter_url.rstrip('/')}/chapterfun.ashx",
            cid=str(parser._extract_js_var(html_text, "DM5_CID")),
            mid=str(parser._extract_js_var(html_text, "DM5_MID")),
            image_count=image_count,
            pageindex=int(parser._extract_js_var(html_text, "DM5_PAGEINDEX")),
            viewsign=str(parser._extract_js_var(html_text, "DM5_VIEWSIGN")),
            viewsign_dt=str(parser._extract_js_var(html_text, "DM5_VIEWSIGN_DT")),
            key=parser._normalize_text(sel.xpath("//input[@id='dm5_key']/@value").get()),
        )

    @classmethod
    def from_reader_context(cls, reader_context: dict) -> _ChapterfunSession:
        return cls(
            curl=str(reader_context["DM5_CURL"]),
            chapter_url=str(reader_context["DM5_CHAPTER_URL"]),
            chapterfun_url=str(reader_context["DM5_CHAPTERFUN_URL"]),
            cid=str(reader_context["DM5_CID"]),
            mid=str(reader_context["DM5_MID"]),
            image_count=int(reader_context["DM5_IMAGE_COUNT"]),
            pageindex=int(reader_context["DM5_PAGEINDEX"]),
            viewsign=str(reader_context["DM5_VIEWSIGN"]),
            viewsign_dt=str(reader_context["DM5_VIEWSIGN_DT"]),
            key=str(reader_context.get("DM5_KEY", "")),
            language=str(reader_context.get("DM5_LANGUAGE", "1")),
            gtk=str(reader_context.get("DM5_GTK", "6")),
        )

    def to_reader_context(self) -> dict[str, str | int]:
        return {
            "DM5_CURL": self.curl,
            "DM5_MID": self.mid,
            "DM5_CID": self.cid,
            "DM5_IMAGE_COUNT": self.image_count,
            "DM5_PAGEINDEX": self.pageindex,
            "DM5_VIEWSIGN": self.viewsign,
            "DM5_VIEWSIGN_DT": self.viewsign_dt,
            "DM5_KEY": self.key,
            "DM5_LANGUAGE": self.language,
            "DM5_GTK": self.gtk,
            "DM5_CHAPTERFUN_URL": self.chapterfun_url,
            "DM5_CHAPTER_URL": self.chapter_url,
        }

    def has_pending_request(self) -> bool:
        return self.next_page <= self.image_count

    def build_request(self, *, page: int | None = None) -> _ChapterfunRequest:
        request_page = self.next_page if page is None else max(1, int(page))
        return _ChapterfunRequest(
            page=request_page,
            url=self.chapterfun_url,
            headers={
                **_Dm5Contract.ua,
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.chapter_url,
            },
            params={
                "cid": self.cid,
                "page": str(request_page),
                "key": self.key,
                "language": self.language,
                "gtk": self.gtk,
                "_cid": self.cid,
                "_mid": self.mid,
                "_dt": self.viewsign_dt,
                "_sign": self.viewsign,
            },
        )

    def record_chunk(self, chunk: list[tuple[int, str]], *, request_url: str) -> None:
        if not chunk:
            raise ValueError(f"dm5 chapterfun returned empty image chunk: url={request_url}")
        self.page_chunks.append(chunk)
        chunk_last_page = max(page_no for page_no, _url in chunk)
        if chunk_last_page < self.next_page:
            raise ValueError(f"dm5 chapterfun pagination made no progress: page={self.next_page} url={request_url}")
        self.next_page = self.image_count + 1 if chunk_last_page >= self.image_count else chunk_last_page

    def accept_response(self, parser: type[Dm5Parser], script_text: str, *, request_url: str) -> None:
        chunk = parser.decode_chapterfun_page_urls(script_text, request_url=request_url, expected_cid=self.cid)
        self.record_chunk(chunk, request_url=request_url)

    @staticmethod
    def aggregate_page_urls(chunks: list[list[tuple[int, str]]], *, total: int, request_url: str) -> list[str]:
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

    def build_page_urls(self) -> list[str]:
        return self.aggregate_page_urls(self.page_chunks, total=self.image_count, request_url=self.chapterfun_url)

    def build_image_headers(self) -> dict[str, str]:
        headers = dict(_Dm5Contract.image_ua)
        headers["Referer"] = self.chapter_url
        return headers

    def apply_to_episode(self, episode, *, page_urls: list[str]) -> None:
        reader_context = self.to_reader_context()
        for key, value in reader_context.items():
            setattr(episode, key, value)
        episode.dm5_reader_context = dict(reader_context)
        episode.dm5_image_headers = self.build_image_headers()
        episode.chapter_referer = self.chapter_url
        episode.pages = len(page_urls)
        episode.page_urls = list(page_urls)


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
    def build_rank_url(cls, rank_type: int, *, domain: str) -> str:
        rank_type = int(rank_type)
        if rank_type not in cls.rank_types:
            raise ValueError(f"dm5 rank type must be in 1..13, got {rank_type}")
        return f"https://{domain}{cls.rank_path}?t={rank_type}"

    @staticmethod
    def _normalize_keyword(keyword: str | None) -> str:
        return "".join(str(keyword or "").split())

    @classmethod
    def _mapping_raw_value(cls, mapping_value) -> str:
        if isinstance(mapping_value, dict):
            mapping_value = mapping_value.get("url") or mapping_value.get("value") or ""
        return str(mapping_value or "").strip()

    @classmethod
    def rank_custom_map_examples(cls, *, domain: str) -> dict[str, str]:
        return {
            label: cls.build_rank_url(rank_type, domain=domain)
            for rank_type, label in cls.rank_types.items()
        }

    @classmethod
    def build_mapping_url(cls, mapping_value, *, domain: str) -> str:
        raw_value = cls._mapping_raw_value(mapping_value)
        parsed = urlparse(raw_value)
        normalized_path = Previewer.normalize_preview_resource(parsed.path or raw_value, domain=domain)
        if not normalized_path:
            raise ValueError("dm5 mapping URL is required")
        url = normalized_path
        if parsed.query:
            url = f"{url}?{parsed.query}"
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
    def parse_rank_type_from_mapping(cls, mapping_value, *, domain: str) -> int | None:
        try:
            url = cls.build_mapping_url(mapping_value, domain=domain)
        except ValueError:
            return None
        parsed = urlparse(url)
        if parsed.path.rstrip("/") != cls.rank_path.rstrip("/"):
            return None
        matched = re.search(r"(?:^|[?&])t=(?P<rank_type>\d+)", parsed.query)
        if not matched:
            return None
        rank_type = int(matched.group("rank_type"))
        return rank_type if rank_type in cls.rank_types else None

    @classmethod
    def resolve_rank_search_spec(cls, keyword: str, *, mappings: dict | None, domain: str) -> dict | None:
        normalized_keyword = cls._normalize_keyword(keyword)
        if not normalized_keyword:
            return None

        period = cls.rank_default_period
        rank_keyword = normalized_keyword
        if normalized_keyword[-1:] in cls.rank_period_labels:
            period = normalized_keyword[-1]
            rank_keyword = normalized_keyword[:-1]
        if not rank_keyword:
            return None

        rank_labels = {
            cls._normalize_keyword(label): rank_type
            for rank_type, label in cls.rank_types.items()
        }
        for mapping_key, mapping_value in (mappings or {}).items():
            rank_type = cls.parse_rank_type_from_mapping(mapping_value, domain=domain)
            if rank_type is None:
                continue
            normalized_key = cls._normalize_keyword(mapping_key)
            if normalized_key:
                rank_labels[normalized_key] = rank_type

        rank_type = rank_labels.get(rank_keyword)
        if rank_type is None:
            return None
        return {
            "keyword": rank_keyword,"period": period,"rank_type": rank_type,"rank_label": cls.rank_types[rank_type],
            "url": cls.build_rank_url(rank_type, domain=domain),
        }

    @classmethod
    def build_update_request(cls, *, domain: str, page: int, day: int = 0) -> tuple[str, dict[str, str], dict[str, str]]:
        stamp = int(time.time() * 1000)
        url = f"https://{domain}/manhua-new/dm5.ashx?action=getupdatecomics&d={stamp}"
        headers = {
            **cls.ua,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": f"https://{domain}",
            "Referer": f"https://{domain}/manhua-new/",
        }
        preview_page = max(1, int(page or 1))
        request_day = max(0, int(day or 0)) + (preview_page - 1)
        data = {"page": "1", "pagesize": str(cls.update_page_size), "DK": str(request_day)}
        return url, headers, data

    @classmethod
    def resolve_preview_route(cls, keyword: str, *, page: int, domain: str, mappings: dict | None) -> _Dm5PreviewRoute:
        normalized_keyword = keyword.strip()
        if normalized_keyword in (mappings or {}):
            mapping_value = mappings[normalized_keyword]
            if cls.is_update_mapping(mapping_value):
                url, headers, data = cls.build_update_request(domain=domain, page=page, day=cls.mapping_update_day(mapping_value))
                return _Dm5PreviewRoute(
                    kind="update",
                    method="POST",
                    url=url,
                    headers=headers,
                    data=data,
                    parser_name="parse_update_payload",
                    response_format="json",
                )

        rank_spec = cls.resolve_rank_search_spec(normalized_keyword, mappings=mappings, domain=domain)
        if rank_spec is not None:
            return _Dm5PreviewRoute(
                kind="rank",
                method="GET",
                url=rank_spec["url"],
                headers=dict(cls.ua),
                parser_name="parse_rank_books",
                parser_kwargs={"period": rank_spec["period"]},
            )

        if normalized_keyword in (mappings or {}):
            return _Dm5PreviewRoute(
                kind="mapping",
                method="GET",
                url=cls.build_mapping_url(mappings[normalized_keyword], domain=domain),
                headers=dict(cls.ua),
                parser_name="parse_html_books",
            )

        return _Dm5PreviewRoute(
            kind="search",
            method="GET",
            url=cls.build_search_url(normalized_keyword, domain=domain, page=page),
            headers=dict(cls.ua),
            parser_name="parse_search_document",
        )

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
        route = self.resolve_preview_route(keyword, page=page, domain=domain, mappings=mappings)
        request_kw = {"headers": route.headers, "follow_redirects": True, "timeout": 12}
        if route.data is not None:
            request_kw["data"] = route.data
        resp = await self.ensure_preview_client().request(route.method, route.url, **request_kw)
        resp.raise_for_status()
        parser = getattr(owner.parser, route.parser_name)
        if route.response_format == "json":
            payload = resp.json()
            parse_domain = domain
        else:
            payload = resp.text
            parse_domain = urlparse(str(resp.url)).netloc or domain
        return await asyncio.to_thread(parser, payload, domain=parse_domain, **route.parser_kwargs)

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

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        resp = await self.ensure_preview_client().get(episode.url, headers=self.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        episode.url = str(resp.url)
        chapterfun = await asyncio.to_thread(_ChapterfunSession.from_reader_html, owner.parser, resp.text, chapter_url=episode.url)
        while chapterfun.has_pending_request():
            request = chapterfun.build_request()
            chunk_resp = await self.ensure_preview_client().get(
                request.url,
                params=request.params,
                headers=request.headers,
                follow_redirects=True,
                timeout=12,
            )
            chunk_resp.raise_for_status()
            await asyncio.to_thread(chapterfun.accept_response, owner.parser, chunk_resp.text, request_url=str(chunk_resp.url))
        page_urls = chapterfun.build_page_urls()
        chapterfun.apply_to_episode(episode, page_urls=page_urls)
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
