import hashlib
import re
import math
import json
from datetime import datetime, timezone
from io import BytesIO
import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from urllib.parse import quote, urlencode

import httpx
from PIL import Image
from lxml import etree, html
from scrapy import Selector
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from assets import res
from variables import COOKIES_SUPPORT
from utils import ori_path, conf, get_loop
from utils.website.core import *
from utils.website.hitomi import *
from . import registry
from .info import *
from .req_schema import MbSearchBody, mb_curr_time_format


class HComicParseError(ValueError):
    """h-comic 解析异常，直接抛出给上层做统一错误展示。"""


class JmUtils(EroUtils, DomainUtils, Req, Cookies):
    name = "jm"
    forever_url = "https://jm365.work/3YeBdF"
    publish_url = "https://jm365.work/mJ8rWd"
    publish_url2 = "https://jm-3x.cc/mJ8rWd"
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
    }
    uuid_regex = re.compile(r"[^/]+/(\d+)")

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
    def get_cli(cls, _conf, is_async=False, **kwargs):
        client_class = httpx.AsyncClient if is_async else httpx.Client
        headers = {**cls.book_hea, 'Referer': f"https://{cls.get_domain()}"}
        cli = client_class(headers=headers, **kwargs)
        return cli

    @classmethod
    async def by_publish(cls):
        async with httpx.AsyncClient(headers=cls.publish_headers,transport=httpx.AsyncHTTPTransport(retries=2),http2=True) as sess:
            resp = await sess.get(cls.publish_url2)
            e = None
            while True:
                try:
                    if str(resp.status_code).startswith('3') and resp.headers.get('location'):
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
        _html = etree.HTML(html_text)
        ps = _html.xpath('//div[@class="wrap"]//p')
        domains = []
        def get_text(p):
            return ''.join(p.xpath('.//text()'))
        idx_start = next((i for i, p in enumerate(ps) if '內地' in get_text(p)), None)
        idx_end = next((i for i, p in enumerate(ps) if get_text(p).strip().lower().startswith('app')), len(ps))
        if idx_start is not None:
            if idx_end <= idx_start:
                idx_end = len(ps)
            for p in ps[idx_start:idx_end]:
                fuck_text = p.xpath("./following-sibling::div//text()")
                for _domain in fuck_text:
                    domain = _domain.strip()
                    if "." in domain and not bool(re.search(r"discord|\.work|@|＠|<", domain)):
                        domains.append(re.sub(r'^https?://', '', domain).split('/', 1)[0])
        hosts = await asyncio.gather(*[cls.test_aviable_domain(domain) for domain in domains])
        for host in hosts:
            if host:
                return host
        cls.status_publish = False
        raise ConnectionError(
            res.SPIDER.DOMAINS_INVALID % (cls.publish_url, domains, str(ori_path.joinpath(f'__temp/{cls.name}_domain.txt')))
        )

    book_url_regex = r"^https://.*?(18|jm).*?/album/\d+"

    def build_search_url(self, key):
        self.domain = self.domain or self.get_domain()
        return f'https://{self.domain}/search/photos?main_tag=0&search_query={key}'

    @staticmethod
    def parse_search_item(target):
        _parent_div = target.xpath('./parent::*/parent::div')
        pre_url = '/'.join(target.xpath('../@href | ./a/@href').get().split('/')[:-1])
        img_preview = target.xpath('./a/img/@src | ./img/@src').get()
        if (img_preview or "").endswith("blank.jpg"):
            img_preview: str = target.xpath('./a/img/@data-original | ./img/@data-original').get()
        _likes = target.xpath('.//span[contains(@id,"albim_likes")]/text()').get()
        _btypes = target.xpath('.//div[@class="category-icon"]/div/text()').getall()
        artist = _parent_div.xpath('.//div//a[contains(@href, "main_tag=2")]/text()').get()
        tags = _parent_div.xpath('.//div[contains(@class, "tags")]//a[@class="tag"]/text()').getall()
        book = JmBookInfo(
            name=target.xpath('.//img/@title').get().strip().replace("\n", ""),
            preview_url=pre_url, url=pre_url.replace('album', 'photo'),
            btype=" ".join(map(str.strip, _btypes)).strip(),
            img_preview=img_preview, artist=(artist or '').strip() or None, tags=tags,
            likes=_likes.strip() if _likes else 0
        ).get_id(pre_url)
        return book

    def parse_search(self, resp_text):
        self.domain = self.domain or self.get_domain()
        _html = Selector(text=resp_text)
        targets = _html.xpath('//div[contains(@class,"thumb-overlay") and not(@class="thumb-overlay-guess_likes")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(self.parse_search_item, targets))
        for book in books:
            book.preview_url = f'https://{self.domain}{book.preview_url}'
            book.url = f'https://{self.domain}{book.url}'
        return books

    @classmethod
    def parse_book(cls, resp_text):
        if "Just a moment..." in resp_text[:100]:
            raise ValueError("触发5秒盾")
        _html = Selector(text=resp_text)
        cover_el = _html.xpath('//div[@id="album_photo_cover"]')[-1]
        info_el = cover_el.xpath('./following-sibling::div')[0]
        pages_text = info_el.xpath('./div/div[contains(text(), "頁數") or contains(text(), "页数")]/text()').get()
        url = jm_id = re.search(r"var aid = (\d+);", resp_text).group(1)
        epa_els = _html.xpath('(//div[@class="episode"])[last()]/ul/a')
        public_date = info_el.xpath('.//span[@itemprop="datePublished"][contains(text(), "上架日期")]/@content').get()
        book = JmBookInfo(
            name=_html.xpath('//h1/text()').get(),
            artist=(info_el.xpath('.//span[@data-type="author"]/a/text()').getall() or [None])[-1],
            id=jm_id,
            tags=info_el.xpath('.//span[@data-type="tags"]/a/text()').getall(),
            img_preview=cover_el.xpath('.//div[@class="thumb-overlay"]/img[contains(@class,"img-responsive")]/@src').get(),
            pages=re.search(r'\d+', pages_text).group(0), public_date=public_date, episodes=[]
        )
        for epa_el in epa_els:
            if not book.episodes:
                book.episodes = []
            _ep_title = epa_el.xpath('.//h3/text()[normalize-space()]').get().strip()
            episode = Episode(
                from_book=book,
                id=epa_el.xpath('./@data-album').get(),
                idx=int(epa_el.xpath('./@data-index').get()) + 1,
                name=re.split(r"\s+", _ep_title)[0]
            )
            book.episodes.append(episode)
        return book


class WnacgUtils(EroUtils, DomainUtils, Req):
    name = "wnacg"
    publish_domain = "wnacg01.link"
    publish_domain_old = ["wnacg.date","wn01.link"]
    publish_url = f"https://{publish_domain}"
    status_publish = True
    publish_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5',
    }
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
        _html = etree.HTML(html_text)
        hrefs = _html.xpath('//div[@class="main"]//li[not(contains(.,"發佈頁") or contains(.,"发布页"))]/a/@href')
        publish_domain_old_str = "|".join(cls.publish_domain_old)
        match_regex = re.compile(f"google|{cls.publish_domain}|email|link|{publish_domain_old_str}")
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

    def build_search_url(self, key):
        self.domain = self.domain or self.get_domain()
        return f'https://{self.domain}/search/?f=_all&s=create_time_DESC&syn=yes&q={key}'

    @staticmethod
    def parse_search_item(target):
        tar_xpath = './div[contains(@class, "pic")]'
        item_elem = target.xpath(f"{tar_xpath}/a")
        pre_url = item_elem.xpath('./@href').get()
        _page = target.xpath('.//div[contains(@class, "info_col")]/text()').get()
        _cate = (target.xpath(f"{tar_xpath}/@class").get() or "").split(" ")[-1]
        public_date = re.search(r'\d{4}-\d{2}-\d{2}', _page).group() \
            if _page and bool(re.search(r'\d{4}-\d{2}-\d{2}', _page)) else None
        book = WnacgBookInfo(
            name=item_elem.xpath('./@title').get(),
            preview_url=pre_url,
            url=pre_url.replace('index', 'gallery'),
            pages=re.search(r'(\d+)[張张]', _page.strip()).group(1) if _page else 0,
            btype=WnacgUtils.cate_mappings.get(_cate, ""),
            img_preview='http:' + item_elem.xpath('./img/@src').get(),
            public_date=public_date,
        ).get_id(pre_url)
        return book

    def parse_search(self, resp_text):
        """parse search-page"""
        self.domain = self.domain or self.get_domain()
        _html = Selector(text=resp_text)
        targets = _html.xpath('//li[contains(@class, "gallary_item")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(self.parse_search_item, targets))
        for book in books:
            book.preview_url = f'https://{self.domain}{book.preview_url}'
            book.url = f'https://{self.domain}{book.url}'
        return books

    @staticmethod
    def parse_book(resp_text):
        _html = Selector(text=resp_text)
        thumb_el = _html.xpath('//div[contains(@class, "uwthumb")]')[0]
        url = thumb_el.xpath('./a/@href').get().replace('slide', 'gallery')
        info_el = _html.xpath('//div[contains(@class, "uwconn")]')[0]
        label_texts = info_el.xpath('./label/text()').getall()
        
        cate_hrefs = _html.xpath('//div[contains(@class, "bread")]//a[contains(@href, "albums-index-cate-")]/@href').getall()
        btype = WnacgUtils.cate_mappings.get(f"cate-{m.group(1)}", "") if cate_hrefs and (m := re.search(r'cate-(\d+)', cate_hrefs[-1])) else None
        date_text = _html.xpath('//div[@class="grid"]//li[1]//div[@class="info_col"]/text()').get()
        public_date = re.search(r'\d{4}-\d{2}-\d{2}', date_text).group() if date_text else None
        
        book = WnacgBookInfo(
            name=_html.xpath('//body/div/h2/text()').get(), 
            url=url, preview_url=url.replace('gallery', 'index'),
            tags=info_el.xpath('.//a[@class="tagshow"]/text()').getall(),
            img_preview=thumb_el.xpath('./img/@src').get().replace("////", "https://"),
            pages=re.search(r'\d+', next(filter(lambda _: "頁數" in _, label_texts))).group(0),
            btype=btype, public_date=public_date, episodes=[]
        ).get_id(url)
        return book


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

    def __init__(self, _conf):
        super().__init__(_conf)
        self.cli = self.get_cli(_conf)

    def test_index(self):
        try:
            resp = self.cli.get(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return False
        return bool(resp.text)

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        cli = super().get_cli(_conf, is_async=is_async, **kwargs)
        cli.headers = {**cls.book_hea, "Cookie": cls.to_str_(_conf.cookies.get(cls.name))}
        return cli

    book_url_regex = r"^https://exhentai\.org/g/[0-9a-z]+/[0-9a-z]+"

    def build_search_url(self, key):
        return f'https://exhentai.org/?f_search={key}'

    @staticmethod
    def parse_search_item(target):
        def _parse_tags(tag_divs):
            artist = language = None
            tags = []
            for tag_div in tag_divs:
                title = tag_div.xpath('./@title').get()
                if not title or ':' not in title:
                    continue
                tag_type, tag_value = title.split(':', 1)
                if tag_type == 'language' and tag_value != 'translated':
                    language = tag_value
                elif tag_type == 'artist':
                    artist = tag_value
                elif tag_type in ['character', 'female', 'parody', 'male', 'group']:
                    tags.append(tag_value)
            return language, tags, artist
        item_elem = target.xpath('./td/div[@class="glthumb"]')
        pages = (next(filter(
            lambda _: 'pages' in _, item_elem.xpath('.//div/text()').getall()))
                 .replace(" pages", ""))
        _url = target.xpath('./td[contains(@class, "glname")]/a/@href').get()
        btype = " ".join(map(str.strip, target.xpath('./td[contains(@class, "gl1c")]/div/text()').getall())) or None
        language, tags, artist = _parse_tags(target.xpath('.//div[@class="gt"]'))
        book = EhBookInfo(
            name=item_elem.xpath('.//img/@title').get(),
            preview_url=_url, url=_url, pages=int(pages), btype=btype,
            img_preview=(item_elem.xpath('.//img/@data-src') or item_elem.xpath('.//img/@src')).get(),
            lang=language, tags=tags, artist=artist
        ).get_id(_url)
        return book

    def parse_search(self, resp_text):
        _html = Selector(text=resp_text)
        targets = _html.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(EHentaiKits.parse_search_item, targets))
        return books

    @staticmethod
    def parse_book(resp_text):
        _html = Selector(text=resp_text)
        script_string = _html.xpath('//script[contains(text(), "var base_url")]/text()').get()
        gid = re.search(r"gid = ([0-9a-z]+)", script_string).group(1)
        token = re.search(r"""token = "?([0-9a-z]+)""", script_string).group(1)
        tags_ = _html.xpath('//td[@class="tc" and text()="female:"]/following-sibling::td/div/a/@id').getall()
        author_ = _html.xpath('//div[contains(@id, "td_artist:")]/@id').getall()
        img_src_el = _html.xpath('//div[@id="gleft"]/div/div/@style').get()
        gdd_div_str = _html.xpath('//div[@id="gdd"]').get()
        public_date = re.search(r'\d{4}-\d{2}-\d{2}', gdd_div_str).group() if gdd_div_str else None
        pages = re.search(r">(\d+) pages<", gdd_div_str).group(1) if gdd_div_str else None
        btype = " ".join(map(str.strip, _html.xpath('//div[@id="gdc"]/div/text()').getall())) or None
        book = EhBookInfo(
            id=gid,
            name=(_html.xpath('//h1[@id="gj"]/text()').get() or _html.xpath('//div[@id="gd2"]/h1/text()').get()),
            artist=author_[0].split(':')[-1] if author_ else None, 
            url=f"/g/{gid}/{token}/", preview_url=f"{EHentaiKits.index}g/{gid}/{token}/",
            tags=list(map(lambda x: x.split(":")[-1], tags_)),
            img_preview=re.search(r"url\((.*?)\)", img_src_el.replace("&quot;", "").replace('"', '')).group(1),
            btype=btype, public_date=public_date, pages=pages, episodes=[]
        )
        return book


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


class MangabzUtils(Utils, Req, MangaPreview):
    name = "mangabz"
    domain = "www.mangabz.com"
    index = "https://www.mangabz.com"
    ua = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "TE": "trailers"
    }
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

    @staticmethod
    def parse_book_item(target, rendering_map, render_keys, idx, domain):
        rendered = OrderedDict()
        for attr_name, _path in rendering_map.items():
            rendered[attr_name] = ",".join(map(lambda __: str(__.value), _path.find(target))).strip()
        url = f"https://{domain}/{rendered.pop('book_path').strip('/')}/"
        book = MangabzBookInfo(idx=idx, render_keys=render_keys, url=url, preview_url=url)
        for k in render_keys:
            setattr(book, k, rendered.get(k))
        return book

    @staticmethod
    def parse_ep_item(target, book, domain, idx):
        return Episode(
            from_book=book,
            idx=idx,
            url=f"https://{domain}{target.xpath('./@href').get()}",
            name="".join(target.xpath('./text()').get()).strip(),
        )

    @staticmethod
    def parse_episodes(sel, book, domain):
        targets = list(reversed(sel.xpath('//div[@class="detail-list-item"]/a')))
        return [MangabzUtils.parse_ep_item(t, book, domain, i + 1) for i, t in enumerate(targets)]

    @classmethod
    def _parse_search_targets(cls, json_data, body, **kw):
        domain = kw.get("domain", cls.domain)
        rendering_map = body.rendering_map()
        render_keys = body.print_head[1:]
        books = []
        for idx, target in enumerate(json_data, start=1):
            book = cls.parse_book_item(target, rendering_map, render_keys, idx, domain)
            book.img_preview = target.get("Pic")
            books.append(book)
        return books

    @classmethod
    async def preview_search(cls, keyword, client, **kw):
        page = int(kw.pop("page", 1) or 1)
        if page < 1:
            page = 1
        body = MbSearchBody(title=keyword)
        body.dic["pageindex"] = str(page)
        url = f"https://{cls.domain}/pager.ashx?d={mb_curr_time_format()}"
        headers = {**cls.ua, "Content-Type": "application/x-www-form-urlencoded"}
        resp = await client.post(url, data=body.dic, headers=headers, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()
        return await asyncio.to_thread(cls._parse_search_targets, resp.json(), body)

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        resp = await client.get(book.url, headers=cls.ua, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()

        def _parse_and_extract(resp_text, bk, domain):
            sel = Selector(text=resp_text)
            return cls.parse_episodes(sel, bk, domain)

        return await asyncio.to_thread(_parse_and_extract, resp.text, book, cls.domain)

    def __init__(self, _conf):
        super().__init__(_conf)
        self.cli = self.get_cli(_conf)

    def test_index(self):
        try:
            resp = self.cli.head(self.index, follow_redirects=True, timeout=3.5,
                                 headers={
                                     "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1"})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return False
        return True


class HComicUtils(EroUtils, Req):
    name = "h_comic"
    index = "https://h-comic.com"
    image_server = "https://h-comic.link/api"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,en-US;q=0.5,en;q=0.3",
    }
    book_hea = headers
    uuid_regex = re.compile(r"[?&]id=(\d+)")
    book_url_regex = r"^https://h-comic\.com/comics/.+\?id=\d+"
    payload_regex = re.compile(r"data:\s*\[null,\s*(\{.*?\})\s*],\s*form:", re.S)
    object_key_regex = re.compile(r'([{\[,]\s*)([A-Za-z_]\w*)\s*:')

    def __init__(self, _conf):
        super().__init__(_conf)
        self.cli = self.get_cli(_conf)

    def test_index(self):
        try:
            resp = self.cli.head(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError:
            try:
                resp = self.cli.get(self.index, follow_redirects=True, timeout=3.5)
                resp.raise_for_status()
            except httpx.HTTPError:
                return False
        return True

    @classmethod
    def build_search_url(cls, key):
        return f"{cls.index}/?q={key}"

    @classmethod
    def _format_public_date(cls, unix_ts):
        try:
            ts = int(float(unix_ts))
            if ts > 10_000_000_000:
                ts = ts // 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError, OverflowError):
            return None

    @classmethod
    def _jsobj_to_dict(cls, js_obj_text):
        json_ready = cls.object_key_regex.sub(r'\1"\2":', js_obj_text)
        return json.loads(json_ready)

    @classmethod
    def _extract_payload_data(cls, resp_text):
        m = cls.payload_regex.search(resp_text)
        if not m:
            raise ValueError("h-comic payload not found")
        payload_obj = cls._jsobj_to_dict(m.group(1))
        if not isinstance(payload_obj, dict):
            raise ValueError("h-comic payload root is not an object")
        data = payload_obj.get("data")
        if not isinstance(data, dict):
            raise ValueError("h-comic payload missing `data` object")
        return data

    @classmethod
    def _get_image_prefix(cls, comic_source):
        source_upper = (comic_source or "").upper()
        if source_upper == "MMCG_SHORT":
            suffix = "mms"
        elif source_upper == "MMCG_LONG":
            suffix = "mml"
        else:
            suffix = "nh"
        return f"{cls.image_server}/{suffix}"

    @classmethod
    def _build_cover_url(cls, comic):
        media_id = comic.get("media_id")
        if not media_id:
            return None
        return f"{cls._get_image_prefix(comic.get('comic_source'))}/{media_id}"

    @classmethod
    def _build_book_urls(cls, comic):
        title_info = comic.get("title") or {}
        comic_id = comic.get("id")
        slug_source = title_info.get("japanese") or title_info.get("english") or str(comic_id)
        slug = quote(slug_source, safe="")
        preview_url = f"{cls.index}/comics/{slug}?id={comic_id}"
        url = f"{cls.index}/comics/{slug}/1?id={comic_id}"
        return preview_url, url

    @classmethod
    def parse_search_item(cls, target):
        title_info = target.get("title") or {}
        tags = target.get("tags") or []
        artist = next((t.get("name") for t in tags if t.get("type") == "artist"), None)
        category = next((t.get("name_zh") or t.get("name") for t in tags if t.get("type") == "category"), None)
        tag_names = [t.get("name_zh") or t.get("name") for t in tags if t.get("type") == "tag"]
        preview_url, url = cls._build_book_urls(target)
        pages = target.get("num_pages") or len((target.get("images") or {}).get("pages") or [])
        book = HComicBookInfo(
            name=title_info.get("display") or title_info.get("japanese") or title_info.get("english") or "未知标题",
            preview_url=preview_url,
            url=url,
            pages=pages,
            artist=artist,
            tags=[tag for tag in tag_names if tag],
            btype=category,
            public_date=cls._format_public_date(target.get("upload_date")),
            img_preview=cls._build_cover_url(target),
            id=str(target.get("id") or ""),
            media_id=str(target.get("media_id") or ""),
            comic_source=target.get("comic_source"),
        ).get_id(url)
        return book

    @classmethod
    def parse_search(cls, resp_text):
        try:
            data = cls._extract_payload_data(resp_text)
        except (ValueError, json.JSONDecodeError, TypeError) as e:
            raise HComicParseError(f"h-comic 搜索页解析失败: {e}") from e
        targets = data.get("comics")
        if not isinstance(targets, list):
            raise HComicParseError("h-comic 搜索页解析失败: `comics` 字段不是列表")
        books = []
        for idx, target in enumerate(targets, start=1):
            if not isinstance(target, dict):
                raise HComicParseError(f"h-comic 搜索页解析失败: 第 {idx} 项不是对象")
            try:
                books.append(cls.parse_search_item(target))
            except (KeyError, TypeError, ValueError) as e:
                raise HComicParseError(f"h-comic 搜索条目解析失败(第 {idx} 项): {e}") from e
        return books

    @classmethod
    def parse_book(cls, resp_text):
        data = cls._extract_payload_data(resp_text)
        comic = data.get("comic")
        if not comic:
            raise ValueError("h-comic comic payload missing")
        return cls.parse_search_item(comic)


registry.spider_utils_map.update({
    1: KaobeiUtils, 2: JmUtils, 3: WnacgUtils, 4: EHentaiKits, 5: MangabzUtils,
    6: HitomiUtils, 8: HComicUtils,
    'manga_copy': KaobeiUtils, 'jm': JmUtils, 'wnacg': WnacgUtils, 'ehentai': EHentaiKits, 'mangabz': MangabzUtils,
    'hitomi': HitomiUtils, 'h_comic': HComicUtils
})
