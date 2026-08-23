import asyncio
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

from assets import res
from utils import ori_path
from utils.website.core import Cookies, EroUtils, Previewer, Req
from utils.website.info import NhentaiBookInfo


class NhentaiParseError(ValueError):
    pass


class NhentaiTagCatalog:
    _tag_types = ("language", "category", "artist")

    def __init__(self):
        self.reset()

    def reset(self):
        self.loaded = False
        self.db_path = None
        self.by_type = {tag_type: {} for tag_type in self._tag_types}
        self.valid_ids_by_type = {tag_type: set() for tag_type in self._tag_types}

    def load(self, db_path: str | Path | None = None, *, default_db_path: str | Path, excluded_language_names: set[str]) -> dict[str, int]:
        resolved_db_path = Path(db_path) if db_path is not None else Path(default_db_path)
        if not resolved_db_path.exists():
            raise NhentaiParseError(f"nhentai tag db not found: {resolved_db_path}")
        with closing(sqlite3.connect(resolved_db_path)) as conn:
            rows = conn.execute("SELECT id, name, type FROM tags WHERE type IN ('language', 'category', 'artist')").fetchall()
        catalog = {tag_type: {} for tag_type in self._tag_types}
        for tag_id, name, tag_type in rows:
            if tag_type in catalog:
                catalog[tag_type][int(tag_id)] = str(name)
        valid_ids_by_type = {
            tag_type: {
                tag_id for tag_id, tag_name in mapping.items()
                if tag_type != "language" or tag_name not in excluded_language_names
            }
            for tag_type, mapping in catalog.items()
        }
        self.by_type = catalog
        self.valid_ids_by_type = valid_ids_by_type
        self.db_path = resolved_db_path
        self.loaded = True
        return {tag_type: len(mapping) for tag_type, mapping in catalog.items()}

    def preload(self, db_path: str | Path | None = None, *, default_db_path: str | Path, excluded_language_names: set[str]) -> dict[str, int]:
        return self.load(db_path=db_path, default_db_path=default_db_path, excluded_language_names=excluded_language_names)


NHENTAI_TAG_CATALOG = NhentaiTagCatalog()


class _NhentaiContract:
    _language_excluded_names = {"translated"}
    name = "nhentai"
    proxy_policy = "proxy"
    domain = "nhentai.net"
    browser_referer_mode = "provider_index"
    browser_cookie_set_enabled = True
    index = "https://nhentai.net/"
    api_index = "https://nhentai.net/api/v2"
    image_host = "https://i.nhentai.net"
    thumbnail_host = "https://t.nhentai.net"
    search_url_head = f"{api_index}/search?query="
    turn_page_info = (r"page=\d+",)
    mappings = {
        res.SPIDER.Completer.update: f"{api_index}/galleries?page=1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
    }
    image_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": headers["Accept-Language"],
    }
    book_hea = headers
    cookies_field = set()
    uuid_regex = re.compile(r"(?:/g/|/api/v2/galleries/)(\d+)")
    book_url_regex = r"^https://nhentai\.net/(?:g/\d+/?|api/v2/galleries/\d+(?:\?.*)?)"
    tag_db_path = ori_path.joinpath("__temp/nhentai.db")
    gallery_url_template = f"{index}g/%s/"
    gallery_api_url_template = f"{api_index}/galleries/%s?include=comments%%2Crelated"
    # Access probe must hit API v2 JSON, not HTML index: homepage is CF-challenged for bare httpx
    # while /api/v2/* stays open (live matrix + Tsuk1ko nhentai-helper / CGS search path).
    # Prefer list page used by completer mapping over fixed gallery id (177013 is 404 on v2).
    access_probe_url = f"{api_index}/galleries?page=1"

    @classmethod
    def build_search_url(cls, keyword: str, *, page: int = 1, sort: str = "date") -> str:
        query = urlencode({"query": keyword, "sort": sort, "page": max(1, int(page or 1))}, quote_via=quote)
        return f"{cls.api_index}/search?{query}"

    @classmethod
    def with_referer(cls, referer: str | None = None) -> dict:
        headers = dict(cls.headers)
        if referer:
            headers["Referer"] = referer
        return headers


class NhentaiParser(_NhentaiContract):
    catalog: NhentaiTagCatalog = NHENTAI_TAG_CATALOG

    @classmethod
    def _json_payload(cls, resp_text):
        try:
            payload = json.loads(resp_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise NhentaiParseError(f"nhentai JSON 解析失败: {exc}") from exc
        if not isinstance(payload, dict):
            raise NhentaiParseError("nhentai JSON 根节点不是对象")
        return payload

    @staticmethod
    def _required(target: dict, key: str):
        value = target.get(key)
        if value is None or value == "":
            raise NhentaiParseError(f"nhentai payload missing `{key}`")
        return value

    @classmethod
    def _asset_url(cls, asset_path: str, *, host: str) -> str:
        path = str(asset_path or "").strip()
        if not path:
            raise NhentaiParseError("nhentai asset path is empty")
        if path.startswith("http://") or path.startswith("https://"):
            return path
        path = path.lstrip("/")
        if not path.startswith("galleries/"):
            raise NhentaiParseError(f"nhentai asset path must start with galleries/: {asset_path!r}")
        return f"{host.rstrip('/')}/{path}"

    @classmethod
    def build_image_url(cls, asset_path: str) -> str:
        return cls._asset_url(asset_path, host=cls.image_host)

    @classmethod
    def build_thumbnail_url(cls, asset_path: str | None) -> str | None:
        return cls._asset_url(asset_path, host=cls.thumbnail_host) if asset_path else None

    @staticmethod
    def _select_title(*, english_title=None, japanese_title=None, pretty_title=None) -> str:
        return japanese_title or pretty_title or english_title or "未知标题"

    @classmethod
    def _tag_name_from_ids(cls, tag_ids: list[int], tag_type: str, *, excluded_names: set[str] | None = None) -> str | None:
        if not tag_ids:
            return None
        mapping = cls.catalog.by_type.get(tag_type, {})
        valid_ids = cls.catalog.valid_ids_by_type.get(tag_type, set())
        excluded = excluded_names or set()
        for tag_id in tag_ids:
            resolved_tag_id = int(tag_id)
            if resolved_tag_id not in valid_ids:
                continue
            name = mapping[resolved_tag_id]
            if name not in excluded:
                return name
        return None

    @classmethod
    def parse_search_item(cls, target: dict):
        if not isinstance(target, dict):
            raise NhentaiParseError("nhentai 搜索条目不是对象")
        gallery_id = str(cls._required(target, "id"))
        media_id = str(cls._required(target, "media_id"))
        tag_ids = target.get("tag_ids") or []
        if not isinstance(tag_ids, list):
            raise NhentaiParseError("nhentai search item tag_ids is not list")
        english_title = target.get("english_title")
        japanese_title = target.get("japanese_title")
        thumbnail = target.get("thumbnail")
        return NhentaiBookInfo(
            id=gallery_id, media_id=media_id, name=cls._select_title(english_title=english_title, japanese_title=japanese_title),
            english_title=english_title, japanese_title=japanese_title, preview_url=cls.gallery_url_template % gallery_id,
            url=cls.gallery_api_url_template % gallery_id, pages=int(cls._required(target, "num_pages")),
            img_preview=cls.build_thumbnail_url(thumbnail), lang=cls._tag_name_from_ids(tag_ids, "language"),
            btype=cls._tag_name_from_ids(tag_ids, "category"),
        )

    @classmethod
    def parse_search(cls, resp_text):
        payload = cls._json_payload(resp_text)
        targets = payload.get("result")
        if not isinstance(targets, list):
            raise NhentaiParseError("nhentai 搜索 API 缺少 result 列表")
        return [cls.parse_search_item(target) for target in targets]

    @classmethod
    def _parse_page_assets(cls, pages: list[dict], *, media_id: str) -> list[dict]:
        if not isinstance(pages, list):
            raise NhentaiParseError("nhentai gallery detail pages 不是列表")
        pics = []
        for idx, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                raise NhentaiParseError(f"nhentai gallery detail 第 {idx} 页不是对象")
            path = str(cls._required(page, "path"))
            if f"galleries/{media_id}/" not in path:
                raise NhentaiParseError(f"nhentai page asset 与 media_id 不匹配: media_id={media_id} path={path}")
            pics.append({"number": int(page.get("number") or idx), "path": path, "thumbnail": page.get("thumbnail")})
        return pics

    @classmethod
    def parse_book(cls, resp_text):
        payload = cls._json_payload(resp_text)
        gallery_id = str(cls._required(payload, "id"))
        media_id = str(cls._required(payload, "media_id"))
        title = payload.get("title") or {}
        if not isinstance(title, dict):
            raise NhentaiParseError("nhentai gallery detail title 不是对象")
        tags = payload.get("tags") or []
        if not isinstance(tags, list):
            raise NhentaiParseError("nhentai gallery detail tags 不是列表")
        pics = cls._parse_page_assets(payload.get("pages"), media_id=media_id)
        thumbnail_path = (payload.get("thumbnail") or {}).get("path")
        cover_path = (payload.get("cover") or {}).get("path")
        english_title = title.get("english")
        japanese_title = title.get("japanese")
        pretty_title = title.get("pretty")
        tag_ids_by_type = {"language": [], "category": [], "artist": []}
        for tag in tags:
            tag_type = tag.get("type")
            tag_id = tag.get("id")
            if tag_type in tag_ids_by_type and tag_id:
                tag_ids_by_type[tag_type].append(tag_id)
        return NhentaiBookInfo(
            id=gallery_id, media_id=media_id,
            name=cls._select_title(english_title=english_title, japanese_title=japanese_title, pretty_title=pretty_title),
            english_title=english_title, japanese_title=japanese_title, pretty_title=pretty_title,
            preview_url=cls.gallery_url_template % gallery_id, url=cls.gallery_api_url_template % gallery_id,
            pages=int(cls._required(payload, "num_pages")), img_preview=cls.build_thumbnail_url(thumbnail_path or cover_path),
            lang=cls._tag_name_from_ids(tag_ids_by_type["language"], "language"),
            artist=cls._tag_name_from_ids(tag_ids_by_type["artist"], "artist"),
            btype=cls._tag_name_from_ids(tag_ids_by_type["category"], "category"),
            tags=[tag.get("name") for tag in tags if tag.get("type") != "language" and tag.get("name")], pics=pics,
        )

    @classmethod
    def apply_detail(cls, book: NhentaiBookInfo, detail: NhentaiBookInfo):
        for attr in (
            "id", "media_id", "name", "english_title", "japanese_title", "pretty_title", "url", "preview_url", "pages",
            "img_preview", "lang", "artist", "btype", "tags", "pics",
        ):
            setattr(book, attr, getattr(detail, attr, None))
        return book

    @classmethod
    def build_page_image_map(cls, book: NhentaiBookInfo) -> dict[int, str]:
        pics = getattr(book, "pics", None)
        if not isinstance(pics, list) or not pics:
            raise NhentaiParseError("nhentai gallery detail 缺少 pics，无法产出图片 URL")
        image_map = {}
        for idx, page in enumerate(pics, start=1):
            if not isinstance(page, dict):
                raise NhentaiParseError(f"nhentai page asset 第 {idx} 项不是对象")
            image_map[int(cls._required(page, "number"))] = cls.build_image_url(cls._required(page, "path"))
        return image_map

    @classmethod
    def build_page_image_urls(cls, book: NhentaiBookInfo) -> list[str]:
        return [url for _, url in sorted(cls.build_page_image_map(book).items())]

    @classmethod
    def parse_preview_books(cls, resp_text):
        books = cls.parse_search(resp_text)
        for idx, book in enumerate(books, start=1):
            book.idx = idx
        return books


class NhentaiReqer(_NhentaiContract, Cookies, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        cli = super().get_cli(_conf, is_async=is_async, **kwargs)
        cli.headers = {**cls.book_hea, "Cookie": cls.to_str_(_conf.cookies.get(cls.name))}
        return cli

    def test_index(self):
        """Probe crawler-reachable API v2, not browser homepage HTML.

        Competitor paths (Zekfad/Enma/archivist legacy ``/api/gallery/*``) return 403 under
        current CF; CGS + Tsuk1ko use ``/api/v2/galleries*``. Homepage stays 403 for httpx.
        """
        try:
            resp = self.cli.get(self.access_probe_url, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        result = payload.get("result")
        return isinstance(result, list)

    def _headers(self, *, referer: str | None = None) -> dict:
        return self.with_referer(referer)

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        site_kw = self.preview_site_kwargs()
        mappings = owner_type.merge_search_mappings(self.mappings, site_kw.get("custom_map"))
        if keyword in mappings:
            url = owner_type.build_page_url(mappings[keyword], page, self.turn_page_info)
            referer = self.index
        else:
            url = owner_type.build_search_url(keyword, page=page)
            referer = f"{self.index}?page={max(1, int(page or 1))}"
        client = self.ensure_preview_client()
        headers = self._headers(referer=referer)
        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(owner.parser.parse_preview_books, resp.text)

    async def preview_fetch_pages(self, item):
        if not getattr(item, "url", None):
            raise ValueError("nhentai book url is required for preview_fetch_pages")
        client = self.ensure_preview_client()
        headers = self._headers(referer=item.preview_url)
        resp = await client.get(item.url, headers=headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        detail = self.owner.parser.parse_book(resp.text)
        self.owner.parser.apply_detail(item, detail)
        return self.owner.parser.build_page_image_urls(item)


class NhentaiUtils(_NhentaiContract, EroUtils, Cookies, Previewer):
    parser = NhentaiParser
    reqer_cls = NhentaiReqer
    browser_referer_mode = "provider_index"
    catalog = NHENTAI_TAG_CATALOG

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser
        self.parser.catalog = self.catalog

    @classmethod
    def reset_tag_catalog(cls):
        cls.catalog.reset()

    @classmethod
    def load_tag_catalog(cls, db_path: str | Path | None = None) -> dict[str, int]:
        return cls.catalog.load(db_path=db_path, default_db_path=cls.tag_db_path, excluded_language_names=cls._language_excluded_names)

    @classmethod
    def preload_tag_catalog(cls, db_path: str | Path | None = None) -> dict[str, int]:
        return cls.catalog.preload(db_path=db_path, default_db_path=cls.tag_db_path, excluded_language_names=cls._language_excluded_names)

    @classmethod
    def preview_headers(cls, domain: str, cookies: dict | None = None) -> dict[str, str]:
        return cls.build_site_headers(
            domain,
            cls.headers,
            referer_url=cls.index,
            cookies=cookies,
            cookie_serializer=cls.to_str_,
        )

    @classmethod
    def preview_client_config(cls, **context):
        domain = context.get("domain") or cls.domain
        return {"headers": cls.preview_headers(domain, context.get("cookies"))}
