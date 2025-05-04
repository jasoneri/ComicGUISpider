import time
import re
import json
import struct

import httpx

from assets import res
from utils import conf
from utils.website.core import EroUtils, Req


class HitomiUtils(EroUtils, Req):
    name = "hitomi"
    index = "https://hitomi.la/"
    domain = r"ltn.gold-usergeneratedcontent.net"
    domain2 = r"gold-usergeneratedcontent.net"
    headers = {
        "accept": "*/*",
        "accept-language": res.Vars.ua_accept_language,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "referer": index
    }
    book_hea = headers
    galleries_per_page = 100
    uuid_regex = re.compile(r"(\d+)\.(html|js)$")
    img_domain = r"w1.gold-usergeneratedcontent.net"  # unsure its source or it's stable

    def __init__(self, conf):
        self.cli = self.get_cli(conf)
        self.gg = gg(cli=self.cli)

    @staticmethod
    def parse_nozomi(data):
        view = DataView(data)
        total = len(data) // 4
        return [view.get_int32(i * 4, little_endian=False) for i in range(total)]

    @staticmethod
    def parse_galleries(data_str):
        json_str = re.search(r"var galleryinfo = (\{.*\}$)", data_str).group(1)
        data = json.loads(json_str)
        return data
    
    def get_range(self, page):
        end_byte = self.galleries_per_page * int(page)
        return f"bytes={end_byte-self.galleries_per_page}-{end_byte-1}"
    
    def get_img_url(self, img_hash, hasavif=0):
        g = self.gg.s(img_hash)
        img_type = "avif" if hasavif else "webp"
        retval = f"{img_type[0]}{1 + int(self.gg.m((g)))}"
        return f"https://{retval}.{self.domain2}/{self.gg.b}{g}/{img_hash}.{img_type}"

    @classmethod
    def get_cli(cls, conf):
        if conf.proxies:
            return httpx.Client(http2=True,
                headers=cls.book_hea,
                proxies={"https://": f"http://{conf.proxies[0]}"},
                transport=httpx.HTTPTransport(retries=3))
        return httpx.Client(headers=cls.book_hea, trust_env=True, http2=True)

    def test_index(self):
        try:
            resp = self.cli.head(f'https://{self.domain}/popular/week-all.nozomi', 
                                 headers={**HitomiUtils.headers, "Range": self.get_range(1)},
                                 follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return False
        return True


class gg:
    def __init__(self, cli=None, js_code=None):
        if not js_code:
            script_resp = cli.get(f"https://ltn.{HitomiUtils.domain2}/gg.js?_={int(time.time() * 1000)}")
            script_text = script_resp.text
        else:
            script_text = js_code
        self.m_cases = self._parse_m_cases(script_text)
        self.b = f"{self._parse_b(script_text)}/"
        
    def _parse_m_cases(self, js_code):
        pattern = r"case (\d+):"
        return set(map(int, re.findall(pattern, js_code)))

    def _parse_b(self, js_code):
        match = re.search(r"(\d{10})", js_code)
        return match.group(1)

    def m(self, g):
        return 0 if int(g) in self.m_cases else 1

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
        fmt = '<i' if little_endian else '>i'
        return struct.unpack(fmt, binary)[0]
