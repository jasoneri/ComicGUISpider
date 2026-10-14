from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import httpx

from assets import res
from utils.website.core import Previewer, Req, Utils
from utils.website.info import Episode, MangadexBookInfo

# MangaDex 是 React SPA + JSON API 站点：页面本身不含数据，全部走 api.mangadex.org。
# 契约对照 https://api.mangadex.org/docs/ ，字段以 2026-09-17 实际响应为准。


class MangadexNoPreferredLanguageError(RuntimeError):
    """feed 在偏好语言下一章都没有。按既定口径不回退到全部语言，避免下到非偏好语言章节。"""

    def __init__(self, *, book_name, preferred_languages, feed_url):
        langs = "/".join(preferred_languages)
        super().__init__(
            f"mangadex book {book_name!r} has no chapters in preferred languages "
            f"[{langs}] and fallback to all languages is disabled: url={feed_url}"
        )
        self.book_name = book_name
        self.preferred_languages = [str(code) for code in preferred_languages]
        self.feed_url = feed_url


class _MangadexContract:
    name = "mangadex"
    proxy_policy = "proxy"
    domain = "api.mangadex.org"
    index = "https://mangadex.org/"
    web_domain = "mangadex.org"
    api_base = "https://api.mangadex.org"
    cover_base = "https://uploads.mangadex.org/covers"
    # 搜索/Feed 默认只取可读章节（externalUrl 为空者），排除 MangaPlus/Alpha Manga 外链章
    feed_limit = 100
    search_limit = 20
    mappings = {
        res.SPIDER.Completer.index: f"{api_base}/manga?limit={search_limit}&order[followedCount]=desc&includes[]=cover_art&includes[]=author",
        res.SPIDER.Completer.update: f"{api_base}/manga?limit={search_limit}&order[latestUploadedChapter]=desc&includes[]=cover_art&includes[]=author",
    }
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://mangadex.org",
        "Connection": "close",
    }
    headers = ua
    book_hea = ua
    image_ua = {
        "User-Agent": ua["User-Agent"],
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": ua["Accept-Language"],
        "Referer": index,
    }
    # 界面语言 -> MangaDex translatedLanguage[] 列表。对照 configDialog 的中英选择
    # （res.lang）与 res.Vars.ua_accept_language 基底：zh_CN 的 accept-language 序列是
    # zh > zh-TW > zh-HK > en，映射为简中/繁中/英文；en_US 只有 en。translatedLanguage
    # 只能匹配“翻译语言”，原文章节不在 feed 里，因此不需要把 originalLanguage 加入。
    ui_lang_to_feed_langs = {
        "zh_CN": ("zh", "zh-hk", "en"),
        "en_US": ("en",),
    }

    @classmethod
    def preferred_languages(cls) -> list[str]:
        # 运行时读取 res.lang，使其跟随 configDialog 的界面语言切换
        feed_langs = cls.ui_lang_to_feed_langs.get(res.lang or "")
        if not feed_langs:
            feed_langs = cls.ui_lang_to_feed_langs["en_US"]
        return [str(code) for code in feed_langs]


class MangadexParser(_MangadexContract):
    @staticmethod
    def _require_ok(payload, *, request_url):
        if not isinstance(payload, dict):
            raise TypeError(f"mangadex response must be a JSON object, got {type(payload).__name__}: url={request_url}")
        if payload.get("result") != "ok":
            errors = payload.get("errors") or payload.get("error")
            raise ValueError(f"mangadex api error: url={request_url} errors={errors}")
        return payload

    @staticmethod
    def _require_collection(payload, *, request_url):
        MangadexParser._require_ok(payload, request_url=request_url)
        data = payload.get("data")
        if not isinstance(data, list):
            raise TypeError(f"mangadex collection response missing data list: url={request_url}")
        return data

    @staticmethod
    def _require_entity(payload, *, request_url):
        MangadexParser._require_ok(payload, request_url=request_url)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise TypeError(f"mangadex entity response missing data object: url={request_url}")
        return data

    @staticmethod
    def _localized_title(title_map, alt_titles) -> str:
        # title 是 {lang: text}；优先英文，其次原始语言，最后任意一个
        if isinstance(title_map, dict) and title_map:
            for lang in ("en", "ja", "zh", "zh-hk", "ko"):
                value = title_map.get(lang)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            first_value = next(iter(title_map.values()))
            if isinstance(first_value, str):
                return first_value.strip()
        if isinstance(alt_titles, list):
            for alt in alt_titles:
                if isinstance(alt, dict):
                    first_value = next(iter(alt.values()), None)
                    if isinstance(first_value, str) and first_value.strip():
                        return first_value.strip()
        return ""

    @staticmethod
    def _first_description(descriptions) -> str | None:
        if not isinstance(descriptions, dict):
            return None
        for lang in ("zh", "zh-hk", "en", "ja"):
            value = descriptions.get(lang)
            if isinstance(value, str) and value.strip():
                return value.strip()
        first_value = next(iter(descriptions.values()), None)
        return first_value.strip() if isinstance(first_value, str) else None

    @classmethod
    def _relationship(cls, entity, rel_type) -> dict | None:
        for relationship in entity.get("relationships") or []:
            if isinstance(relationship, dict) and relationship.get("type") == rel_type:
                return relationship
        return None

    @classmethod
    def _cover_url(cls, entity) -> str | None:
        cover = cls._relationship(entity, "cover_art")
        if cover is None:
            return None
        file_name = (cover.get("attributes") or {}).get("fileName")
        if not isinstance(file_name, str) or not file_name.strip():
            return None
        return f"{cls.cover_base}/{entity['id']}/{file_name}"

    @classmethod
    def _author_name(cls, entity) -> str | None:
        author = cls._relationship(entity, "author")
        if author is None:
            return None
        name = (author.get("attributes") or {}).get("name")
        return name.strip() if isinstance(name, str) and name.strip() else None

    @classmethod
    def parse_book_entity(cls, entity, *, idx, render_keys) -> MangadexBookInfo:
        if not isinstance(entity, dict) or entity.get("type") != "manga":
            raise TypeError(f"mangadex search target must be a manga entity, got {type(entity).__name__}")
        attributes = entity.get("attributes") or {}
        book_url = f"https://{cls.web_domain}/title/{entity['id']}"
        book = MangadexBookInfo(
            idx=idx,
            render_keys=render_keys,
            url=book_url,
            preview_url=book_url,
        )
        book.id = entity["id"]
        book.name = cls._localized_title(attributes.get("title"), attributes.get("altTitles"))
        if not book.name:
            raise ValueError(f"mangadex manga entity missing title: id={entity['id']}")
        book.artist = cls._author_name(entity)
        book.img_preview = cls._cover_url(entity)
        book.status = attributes.get("status") or None
        book.public_date = attributes.get("year") and str(attributes["year"]) or None
        book.description = cls._first_description(attributes.get("description"))
        tag_names = []
        for tag in attributes.get("tags") or []:
            tag_attrs = tag.get("attributes") or {}
            tag_title = tag_attrs.get("name") or {}
            tag_name = tag_title.get("en") or next(iter(tag_title.values()), None) if isinstance(tag_title, dict) else None
            if isinstance(tag_name, str) and tag_name.strip():
                tag_names.append(tag_name.strip())
        if tag_names:
            book.tags = tag_names
        return book

    @classmethod
    def parse_search_document(cls, payload, *, request_url) -> list[MangadexBookInfo]:
        entities = cls._require_collection(payload, request_url=request_url)
        render_keys = ["name", "artist"]
        return [
            cls.parse_book_entity(entity, idx=idx, render_keys=render_keys)
            for idx, entity in enumerate(entities, start=1)
        ]

    @classmethod
    def parse_book_state(cls, payload, book, *, request_url) -> None:
        entity = cls._require_entity(payload, request_url=request_url)
        refreshed = cls.parse_book_entity(entity, idx=book.idx or 1, render_keys=book.render_keys or ["name", "artist"])
        for attr in ("name", "artist", "img_preview", "status", "public_date", "description", "tags"):
            value = getattr(refreshed, attr, None)
            if value:
                setattr(book, attr, value)

    @staticmethod
    def _chapter_display_name(attributes) -> str:
        volume = attributes.get("volume") or ""
        chapter = attributes.get("chapter") or ""
        title = attributes.get("title") or ""
        parts = []
        if volume:
            parts.append(f"Vol.{volume}")
        if chapter:
            parts.append(f"Ch.{chapter}")
        chapter_label = " ".join(parts)
        if title:
            return f"{chapter_label} {title}".strip() if chapter_label else title.strip()
        return chapter_label or "Oneshot"

    @staticmethod
    def _scanlation_group(entity) -> str | None:
        for relationship in entity.get("relationships") or []:
            if isinstance(relationship, dict) and relationship.get("type") == "scanlation_group":
                name = (relationship.get("attributes") or {}).get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        return None

    @classmethod
    def parse_episodes(cls, payload, book, *, request_url) -> list[Episode]:
        entities = cls._require_collection(payload, request_url=request_url)
        episodes = []
        for entity in entities:
            attributes = entity.get("attributes") or {}
            # 外链章节没有上传页面，无法在 MangaDex 站内阅读，下载链路必须排除
            if attributes.get("externalUrl"):
                continue
            group_name = cls._scanlation_group(entity)
            episode = Episode(
                from_book=book,
                idx=len(episodes) + 1,
                id=entity["id"],
                url=f"{cls.api_base}/at-home/server/{entity['id']}",
                name=cls._chapter_display_name(attributes),
            )
            if group_name:
                episode.name = f"{episode.name} [{group_name}]"
            episodes.append(episode)
        if not episodes:
            raise ValueError(f"mangadex feed has no readable chapters: url={request_url}")
        return episodes

    @classmethod
    def parse_page_urls(cls, payload, *, request_url) -> list[str]:
        # at-home 响应不套 data 实体信封：baseUrl/chapter 直接在顶层
        cls._require_ok(payload, request_url=request_url)
        base_url = payload.get("baseUrl")
        chapter = payload.get("chapter") or {}
        chapter_hash = chapter.get("hash")
        page_files = chapter.get("data")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError(f"mangadex at-home response missing baseUrl: url={request_url}")
        if not isinstance(chapter_hash, str) or not chapter_hash.strip():
            raise ValueError(f"mangadex at-home response missing chapter.hash: url={request_url}")
        if not isinstance(page_files, list) or not page_files:
            raise ValueError(f"mangadex at-home response missing chapter.data list: url={request_url}")
        normalized = [str(file_name).strip() for file_name in page_files]
        if not all(normalized):
            raise ValueError(f"mangadex at-home response contains empty file names: url={request_url}")
        return [f"{base_url.rstrip('/')}/data/{chapter_hash}/{file_name}" for file_name in normalized]


class MangadexReqer(_MangadexContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def build_search_url(cls, keyword: str, *, page: int = 1, custom_map: dict | None = None) -> str:
        keyword = (keyword or "").strip()
        mappings = Previewer.merge_search_mappings(cls.mappings, custom_map)
        if keyword in mappings:
            base_url = mappings[keyword]
        else:
            base_url = (
                f"{cls.api_base}/manga?limit={cls.search_limit}"
                f"&title={quote(keyword)}&includes[]=cover_art&includes[]=author"
            )
        # MangaDex API 分页是 offset 偏移：page N → offset=(N-1)*limit
        normalized_page = max(1, int(page or 1))
        if normalized_page == 1:
            return base_url
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}offset={(normalized_page - 1) * cls.search_limit}"

    def test_index(self):
        # 探测目标必须是 provider 实际使用的 api.mangadex.org，不是 web 主站：
        # web 主站对 HEAD 返回 405（确定性失败，与代理无关），且它的可达性与
        # API 业务流量无关。/ping 是无参无认证的健康检查端点，最轻量。
        try:
            resp = self.cli.get(f"{self.api_base}/ping", timeout=3.5, headers=self.ua)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        site_kw = self.preview_site_kwargs()
        url = self.build_search_url(
            keyword,
            page=max(1, int(page or 1)),
            custom_map=site_kw.get("custom_map"),
        )
        resp = await self.ensure_preview_client().get(url, headers=self.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(
            owner.parser.parse_search_document, resp.json(), request_url=url,
        )

    async def preview_fetch_episodes(self, book):
        owner = self._require_preview_owner()
        # MangaDex 的 feed 把同一章节号的各语言版本平铺返回（不做跨语言去重）。
        # 必须用 translatedLanguage[] 做服务端过滤，否则用户会看到 ca/ar/pt-br 等
        # 非偏好语言的章节混排（实测 One Piece 无过滤时 500 章里 ca=292/ar=117）。
        # 语言列表跟随项目界面语言（configDialog 中英选择），对照 res.Vars.ua_accept_language
        # 的基底：zh_CN -> zh/zh-hk + en 兜底，en_US -> en。filteredLanguage 只能匹配
        # “翻译语言”，原文章节不在 feed 里，所以不需要把 originalLanguage 加进列表。
        preferred_languages = self.preferred_languages()
        language_params = "".join(f"&translatedLanguage[]={code}" for code in preferred_languages)
        feed_url = (
            f"{self.api_base}/manga/{book.id}/feed"
            f"?limit={self.feed_limit}&order[volume]=asc&order[chapter]=asc"
            f"&includes[]=scanlation_group{language_params}"
        )
        resp = await self.ensure_preview_client().get(feed_url, headers=self.ua, follow_redirects=True, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("data"):
            # 偏好语言一章都没有（如 Solo Leveling: Ragnarok 只有 it/pl/pt-br）。
            # 按既定口径不回退到全部语言，避免下到非偏好语言的章节。
            raise MangadexNoPreferredLanguageError(
                book_name=getattr(book, "name", "") or "",
                preferred_languages=preferred_languages,
                feed_url=feed_url,
            )
        return await asyncio.to_thread(
            owner.parser.parse_episodes, payload, book, request_url=feed_url,
        )

    async def preview_fetch_pages(self, episode) -> list[str]:
        owner = self._require_preview_owner()
        resp = await self.ensure_preview_client().get(
            episode.url, headers=self.ua, follow_redirects=True, timeout=15,
        )
        resp.raise_for_status()
        urls = await asyncio.to_thread(
            owner.parser.parse_page_urls, resp.json(), request_url=episode.url,
        )
        episode.pages = len(urls)
        return urls


class MangadexUtils(_MangadexContract, Utils, Previewer):
    parser = MangadexParser
    reqer_cls = MangadexReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {"headers": dict(cls.ua)}
