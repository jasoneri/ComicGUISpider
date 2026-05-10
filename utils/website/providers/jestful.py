from __future__ import annotations

import asyncio
import json
import re
import secrets
import string
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import httpx
from scrapy import Selector

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.info import Episode, JestfulBookInfo

SHOW_ID_RE = re.compile(r"show\((\d+)\)")


class _JestfulContract:
    name = "jestful"
    proxy_policy = "direct"
    domain = "jestful.net"
    index = f"https://{domain}/"
    mappings = {res.SPIDER.Completer.index: index}
    pop_concurrency = 6
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
    _update_sort = "last_update"
    _update_sort_type = "DESC"
    _random_alphabet = string.ascii_letters + string.digits


@dataclass(frozen=True, slots=True)
class _JestfulSiteContext:
    host: str
    origin: str


@dataclass(frozen=True, slots=True)
class TitleAliasResult:
    raw_other_name: str
    aliases: tuple[str, ...]
    preferred_title: str
    preferred_reason: str


class TextSemantics:
    def normalize_text(self, value: str | None) -> str:
        return " ".join((value or "").split())

    def unique_keep_order(self, values: list[str]) -> list[str]:
        seen = set()
        resolved = []
        for value in values:
            cleaned = self.normalize_text(value)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            resolved.append(cleaned)
        return resolved

    def strip_label_prefix(self, full_text: str, label: str) -> str:
        normalized_full = self.normalize_text(full_text)
        normalized_label = self.normalize_text(label).rstrip(":")
        if not normalized_label:
            return normalized_full
        for prefix in (f"{normalized_label}:", normalized_label):
            if normalized_full.startswith(prefix):
                return self.normalize_text(normalized_full[len(prefix):].lstrip(" :"))
        return normalized_full

    def parse_labeled_rows(self, rows, *, label_xpath: str) -> dict[str, str]:
        fields = {}
        for row in rows:
            label = self.normalize_text("".join(row.xpath(label_xpath).getall())).rstrip(":")
            if not label:
                continue
            full_text = self.normalize_text("".join(row.xpath(".//text()").getall()))
            fields[label.lower()] = self.strip_label_prefix(full_text, label)
        return fields

    def split_csv_field(self, value: str | None) -> list[str]:
        return [part for part in (self.normalize_text(chunk) for chunk in (value or "").split(",")) if part]


class UnicodeScriptClassifier:
    def __init__(self):
        self._char_family_cache: dict[str, str] = {}

    @staticmethod
    def is_non_ascii(value: str) -> bool:
        return any(ord(ch) > 127 for ch in value)

    def char_script_family(self, ch: str) -> str:
        if ch in self._char_family_cache:
            return self._char_family_cache[ch]
        codepoint = ord(ch)
        if 0x3040 <= codepoint <= 0x30FF or 0x31F0 <= codepoint <= 0x31FF:
            family = "japanese-kana"
        elif 0x3400 <= codepoint <= 0x4DBF or 0x4E00 <= codepoint <= 0x9FFF:
            family = "han"
        elif 0x1100 <= codepoint <= 0x11FF or 0x3130 <= codepoint <= 0x318F or 0xAC00 <= codepoint <= 0xD7AF:
            family = "hangul"
        else:
            name = unicodedata.name(ch, "")
            if "LATIN" in name:
                family = "latin"
            elif "CYRILLIC" in name:
                family = "cyrillic"
            elif "GREEK" in name:
                family = "greek"
            elif "ARABIC" in name:
                family = "arabic"
            elif "HEBREW" in name:
                family = "hebrew"
            elif "THAI" in name:
                family = "thai"
            else:
                family = "non-latin"
        self._char_family_cache[ch] = family
        return family

    def token_family(self, token: str) -> str:
        families = set()
        for ch in token:
            if ch.isascii():
                if ch.isalpha():
                    families.add("latin")
                continue
            if ch.isdigit():
                continue
            category = unicodedata.category(ch)
            if category.startswith(("P", "S")):
                continue
            families.add(self.char_script_family(ch))
        if not families:
            return ""
        if families <= {"latin"}:
            return "latin"
        if families <= {"han", "japanese-kana"}:
            return "japanese" if "japanese-kana" in families else "han"
        if families <= {"hangul"}:
            return "hangul"
        if "latin" in families:
            return "mixed-non-latin"
        non_latin_families = sorted(families)
        return non_latin_families[0] if len(non_latin_families) == 1 else "+".join(non_latin_families)

class TitleAliasSession:
    def __init__(self, *, base_title: str | None, raw_other_name: str | None):
        self._semantics = TextSemantics()
        self._classifier = UnicodeScriptClassifier()
        self._base_title = self._semantics.normalize_text(base_title)
        self._raw_other_name = self._semantics.normalize_text(raw_other_name)
        self._aliases: tuple[str, ...] | None = None
        self._result: TitleAliasResult | None = None

    def _extract_aliases(self) -> tuple[str, ...]:
        if self._aliases is not None:
            return self._aliases
        cleaned = self._raw_other_name
        if not cleaned:
            self._aliases = ()
            return self._aliases
        aliases = []
        current_tokens = []
        current_family = ""
        for token in cleaned.split():
            family = self._classifier.token_family(token)
            if family in {"", "latin"}:
                if current_tokens:
                    aliases.append(" ".join(current_tokens))
                    current_tokens = []
                    current_family = ""
                continue
            if current_tokens and family == current_family:
                current_tokens.append(token)
                continue
            if current_tokens:
                aliases.append(" ".join(current_tokens))
            current_tokens = [token]
            current_family = family
        if current_tokens:
            aliases.append(" ".join(current_tokens))
        if not aliases:
            aliases = [cleaned]
        else:
            aliases = self._semantics.unique_keep_order([cleaned, *aliases])
        self._aliases = tuple(aliases)
        return self._aliases

    def _pick_preferred_title(self, aliases: tuple[str, ...]) -> tuple[str, str]:
        normalized_title = self._base_title
        alias_candidates = aliases[1:] if len(aliases) > 1 else aliases
        for candidate in alias_candidates:
            if candidate != normalized_title and self._classifier.is_non_ascii(candidate):
                return candidate, "first-non-latin-other-name"
        for candidate in alias_candidates:
            if candidate != normalized_title:
                return candidate, "first-other-name"
        for candidate in aliases:
            if candidate != normalized_title:
                return candidate, "raw-other-name"
        return normalized_title, "base-title-only"

    def analyze(self) -> TitleAliasResult:
        if self._result is not None:
            return self._result
        aliases = self._extract_aliases()
        preferred_title, preferred_reason = self._pick_preferred_title(aliases)
        self._result = TitleAliasResult(
            raw_other_name=self._raw_other_name,
            aliases=aliases, preferred_title=preferred_title, preferred_reason=preferred_reason,
        )
        return self._result


class PreviewRequestSession:
    def __init__(self, reqer: JestfulReqer):
        self._reqer = reqer

    @property
    def site_context(self) -> _JestfulSiteContext:
        candidate = str(getattr(self._reqer, "domain", None) or type(self._reqer).domain or "").strip()
        parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        host = (parsed.netloc or parsed.path).strip().rstrip("/")
        if not host:
            raise ValueError("jestful domain is required")
        return _JestfulSiteContext(host=host, origin=f"{parsed.scheme or 'https'}://{host}")

    def home_url(self) -> str:
        return f"{self.site_context.origin}/"

    def random_token(self, length: int) -> str:
        return "".join(secrets.choice(self._reqer._random_alphabet) for _ in range(length))

    def listing_url(self, *, keyword: str = "", page: int = 1, update: bool = False) -> str:
        params = {
            "listType": "pagination",
            "sort": self._reqer._update_sort if update else self._reqer._search_sort,
            "sort_type": self._reqer._update_sort_type if update else self._reqer._search_sort_type,
        }
        if not update and page <= 1:
            return f"{self.site_context.origin}/manga-list.html?name={keyword}"
        if page > 1:
            params["page"] = str(page)
        if page > 1 or not update:
            params.update(
                {"artist": "","author": "","group": "","m_status": "",
                 "name": "" if update else keyword,"genre": "","ungenre": "",}
            )
        return f"{self.site_context.origin}/manga-list.html?{urlencode(params)}"

    def controller_url(self, controller: str, **params: str) -> str:
        return f"{self.site_context.origin}/app/manga/controllers/{controller}.php?{urlencode(params)}"

    def tokenized_url(self, suffix: str, *, token_length: int, query_name: str, value: str) -> str:
        return f"{self.site_context.origin}/{self.random_token(token_length)}.{suffix}?{query_name}={value}"

    def headers(self, *, referer: str | None = None, xhr: bool = False) -> dict[str, str]:
        headers = {
            **self._reqer.ua,
            "Accept": "*/*",
        }
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
        if referer is None and xhr:
            referer = self.home_url()
        if referer is not None:
            headers["Referer"] = referer
        return headers


class JestfulParser(_JestfulContract, Previewer):
    _semantics = TextSemantics()

    @classmethod
    def _extract_hover_id(cls, node: Selector) -> str:
        for raw_attr in node.xpath(".//@onmouseenter").getall():
            if matched := SHOW_ID_RE.search(raw_attr or ""):
                return matched.group(1)
        return ""

    @classmethod
    def _strip_title_prefix(cls, value: str, *, title: str | None) -> str:
        normalized_title = cls._semantics.normalize_text(title)
        if normalized_title and value.lower().startswith(normalized_title.lower()):
            return cls._semantics.normalize_text(value[len(normalized_title):].lstrip(" :#-"))
        return value

    @classmethod
    def clean_latest_chapter(cls, value: str | None, *, title: str | None = None) -> str:
        cleaned = cls._semantics.normalize_text(value)
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        for prefix in ("last chapter", "latest chapter"):
            if lowered.startswith(prefix):
                suffix = cls._semantics.normalize_text(cleaned[len(prefix):].lstrip(" :#-"))
                return f"Chapter {suffix}" if suffix and not suffix.lower().startswith("chapter") else suffix
        stripped = cls._strip_title_prefix(cleaned, title=title)
        chapter_match = re.search(r"\bchapter\b\s*[:#-]?\s*(.+)$", stripped, re.I)
        if chapter_match:
            suffix = cls._semantics.normalize_text(chapter_match.group(1).strip(" :#-"))
            return f"Chapter {suffix}" if suffix else "Chapter"
        return stripped

    @classmethod
    def apply_latest_chapter(cls, book: JestfulBookInfo, value: str | None) -> str:
        latest = cls.clean_latest_chapter(value, title=getattr(book, "name", None))
        if latest:
            book.latest_sec = latest
            book.last_chapter_name = latest
        return latest

    @classmethod
    def _new_book(cls, *, idx: int, url: str) -> JestfulBookInfo:
        return JestfulBookInfo(idx=idx, render_keys=["name", "latest_sec"], url=url, preview_url=url)

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
            book.id = cls._semantics.normalize_text(card.xpath("./@data-id").get()) or cls._extract_hover_id(card)
            book.name = cls._semantics.normalize_text(
                card.xpath("../div[contains(@class,'series-title')][1]//h3[contains(@class,'title-thumb')]/text()").get()
            )
            if not book.name:
                raise ValueError(f"jestful search card missing title: idx={idx} href={href}")
            latest_text = cls._semantics.normalize_text(card.xpath(".//a[contains(@class,'btn-danger')]/text()").get())
            cls.apply_latest_chapter(book, latest_text)
            cover = cls._semantics.normalize_text(card.xpath(".//div[contains(@class,'content')]/@data-bg").get())
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain) if cover else None
            books.append(book)
        return books

    @classmethod
    def parse_index_books(cls, html_text: str, *, domain: str) -> list[JestfulBookInfo]:
        sel = Selector(text=html_text)
        cards = sel.css("div#contentstory div.itemupdate")
        books = []
        for card in cards:
            href = cls._semantics.normalize_text(card.xpath("./a[contains(@class,'cover')][1]/@href").get())
            if not href:
                continue
            book_url = cls.normalize_preview_resource(href, domain=domain)
            book = cls._new_book(idx=len(books) + 1, url=book_url)
            book.id = cls._extract_hover_id(card)
            book.name = cls._semantics.normalize_text(
                card.xpath(".//a[contains(@class,'title-h3-link')]//h3[contains(@class,'title-h3')]/text()").get()
            ) or cls._semantics.normalize_text(card.xpath(".//a[contains(@class,'cover')]//img[1]/@alt").get())
            if not book.name:
                continue
            cls.apply_latest_chapter(book, card.xpath(".//a[contains(@class,'chapter')][1]/@title").get())
            cover = cls._semantics.normalize_text(
                card.xpath(".//a[contains(@class,'cover')]//img[1]/@data-src").get()
                or card.xpath(".//a[contains(@class,'cover')]//img[1]/@src").get()
            )
            book.img_preview = cls.normalize_preview_resource(cover, domain=domain) if cover else None
            books.append(book)
        if not books:
            raise ValueError("jestful index page returned no update-lane cards")
        return books

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
                onclick_text = str(item.get("onclick") or "")
                matched = re.search(r"/(hwms-[^'\"/?#]+\.html)", onclick_text)
                if not matched:
                    raise ValueError(f"jestful suggest item onclick missing owner path: onclick={onclick_text!r}")
                book_path = matched.group(1)
                book_url = cls.normalize_preview_resource(book_path, domain=domain)
                book = cls._new_book(idx=len(books) + 1, url=book_url)
                book.name = cls._semantics.normalize_text(str(item.get("primary") or ""))
                if not book.name:
                    raise ValueError(f"jestful suggest item missing primary: {item!r}")
                cls.apply_latest_chapter(book, str(item.get("secondary") or ""))
                cover = cls._semantics.normalize_text(str(item.get("image") or ""))
                book.img_preview = cls.normalize_preview_resource(cover, domain=domain) if cover else None
                books.append(book)
        return books

    @classmethod
    def parse_book_pop_fields(cls, html_text: str, *, request_url: str) -> dict:
        sel = Selector(text=html_text)
        title = cls._semantics.normalize_text(sel.css("div.pop_title::text").get())
        cover_url = cls._semantics.normalize_text(sel.css("div.pop_info img::attr(src)").get())
        if not title or not cover_url:
            raise ValueError(f"jestful book pop payload missing title or cover: url={request_url}")
        fields = cls._semantics.parse_labeled_rows(sel.xpath("//p[strong]"), label_xpath="./strong[1]//text()")
        alias_result = TitleAliasSession(
            base_title=title,
            raw_other_name=str(fields.get("other name") or fields.get("other name (s)") or ""),
        ).analyze()
        return {
            "title": title,
            "cover_url": cover_url,
            "fields": fields,
            "other_name_raw": alias_result.raw_other_name,
            "other_names": list(alias_result.aliases),
            "preferred_title": alias_result.preferred_title,
            "preferred_title_reason": alias_result.preferred_reason,
            "author": fields.get("author"),
            "tags": cls._semantics.split_csv_field(fields.get("genres")),
            "public_date": fields.get("last update"),
        }

    @classmethod
    def apply_pop_fields(cls, book: JestfulBookInfo, pop_fields: dict, *, domain: str) -> JestfulBookInfo:
        preferred_title = cls._semantics.normalize_text(pop_fields.get("preferred_title") or pop_fields.get("title") or book.name)
        if preferred_title:
            book.name = preferred_title
        other_name_raw = cls._semantics.normalize_text(pop_fields.get("other_name_raw"))
        other_names = list(pop_fields.get("other_names") or [])
        if other_name_raw:
            book.other_name_raw = other_name_raw
        if other_names:
            book.other_names = other_names
        if pop_fields.get("preferred_title_reason"):
            book.preferred_title_reason = pop_fields["preferred_title_reason"]
        if pop_fields.get("title"):
            book.pop_title = pop_fields["title"]
        if pop_fields.get("author"):
            book.artist = pop_fields["author"]
        if pop_fields.get("tags"):
            book.tags = list(pop_fields["tags"])
        if pop_fields.get("public_date"):
            book.public_date = pop_fields["public_date"]
        cover_url = cls._semantics.normalize_text(pop_fields.get("cover_url"))
        if cover_url:
            book.img_preview = cls.normalize_preview_resource(cover_url, domain=domain)
        return book

    @classmethod
    def parse_book_owner_state(cls, html_text: str, *, owner_url: str) -> dict:
        data_l_match = re.search(r"""var\s+dataL\s*=\s*["']([^"']+)["']""", html_text)
        if not data_l_match:
            raise ValueError(f"jestful book owner page missing dataL: url={owner_url}")
        loader_slug = cls._semantics.normalize_text(data_l_match.group(1))
        if not loader_slug:
            raise ValueError(f"jestful book owner page returned empty dataL: url={owner_url}")

        sel = Selector(text=html_text)
        latest_href = sel.css("a.btn.btn-danger.btn-md[target='_blank']::attr(href)").get()
        title = cls._semantics.normalize_text(sel.css("ul.manga-info > h3::text").get())
        latest_sec = cls.clean_latest_chapter(sel.css("a.btn.btn-danger.btn-md[target='_blank']::text").get(), title=title)
        manga_id_match = re.search(r"cont\.pop\.php\?action=pop&id=(\d+)", html_text)
        fields = cls._semantics.parse_labeled_rows(sel.css("ul.manga-info li"), label_xpath="./b[1]//text()")
        alias_result = TitleAliasSession(
            base_title=title,
            raw_other_name=str(fields.get("other name (s)") or fields.get("other name") or ""),
        ).analyze()
        cover_url = cls._semantics.normalize_text(sel.css("div.well.info-cover img.thumbnail::attr(src)").get())

        return {
            "loader_slug": loader_slug,
            "latest_href": latest_href,
            "latest_sec": latest_sec,
            "manga_id": manga_id_match.group(1) if manga_id_match else None,
            "has_chapter_panel": bool(sel.css("#list-chapter")),
            "title": title,
            "cover_url": cover_url,
            "fields": fields,
            "other_name_raw": alias_result.raw_other_name,
            "other_names": list(alias_result.aliases),
            "preferred_title": alias_result.preferred_title,
            "preferred_title_reason": alias_result.preferred_reason,
        }

    @classmethod
    def parse_episodes_from_list_html(cls, html_text: str, book: JestfulBookInfo, *, domain: str) -> list[Episode]:
        sel = Selector(text=html_text)
        rows = list(sel.css("a.chapter[href]"))
        if not rows:
            raise ValueError(f"jestful chapter-list payload returned no chapters: book={book.url}")
        episodes = []
        for idx, row in enumerate(reversed(rows), start=1):
            href = cls._semantics.normalize_text(row.xpath("./@href").get())
            if not href:
                raise ValueError(f"jestful chapter-list row missing href: idx={idx} book={book.url}")
            ep_url = cls.normalize_preview_resource(href, domain=domain)
            name = cls._semantics.normalize_text("".join(row.xpath(".//text()").getall())) or cls._semantics.normalize_text(
                row.xpath("./@title").get()
            )
            if not name:
                raise ValueError(f"jestful chapter-list row missing chapter title: idx={idx} href={href}")
            ep = Episode(from_book=book, id=href.strip("/"), idx=idx, url=ep_url, name=name)
            ep.chapter_referer = ep.url
            episodes.append(ep)
        return episodes

    @staticmethod
    def parse_chapter_image_cid(html_text: str, *, chapter_url: str) -> str:
        target = re.search(r"""load_image\(\s*['"]?([^,'"()\s]+)['"]?\s*,\s*['"]list-imga['"]\s*\)""", html_text)
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
            normalized = cls._semantics.normalize_text(raw_url)
            if normalized:
                urls.append(normalized)
        if not urls:
            raise ValueError(f"jestful iog payload returned no img.chapter-img urls: url={request_url}")
        return urls


class JestfulReqer(_JestfulContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)
        self.preview_requests = PreviewRequestSession(self)

    async def _enrich_book_from_pop(self, book: JestfulBookInfo):
        book_id = str(book.id or "").strip()
        if not book_id:
            return book
        owner = self._require_preview_owner()
        session = self.preview_requests
        domain = session.site_context.host
        pop_resp = await self.ensure_preview_client().get(
            session.controller_url("cont.pop", action="pop", id=book_id),
            headers=session.headers(xhr=True), follow_redirects=True, timeout=12,
        )
        pop_resp.raise_for_status()
        pop_fields = await asyncio.to_thread(owner.parser.parse_book_pop_fields, pop_resp.text, request_url=str(pop_resp.url))
        owner.parser.apply_pop_fields(book, pop_fields, domain=domain)
        return book

    async def _enrich_books_from_pop(self, books: list[JestfulBookInfo]):
        if not books:
            return books
        limit = max(1, int(self.pop_concurrency))
        semaphore = asyncio.Semaphore(limit)

        async def _runner(book: JestfulBookInfo):
            if not book.id:
                return book
            async with semaphore:
                return await self._enrich_book_from_pop(book)

        await asyncio.gather(*(_runner(book) for book in books))
        return books

    def test_index(self):
        session = self.preview_requests
        try:
            resp = self.cli.head(session.home_url(), headers={"User-Agent": self.ua["User-Agent"]}, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    async def _fetch_parse(self, url, parse_fn, *, domain, headers=None):
        resp = await self.ensure_preview_client().get(url, headers=headers or self.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(parse_fn, resp.text, domain=domain)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        session = self.preview_requests
        domain = session.site_context.host
        page = max(1, int(page or 1))
        keyword = keyword.strip()
        parse = owner.parser

        mappings = owner_type.merge_search_mappings(self.mappings, self.preview_site_kwargs().get("custom_map"))
        # Mapping extends the search URL space (index shortcut)
        if keyword in mappings and page <= 1:
            url = owner_type.normalize_mapping_url(domain, mappings[keyword])
            books = await self._fetch_parse(url, parse.parse_index_books, domain=domain)
            return await self._enrich_books_from_pop(books)
        # Listing search (mapping page>1 falls through to update listing)
        url = session.listing_url(page=page, update=True) if keyword in mappings else session.listing_url(keyword=keyword, page=page)
        books = await self._fetch_parse(url, parse.parse_search_document, domain=domain)
        if books or page > 1:
            return await self._enrich_books_from_pop(books)
        # Fallback to suggest
        return await self._fetch_parse(
            session.controller_url("search.single", q=keyword),
            parse.parse_search_suggest, domain=domain, headers=session.headers(xhr=True),
        )

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        preview_client = self.ensure_preview_client()
        session = self.preview_requests
        domain = session.site_context.host

        owner_resp = await preview_client.get(book.url, headers=self.ua, follow_redirects=True, timeout=12)
        owner_resp.raise_for_status()
        owner_url = str(owner_resp.url)
        owner_state = await asyncio.to_thread(owner.parser.parse_book_owner_state, owner_resp.text, owner_url=owner_url)
        if owner_state.get("manga_id"):
            book.id = str(owner_state["manga_id"])
        book.loader_slug = owner_state["loader_slug"]
        book.manga_id = owner_state["manga_id"]
        if owner_state.get("latest_sec"):
            owner.parser.apply_latest_chapter(book, owner_state["latest_sec"])
        if owner_state.get("cover_url") and not book.img_preview:
            book.img_preview = owner.parser.normalize_preview_resource(owner_state["cover_url"], domain=domain)
        if owner_state.get("preferred_title"):
            owner.parser.apply_pop_fields(
                book,
                {
                    "title": owner_state.get("title") or book.name,
                    "preferred_title": owner_state["preferred_title"],
                    "preferred_title_reason": owner_state.get("preferred_title_reason"),
                    "other_name_raw": owner_state.get("other_name_raw"),
                    "other_names": owner_state.get("other_names"),
                    "cover_url": owner_state.get("cover_url"),
                },
                domain=domain,
            )
        if book.id:
            await self._enrich_book_from_pop(book)

        chapter_resp = await preview_client.get(
            session.tokenized_url("lstc", token_length=25, query_name="slug", value=owner_state["loader_slug"]),
            headers=session.headers(referer=owner_url, xhr=True), follow_redirects=True, timeout=12,
        )
        chapter_resp.raise_for_status()
        return await asyncio.to_thread(owner.parser.parse_episodes_from_list_html, chapter_resp.text, book, domain=domain)

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        preview_client = self.ensure_preview_client()
        session = self.preview_requests

        chapter_resp = await preview_client.get(episode.url, headers=self.ua, follow_redirects=True, timeout=12)
        chapter_resp.raise_for_status()
        chapter_url = str(chapter_resp.url)
        cid = await asyncio.to_thread(owner.parser.parse_chapter_image_cid, chapter_resp.text, chapter_url=chapter_url)

        iog_resp = await preview_client.get(
            session.tokenized_url("iog", token_length=30, query_name="cid", value=cid),
            headers=session.headers(referer=chapter_url), follow_redirects=True, timeout=12,
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
