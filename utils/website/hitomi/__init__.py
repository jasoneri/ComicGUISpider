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
        self.dec = self.Decrypt(self.gg)

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
    
    class Decrypt:
        def __init__(self, gg):
            self.gg = gg

        def subdomain_from_url(self, base, 
                               img_type, gg_s):
            if base:    # 目前仅有"tn"
                retval = base
                # retval = chr(97 + self.gg.m(gg_s)) + base
            else:
                retval = f"{img_type[0]}{1 + self.gg.m(gg_s)}"
            return retval
        
        def full_path_from_hash(self, img_hash, gg_s):
            return self.gg.b+gg_s+'/'+img_hash

        def real_full_path_from_hash(self, img_hash, img_type, preview):
            _dir  = f"{img_type}bigtn"
            # _dir = _dir if (not preview and img_type=="avif") else "avifsmallbigtn"
            path2 = re.sub(r'^.*(..)(.)$', r'\2/\1/' + img_hash, img_hash)
            return f"{_dir}/{path2}"
    
    def get_img_url(self, img_hash, hasavif=0, preview=None):
        gg_s = self.gg.s(img_hash)
        img_type = "avif" if hasavif else "webp"
        if not preview:
            img_path = self.dec.full_path_from_hash(img_hash, gg_s)
            retval = self.dec.subdomain_from_url("", img_type, gg_s)
        else:
            img_path = self.dec.real_full_path_from_hash(img_hash, img_type, preview)
            retval = self.dec.subdomain_from_url("tn", img_type, gg_s) 
        url = f"https://{retval}.{self.domain2}/{img_path}.{img_type}"
        return url

    @classmethod
    def get_cli(cls, conf, is_async=False, **kwargs):
        return super().get_cli(conf, is_async=is_async, http2=True, **kwargs)

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
            script_resp = httpx.get(f"https://ltn.{HitomiUtils.domain2}/gg.js", timeout=8, headers=HitomiUtils.headers)
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
        fmt = '<i' if little_endian else '>i'
        return struct.unpack(fmt, binary)[0]
