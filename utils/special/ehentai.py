#!/usr/bin/python
# -*- coding: utf-8 -*-
import httpx
from lxml import etree

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Priority": "u=0, i",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "TE": "trailers",
}


class EhCookies:
    def __init__(self, cookie: dict, *args, **kwargs):
        self.cookie = cookie

    @property
    def to_str(self):
        return '; '.join([f"{k}={v}" for k, v in self.cookie.items()])


class EHentaiKits:
    login_url = "https://forums.e-hentai.org/index.php?act=Login"
    home_url = "https://e-hentai.org/home.php"
    domain = "exhentai.org"
    index = f"https://{domain}/"

    def __init__(self, cookies, proxies: list):
        _proxies = {"https://": f"http://{proxies[0]}"}
        self.cli = httpx.Client(cookies=cookies, proxies=_proxies, headers=headers)

    def get_limit(self):
        """查限额"""
        resp = self.cli.get(self.home_url, follow_redirects=True)
        resp_t = resp.text
        html = etree.HTML(resp_t)
        ps = html.xpath('//div[@class="stuffbox"]/div[1]/p')
        if len(list(filter(lambda p: "No restrictions" in "".join(p.xpath(".//text()")), ps))):
            return '0'
        order_p = next(filter(lambda _: 'limit' in ''.join(_.xpath('./text()')), ps))
        current_access = order_p.xpath('./strong/text()')[0]
        return current_access

    def test_index(self):
        resp = self.cli.get(self.index, follow_redirects=True)
        if not resp.text:
            return False
        return True
