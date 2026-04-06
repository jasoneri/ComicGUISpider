import asyncio
import json
import re
import struct

import httpx

from assets import res
from utils.website.core import EroUtils, Previewer, Req
from utils.website.info import HitomiBookInfo


class _HitomiContract:
    name = "hitomi"
    index = "https://hitomi.la/"
    domain = r"ltn.gold-usergeneratedcontent.net"
    domain2 = r"gold-usergeneratedcontent.net"
    test_nozomi = f"https://{domain}/popular/week-all.nozomi"
    headers = {
        "accept": "*/*",
        "accept-language": res.Vars.ua_accept_language,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "referer": index,
    }
    book_hea = headers
    galleries_per_page = 100
    uuid_regex = re.compile(r"(\d+)\.(html|js)$")
    img_domain = r"w1.gold-usergeneratedcontent.net"  # unsure its source or it's stable


class HitomiParser(_HitomiContract):
    def __init__(self, owner):
        self.owner = owner

    @classmethod
    def parse_galleries(cls, data_str):
        json_str = re.search(r"var galleryinfo = (\{.*\}$)", data_str).group(1)
        return json.loads(json_str)

    def parse_search_item(self, target_text):
        datum = self.parse_galleries(target_text)
        gallery_id = datum["id"]
        pics = datum["files"]
        first_pic = pics[0]
        title = datum["title"]
        img_preview = self.owner.get_img_url(first_pic["hash"], 0, preview=True)
        return HitomiBookInfo(
            id=gallery_id,
            name=title.split(" | ")[-1] if " | " in title else title,
            preview_url=f"{datum['type']}/{gallery_id}.html",
            pages=len(pics),
            pics=pics,
            btype=datum["type"],
            img_preview=img_preview,
            lang=datum["language_localname"],
        )


class HitomiReqer(_HitomiContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def get_cli(cls, conf, is_async=False, **kwargs):
        return super().get_cli(conf, is_async=is_async, http2=True, **kwargs)

    @classmethod
    def build_search_url(cls, key):
        nozomi_path = key if key.endswith(".nozomi") else f"{key}.nozomi"
        return f"https://{cls.domain}/{nozomi_path}"

    def test_index(self):
        try:
            resp = self.cli.head(
                self.test_nozomi,
                headers={**self.headers, "Range": HitomiUtils.get_range(1)},
                follow_redirects=True,
                timeout=3.5,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True


class HitomiUtils(_HitomiContract, EroUtils, Previewer):
    parser = HitomiParser
    reqer_cls = HitomiReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser(self)
        self.cli = self.reqer.cli
        self.gg = gg(cli=self.cli)
        self.dec = self.Decrypt(self.gg)

    @staticmethod
    def parse_nozomi(data):
        view = DataView(data)
        total = len(data) // 4
        return [view.get_int32(i * 4, little_endian=False) for i in range(total)]

    @classmethod
    def get_range(cls, page):
        end_byte = cls.galleries_per_page * int(page)
        return f"bytes={end_byte - cls.galleries_per_page}-{end_byte - 1}"

    class Decrypt:
        def __init__(self, gg_instance):
            self.gg = gg_instance

        def subdomain_from_url(self, base, img_type, gg_s):
            if base:
                return chr(97 + self.gg.m(gg_s)) + base
            return f"{img_type[0]}{1 + self.gg.m(gg_s)}"

        def full_path_from_hash(self, img_hash, gg_s):
            return self.gg.b + gg_s + "/" + img_hash

        def real_full_path_from_hash(self, img_hash, img_type):
            dir_name = f"{img_type}bigtn"
            path2 = re.sub(r"^.*(..)(.)$", r"\2/\1/" + img_hash, img_hash)
            return f"{dir_name}/{path2}"

    def get_img_url(self, img_hash, hasavif=0, preview=None):
        gg_s = self.gg.s(img_hash)
        img_type = "avif" if hasavif else "webp"
        if not preview:
            img_path = self.dec.full_path_from_hash(img_hash, gg_s)
            subdomain = self.dec.subdomain_from_url("", img_type, gg_s)
        else:
            img_path = self.dec.real_full_path_from_hash(img_hash, img_type)
            subdomain = self.dec.subdomain_from_url("tn", img_type, gg_s)
        return f"https://{subdomain}.{self.domain2}/{img_path}.{img_type}"

    @classmethod
    def preview_client_config(cls, **context) -> dict:
        return {"headers": cls.headers}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"http2": True}

    @classmethod
    async def preview_search(
        cls,
        keyword: str,
        client,
        **kw,
    ) -> list:
        page = max(1, int(kw.pop("page", 1) or 1))
        nozomi_url = cls.reqer_cls.build_search_url(keyword)
        range_header = f"bytes={cls.galleries_per_page * (page - 1)}-{cls.galleries_per_page * page - 1}"
        resp, gg_resp = await asyncio.gather(
            client.get(nozomi_url, headers={**cls.headers, "Range": range_header}, timeout=15),
            client.get(f"https://ltn.{cls.domain2}/gg.js", headers=cls.headers, timeout=15),
        )
        resp.raise_for_status()
        gg_resp.raise_for_status()
        gallery_ids = cls.parse_nozomi(resp.content)
        gg_instance = gg(js_code=gg_resp.text)
        decryptor = cls.Decrypt(gg_instance)

        sem = asyncio.Semaphore(10)

        async def fetch_one(gallery_id):
            async with sem:
                url = f"https://{cls.domain}/galleries/{gallery_id}.js"
                gallery_resp = await client.get(url, headers=cls.headers, timeout=10)
                gallery_resp.raise_for_status()
                return gallery_resp.text

        texts = await asyncio.gather(*[fetch_one(gallery_id) for gallery_id in gallery_ids], return_exceptions=True)

        books = []
        for idx, text in enumerate(texts, start=1):
            if isinstance(text, Exception):
                continue
            try:
                datum = cls.parser.parse_galleries(text)
                gallery_id = datum["id"]
                pics = datum["files"]
                first_pic = pics[0]
                img_hash = first_pic["hash"]
                gg_s = gg_instance.s(img_hash)
                img_type = "avif" if first_pic.get("hasavif") else "webp"
                img_path = decryptor.real_full_path_from_hash(img_hash, img_type)
                subdomain = decryptor.subdomain_from_url("tn", img_type, gg_s)
                title = datum["title"]
                book = HitomiBookInfo(
                    id=gallery_id,
                    name=title.split(" | ")[-1] if " | " in title else title,
                    preview_url=f"{cls.index}{datum['type']}/{gallery_id}.html",
                    pages=len(pics),
                    pics=pics,
                    btype=datum["type"],
                    img_preview=f"https://{subdomain}.{cls.domain2}/{img_path}.{img_type}",
                    lang=datum.get("language_localname", ""),
                )
                book.idx = idx
                books.append(book)
            except Exception:
                continue
        return books


class gg:
    def __init__(self, cli=None, js_code=None):
        if js_code is None:
            if cli is None:
                raise ValueError("gg requires a sync client when js_code is not provided")
            script_resp = cli.get(
                f"https://ltn.{HitomiUtils.domain2}/gg.js",
                timeout=8,
                headers=HitomiUtils.headers,
            )
            script_resp.raise_for_status()
            script_text = script_resp.text
        else:
            script_text = js_code
        self.m_cases = self._parse_m_cases(script_text)
        self.b = f"{self._parse_b(script_text)}/"

    def _parse_m_cases(self, js_code):
        return set(map(int, re.findall(r"case (\d+):", js_code)))

    def _parse_b(self, js_code):
        match = re.search(r"(\d{10})", js_code)
        return match.group(1)

    def m(self, g):
        return 1 if int(g) in self.m_cases else 0

    def s(self, h):
        matched = re.match(r"(..)(.)$", h[-3:])
        return str(int(matched.group(2) + matched.group(1), 16))


class DataView:
    def __init__(self, array):
        self.array = array

    def __get_binary(self, start_index, byte_count):
        bytes_data = self.array[start_index:start_index + byte_count]
        return bytes(bytes_data)

    def get_int32(self, start_index, little_endian=False):
        binary = self.__get_binary(start_index, 4)
        fmt = "<i" if little_endian else ">i"
        return struct.unpack(fmt, binary)[0]
