import asyncio
import json
import re
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from lxml import html

from utils import conf, get_loop, temp_p
from utils.processed_class import Url
from utils.website.core import Cache, Previewer, Req, Utils, build_proxy_transport
from utils.website.info import Episode, KbBookInfo


class _KaobeiContract:
    name = "manga_copy"
    proxy_policy = "proxy"
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


def _kaobei_error_body(text: str) -> bool:
    return str(text or "").strip().casefold() == "error"


async def _kaobei_get_with_retry(
    client,
    url: str,
    *,
    stage: str,
    headers: dict | None = None,
    retries: int = 2,
    retry_delay: float = 0.4,
    **kwargs,
):
    last_response = None
    for attempt in range(retries + 1):
        resp = await client.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        if not _kaobei_error_body(resp.text):
            return resp
        last_response = resp
        if attempt < retries:
            await asyncio.sleep(retry_delay * (attempt + 1))
    snippet = " ".join((last_response.text or "").split())[:160] if last_response else "<empty>"
    raise ValueError(
        f"kaobei {stage} expected content instead of error body: "
        f"status={getattr(last_response, 'status_code', '?')} url={url} body={snippet}"
    )


class KaobeiParser(_KaobeiContract):
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

    @classmethod
    def parse_episodes(cls, json_results, book, *, url, aes_key, show_dhb=False):
        resp_data = cls.decrypt_chapter_data(json_results, aes_key=aes_key, url=url)
        comic_path_word = resp_data["build"]["path_word"]
        chapters_data = list(resp_data["groups"]["default"]["chapters"])
        if show_dhb:
            for group_name in ("tankobon", "other_group"):
                if resp_data["groups"].get(group_name):
                    chapters_data.extend(resp_data["groups"][group_name]["chapters"])
        return [
            cls.parse_ep_item(chapter_datum, comic_path_word, book, idx + 1)
            for idx, chapter_datum in enumerate(chapters_data)
        ]

    @staticmethod
    def _decrypt(cipher_hex: str, *, aes_key: str, iv: str) -> dict:
        cipher_bytes = bytes.fromhex(cipher_hex)
        key_bytes = aes_key.encode("utf-8")
        iv_bytes = iv.encode("utf-8")
        cipher = Cipher(
            algorithms.AES(key_bytes),
            modes.CBC(iv_bytes),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(cipher_bytes) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
        return json.loads(decrypted.decode("utf-8"))

    @classmethod
    def decrypt_chapter_data(cls, ret: str, *, aes_key: str, **meta_info):
        if not aes_key:
            raise ValueError("kaobei aes_key is required for decrypt_chapter_data")
        try:
            if len(ret) < 1000:
                raise ValueError(f"加密信息过短疑似风控变化\n{ret=}\n{meta_info=}")
            return cls._decrypt(ret[16:], aes_key=aes_key, iv=ret[:16])
        except Exception as exc:
            KaobeiReqer.clear_aes_key()
            raise RuntimeError(f"kaobei aes_key 失效，已删除缓存: {meta_info=}") from exc

    @classmethod
    def parse_page_urls_from_html(cls, html_text: str, *, url: str, aes_key: str) -> list[dict]:
        if not aes_key:
            raise ValueError("kaobei aes_key is required for parse_page_urls_from_html")
        doc = html.fromstring(html_text)
        scripts = doc.xpath('//script[contains(text(), "var contentKey =")]/text()')
        content_key_script = next(iter(scripts), None)
        if not content_key_script:
            raise ValueError("拷贝更改了contentKey xpath")
        content_key_match = re.search(r"""var contentKey = ["']([^']*)["']""", content_key_script)
        if not content_key_match:
            raise ValueError("拷贝更改了contentKey 格式")
        content_key = content_key_match.group(1)
        return cls.decrypt_chapter_data(content_key, aes_key=aes_key, url=url)


class KaobeiReqer(_KaobeiContract, Req):
    AES_KEY = None

    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

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

    @classmethod
    def _cache(cls):
        cls.cachef = getattr(cls, "cachef", Cache(cls.cache_file))
        return cls.cachef

    @classmethod
    def _cache_path(cls):
        return temp_p.joinpath(cls.cache_file)

    @classmethod
    def _read_cached_key(cls):
        if cls.AES_KEY:
            return cls.AES_KEY
        cached = cls._cache().run(lambda: None, "daily")
        if cached:
            cls.AES_KEY = cached
        return cached

    @classmethod
    def _write_cached_key(cls, key: str):
        cls._cache_path().write_text(key, encoding="utf-8")
        cachef = cls._cache()
        cachef.flag = "new"
        cachef.val = key
        cls.AES_KEY = key
        return key

    @classmethod
    def clear_aes_key(cls):
        cls.AES_KEY = None
        cachef = cls._cache()
        cachef.flag = "new"
        cachef.val = None
        cls._cache_path().unlink(missing_ok=True)

    @classmethod
    def extract_aes_key(cls, html_text: str) -> str:
        html_doc = html.fromstring(html_text)
        script_texts = [text.strip().replace(" ", "") for text in html_doc.xpath("//script/text()")]
        real_script = next(filter(lambda text: text.startswith("var"), script_texts), None)
        if not real_script:
            raise ValueError("kaobei aes key script not found")
        matched = re.search(r"""=['"](.*?)['"]""", real_script.split("\n")[0])
        if not matched:
            raise ValueError("kaobei aes key value not found")
        return matched.group(1)

    @classmethod
    async def _fetch_aes_key(cls, client) -> str:
        resp = await _kaobei_get_with_retry(
            client,
            f"https://{cls.pc_domain}/comic/yiquanchaoren",
            headers=cls.headers,
            stage="aes_key",
            timeout=12,
        )
        return cls._write_cached_key(cls.extract_aes_key(resp.text))

    @classmethod
    async def ensure_aes_key(cls, client=None) -> str:
        if cached := cls._read_cached_key():
            return cached
        if client is not None:
            return await cls._fetch_aes_key(client)
        transport, trust_env = build_proxy_transport(cls.proxy_policy, conf.proxies)
        async with httpx.AsyncClient(
            headers=cls.headers,
            transport=transport,
            trust_env=trust_env,
        ) as cli:
            return await cls._fetch_aes_key(cli)

    @classmethod
    def get_aes_key(cls) -> str:
        if cached := cls._read_cached_key():
            return cached

        try:
            loop = get_loop()
            return loop.run_until_complete(cls.ensure_aes_key())
        except Exception as exc:
            raise ValueError("aes_key 获取失败") from exc
        finally:
            if 'loop' in locals():
                loop.close()


class KaobeiUtils(_KaobeiContract, Utils, Previewer):
    parser = KaobeiParser
    reqer_cls = KaobeiReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

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
        return {"retries": 2}

    @classmethod
    def _preview_json(cls, resp, *, stage, request_url):
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            snippet = " ".join(resp.text.split())
            snippet = snippet[:160] if snippet else "<empty>"
            raise ValueError(
                f"kaobei {stage} expected JSON: status={resp.status_code} url={request_url} body={snippet}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"kaobei {stage} expected object payload: got {type(payload).__name__} url={request_url}"
            )
        return payload

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        **kw,
    ):
        cls.pop_site_kwargs(kw)
        url, frame = cls.reqer_cls.build_search_spec(keyword)
        page = max(1, int(kw.pop("page", 1) or 1))
        if page > 1:
            paged_url = Url(url).set_next(*cls.turn_page_info)
            for _ in range(page - 1):
                paged_url = paged_url.next
            url = str(paged_url)
        resp = await _kaobei_get_with_retry(
            client,
            url,
            headers=cls.ua_mapi,
            stage="preview_search",
            follow_redirects=True,
            timeout=12,
            **kw,
        )
        payload = cls._preview_json(resp, stage="preview_search", request_url=url)
        targets = payload.get("results", {}).get("list", [])
        return await asyncio.to_thread(cls.parser.parse_search_targets, targets, frame)

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        aes_key = await cls.reqer_cls.ensure_aes_key(client)
        path_word = book.url.rstrip("/").split("/")[-2]
        headers = {**cls.ua, "Referer": f"https://{cls.pc_domain}/comic/{path_word}"}
        resp = await _kaobei_get_with_retry(
            client,
            book.url,
            headers=headers,
            stage="preview_fetch_episodes",
            follow_redirects=True,
            timeout=12,
        )
        payload = cls._preview_json(resp, stage="preview_fetch_episodes", request_url=book.url)
        return await asyncio.to_thread(
            cls.parser.parse_episodes,
            payload["results"],
            book,
            url=book.url,
            aes_key=aes_key,
            show_dhb=kw.get("show_dhb", conf.kbShowDhb),
        )

    @classmethod
    async def preview_fetch_pages(cls, episode, client, **kw) -> list[str]:
        aes_key = await cls.reqer_cls.ensure_aes_key(client)
        resp = await _kaobei_get_with_retry(
            client,
            episode.url,
            headers=cls.headers,
            stage="preview_fetch_pages",
            follow_redirects=True,
            timeout=12,
        )
        image_data = await asyncio.to_thread(
            cls.parser.parse_page_urls_from_html,
            resp.text,
            url=str(resp.url),
            aes_key=aes_key,
        )
        episode.pages = len(image_data)
        return [item["url"] for item in image_data]
