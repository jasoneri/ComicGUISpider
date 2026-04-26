from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlencode

import httpx
from retry import retry
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from lxml import html

from utils import conf, get_loop, temp_p
from utils.website.core import Cache, Previewer, Req, Utils, build_proxy_transport
from utils.website.info import Episode, KbBookInfo


class _KaobeiContract:
    name = "manga_copy"
    proxy_policy = "proxy"
    preview_batch_limits = {"episodes": 1, "pages": 1}
    preview_transport_retries = 2
    uuid_regex = re.compile(r"(\d+)$")
    pc_domain = "www.2026copy.com"
    api_domain = "api.2026copy.com"
    cache_file = "kaobei_aeskey.txt"
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Dnts": "3",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }
    ua_mapi = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Origin": f"https://{pc_domain}",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip, compress, br",
        "platform": "1",
        "version": "2026.02.02",
        "webp": "1",
        "region": "0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    book_hea = headers
    _search_mappings = {"更新": "byRefresh", "排名": "byRank"}
    turn_page_info = (r"offset=\d+", None, 30)


class KaobeiParser(_KaobeiContract):
    def __init__(self, reqer: "KaobeiReqer"):
        self.reqer = reqer

    @classmethod
    def parse_search_targets(cls, targets, frame):
        rendering_map = frame.rendering_map()
        render_keys = frame.print_head[1:]
        books = []
        for idx, target in enumerate(targets, start=1):
            book = cls.parse_book_item(target, rendering_map, render_keys, idx)
            book.img_preview = frame.extract_cover(target)
            books.append(book)
        return books

    @classmethod
    def parse_book_item(cls, target, rendering_map, render_keys, idx):
        rendered = {
            attr_name: ",".join(map(lambda value: str(value.value), path.find(target)))
            for attr_name, path in rendering_map.items()
        }
        book_path = rendered.pop("book_path")
        book = KbBookInfo(
            idx=idx,
            render_keys=render_keys,
            url=f"https://{cls.pc_domain}/comicdetail/{book_path}/chapters",
            preview_url=f"https://{cls.pc_domain}/comic/{book_path}",
        )
        for key in render_keys:
            setattr(book, key, rendered.get(key))
        return book

    @classmethod
    def parse_ep_item(cls, chapter_datum, comic_path_word, book, idx):
        return Episode(
            from_book=book,
            id=chapter_datum["id"],
            idx=idx,
            url=f"https://{cls.pc_domain}/comic/{comic_path_word}/chapter/{chapter_datum['id']}",
            name=chapter_datum["name"],
        )

    def parse_episodes(self, json_results, book, *, url, show_dhb=False):
        resp_data = self.decrypt_chapter_data(json_results, url=url)
        build = resp_data.get("build")
        if not isinstance(build, dict):
            raise ValueError(f"kaobei chapters payload missing build block: url={url}")
        comic_path_word = build.get("path_word")
        if not comic_path_word:
            raise ValueError(f"kaobei chapters payload missing path_word: url={url}")
        groups = build.get("groups")
        if not isinstance(groups, dict):
            groups = resp_data.get("groups")
        if not isinstance(groups, dict):
            raise ValueError(f"kaobei chapters payload missing groups: url={url}")
        default_group = groups.get("default")
        if not isinstance(default_group, dict):
            raise ValueError(f"kaobei chapters payload missing default group: url={url}")
        chapters_data = list(default_group.get("chapters") or [])
        if show_dhb:
            for group_name in ("tankobon", "other_group"):
                group = groups.get(group_name)
                if isinstance(group, dict):
                    chapters_data.extend(group.get("chapters") or [])
        if not chapters_data:
            raise ValueError(
                f"kaobei chapters payload returned no chapters: url={url} "
                f"path_word={comic_path_word} group_keys={list(groups)}"
            )
        return [
            self.parse_ep_item(chapter_datum, comic_path_word, book, idx + 1)
            for idx, chapter_datum in enumerate(chapters_data)
        ]

    @staticmethod
    def _decrypt(cipher_hex: str, *, aes_key: str, iv: str) -> dict:
        cipher_bytes = bytes.fromhex(cipher_hex)
        key_bytes = aes_key.encode("utf-8")
        iv_bytes = iv.encode("utf-8")
        cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(cipher_bytes) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return json.loads(decrypted.decode("utf-8"))

    def decrypt_chapter_data(self, ret: str, **meta_info):
        aes_key = self.reqer.get_aes_key()
        if not isinstance(ret, str):
            raise TypeError(f"kaobei encrypted payload must be str: got {type(ret).__name__} {meta_info=}")
        if len(ret) <= 16:
            raise ValueError(f"kaobei encrypted payload is empty or too short: len={len(ret)} {meta_info=}")
        try:
            return self._decrypt(ret[16:], aes_key=aes_key, iv=ret[:16])
        except Exception as exc:
            self.reqer.clear_aes_key()
            raise RuntimeError(f"kaobei decrypt failed, aes_key cache cleared: len={len(ret)} {meta_info=}") from exc

    @staticmethod
    def extract_page_content_key(html_text: str, *, url: str) -> str:
        doc = html.fromstring(html_text)
        scripts = doc.xpath('//script[contains(text(), "var contentKey =")]/text()')
        content_key_script = next(iter(scripts), None)
        if not content_key_script:
            raise ValueError("拷贝更改了contentKey xpath")
        content_key_match = re.search(r"""var contentKey = ["']([^']*)["']""", content_key_script)
        if not content_key_match:
            raise ValueError("拷贝更改了contentKey 格式")
        content_key = content_key_match.group(1)
        if not content_key:
            raise ValueError(f"kaobei chapter page returned empty contentKey: url={url}")
        return content_key

    def parse_page_urls_from_html(self, html_text: str, *, url: str) -> list[dict]:
        content_key = self.extract_page_content_key(html_text, url=url)
        return self.decrypt_chapter_data(content_key, url=url)


class KaobeiReqer(_KaobeiContract, Req):
    parser_cls = KaobeiParser

    def __init__(self, _conf=None, *, owner=None, build_sync_client=True):
        self.conf = _conf or conf
        self.owner = owner
        self.preview_client = None
        self._owned_preview_client = None
        self._aes_key = None
        self._aes_cache_path = temp_p.joinpath(self.cache_file)
        self._aes_cache = Cache(self.cache_file)
        self.parser = self.parser_cls(self)
        if build_sync_client:
            self.cli = self.get_cli(self.conf)

    @classmethod
    def build_search_spec(cls, keyword: str, domain: str = None) -> tuple:
        from utils.website.schema import KbFrameBook

        domain = domain or cls.api_domain
        frame = KbFrameBook(domain)
        url = frame.url + keyword

        if matched := re.search(r".*?(排名|更新)", keyword):
            getattr(frame, cls._search_mappings[matched[1]])()
            url = frame.url
        if "轻小说" in keyword:
            frame.byQingXiaoShuo()
        if "排名" in keyword:
            params = {"type": 1}
            time_search = re.search(r".*?([日周月总])", keyword)
            kind_search = re.search(r".*?(轻小说|男|女)", keyword)
            params |= frame.expand_map[kind_search[1]] if kind_search else frame.expand_map["男"]
            params |= frame.expand_map[time_search[1]] if time_search else frame.expand_map["日"]
            url = f"{frame.url}&{urlencode(params)}"
        return url, frame

    def _read_cached_key(self):
        if self._aes_key:
            return self._aes_key
        cached = self._aes_cache.run(lambda: None, "daily")
        if cached:
            self._aes_key = cached
        return cached

    def _write_cached_key(self, key: str):
        self._aes_cache_path.write_text(key, encoding="utf-8")
        self._aes_cache.flag = "new"
        self._aes_cache.val = key
        self._aes_key = key
        return key

    def clear_aes_key(self):
        self._aes_key = None
        self._aes_cache.flag = "new"
        self._aes_cache.val = None
        self._aes_cache_path.unlink(missing_ok=True)

    def aes_cache_hit(self) -> bool:
        if self._aes_cache.flag is None:
            self._read_cached_key()
        return self._aes_cache.flag != "new"

    @staticmethod
    def extract_aes_key(html_text: str) -> str:
        html_doc = html.fromstring(html_text)
        script_texts = [text.strip().replace(" ", "") for text in html_doc.xpath("//script/text()")]
        real_script = next(filter(lambda text: text.startswith("var"), script_texts), None)
        if not real_script:
            raise ValueError("kaobei aes key script not found")
        matched = re.search(r"""=['"](.*?)['"]""", real_script.split("\n")[0])
        if not matched:
            raise ValueError("kaobei aes key value not found")
        return matched.group(1)

    def _active_preview_client(self) -> httpx.AsyncClient:
        if self.preview_client is not None:
            return self.preview_client
        if self._owned_preview_client is not None:
            return self._owned_preview_client
        raise RuntimeError("kaobei preview client is required for preview requests")

    @staticmethod
    def _parse_preview_json(resp, *, stage: str, request_url: str) -> dict:
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            snippet = " ".join(resp.text.split())
            snippet = snippet[:160] if snippet else "<empty>"
            raise ValueError(f"kaobei {stage} expected JSON: status={resp.status_code} url={request_url} body={snippet}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"kaobei {stage} expected object payload: got {type(payload).__name__} url={request_url}")
        return payload

    async def _preview_get(self, url: str, *, stage: str, headers: dict | None = None, **kwargs):
        async def fetch_once():
            resp = await self._active_preview_client().get(url, headers=headers, **kwargs)
            resp.raise_for_status()
            if str(resp.text or "").strip().casefold() == "error":
                snippet = " ".join((resp.text or "").split())[:160] if resp.text else "<empty>"
                raise ValueError(
                    f"kaobei {stage} expected content instead of error body: "
                    f"status={getattr(resp, 'status_code', '?')} url={url} body={snippet}"
                )
            return resp

        @retry(tries=self.preview_transport_retries + 1, delay=0.4, backoff=1, logger=None)
        def fetch_with_retry():
            return asyncio.run(fetch_once())

        return await asyncio.to_thread(fetch_with_retry)

    async def _fetch_aes_key(self) -> str:
        resp = await self._preview_get(
            f"https://{self.pc_domain}/comic/yiquanchaoren",
            headers=self.headers,
            stage="aes_key",
            follow_redirects=True,
            timeout=12,
        )
        return self._write_cached_key(self.extract_aes_key(resp.text))

    async def ensure_preview_aes_key(self) -> str:
        if cached := self._read_cached_key():
            return cached
        if self.preview_client is not None:
            return await self._fetch_aes_key()
        transport, trust_env = build_proxy_transport(self.proxy_policy, self.conf.proxies)
        async with httpx.AsyncClient(headers=self.headers, transport=transport, trust_env=trust_env) as cli:
            self._owned_preview_client = cli
            try:
                return await self._fetch_aes_key()
            finally:
                self._owned_preview_client = None

    def get_aes_key(self) -> str:
        if cached := self._read_cached_key():
            return cached
        loop = get_loop()
        try:
            return loop.run_until_complete(self.ensure_preview_aes_key())
        finally:
            loop.close()

    async def preview_search(self, keyword: str, *, page: int = 1):
        url, frame = self.build_search_spec(keyword)
        url = Previewer.build_page_url(url, page, self.turn_page_info)
        resp = await self._preview_get(url, headers=self.ua_mapi, stage="preview_search", follow_redirects=True, timeout=12)
        payload = self._parse_preview_json(resp, stage="preview_search", request_url=url)
        targets = payload.get("results", {}).get("list", [])
        return await asyncio.to_thread(self.parser.parse_search_targets, targets, frame)

    async def preview_fetch_episodes(self, book, *, show_dhb=None):
        self._active_preview_client()
        await self.ensure_preview_aes_key()
        path_word = book.url.rstrip("/").split("/")[-2]
        headers = {**self.ua, "Referer": f"https://{self.pc_domain}/comic/{path_word}"}
        resp = await self._preview_get(book.url, headers=headers, stage="preview_fetch_episodes", follow_redirects=True, timeout=12)
        payload = self._parse_preview_json(resp, stage="preview_fetch_episodes", request_url=book.url)
        return await asyncio.to_thread(
            self.parser.parse_episodes,
            payload["results"],
            book,
            url=book.url,
            show_dhb=conf.kbShowDhb if show_dhb is None else show_dhb,
        )

    async def preview_fetch_pages(self, episode) -> list[str]:
        self._active_preview_client()
        await self.ensure_preview_aes_key()
        resp = await self._preview_get(episode.url, headers=self.headers, stage="preview_fetch_pages", follow_redirects=True, timeout=12)
        image_data = await asyncio.to_thread(self.parser.parse_page_urls_from_html, resp.text, url=str(resp.url))
        episode.pages = len(image_data)
        return [item["url"] for item in image_data]


class KaobeiUtils(_KaobeiContract, Utils, Previewer):
    parser = KaobeiParser
    reqer_cls = KaobeiReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf, owner=self)
        self.parser = self.reqer.parser

    @classmethod
    def display_meta(cls, *args, **kw) -> dict:
        return {
            "extra": " →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选，想多选请多开<br>"
            "拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算",
        }

    @classmethod
    def preview_client_config(cls, **context):
        return {
            "headers": cls.ua_mapi,
        }

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"retries": cls.preview_transport_retries}
