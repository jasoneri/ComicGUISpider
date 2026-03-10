import re
import json
import asyncio
from urllib.parse import urlencode

import httpx
from lxml import html

from assets import res
from utils import conf, get_loop
from utils.website.core import Utils, MangaPreview, Cache
from utils.website.info import KbBookInfo, Episode
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend


class KaobeiUtils(Utils, MangaPreview):
    name = "manga_copy"
    uuid_regex = re.compile(r"(\d+)$")
    pc_domain = "www.2026copy.com"
    api_domain = "api.2026copy.com"
    AES_KEY = None
    ua = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'Dnts': '3',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    ua_mapi = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'Accept': 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Origin': f'https://{pc_domain}',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, compress, br',
        'platform': '1',
        'version': '2026.02.02',
        'webp': '1',
        'region': '0'
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }
    _search_mappings = {'更新': "byRefresh", '排名': "byRank"}
    turn_page_info = (r"offset=\d+", None, 30)

    @staticmethod
    def build_search_spec(keyword: str, domain: str = None) -> tuple:
        from utils.website.req_schema import KbFrameBook
        domain = domain or KaobeiUtils.api_domain
        frame = KbFrameBook(domain)
        url = frame.url + keyword

        if what:= re.search(r".*?(排名|更新)", keyword):
            getattr(frame, KaobeiUtils._search_mappings[what[1]])()
            url = frame.url
        if "轻小说" in keyword:
            frame.byQingXiaoShuo()
        if "排名" in keyword:
            param = {'type': 1}
            time_search = re.search(r".*?([日周月总])", keyword)
            kind_search = re.search(r".*?(轻小说|男|女)", keyword)
            param |= (frame.expand_map[kind_search[1]] if kind_search else frame.expand_map["男"])
            param |= (frame.expand_map[time_search[1]] if time_search else frame.expand_map["日"])
            url = f"{frame.url}&{urlencode(param)}"
        return url, frame

    @classmethod
    def _parse_search_targets(cls, targets, frame):
        rendering_map = frame.rendering_map()
        render_keys = frame.print_head[1:]
        books = []
        for idx, target in enumerate(targets, start=1):
            book = cls.parse_book_item(target, rendering_map, render_keys, idx)
            book.img_preview = frame.extract_cover(target)
            books.append(book)
        return books

    @classmethod
    def display_meta(cls, *args, **kw) -> dict:
        return {'extra': " →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选，想多选请多开<br>"
                     "拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算",}

    @classmethod
    async def preview_search(cls, keyword, client, **kw):
        url, frame = cls.build_search_spec(keyword)
        page = int(kw.pop("page", 1) or 1)
        if page < 1:
            page = 1
        if page > 1:
            from utils.processed_class import Url
            paged_url = Url(url).set_next(*cls.turn_page_info)
            for _ in range(page - 1):
                paged_url = paged_url.next
            url = str(paged_url)
        resp = await client.get(url, headers=cls.ua_mapi, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()
        targets = resp.json().get("results", {}).get("list", [])
        return await asyncio.to_thread(cls._parse_search_targets, targets, frame)

    @classmethod
    async def _ensure_aes_key(cls):
        """Async version for preview - uses shared client from worker"""
        async def _fetch_key(client):
            resp = await client.get(f"https://{cls.pc_domain}/comic/yiquanchaoren", timeout=12)
            html_doc = html.fromstring(resp.text)
            dio = list(map(lambda x: x.strip().replace(" ", ""), html_doc.xpath('//script/text()')))
            real_dio = next(filter(lambda x: x.startswith("var"), dio))
            key = re.findall(r"""=['"](.*?)['"]""", real_dio.split("\n")[0])[0]
            cls.AES_KEY = key
            return key

        if cls.AES_KEY:
            return cls.AES_KEY

        def _load_cached():
            cls.cachef = getattr(cls, "cachef", Cache("kaobei_aeskey.txt"))
            cached = cls.cachef.val
            if cached:
                cls.AES_KEY = cached
                return cached
            return None

        if cached := _load_cached():
            return cached

        async with httpx.AsyncClient(headers=cls.headers) as cli:
            key = await _fetch_key(cli)
            cls.cachef = getattr(cls, "cachef", Cache("kaobei_aeskey.txt"))
            cls.cachef.val = key
            return key
    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        await cls._ensure_aes_key()
        path_word = book.url.rstrip("/").split("/")[-2]
        headers = {**cls.ua, 'Referer': f'https://{cls.pc_domain}/comic/{path_word}'}
        resp = await client.get(book.url, headers=headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(
            cls.parse_episodes, resp.json()["results"], book,
            url=book.url, show_dhb=kw.get("show_dhb", conf.kbShowDhb)
        )

    @staticmethod
    def parse_book_item(target, rendering_map, render_keys, idx):
        rendered = {
            attr_name: ",".join(map(lambda __: str(__.value), _path.find(target)))
            for attr_name, _path in rendering_map.items()
        }
        book_path = rendered.pop('book_path')
        book = KbBookInfo(
            idx=idx, render_keys=render_keys,
            url=f"https://{KaobeiUtils.pc_domain}/comicdetail/{book_path}/chapters",
            preview_url=f"https://{KaobeiUtils.pc_domain}/comic/{book_path}",
        )
        for k in render_keys:
            setattr(book, k, rendered.get(k))
        return book

    @classmethod
    def parse_ep_item(cls, chapter_datum, comic_path_word, book, idx):
        return Episode(
            from_book=book,
            id=chapter_datum['id'],
            idx=idx,
            url=f"https://{cls.pc_domain}/comic/{comic_path_word}/chapter/{chapter_datum['id']}",
            name=chapter_datum['name'],
        )

    @classmethod
    def parse_episodes(cls, json_results, book, url, show_dhb=False):
        resp_data = cls.decrypt_chapter_data(json_results, url=url)
        comic_path_word = resp_data['build']['path_word']
        chapters_data = list(resp_data['groups']['default']['chapters'])
        if show_dhb:
            for g in ("tankobon", "other_group"):
                if resp_data['groups'].get(g):
                    chapters_data.extend(resp_data['groups'][g]['chapters'])
        return [cls.parse_ep_item(d, comic_path_word, book, i + 1) for i, d in enumerate(chapters_data)]
    @classmethod
    def decrypt_chapter_data(cls, ret: str, **meta_info):
        def _(cipher_hex: str, key: str, iv: str) -> dict:
            cipher_bytes = bytes.fromhex(cipher_hex)
            key_bytes = key.encode('utf-8')
            iv_bytes = iv.encode('utf-8')
            cipher = Cipher(
                algorithms.AES(key_bytes),
                modes.CBC(iv_bytes),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            decrypted_padded = decryptor.update(cipher_bytes) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
            return json.loads(decrypted.decode('utf-8'))

        cls.cachef = getattr(cls, "cachef", Cache("kaobei_aeskey.txt"))
        @cls.cachef.with_error_cleanup()
        def _decrypt():
            if len(ret) < 1000:
                raise ValueError(f"加密信息过短疑似风控变化\n{cls.cachef.val=}\n{ret=}\n{meta_info=}")
            return _(ret[16:], cls.cachef.val, ret[:16])
        return _decrypt()

    @classmethod
    def get_aes_key(cls):
        """获取AES密钥，使用缓存装饰器优化"""
        def _fetch():
            async def fetch():
                async with httpx.AsyncClient(headers=cls.headers) as cli:
                    resp = await cli.get(f"https://{cls.pc_domain}/comic/yiquanchaoren")
                    return resp.text
            try:
                loop = get_loop()
                html_text = loop.run_until_complete(fetch())
                html_doc = html.fromstring(html_text)
                dio = list(map(lambda x: x.strip().replace(" ", ""), html_doc.xpath('//script/text()')))
                real_dio = next(filter(lambda x: x.startswith("var"), dio))
                return re.findall(r"""=['"](.*?)['"]""", real_dio.split("\n")[0])[0]
            except Exception as e:
                print(e)
                raise ValueError("aes_key 获取失败")

        cls.cachef = getattr(cls, "cachef", Cache("kaobei_aeskey.txt"))
        return cls.cachef.run(_fetch, "daily", write_in=True)
