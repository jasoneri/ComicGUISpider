import asyncio
import hashlib
import math
import re
import typing as t
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.parse import urlencode

import httpx
from PIL import Image
from lxml import etree
from scrapy import Selector

from assets import res
from utils import conf, convert_punctuation, ori_path
from utils.config.qc import cgs_cfg
from utils.network.doh import build_http_transport
from utils.website.core import Cookies, DomainUtils, EroUtils, Previewer, Req
from utils.website.info import Episode, JmBookInfo
from variables import COOKIES_SUPPORT


class _JmContract:
    name = "jm"
    proxy_policy = "direct"
    forever_url = "https://jm365.work/3YeBdF"
    publish_url = "https://jm365.work/mJ8rWd"
    publish_url2 = "https://jm-3x.cc/mJ8rWd"
    status_forever = True
    status_publish = True
    cookies_field = COOKIES_SUPPORT[name]
    publish_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }
    book_hea = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br",
    }
    uuid_regex = re.compile(r"[^/]+/(\d+)")
    search_url_head = "https://18comic-zzz.xyz/search/photos?main_tag=0&search_query="
    mappings = {}
    time_regex = re.compile(r".*?([日周月总])")
    kind_regex = re.compile(r".*?(更新|点击|评分|评论|收藏)")
    expand_map: t.Dict[str, dict] = {
        "日": {"t": "t"},
        "周": {"t": "w"},
        "月": {"t": "m"},
        "总": {"t": "a"},
        "更新": {"o": "mr"},
        "点击": {"o": "mv"},
        "评分": {"o": "tr"},
        "评论": {"o": "md"},
        "收藏": {"o": "tf"},
    }
    turn_page_info = (r"page=\d+",)
    book_url_regex = r"^https://.*?(18|jm).*?/album/\d+"

    class JmImage:
        regex = re.compile(r"(\d+)/(\d+)")
        epsId = None
        scramble_id = None

        def convert_img(self, img_content: bytes) -> Image:
            self.epsId = int(self.epsId)

            def get_num():
                def _get_num(limit: int):
                    string = str(self.epsId) + self.scramble_id
                    string = string.encode()
                    string = hashlib.md5(string).hexdigest()
                    ret = ord(string[-1])
                    ret %= limit
                    return ret * 2 + 2

                if self.epsId < 220980:
                    return 0
                if self.epsId < 268850:
                    return 10
                if self.epsId > 421926:
                    return _get_num(8)
                return _get_num(10)

            num = get_num()
            img = BytesIO(img_content)
            src_img = Image.open(img)
            if not num:
                return src_img
            size = (width, height) = src_img.size
            des_img = Image.new(src_img.mode, size)
            rem = height % num
            copy_height = math.floor(height / num)
            block = []
            total_h = 0
            for i in range(num):
                h = copy_height * (i + 1)
                if i == num - 1:
                    h += rem
                block.append((total_h, h))
                total_h = h
            h = 0
            for start, end in reversed(block):
                co_h = end - start
                temp_img = src_img.crop((0, start, width, end))
                des_img.paste(temp_img, (0, h, width, h + co_h))
                h += co_h
            src_img.close()
            del img
            return des_img

        @classmethod
        def by_url(cls, url):
            obj = cls()
            obj.epsId, obj.scramble_id = cls.regex.search(url).groups()
            return obj


class JmParser(_JmContract, Previewer):
    @classmethod
    async def parse_publish_(cls, html_text):
        html_doc = etree.HTML(html_text)
        ps = html_doc.xpath('//div[@class="wrap"]//p')
        domains = []

        def get_text(p):
            return "".join(p.xpath(".//text()"))

        idx_start = next((i for i, p in enumerate(ps) if "內地" in get_text(p)), None)
        idx_end = next((i for i, p in enumerate(ps) if get_text(p).strip().lower().startswith("app")), len(ps))
        if idx_start is not None:
            if idx_end <= idx_start:
                idx_end = len(ps)
            for p in ps[idx_start:idx_end]:
                for raw_domain in p.xpath("./following-sibling::div//text()"):
                    domain = raw_domain.strip()
                    if "." in domain and not bool(re.search(r"discord|\.work|@|＠|<", domain)):
                        domains.append(re.sub(r"^https?://", "", domain).split("/", 1)[0])
        hosts = await asyncio.gather(*[JmUtils.test_aviable_domain(domain) for domain in domains])
        for host in hosts:
            if host:
                return host
        JmUtils.status_publish = False
        raise ConnectionError(
            res.SPIDER.DOMAINS_INVALID % (cls.publish_url, domains, str(ori_path.joinpath(f"__temp/{cls.name}_domain.txt")))
        )

    @classmethod
    def parse_search_item(cls, target):
        parent_div = target.xpath("./parent::*/parent::div")
        pre_url = "/".join(target.xpath("../@href | ./a/@href").get().split("/")[:-1])
        img_preview = target.xpath("./a/img/@src | ./img/@src").get()
        if (img_preview or "").endswith("blank.jpg"):
            img_preview = target.xpath("./a/img/@data-original | ./img/@data-original").get()
        likes = target.xpath('.//span[contains(@id,"albim_likes")]/text()').get()
        btypes = target.xpath('.//div[@class="category-icon"]/div/text()').getall()
        artist = parent_div.xpath('.//div//a[contains(@href, "main_tag=2")]/text()').get()
        tags = parent_div.xpath('.//div[contains(@class, "tags")]//a[@class="tag"]/text()').getall()
        return JmBookInfo(
            name=target.xpath('.//img/@title').get().strip().replace("\n", ""),
            preview_url=pre_url,
            url=pre_url.replace("album", "photo"),
            btype=" ".join(map(str.strip, btypes)).strip(),
            img_preview=cls.normalize_preview_resource(img_preview),
            artist=(artist or "").strip() or None,
            tags=tags,
            likes=likes.strip() if likes else 0,
        ).get_id(pre_url)

    @classmethod
    def parse_search(cls, resp_text, *, domain: str | None = None):
        domain = domain or JmUtils.get_domain()
        html_doc = Selector(text=resp_text)
        targets = html_doc.xpath('//div[contains(@class,"thumb-overlay") and not(@class="thumb-overlay-guess_likes")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(cls.parse_search_item, targets))
        for book in books:
            cls.normalize_preview_fields(book, domain=domain)
        return books

    @classmethod
    def parse_preview_books(cls, text, domain):
        html_doc = Selector(text=text)
        targets = html_doc.xpath('//div[contains(@class,"thumb-overlay") and not(@class="thumb-overlay-guess_likes")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(cls.parse_search_item, targets))
        for idx, book in enumerate(books, start=1):
            book.idx = idx
            cls.normalize_preview_fields(book, domain=domain)
        return books

    @classmethod
    def parse_preview_search_response(cls, resp_text, domain):
        if "album_photo_cover" in (resp_text or "") and bool(re.search(r"var aid = (\d+);", resp_text or "")):
            book = cls.parse_book(resp_text, domain=domain)
            book.idx = 1
            return [book]
        return cls.parse_preview_books(resp_text, domain)

    @classmethod
    def parse_book(cls, resp_text, *, domain: str | None = None):
        if "Just a moment..." in resp_text[:100]:
            raise ValueError("触发5秒盾")
        html_doc = Selector(text=resp_text)
        cover_el = html_doc.xpath('//div[@id="album_photo_cover"]')[-1]
        info_el = cover_el.xpath("./following-sibling::div")[0]
        pages_text = info_el.xpath('./div/div[contains(text(), "頁數") or contains(text(), "页数")]/text()').get()
        jm_id = re.search(r"var aid = (\d+);", resp_text).group(1)
        epa_els = html_doc.xpath('(//div[@class="episode"])[last()]/ul/a')
        public_date = info_el.xpath('.//span[@itemprop="datePublished"][contains(text(), "上架日期")]/@content').get()
        book = JmBookInfo(
            name=html_doc.xpath("//h1/text()").get(),
            artist=(info_el.xpath('.//span[@data-type="author"]/a/text()').getall() or [None])[-1],
            id=jm_id,
            preview_url=f"/album/{jm_id}",
            url=f"/photo/{jm_id}",
            tags=info_el.xpath('.//span[@data-type="tags"]/a/text()').getall(),
            img_preview=cls.normalize_preview_resource(
                cover_el.xpath('.//div[@class="thumb-overlay"]/img[contains(@class,"img-responsive")]/@src').get(),
                domain=domain,
            ),
            pages=re.search(r"\d+", pages_text).group(0),
            public_date=public_date,
        )
        book.episodes = []
        for epa_el in epa_els:
            title = epa_el.xpath(".//h3/text()[normalize-space()]").get().strip()
            episode = Episode(
                from_book=book,
                id=epa_el.xpath("./@data-album").get(),
                idx=int(epa_el.xpath("./@data-index").get()) + 1,
                url=f"/photo/{epa_el.xpath('./@data-album').get()}",
                name=re.split(r"\s+", title)[0],
            )
            book.episodes.append(episode)
        if domain:
            cls.normalize_preview_fields(book, domain=domain)
            for episode in book.episodes:
                cls.normalize_preview_fields(episode, domain=domain, attrs=("url",))
        return book

    @classmethod
    def parse_book_episodes(cls, resp_text, book, domain):
        parsed = cls.parse_book(resp_text, domain=domain)
        cls.merge_book_detail(book, parsed, domain)
        if parsed.episodes:
            for episode in parsed.episodes:
                episode.from_book = book
                if not episode.url and episode.id:
                    episode.url = f"/photo/{episode.id}"
                cls.normalize_preview_fields(episode, domain=domain, attrs=("url",))
            return parsed.episodes
        return []

    @classmethod
    def merge_book_detail(cls, book, parsed, domain):
        for attr in ("name", "artist", "public_date", "pages", "btype", "likes"):
            value = getattr(parsed, attr, None)
            if value is not None:
                setattr(book, attr, value)
        if parsed.tags:
            book.tags = parsed.tags
        if parsed.img_preview:
            book.img_preview = parsed.img_preview
        if parsed.preview_url and not getattr(book, "preview_url", None):
            book.preview_url = parsed.preview_url
        if parsed.url and not getattr(book, "url", None):
            book.url = parsed.url
        cls.normalize_preview_fields(book, domain=domain)

    @classmethod
    def parse_page_urls_from_html(cls, resp_text):
        html_doc = Selector(text=resp_text)
        urls = []
        for target in html_doc.xpath(".//img[contains(@id,'album_photo_')]"):
            img_url = target.xpath("./@data-original").get() or target.xpath("./@src").get()
            if not img_url or img_url.endswith("blank.jpg"):
                continue
            urls.append(img_url)
        return urls


class JmReqer(_JmContract, Req, Cookies, Previewer):
    def __init__(self, _conf):
        self.domain = None
        self.cli = self.get_cli(_conf)

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        client_class = httpx.AsyncClient if is_async else httpx.Client
        domain = JmUtils.get_domain()
        headers = {**cls.book_hea, "Referer": f"https://{domain}"}
        transport_kw = {k: kwargs.pop(k) for k in Req._TRANSPORT_PARAMS if k in kwargs}
        transport, trust_env = build_http_transport(
            cls.proxy_policy,
            _conf.proxies,
            doh_url=getattr(_conf, "doh_url", ""),
            is_async=is_async,
            **transport_kw,
        )
        base_kwargs = {
            "headers": headers,
            "transport": transport,
            "trust_env": trust_env,
        }
        base_kwargs.update(kwargs)
        return client_class(**base_kwargs)

    def build_search_url(self, key):
        self.domain = self.domain or JmUtils.get_domain()
        return f"https://{self.domain}/search/photos?main_tag=0&search_query={key}"

    @classmethod
    def preview_headers(cls, domain: str, cookies: dict | None = None) -> dict[str, str]:
        return cls.build_site_headers(
            domain,
            cls.headers,
            referer_url=cls.preview_origin(domain),
            cookies=cookies,
            cookie_serializer=cls.to_str_,
        )

    @classmethod
    def build_preview_search_url(
        cls,
        keyword: str,
        *,
        domain: str,
        custom_map: dict | None = None,
        page: int = 1,
    ) -> str:
        keyword = convert_punctuation(keyword).replace(" ", "")
        mappings = cls.merge_search_mappings(cls.mappings, custom_map)
        if keyword in mappings:
            url = cls.normalize_mapping_url(domain, mappings[keyword])
        else:
            time_match = cls.time_regex.search(keyword)
            kind_match = cls.kind_regex.search(keyword)
            if not kind_match:
                url = f"https://{domain}/search/photos?main_tag=0&search_query={keyword}"
            else:
                time_key = time_match.group(1) if time_match else "周"
                kind_key = kind_match.group(1) if kind_match else "点击"
                params = {**cls.expand_map[time_key], **cls.expand_map[kind_key]}
                url = f"https://{domain}/albums?{urlencode(params)}"
                if len(keyword) > 4:
                    url += keyword[4:]
        return cls.build_page_url(url, page, cls.turn_page_info)


class JmUtils(_JmContract, EroUtils, DomainUtils, Cookies, Previewer):
    parser = JmParser
    reqer_cls = JmReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    async def by_publish(cls):
        transport, trust_env = build_http_transport(
            cls.proxy_policy,
            conf.proxies,
            doh_url=cgs_cfg.get_doh_url(),
            is_async=True,
            http2=True,
            retries=2,
        )
        async with httpx.AsyncClient(
            headers=cls.publish_headers,
            transport=transport,
            trust_env=trust_env,
        ) as sess:
            resp = await sess.get(cls.publish_url2)
            error = None
            while True:
                try:
                    if str(resp.status_code).startswith("3") and resp.headers.get("location"):
                        resp = await sess.get(resp.headers.get("location"))
                    elif str(resp.status_code).startswith("2"):
                        return await cls.parse_publish(resp.text)
                except Exception as exc:
                    error = exc
                    break
            cls.status_publish = False
            raise error or ConnectionError(
                res.SPIDER.PUBLISH_INVALID % (cls.publish_url, str(ori_path.joinpath(f"__temp/{cls.name}_domain.txt")))
            )

    @classmethod
    async def parse_publish_(cls, html_text):
        return await cls.parser.parse_publish_(html_text)

    @classmethod
    def preview_client_config(cls, **context):
        domain = context.get("domain") or cls.get_domain()
        if not domain:
            raise ValueError("preview domain is required for jm")
        return {"headers": cls.reqer_cls.preview_headers(domain, context.get("cookies"))}

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"verify": False}

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        **kw,
    ):
        page = max(1, int(kw.pop("page", 1) or 1))
        site_kw = cls.pop_site_kwargs(kw)
        domain = site_kw["domain"] or cls.get_domain()
        if not domain:
            raise ValueError("preview domain is required for jm")
        headers = cls.reqer_cls.preview_headers(domain, site_kw["cookies"])
        url = cls.reqer_cls.build_preview_search_url(
            keyword,
            domain=domain,
            custom_map=site_kw["custom_map"],
            page=page,
        )
        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()
        return await asyncio.to_thread(cls.parser.parse_preview_search_response, resp.text, domain)

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        domain = kw.pop("domain", None) or cls.get_domain()
        if not domain:
            raise ValueError("preview domain is required for jm")
        headers = cls.reqer_cls.preview_headers(domain, kw.pop("cookies", None))
        resp = await client.get(book.preview_url, headers=headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        return await asyncio.to_thread(cls.parser.parse_book_episodes, resp.text, book, domain)

    @classmethod
    async def preview_fetch_pages(cls, item, client, **kw):
        if isinstance(item, JmBookInfo):
            return await item.preview_fetch_pages(client, **kw)
        domain = kw.pop("domain", None) or cls.get_domain()
        if not domain:
            raise ValueError("preview domain is required for jm")
        headers = cls.reqer_cls.preview_headers(domain, kw.pop("cookies", None))
        target_url = cls.normalize_preview_resource(
            item.url or (f"/photo/{item.id}" if item.id else None),
            domain=domain,
        )
        if not target_url:
            raise ValueError("jm episode url is required for preview_fetch_pages")
        resp = await client.get(target_url, headers=headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        urls = await asyncio.to_thread(cls.parser.parse_page_urls_from_html, resp.text)
        item.url = str(resp.url)
        item.pages = len(urls)
        return urls


async def _jm_book_preview_fetch_pages(self, client, **kw):
    domain = kw.pop("domain", None) or JmUtils.get_domain()
    if not domain:
        raise ValueError("preview domain is required for jm")
    headers = JmUtils.reqer_cls.preview_headers(domain, kw.pop("cookies", None))
    target_url = JmUtils.normalize_preview_resource(self.url or self.preview_url, domain=domain)
    if not target_url:
        raise ValueError("jm book url is required for preview_fetch_pages")
    resp = await client.get(target_url, headers=headers, follow_redirects=True, timeout=12)
    resp.raise_for_status()
    urls = await asyncio.to_thread(JmUtils.parser.parse_page_urls_from_html, resp.text)
    self.url = str(resp.url)
    self.pages = len(urls)
    return urls


JmBookInfo.preview_fetch_pages = _jm_book_preview_fetch_pages
