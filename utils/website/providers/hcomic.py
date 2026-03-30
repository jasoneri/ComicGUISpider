import asyncio
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from utils.website.core import EroUtils, Previewer, Req
from utils.website.info import HComicBookInfo


class HComicParseError(ValueError):
    """h-comic 解析异常，直接抛出给上层做统一错误展示。"""


class _HComicContract:
    name = "h_comic"
    proxy_policy = "proxy"
    domain = "h-comic.com"
    index = "https://h-comic.com"
    image_server = "https://h-comic.link/api"
    search_url_head = f"https://{domain}/?q="
    mappings = {}
    turn_page_info = (r"page=\d+",)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,en-US;q=0.5,en;q=0.3",
    }
    book_hea = headers
    uuid_regex = re.compile(r"[?&]id=(\d+)")
    book_url_regex = r"^https://h-comic\.com/comics/.+\?id=\d+"
    payload_regex = re.compile(r"data:\s*\[null,\s*(\{.*?\})\s*],\s*form:", re.S)
    object_key_regex = re.compile(r'([{\[,]\s*)([A-Za-z_]\w*)\s*:')  # JS object -> JSON


class HComicParser(_HComicContract):
    @classmethod
    def _format_public_date(cls, unix_ts):
        try:
            ts = int(float(unix_ts))
            if ts > 10_000_000_000:
                ts = ts // 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    @classmethod
    def _jsobj_to_dict(cls, js_obj_text):
        json_ready = cls.object_key_regex.sub(r'\1"\2":', js_obj_text)
        return json.loads(json_ready)

    @classmethod
    def _extract_payload_data(cls, resp_text):
        m = cls.payload_regex.search(resp_text)
        if not m:
            raise ValueError("h-comic payload not found")
        payload_obj = cls._jsobj_to_dict(m.group(1))
        if not isinstance(payload_obj, dict):
            raise ValueError("h-comic payload root is not an object")
        data = payload_obj.get("data")
        if not isinstance(data, dict):
            raise ValueError("h-comic payload missing `data` object")
        return data

    @classmethod
    def get_image_prefix(cls, comic_source):
        source_upper = (comic_source or "").upper()
        if source_upper == "MMCG_SHORT":
            suffix = "mms"
        elif source_upper == "MMCG_LONG":
            suffix = "mml"
        else:
            suffix = "nh"
        return f"{cls.image_server}/{suffix}"

    @classmethod
    def _build_cover_url(cls, comic):
        media_id = comic.get("media_id")
        if not media_id:
            return None
        return f"{cls.get_image_prefix(comic.get('comic_source'))}/{media_id}"

    @classmethod
    def _build_book_urls(cls, comic):
        title_info = comic.get("title") or {}
        comic_id = comic.get("id")
        slug_source = title_info.get("japanese") or title_info.get("english") or str(comic_id)
        slug = quote(slug_source, safe="")
        preview_url = f"{cls.index}/comics/{slug}?id={comic_id}"
        url = f"{cls.index}/comics/{slug}/1?id={comic_id}"
        return preview_url, url

    @classmethod
    def parse_search_item(cls, target):
        title_info = target.get("title") or {}
        tags = target.get("tags") or []
        artist = next((t.get("name") for t in tags if t.get("type") == "artist"), None)
        category = next((t.get("name_zh") or t.get("name") for t in tags if t.get("type") == "category"), None)
        tag_names = [t.get("name_zh") or t.get("name") for t in tags if t.get("type") == "tag"]
        preview_url, url = cls._build_book_urls(target)
        pages = target.get("num_pages") or len((target.get("images") or {}).get("pages") or [])
        book = HComicBookInfo(
            name=title_info.get("display") or title_info.get("japanese") or title_info.get("english") or "未知标题",
            preview_url=preview_url,
            url=url,
            pages=pages,
            artist=artist,
            tags=[tag for tag in tag_names if tag],
            btype=category,
            public_date=cls._format_public_date(target.get("upload_date")),
            img_preview=cls._build_cover_url(target),
            id=str(target.get("id") or ""),
            media_id=str(target.get("media_id") or ""),
            comic_source=target.get("comic_source"),
        ).get_id(url)
        return book

    @classmethod
    def parse_search(cls, resp_text):
        try:
            data = cls._extract_payload_data(resp_text)
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            raise HComicParseError(f"h-comic 搜索页解析失败: {exc}") from exc
        targets = data.get("comics")
        if not isinstance(targets, list):
            raise HComicParseError("h-comic 搜索页解析失败: `comics` 字段不是列表")
        books = []
        for idx, target in enumerate(targets, start=1):
            if not isinstance(target, dict):
                raise HComicParseError(f"h-comic 搜索页解析失败: 第 {idx} 项不是对象")
            try:
                books.append(cls.parse_search_item(target))
            except (KeyError, TypeError, ValueError) as exc:
                raise HComicParseError(f"h-comic 搜索条目解析失败(第 {idx} 项): {exc}") from exc
        return books

    @classmethod
    def parse_book(cls, resp_text):
        data = cls._extract_payload_data(resp_text)
        comic = data.get("comic")
        if not comic:
            raise ValueError("h-comic comic payload missing")
        return cls.parse_search_item(comic)

    @classmethod
    def parse_preview_books(cls, text):
        data = cls._extract_payload_data(text)
        targets = data.get("comics")
        if not isinstance(targets, list):
            return []
        books = []
        for idx, target in enumerate(targets, start=1):
            if not isinstance(target, dict):
                continue
            try:
                book = cls.parse_search_item(target)
            except (KeyError, TypeError, ValueError):
                continue
            book.idx = idx
            books.append(book)
        return books


class HComicReqer(_HComicContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    def test_index(self):
        try:
            resp = self.cli.head(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError:
            try:
                resp = self.cli.get(self.index, follow_redirects=True, timeout=3.5)
                resp.raise_for_status()
            except httpx.HTTPError:
                return False
        return True

    def build_search_url(self, key):
        return f"{self.index}/?q={key}"


class HComicUtils(_HComicContract, EroUtils, Previewer):
    parser = HComicParser
    reqer_cls = HComicReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {
            "headers": cls.headers,
        }

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"verify": False}

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        **kw,
    ):
        page = max(1, int(kw.pop("page", 1) or 1))
        domain = kw.pop("domain", None) or cls.domain
        spec = cls.build_basic_search_request(
            keyword,
            page=page,
            domain=domain,
            search_url_head=f"https://{domain}/?q=",
            turn_page_info=cls.turn_page_info,
            mappings=cls.mappings,
            custom_map=kw.pop("custom_map", None),
            headers=cls.headers,
        )
        resp = await cls.perform_preview_request(client, spec)
        return await asyncio.to_thread(cls.parser.parse_preview_books, resp.text)
