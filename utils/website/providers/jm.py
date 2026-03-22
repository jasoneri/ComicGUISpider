import hashlib
import re
import math
from io import BytesIO
import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
from PIL import Image
from lxml import etree
from scrapy import Selector

from assets import res
from variables import COOKIES_SUPPORT
from utils import ori_path, conf
from utils.website.core import EroUtils, DomainUtils, Req, Cookies, Previewer, build_proxy_transport
from utils.website.info import JmBookInfo, Episode


class JmUtils(EroUtils, DomainUtils, Req, Cookies, Previewer):
    name = "jm"
    proxy_policy = "direct"
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
        transport_kw = {k: kwargs.pop(k) for k in Req._TRANSPORT_PARAMS if k in kwargs}
        transport, trust_env = build_proxy_transport(
            cls.proxy_policy, _conf.proxies, is_async=is_async, **transport_kw
        )
        base_kwargs = {
            'headers': headers,
            'transport': transport,
            'trust_env': trust_env,
        }
        base_kwargs.update(kwargs)
        return client_class(**base_kwargs)

    @classmethod
    async def by_publish(cls):
        transport, trust_env = build_proxy_transport(
            cls.proxy_policy, conf.proxies, http2=True, retries=2
        )
        async with httpx.AsyncClient(
            headers=cls.publish_headers,
            transport=transport,
            trust_env=trust_env,
        ) as sess:
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
    def preview_client_config(cls, **context):
        domain = context.get("domain")
        if not domain:
            raise ValueError("preview domain is required for jm")
        return {
            'headers': {'Host': domain, **cls.headers, 'Referer': f'https://{domain}'}, 'verify': False,
        }

    @classmethod
    async def preview_search(cls, keyword, client, **kw):
        page = max(1, int(kw.pop("page", 1) or 1))
        kw.pop("cookies", None)
        domain = kw.pop("domain", None)
        if not domain:
            raise ValueError("preview domain is required for jm")
        url = f'https://{domain}/search/photos?main_tag=0&search_query={keyword}&page={page}'
        headers = {'Host': domain, **cls.headers, 'Referer': f'https://{domain}'}
        client.headers = headers
        resp = await client.get(url, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()

        def _parse(text, _domain):
            _html = Selector(text=text)
            targets = _html.xpath('//div[contains(@class,"thumb-overlay") and not(@class="thumb-overlay-guess_likes")]')
            with ThreadPoolExecutor() as executor:
                books = list(executor.map(cls.parse_search_item, targets))
            for idx, book in enumerate(books):
                book.idx = idx
                book.preview_url = f'https://{_domain}{book.preview_url}'
                book.url = f'https://{_domain}{book.url}'
            return books

        return await asyncio.to_thread(_parse, resp.text, domain)

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        kw.pop("cookies", None)
        domain = kw.pop("domain", None)
        if not domain:
            raise ValueError("preview domain is required for jm")
        headers = {'Host': domain, **cls.headers, 'Referer': f'https://{domain}'}
        resp = await client.get(book.preview_url, headers=headers, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()
        return await asyncio.to_thread(cls._parse_book_episodes, resp.text, book, domain)

    @classmethod
    def _parse_book_episodes(cls, resp_text, book, domain):
        parsed = cls.parse_book(resp_text)
        if parsed.episodes:
            for ep in parsed.episodes:
                ep.from_book = book
                if ep.url and not ep.url.startswith('http'):
                    ep.url = f'https://{domain}{ep.url}'
            return parsed.episodes
        return [Episode(from_book=book, idx=1, id=parsed.id, name=parsed.name or "全本")]

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
