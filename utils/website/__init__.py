#!/usr/bin/python
# -*- coding: utf-8 -*-
import hashlib
import re
import math
import json
from io import BytesIO
import asyncio

import httpx
from PIL import Image
from lxml import etree, html
from scrapy import Selector
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from assets import res
from variables import COOKIES_SUPPORT
from utils import md5, ori_path, conf, temp_p, get_loop
from utils.website.core import *
from utils.website.chore import *
from utils.website.hitomi import HitomiUtils


class JmUtils(EroUtils, DomainUtils, Req, Cookies):
    name = "jm"
    forever_url = "https://jm365.work/3YeBdF"
    publish_url = "https://jm365.work/mJ8rWd"
    status_forever = True
    status_publish = True
    cookies_field = COOKIES_SUPPORT[name]
    publish_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Priority': 'u=0, i',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }
    book_hea = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
    }
    uuid_regex = re.compile(r"/(\d{5,})")

    class JmImage:
        regex = re.compile(r"(\d+)/(\d+)")
        epsId = None  # 书id '536323'
        scramble_id = None  # 页数(带前缀0) '00020'

        def convert_img(self, img_content: bytes) -> Image:
            self.epsId = int(self.epsId)

            def get_num():
                def _get_num(__: int):
                    string = str(self.epsId) + self.scramble_id
                    string = string.encode()
                    string = hashlib.md5(string).hexdigest()
                    _ = ord(string[-1])
                    _ %= __
                    return _ * 2 + 2

                if self.epsId < 220980:
                    return 0
                elif self.epsId < 268850:
                    return 10
                elif self.epsId > 421926:
                    return _get_num(8)
                else:
                    return _get_num(10)

            num = get_num()
            img = BytesIO(img_content)
            srcImg = Image.open(img)
            if not num:
                return srcImg
            size = (width, height) = srcImg.size
            desImg = Image.new(srcImg.mode, size)
            rem = height % num
            copyHeight = math.floor(height / num)
            block = []
            totalH = 0
            for i in range(num):
                h = copyHeight * (i + 1)
                if i == num - 1:
                    h += rem
                block.append((totalH, h))
                totalH = h
            h = 0
            for start, end in reversed(block):
                coH = end - start
                temp_img = srcImg.crop((0, start, width, end))
                desImg.paste(temp_img, (0, h, width, h + coH))
                h += coH
            srcImg.close()
            del img
            return desImg

        @classmethod
        def by_url(cls, url):
            obj = cls()
            obj.epsId, obj.scramble_id = cls.regex.search(url).groups()
            return obj

    @classmethod
    def get_cli(cls, conf, is_async=False, **kwargs):
        client_class = httpx.AsyncClient if is_async else httpx.Client
        headers = {**cls.book_hea, 'Referer': f"https://{cls.get_domain()}"}
        return client_class(headers=headers, **kwargs)

    @classmethod
    async def by_publish(cls):
        async with httpx.AsyncClient(headers=cls.publish_headers,transport=httpx.AsyncHTTPTransport(retries=2)) as sess:
            resp = await sess.get(cls.publish_url)
            e = None
            while True:
                try:
                    if str(resp.status_code).startswith('3') and resp.headers.get('location'):
                        if resp.status_code == 302:
                            transport=dict(proxy=f"http://{conf.proxies[0]}",retries=2) if conf.proxies else dict(retries=2)
                            async with httpx.AsyncClient(headers=cls.publish_headers,transport=httpx.AsyncHTTPTransport(**transport),verify=False) as cli:
                                resp = await cli.get(resp.headers.get('location'))
                        else:
                            resp = await sess.get(resp.headers.get('location'))
                    elif str(resp.status_code).startswith('2'):
                        return await cls.parse_publish(resp.text)
                except Exception as _e:
                    e = _e
                    break
            cls.status_publish = False
            raise e or ConnectionError(
                res.SPIDER.PUBLISH_INVALID % (cls.publish_url, str(ori_path.joinpath(f'__temp/{cls.name}_domain.txt')))
            )

    @classmethod
    async def parse_publish_(cls, html_text):
        html = etree.HTML(html_text)
        ps = html.xpath('//div[@class="wrap"]//p')
        domains = []
        order_p = list(filter(lambda p: '內地' in ''.join(p.xpath('.//text()')), ps))  # 小心这个"內"字是繁体
        if order_p:
            idx = ps.index(order_p[0])
            for p in ps[idx:]:
                fuck_text = p.xpath('./following-sibling::div//text()')
                for _domain in fuck_text:
                    domain = _domain.strip()
                    if "." in domain and not bool(re.search(r"discord|\.work|@|＠|<|/", domain)):
                        domains.append(domain)
        hosts = await asyncio.gather(*[cls.test_aviable_domain(domain) for domain in domains])
        for host in hosts:
            if host:
                return host
        cls.status_publish = False
        raise ConnectionError(
            res.SPIDER.DOMAINS_INVALID % (cls.publish_url, domains, str(ori_path.joinpath(f'__temp/{cls.name}_domain.txt')))
        )

    book_url_regex = r"^https://.*?comic.*?/album/\d+"

    @staticmethod
    def parse_book(resp_text):
        html = Selector(text=resp_text)
        cover_el = html.xpath('//div[@id="album_photo_cover"]')[-1]
        title = html.xpath('//h1/text()').get()
        img_src = cover_el.xpath('.//div[@class="thumb-overlay"]/img[contains(@class,"img-responsive")]/@src').get()
        info_el = cover_el.xpath('./following-sibling::div')[0]
        author = (info_el.xpath('.//span[@data-type="author"]/a/text()').getall() or ["-"])[-1]
        pages_text = info_el.xpath('./div/div[contains(text(), "頁數") or contains(text(), "页数")]/text()').get()
        pages = re.search(r'\d+', pages_text).group(0)
        tags = info_el.xpath('.//span[@data-type="tags"]/a/text()').getall()
        url = jm_id = re.search(r"var aid = (\d+);", resp_text).group(1)
        epa_els = html.xpath('(//div[@class="episode"])[last()]/ul/a')
        episodes = []
        for epa_el in epa_els:
            _ep_title = epa_el.xpath('.//h3/text()[normalize-space()]').get().strip()
            ep_title = re.split(r"\s+", _ep_title)[0]
            bid = epa_el.xpath('./@data-album').get()
            idx = int(epa_el.xpath('./@data-index').get()) + 1  # 转换为1开始的索引
            episodes.append({"ep": ep_title, "idx": idx, "bid": bid})
        return url, img_src, title, author, pages, tags[:20], episodes


class WnacgUtils(EroUtils, DomainUtils, Req):
    name = "wnacg"
    publish_domain = "wnlink.ru"
    publish_domain_old = ["wnacg.date"]
    publish_url = f"https://{publish_domain}"
    status_publish = True
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36 Edg/133.0.0.0"
    }
    book_hea = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
    }
    uuid_regex = re.compile(r"-(\d+)\.html$")
    cate_mappings = {"cate-5": "同人誌","cate-1": "同人誌 / 漢化","cate-12": "同人誌 / 日語","cate-16": "同人誌 / English","cate-2": "同人誌 / CG畫集","cate-37": "同人誌 / AI圖集","cate-22": "同人誌 / 3D漫畫","cate-3": "同人誌 / Cosplay","cate-6": "單行本","cate-9": "單行本 / 漢化","cate-13": "單行本 / 日語","cate-17": "單行本 / English","cate-7": "雜誌&短篇","cate-10": "雜誌&短篇 / 漢化","cate-14": "雜誌&短篇 / 日語","cate-18": "雜誌&短篇 / English","cate-19": "韓漫","cate-20": "韓漫 / 漢化","cate-21": "韓漫 / 其他",}

    @classmethod
    async def parse_publish_(cls, html_text):
        html = etree.HTML(html_text)
        hrefs = html.xpath('//div[@class="main"]//li/a/@href')
        publish_domain_old_str = "|".join(cls.publish_domain_old)
        match_regex = re.compile(f"google|{cls.publish_domain}|email|{publish_domain_old_str}")
        order_href = list(map(lambda url: re.sub("https?://", "", url).strip("/"), filter(
            lambda href: not bool(match_regex.search(href)), hrefs
        )))
        hosts = await asyncio.gather(*[cls.test_aviable_domain(domain) for domain in order_href])
        for host in hosts:
            if host:
                return host
        cls.status_publish = False
        raise ConnectionError(
            res.SPIDER.DOMAINS_INVALID % (cls.publish_url, order_href, ori_path.joinpath(f'__temp/{cls.name}_domain.txt'))
        )

    book_id_url = "https://www.wnacg02.cc/photos-index-aid-%s.html"
    book_url_regex = r"^https://(www\.)?wn.*?/photos-index-aid-\d+\.html$"

    @staticmethod
    def parse_book(resp_text):
        html = Selector(text=resp_text)
        title = html.xpath('//body/div/h2/text()').get()
        thumb_el = html.xpath('//div[contains(@class, "uwthumb")]')[0]
        img_src = thumb_el.xpath('./img/@src').get().replace("////", "https://")
        url = thumb_el.xpath('./a/@href').get().replace('slide', 'gallery')
        info_el = html.xpath('//div[contains(@class, "uwconn")]')[0]
        label_texts = info_el.xpath('./label/text()').getall()
        pages = re.search(r'\d+', next(filter(lambda _: "頁數" in _, label_texts))).group(0)
        tags = info_el.xpath('.//a[@class="tagshow"]/text()').getall()
        author = "-"
        return url, img_src, title, author, pages, tags[:20], []


class EHentaiKits(EroUtils, Req, Cookies):
    name = "ehentai"
    login_url = "https://forums.e-hentai.org/index.php?act=Login"
    home_url = "https://e-hentai.org/home.php"
    domain = "exhentai.org"
    index = f"https://{domain}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": res.Vars.ua_accept_language,
        "Accept-Encoding": "gzip, deflate, br"
    }
    book_hea = headers
    uuid_regex = re.compile(r"/g/(\d+)/")
    cookies_field = COOKIES_SUPPORT[name]

    def __init__(self, conf):
        self.cli = self.get_cli(conf)

    def get_limit(self):  # discard
        """查限额"""
        ...

    def test_index(self):
        try:
            resp = self.cli.get(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return False
        if not resp.text:
            return False
        return True

    @classmethod
    def get_cli(cls, conf, is_async=False, **kwargs):
        cli = super().get_cli(conf, is_async=is_async, **kwargs)
        cli.headers = {**cls.book_hea, "Cookie": cls.to_str_(conf.cookies.get(cls.name))}
        return cli

    book_url_regex = r"^https://exhentai\.org/g/[0-9a-z]+/[0-9a-z]+"

    @staticmethod
    def parse_book(resp_text):
        html = Selector(text=resp_text)
        title = (html.xpath('//h1[@id="gj"]/text()').get() or html.xpath('//div[@id="gd2"]/h1/text()').get())
        script_string = html.xpath('//script[contains(text(), "var base_url")]/text()').get()
        gid = re.search(r"gid = ([0-9a-z]+)", script_string).group(1)
        token = re.search(r"""token = "?([0-9a-z]+)""", script_string).group(1)
        url = f"/g/{gid}/{token}/"
        pages = re.search(r">(\d+) pages<", resp_text).group(1)
        tags_ = html.xpath('//td[@class="tc" and text()="female:"]/following-sibling::td/div/a/@id').getall()
        tags = list(map(lambda x: x.split(":")[-1], tags_))
        author_ = html.xpath('//div[contains(@id, "td_artist:")]/@id').getall()
        author = author_[0].split(':')[-1] if author_ else '-'
        img_src_el = html.xpath('//div[@id="gleft"]/div/div/@style').get()
        img_src = re.search(r"url\((.*?)\)", img_src_el.replace("&quot;", "").replace('"', '')
                            ).group(1)
        return url, img_src, title, author, pages, tags[:20] if tags else [], []


class KaobeiUtils(Utils):
    name = "manga_copy"
    uuid_regex = re.compile(r"(\d+)$")
    pc_domain = "www.2025copy.com"
    AES_KEY = None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }
    cachef = Cache("kaobei_aeskey.txt")

    @classmethod
    @cachef.with_error_cleanup()
    def decrypt_chapter_data(cls, ret: str):
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
        return _(ret[16:], cls.cachef.val, ret[:16])

    @classmethod
    @cachef.with_expiry("daily", write_in=True)
    def get_aes_key(cls):
        """获取AES密钥，使用缓存装饰器优化"""
        async def fetch():
            async with httpx.AsyncClient(headers=cls.headers) as cli:
                resp = await cli.get(f"https://{cls.pc_domain}/comic/xsjzmwls")
                return resp.text
        try:
            loop = get_loop()
            html_text = loop.run_until_complete(fetch())
            html_doc = html.fromstring(html_text)
            dio = list(map(lambda x: x.strip().replace(" ", ""), html_doc.xpath('//script/text()')))
            real_dio = next(filter(lambda x: x.startswith("var") and "\n" not in x, dio))
            aes_key = re.findall(r"""=['"](.*?)['"]""", real_dio)[0]
            return aes_key
        except Exception as e:
            print(e)
            raise ValueError("aes_key 获取失败")


class MangabzUtils(Utils, Req):
    name = "mangabz"
    index = "https://www.mangabz.com"
    image_ua = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.mangabz.com/",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
        "Priority": "u=5, i",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "TE": "trailers"
    }

    def __init__(self, conf):
        self.cli = self.get_cli(conf)

    def test_index(self):
        try:
            resp = self.cli.head(self.index, follow_redirects=True, timeout=3.5,
                                 headers={
                                     "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1"})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return False
        return True


spider_utils_map = {
    1: KaobeiUtils, 2: JmUtils, 3: WnacgUtils, 4: EHentaiKits, 5: MangabzUtils,
    6: HitomiUtils,
    'manga_copy': KaobeiUtils, 'jm': JmUtils, 'wnacg': WnacgUtils, 'ehentai': EHentaiKits, 'mangabz': MangabzUtils,
    'hitomi': HitomiUtils
}


class Uuid:
    def __init__(self, spider_name):
        self.spider = spider_name
        self.get = getattr(spider_utils_map[self.spider], 'get_uuid')

    def id_and_md5(self, info):
        _id = self.get(info)
        return _id, md5(_id)
