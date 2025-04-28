import time
import re
import json
import struct

import httpx
import execjs

from assets import res
from utils import conf
from utils.website.core import EroUtils, Req


class HitomiUtils(EroUtils, Req):
    name = "hitomi"
    index = "https://hitomi.la/"
    headers = {
        "accept": "*/*",
        "accept-language": res.Vars.ua_accept_language,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "referer": index
    }
    book_hea = headers
    uuid_regex = ...
    book_url_regex = ...
    domain = r"ltn.gold-usergeneratedcontent.net"
    domain2 = r"gold-usergeneratedcontent.net"
    img_domain = r"w1.gold-usergeneratedcontent.net"  # unsure its source or it's stable

    def __init__(self, conf):
        self.cli = self.get_cli(conf)
        self.gg = gg(self.cli)

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
    
    def get_img_url(self, img_hash, hasavif=0):
        g = self.gg.s(img_hash)
        img_type = "avif" if hasavif else "webp"
        retval = f"{img_type[0]}{1 + int(self.gg.m((g)))}"
        return f"https://{retval}.{self.domain2}/{self.gg.b}{g}/{img_hash}.{img_type}"

    def test_index(self):
        try:
            resp = self.cli.head(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return False
        return True


class gg:
    def __init__(self, cli):
        script_resp = cli.get(f"https://ltn.{HitomiUtils.domain2}/gg.js?_={int(time.time() * 1000)}")
        script_text = script_resp.text
        self.ctx = execjs.compile(script_text.replace('gg = {', 'var gg = {', 1))
        self.b = self.ctx.eval('gg.b')

    def s(self, h):
        return self.ctx.call('gg.s', h)
    
    def m(self, g):
        return self.ctx.call('gg.m', int(g))


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
