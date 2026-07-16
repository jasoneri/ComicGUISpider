from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from urllib.parse import parse_qs, quote, urlsplit

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.core.err import SiteBusinessError
from utils.website.info import ComicabcBookInfo, Episode

_COMICABC_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True, slots=True)
class _SectionImageChapter:
    page_count: int
    server_code: str
    chapter_id: str
    part_code: str
    chapter_path: str
    page_token: str


class _SectionImageTarget:
    __slots__ = ("chapter", "part")

    def __init__(self, section_url: str) -> None:
        raw_chapter = parse_qs(urlsplit(section_url).query).get("ch", ["1"])[0].split("#", 1)[0]
        chapter = raw_chapter.split("-", 1)[0] or "1"
        part_match = re.search(r"[a-z]$", chapter)
        self.part = part_match.group(0) if part_match else ""
        if self.part != "" and len(chapter) > 1:
            chapter = chapter[:-1]
        self.chapter = chapter


@dataclass(frozen=True, slots=True)
class _SectionImageSlot:
    stride: int
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class _SectionImageRoles:
    pages: str
    chapter: str
    part: str
    server: str
    token: str


class _SectionImageHost:
    __slots__ = ("prefix", "domain_left", "domain_right", "image_suffix", "item_id")

    def __init__(self, data: str, item_id: int) -> None:
        tail = []
        tail_base = len(data) - 47
        for index in range(1, 5):
            start = tail_base - index * 6
            tail.append(bytes.fromhex(data[start : start + 6]).decode("latin-1"))
        self.image_suffix, self.domain_right, self.domain_left, self.prefix = tail
        self.item_id = item_id


# Python reimplementation of observed 8comic script behavior.
# Cross-checked with Keiyoushi zh/comicabc Comicabc.kt, Apache-2.0, commit 5d33d04c61b7ad4da05f148feecbab169f54dc64.
class _SectionImageDecoder:
    _string_var_re = re.compile(r"var\s+(?P<name>[A-Za-z_]\w*)\s*=\s*'(?P<value>[^']*)';")
    _int_var_re = re.compile(r"var\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(?:(?P<alias>[A-Za-z_]\w*)\s*=\s*)?'?(?P<value>\d+)'?;")
    _loop_count_re = re.compile(r"for\s*\(\s*var\s+i\s*=\s*0\s*;\s*i\s*<\s*(?P<count>\d+)\s*;\s*i\+\+\s*\)")
    _slot_re = re.compile(
        r"var\s+(?P<name>[A-Za-z_]\w*)\s*=\s*lc\((?P<slice>[A-Za-z_]\w*)\("
        r"(?P<data>[A-Za-z_]\w*)\s*,\s*i\s*\*\s*\((?P<stride>[A-Za-z_]\w*)\s*(?P<op>[+-])\s*(?P<delta>\d+)\)"
        r"\s*\+\s*(?P<offset>\d+)(?:\s*,\s*(?P<length>\d+))?\)\);"
    )

    def __init__(self, script: str, section_url: str):
        self.script = script
        self.section_url = section_url
        self.string_vars = {match.group("name"): match.group("value") for match in self._string_var_re.finditer(script)}
        self.int_vars = {}
        for match in self._int_var_re.finditer(script):
            value = int(match.group("value"))
            self.int_vars[match.group("name")] = value
            if alias := match.group("alias"):
                self.int_vars[alias] = value
        loop_match = self._loop_count_re.search(script)
        missing = [
            name
            for name, present in (("integer var 'ti'", "ti" in self.int_vars), ("chapter loop count", loop_match))
            if not present
        ]
        if missing:
            raise ValueError(f"comicabc section image script missing {', '.join(missing)}: url={section_url}")
        self.item_id = self.int_vars["ti"]
        self.chapter_count = int(loop_match.group("count"))
        self.slots: dict[str, _SectionImageSlot] = {}
        self.data = ""
        self.slice_name = ""
        self._load_slots()
        self.roles = self._decode_roles()
        self.host = _SectionImageHost(self.data, self.item_id)
        self.target = _SectionImageTarget(section_url)

    def _load_slots(self) -> None:
        slot_matches = list(self._slot_re.finditer(self.script))
        if len(slot_matches) == 0:
            raise ValueError(f"comicabc section image script missing slot declarations: url={self.section_url}")

        data_names = {match.group("data") for match in slot_matches}
        slice_names = {match.group("slice") for match in slot_matches}
        missing_ints = set()
        for match in slot_matches:
            stride_name = match.group("stride")
            if stride_name not in self.int_vars:
                missing_ints.add(stride_name)
                continue
            delta = int(match.group("delta"))
            stride = self.int_vars[stride_name] + delta if match.group("op") == "+" else self.int_vars[stride_name] - delta
            self.slots[match.group("name")] = _SectionImageSlot(stride, int(match.group("offset")), int(match.group("length") or 40))

        if missing_ints:
            raise ValueError(f"comicabc section image script missing integer vars {sorted(missing_ints)}: url={self.section_url}")
        if len(data_names) != 1 or len(slice_names) != 1:
            raise ValueError(f"comicabc section image script has ambiguous slot declarations: url={self.section_url}")

        self.data_name = next(iter(data_names))
        self.slice_name = next(iter(slice_names))
        if self.data_name not in self.string_vars:
            raise ValueError(f"comicabc section image script missing data var {self.data_name!r}: url={self.section_url}")
        self.data = self.string_vars[self.data_name]

    def _decode_roles(self) -> _SectionImageRoles:
        condition = re.search(
            r"ps\s*=\s*(?P<pages>[A-Za-z_]\w*)\s*;\s*if\s*\(\s*(?P<chapter>[A-Za-z_]\w*)\s*==\s*ch"
            r"\s*&&\s*\(\s*part\s*==\s*''\s*\|\|\s*part\s*==\s*(?P<part>[A-Za-z_]\w*)\s*\)\s*\)",
            self.script,
        )
        slice_call = re.escape(self.slice_name)
        server_pattern = (
            rf"\+{slice_call}\((?P<server>[A-Za-z_]\w*)\s*,\s*0\s*,\s*1\s*\)"
            rf".*?\+{slice_call}\((?P=server)\s*,\s*1\s*,\s*1\s*\)"
        )
        token_pattern = rf"nn\(j\).*?\+{slice_call}\((?P<token>[A-Za-z_]\w*)\s*,\s*mm\(j\)\s*,\s*3\s*\)"
        server = re.search(server_pattern, self.script, re.S)
        token = re.search(token_pattern, self.script, re.S)
        missing = [
            name
            for name, match in (
                ("chapter condition", condition),
                ("server image expression", server),
                ("page token image expression", token),
            )
            if match is None
        ]
        if missing:
            raise ValueError(f"comicabc section image script missing {', '.join(missing)}: url={self.section_url}")
        roles = _SectionImageRoles(
            condition.group("pages"), condition.group("chapter"), condition.group("part"), server.group("server"), token.group("token")
        )
        missing_slots = sorted(set((roles.pages, roles.chapter, roles.part, roles.server, roles.token)).difference(self.slots))
        if missing_slots:
            raise ValueError(f"comicabc section image script roles missing slots {missing_slots}: url={self.section_url}")
        return roles

    def _read(self, slot_name: str, index: int) -> int | str:
        slot = self.slots[slot_name]
        start = index * slot.stride + slot.offset
        value = self.data[start : start + slot.length]
        if len(value) != 2:
            return value
        head, tail = value
        if head == "Z":
            return 8000 + _COMICABC_ALPHABET.index(tail)
        return _COMICABC_ALPHABET.index(head) * 52 + _COMICABC_ALPHABET.index(tail)

    def _chapter_at(self, index: int) -> _SectionImageChapter:
        chapter_id = str(self._read(self.roles.chapter, index))
        part_code = str(self._read(self.roles.part, index))
        resolved_part = part_code if self.target.part == "" and part_code != "0" else self.target.part
        page_count = int(self._read(self.roles.pages, index))
        server_code = str(self._read(self.roles.server, index))
        page_token = str(self._read(self.roles.token, index))
        return _SectionImageChapter(
            page_count=page_count, server_code=server_code, chapter_id=chapter_id, part_code=part_code,
            chapter_path=chapter_id + resolved_part, page_token=page_token
        )

    def _page_url(self, chapter: _SectionImageChapter, page: int) -> str:
        host = f"https://{self.host.prefix}{chapter.server_code[0]}.8{self.host.domain_left}{self.host.domain_right}{self.host.domain_left}"
        token_offset = ((page - 1) // 10) % 10 + ((page - 1) % 10) * 3
        page_token = chapter.page_token[token_offset : token_offset + 3]
        path = f"{chapter.server_code[1]}/{self.host.item_id}/{chapter.chapter_path}/{page:03d}_{page_token}.{self.host.image_suffix}"
        return f"{host}/{path}"

    def decode(self) -> list[str]:
        for index in range(self.chapter_count):
            chapter = self._chapter_at(index)
            if chapter.chapter_id == self.target.chapter and (self.target.part == "" or self.target.part == chapter.part_code):
                return [self._page_url(chapter, page) for page in range(1, chapter.page_count + 1)]
        raise ValueError(f"comicabc section image script missing chapter {self.target.chapter!r}: url={self.section_url}")


class _ComicabcContract:
    name = "comicabc"
    proxy_policy = "proxy"
    domain = "www.8comic.com"
    index = f"https://{domain}/"
    popular = f"{index}comic/h-1.html"
    update = f"{index}comic/u-1.html"
    search_url_head = f"{index}member/search.aspx?key="
    mappings = {
        res.SPIDER.Completer.index: popular,
        res.SPIDER.Completer.popular: popular,
        res.SPIDER.Completer.update: update,
    }
    turn_page_info = (r"-\d+\.html",)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,zh-CN;q=0.8,en;q=0.5",
    }
    book_hea = headers
    image_ua = {
        "User-Agent": headers["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": headers["Accept-Language"],
    }


class ComicabcParser(_ComicabcContract, Previewer):
    _book_id_re = re.compile(r"/html/(?P<book_id>\d+)\.html")
    _chapter_re = re.compile(r"cview\('(?P<comic_id>\d+)-(?P<chapter_id>[^']+)\.html")

    @classmethod
    def normalize_site_resource(cls, value: str | None, *, domain: str | None = None) -> str | None:
        return cls.normalize_preview_resource(value, domain=domain or cls.domain)

    @staticmethod
    def _clean_text(value: str | None) -> str:
        return " ".join((value or "").split())

    @classmethod
    def _clean_node_text(cls, node, xpath: str = ".//text()") -> str:
        return cls._clean_text("".join(node.xpath(xpath).getall()))

    @staticmethod
    def _assert_not_cloudflare_block(html_text: str, *, stage: str) -> None:
        if "cf-error-details" in html_text or "Attention Required! | Cloudflare" in html_text:
            raise ValueError(f"comicabc {stage} response is a Cloudflare block page")

    @classmethod
    def parse_book_id(cls, url: str) -> str:
        matched = cls._book_id_re.search(url or "")
        if not matched:
            raise ValueError(f"comicabc book url missing /html/<id>.html shape: {url!r}")
        return matched.group("book_id")

    @classmethod
    def _new_book(cls, *, idx: int, url: str) -> ComicabcBookInfo:
        return ComicabcBookInfo(idx=idx, render_keys=["name", "latest_sec"], url=url, preview_url=url)

    @classmethod
    def parse_search_item(cls, node, *, idx: int, domain: str) -> ComicabcBookInfo:
        href = node.xpath("./@href").get()
        if not href:
            raise ValueError(f"comicabc search card missing href: idx={idx}")
        url = cls.normalize_site_resource(href, domain=domain)
        book = cls._new_book(idx=idx, url=url)
        book.id = cls.parse_book_id(url)
        book.name = cls._clean_node_text(node, ".//li[contains(@class,'comicpic_col6_name')]//text()")
        if not book.name:
            raise ValueError(f"comicabc search card missing title: idx={idx} href={href}")
        latest = cls._clean_node_text(node, ".//*[contains(@class,'comicpic_col6_eps') or contains(@class,'li-covers-eps')]//text()")
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        cover = node.xpath(".//img[1]/@src").get()
        book.img_preview = cls.normalize_site_resource(cover, domain=domain) if cover else None
        return book

    @classmethod
    def parse_list_item(cls, node, *, idx: int, domain: str) -> ComicabcBookInfo:
        href = node.xpath("./@href").get()
        if not href:
            raise ValueError(f"comicabc list card missing href: idx={idx}")
        url = cls.normalize_site_resource(href, domain=domain)
        if not url:
            raise ValueError(f"comicabc list card has invalid href: idx={idx} href={href!r}")
        book = cls._new_book(idx=idx, url=url)
        book.id = cls.parse_book_id(url)
        name = cls._clean_text(node.xpath("./@title").get())
        if not name:
            name = cls._clean_node_text(node, ".//*[contains(@class,'cat2_list_name')]//text()")
        book.name = name
        if not book.name:
            raise ValueError(f"comicabc list card missing title: idx={idx} href={href}")
        latest = cls._clean_node_text(node, ".//*[contains(@class,'cat2_list_epsstatus')]//text()")
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        updated = cls._clean_node_text(node, ".//*[contains(@class,'cat2_list_date')]//text()")
        if updated:
            book.public_date = updated
            book.datetime_updated = updated
        cover = node.xpath(".//img[1]/@src").get()
        book.img_preview = cls.normalize_site_resource(cover, domain=domain) if cover else None
        return book

    @classmethod
    def parse_list_document(cls, html_text: str, *, domain: str) -> list[ComicabcBookInfo]:
        cls._assert_not_cloudflare_block(html_text, stage="list")
        sel = Selector(text=html_text)
        cards = sel.css("a.comicpic_col6[href]")
        if len(cards):
            return [cls.parse_search_item(card, idx=idx, domain=domain) for idx, card in enumerate(cards, start=1)]
        list_cards = sel.css(".cat2_list a[href]")
        if not len(list_cards):
            raise ValueError("comicabc list page missing result cards")
        return [cls.parse_list_item(card, idx=idx, domain=domain) for idx, card in enumerate(list_cards, start=1)]

    @classmethod
    def parse_search_document(cls, html_text: str, *, domain: str) -> list[ComicabcBookInfo]:
        cls._assert_not_cloudflare_block(html_text, stage="search")
        sel = Selector(text=html_text)
        cards = sel.css("a.comicpic_col6[href]")
        if len(cards) == 0 and not sel.xpath("//*[contains(text(), '檢索結果')]").get():
            raise ValueError("comicabc search page missing result container")
        return [cls.parse_search_item(card, idx=idx, domain=domain) for idx, card in enumerate(cards, start=1)]

    @classmethod
    def _extract_book_title(cls, sel: Selector) -> str:
        title = cls._clean_text(sel.css(".item_content_box .h2::text").get())
        if title:
            return title
        title = cls._clean_node_text(sel.css(".item_content_box .h2"))
        if title:
            return title
        title = cls._clean_text(sel.css("title::text").get())
        if not title:
            return ""
        for separator in (" 最新漫畫", " 最新漫画", " - 無限動漫", " - 无限动漫", " - 8comic"):
            if separator in title:
                title = title.split(separator, 1)[0]
                break
        return cls._clean_text(title)

    @classmethod
    def apply_book_fields(cls, book: ComicabcBookInfo, html_text: str, *, domain: str) -> ComicabcBookInfo:
        cls._assert_not_cloudflare_block(html_text, stage="book")
        if not (html_text or "").strip():
            raise SiteBusinessError(f"comicabc book page returned empty body: url={book.url}")
        sel = Selector(text=html_text)
        title = cls._extract_book_title(sel)
        if not title:
            raise SiteBusinessError(f"comicabc book page missing title: url={book.url}")
        book.name = title
        aliases = cls._clean_text(sel.css(".item_content_box .h6::text").get())
        if aliases:
            book.other_name_raw = aliases
            book.other_names = [item.strip() for item in aliases.split(",") if item.strip()]
        author = cls._clean_text(sel.css(".item-info-author::text").get())
        if author:
            book.artist = author.removeprefix("作者:").strip()
        book.public_date = cls._clean_text(sel.css(".item-info-date::text").get()) or None
        book.description = cls._clean_node_text(sel.css(".item_info_detail"))
        cover = sel.css(".item-cover img::attr(src)").get()
        book.img_preview = cls.normalize_site_resource(cover, domain=domain) if cover else book.img_preview
        book.episodes = cls.parse_episodes(html_text, book, domain=domain)
        return book

    @classmethod
    def parse_book(cls, html_text: str, book: ComicabcBookInfo, *, domain: str) -> ComicabcBookInfo:
        return cls.apply_book_fields(book, html_text, domain=domain)

    @classmethod
    def parse_episodes(cls, html_text: str, book: ComicabcBookInfo, *, domain: str) -> list[Episode]:
        sel = Selector(text=html_text)
        rows = sel.css("#chapters a[onclick*='cview']")
        if not rows:
            raise ValueError(f"comicabc chapter list returned no chapters: book={book.url}")
        episodes = []
        for row in rows:
            onclick = row.xpath("./@onclick").get() or ""
            matched = cls._chapter_re.search(onclick)
            if not matched:
                raise ValueError(f"comicabc chapter row missing cview target: book={book.url} onclick={onclick!r}")
            name = cls._clean_node_text(row, ".//text()[not(ancestor::script)]")
            if not name:
                raise ValueError(f"comicabc chapter row missing title: book={book.url} onclick={onclick!r}")
            comic_id = matched.group("comic_id")
            chapter_id = matched.group("chapter_id")
            url = cls.normalize_site_resource(f"/online/new-{comic_id}.html?ch={chapter_id}", domain=domain)
            episode = Episode(from_book=book, id=f"{comic_id}-{chapter_id}", idx=len(episodes) + 1, url=url, name=name)
            episode.chapter_referer = url
            episodes.append(episode)
        return episodes

    @classmethod
    def _section_image_script(cls, html_text: str, *, section_url: str) -> str:
        cls._assert_not_cloudflare_block(html_text, stage="section")
        for script in re.findall(r"<script[^>]*>(.*?)</script>", html_text, flags=re.S | re.I):
            if "function request(qs)" in script and "comics-pics" in script:
                return script
        raise ValueError(f"comicabc section page missing image construction script: url={section_url}")

    @classmethod
    def parse_page_urls_from_html(cls, html_text: str, *, section_url: str) -> list[str]:
        script = cls._section_image_script(html_text, section_url=section_url)
        return _SectionImageDecoder(script, section_url).decode()


class ComicabcReqer(_ComicabcContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def build_search_url(cls, keyword: str, *, domain: str, custom_map: dict | None = None, page: int = 1) -> str:
        keyword = keyword.strip()
        mappings = Previewer.merge_search_mappings(cls.mappings, custom_map)
        if keyword in mappings:
            base_url = Previewer.normalize_preview_resource(mappings[keyword], domain=domain)
            return Previewer.build_page_url(base_url, page, cls.turn_page_info)
        return f"https://{domain}/member/search.aspx?key={quote(keyword)}&page={max(1, int(page or 1))}"

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

    async def _fetch_text(self, url: str, *, headers: dict | None = None, stage: str = "page"):
        request_headers = dict(headers or self.headers)
        if "Referer" not in request_headers:
            request_headers["Referer"] = self.index
        resp = await self.ensure_preview_client().get(
            url, headers=request_headers, follow_redirects=True, timeout=12
        )
        resp.raise_for_status()
        if not (resp.text or "").strip():
            raise SiteBusinessError(f"comicabc {stage} returned empty body: url={url}")
        return resp

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        domain = site_kw.get("domain") or getattr(self, "domain", None) or type(owner).domain
        custom_map = site_kw.get("custom_map")
        page = max(1, int(page or 1))
        url = self.build_search_url(keyword, domain=domain, custom_map=custom_map, page=page)
        resp = await self._fetch_text(url, stage="list" if self.is_mapped_search_keyword(keyword, custom_map=custom_map) else "search")
        mapped_keyword = self.is_mapped_search_keyword(keyword, custom_map=custom_map)
        parser = owner.parser.parse_list_document if mapped_keyword else owner.parser.parse_search_document
        return await asyncio.to_thread(parser, resp.text, domain=domain)

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        domain = self.preview_site_kwargs().get("domain") or getattr(self, "domain", None) or type(owner).domain
        referer = getattr(book, "preview_url", None) or getattr(book, "url", None) or self.index
        resp = await self._fetch_text(book.url, headers={**self.headers, "Referer": referer}, stage="book")
        parsed = await asyncio.to_thread(owner.parser.parse_book, resp.text, book, domain=domain)
        return parsed.episodes

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        referer = getattr(episode.from_book, "preview_url", None) or getattr(episode.from_book, "url", None) or self.index
        resp = await self._fetch_text(
            episode.url, headers={**self.headers, "Referer": referer}, stage="section"
        )
        urls = await asyncio.to_thread(owner.parser.parse_page_urls_from_html, resp.text, section_url=str(resp.url))
        episode.pages = len(urls)
        episode.page_urls = list(urls)
        episode.chapter_referer = str(resp.url)
        return urls


class ComicabcUtils(_ComicabcContract, Utils, Previewer):
    parser = ComicabcParser
    reqer_cls = ComicabcReqer

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
