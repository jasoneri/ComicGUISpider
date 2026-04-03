import re
import asyncio
import concurrent.futures
import httpx
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from lxml import etree
from scrapy import Selector

from assets import res
from utils import conf, get_loop, ori_path, temp_p
from utils.website.core import DomainUtils, EroUtils, Previewer, Req, build_proxy_transport
from utils.website.info import WnacgBookInfo


class _WnacgContract:
    name = "wnacg"
    cover_preload_via_http = False
    publish_domain = "wnacg01.link"
    publish_domain_old = ["wnacg.date", "wn01.link"]
    publish_url = f"https://{publish_domain}"
    status_publish = True
    publish_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5",
    }
    book_hea = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
    }
    uuid_regex = re.compile(r"-(\d+)\.html$")
    cate_mappings = {
        "cate-5": "同人誌",
        "cate-1": "同人誌 / 漢化",
        "cate-12": "同人誌 / 日語",
        "cate-16": "同人誌 / English",
        "cate-2": "同人誌 / CG畫集",
        "cate-37": "同人誌 / AI圖集",
        "cate-22": "同人誌 / 3D漫畫",
        "cate-3": "同人誌 / Cosplay",
        "cate-6": "單行本",
        "cate-9": "單行本 / 漢化",
        "cate-13": "單行本 / 日語",
        "cate-17": "單行本 / English",
        "cate-7": "雜誌&短篇",
        "cate-10": "雜誌&短篇 / 漢化",
        "cate-14": "雜誌&短篇 / 日語",
        "cate-18": "雜誌&短篇 / English",
        "cate-19": "韓漫",
        "cate-20": "韓漫 / 漢化",
        "cate-21": "韓漫 / 其他",
    }
    search_url_head = "https://wnacg.com/search/?f=_all&s=create_time_DESC&syn=yes&q="
    mappings = {
        "更新": "https://wnacg.com/albums-index.html",
        "汉化": "https://wnacg.com/albums-index-cate-1.html",
    }
    turn_page_search = r"p=\d+"
    turn_page_info = (r"-page-\d+", "albums-index%s")
    book_id_url = "https://www.wnacg02.cc/photos-index-aid-%s.html"
    book_url_regex = r"^https://(www\.)?wn.*?/photos-index-aid-\d+\.html$"


class WnacgParser(_WnacgContract, Previewer):
    @classmethod
    def extract_publish_domains(cls, html_text) -> list[str]:
        html_doc = etree.HTML(html_text)
        hrefs = html_doc.xpath('//div[@class="main"]//li[not(contains(.,"發佈頁") or contains(.,"发布页"))]/a/@href')
        publish_domain_old_str = "|".join(cls.publish_domain_old)
        match_regex = re.compile(f"google|{cls.publish_domain}|email|link|{publish_domain_old_str}")
        return list(map(lambda url: re.sub("https?://", "", url).strip("/"), filter(
            lambda href: not bool(match_regex.search(href)), hrefs
        )))

    @classmethod
    def normalize_preview_resource(
        cls,
        value: str | None,
        *,
        domain: str | None = None,
        default_scheme: str = "https",
    ) -> str | None:
        normalized = super().normalize_preview_resource(
            value,
            domain=domain,
            default_scheme=default_scheme,
        )
        if not normalized:
            return normalized
        parsed = urlparse(normalized)
        if parsed.scheme == "http" and "wnimg" in parsed.netloc.lower():
            return normalized.replace("http://", "https://", 1)
        return normalized

    @classmethod
    def parse_search_item(cls, target):
        tar_xpath = './div[contains(@class, "pic")]'
        item_elem = target.xpath(f"{tar_xpath}/a")
        pre_url = item_elem.xpath("./@href").get()
        page_text = target.xpath('.//div[contains(@class, "info_col")]/text()').get()
        cate = (target.xpath(f"{tar_xpath}/@class").get() or "").split(" ")[-1]
        public_date = (
            re.search(r"\d{4}-\d{2}-\d{2}", page_text).group()
            if page_text and bool(re.search(r"\d{4}-\d{2}-\d{2}", page_text))
            else None
        )
        return WnacgBookInfo(
            name=item_elem.xpath("./@title").get(),
            preview_url=pre_url,
            url=pre_url.replace("index", "gallery"),
            pages=re.search(r"(\d+)[張张]", page_text.strip()).group(1) if page_text else 0,
            btype=cls.cate_mappings.get(cate, ""),
            img_preview=cls.normalize_preview_resource(item_elem.xpath("./img/@src").get()),
            public_date=public_date,
        ).get_id(pre_url)

    @classmethod
    def parse_search(cls, resp_text, *, domain: str | None = None):
        domain = domain or WnacgUtils.get_domain()
        html_doc = Selector(text=resp_text)
        targets = html_doc.xpath('//li[contains(@class, "gallary_item")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(cls.parse_search_item, targets))
        for book in books:
            cls.normalize_preview_fields(book, domain=domain)
        return books

    @classmethod
    def parse_preview_books(cls, text, domain):
        html_doc = Selector(text=text)
        targets = html_doc.xpath('//li[contains(@class, "gallary_item")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(cls.parse_search_item, targets))
        for idx, book in enumerate(books, start=1):
            book.idx = idx
            cls.normalize_preview_fields(book, domain=domain)
        return books

    @classmethod
    def parse_book(cls, resp_text, *, domain: str | None = None):
        html_doc = Selector(text=resp_text)
        thumb_el = html_doc.xpath('//div[contains(@class, "uwthumb")]')[0]
        url = thumb_el.xpath("./a/@href").get().replace("slide", "gallery")
        info_el = html_doc.xpath('//div[contains(@class, "uwconn")]')[0]
        label_texts = info_el.xpath("./label/text()").getall()
        cate_hrefs = html_doc.xpath(
            '//div[contains(@class, "bread")]//a[contains(@href, "albums-index-cate-")]/@href'
        ).getall()
        btype = (
            cls.cate_mappings.get(f"cate-{match.group(1)}", "")
            if cate_hrefs and (match := re.search(r"cate-(\d+)", cate_hrefs[-1]))
            else None
        )
        date_text = html_doc.xpath('//div[@class="grid"]//li[1]//div[@class="info_col"]/text()').get()
        public_date = re.search(r"\d{4}-\d{2}-\d{2}", date_text).group() if date_text else None
        book = WnacgBookInfo(
            name=html_doc.xpath("//body/div/h2/text()").get(),
            url=url,
            preview_url=url.replace("gallery", "index"),
            tags=info_el.xpath('.//a[@class="tagshow"]/text()').getall(),
            img_preview=cls.normalize_preview_resource(thumb_el.xpath("./img/@src").get(), domain=domain),
            pages=re.search(r"\d+", next(filter(lambda text: "頁數" in text, label_texts))).group(0),
            btype=btype,
            public_date=public_date,
            episodes=[],
        ).get_id(url)
        if domain:
            cls.normalize_preview_fields(book, domain=domain)
        return book


class WnacgReqer(_WnacgContract, Req):
    def __init__(self, _conf):
        self.domain = None
        self.cli = self.get_cli(_conf)

    def build_search_url(self, key):
        self.domain = self.domain or WnacgUtils.get_domain()
        return f"https://{self.domain}/search/?f=_all&s=create_time_DESC&syn=yes&q={key}"


class WnacgUtils(_WnacgContract, EroUtils, DomainUtils, Previewer):
    parser = WnacgParser
    reqer_cls = WnacgReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    async def parse_publish_(cls, html_text):
        candidates = cls.parser.extract_publish_domains(html_text)
        hosts = await asyncio.gather(*[cls.test_aviable_domain(domain) for domain in candidates])
        for host in hosts:
            if host:
                return host
        cls.status_publish = False
        raise ConnectionError(
            res.SPIDER.DOMAINS_INVALID % (cls.publish_url, candidates, ori_path.joinpath(f"__temp/{cls.name}_domain.txt"))
        )

    @staticmethod
    def _is_redirect_challenge(html_text: str) -> bool:
        lowered = str(html_text or "").casefold()
        return (
            "<title>redirecting...</title>" in lowered
            or "router.parklogic.com" in lowered
            or "adblockingdetected" in lowered
        )

    @classmethod
    def _probe_search_url(cls, domain: str) -> str:
        return f"https://{domain}/search/?f=_all&s=create_time_DESC&syn=yes&q=%E3%83%86%E3%82%B9%E3%83%88"

    @classmethod
    async def test_aviable_domain(cls, domain):
        url = cls._probe_search_url(domain)
        try:
            transport, trust_env = build_proxy_transport(
                cls.proxy_policy,
                conf.proxies,
                retries=1,
                verify=False,
            )
            async with httpx.AsyncClient(
                headers=cls.build_site_headers(domain, cls.headers, referer_url=cls.preview_origin(domain)),
                transport=transport,
                trust_env=trust_env,
                follow_redirects=True,
            ) as cli:
                resp = await cli.get(url, timeout=6)
                resp.raise_for_status()
                title = re.search(r"<title>(.*?)</title>", resp.text, re.I | re.S)
                if cls._is_redirect_challenge(resp.text):
                    return None
                if title and "紳士漫畫" in title.group(1):
                    return resp.url.host
        except Exception:
            return None
        return None

    @classmethod
    def _validate_cached_domain(cls, domain: str) -> bool:
        loop = get_loop()
        try:
            return bool(loop.run_until_complete(cls.test_aviable_domain(domain)))
        finally:
            loop.close()

    @classmethod
    def get_domain(cls):
        from utils.website.core import Cache

        cls.cachef = getattr(cls, "cachef", Cache(f"{cls.name}_domain.txt"))
        cached = cls.cachef.run(lambda: None, 168)
        if isinstance(cached, str) and cached.strip():
            try:
                asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    if executor.submit(cls._validate_cached_domain, cached.strip()).result():
                        return cached.strip()
            except RuntimeError:
                if cls._validate_cached_domain(cached.strip()):
                    return cached.strip()
            temp_p.joinpath(f"{cls.name}_domain.txt").unlink(missing_ok=True)
            if cls.cachef is not None:
                cls.cachef.flag = "new"
                cls.cachef.val = None
        return super().get_domain()

    @classmethod
    def normalize_preview_resource(
        cls,
        value: str | None,
        *,
        domain: str | None = None,
        default_scheme: str = "https",
    ) -> str | None:
        return cls.parser.normalize_preview_resource(value, domain=domain,
            default_scheme=default_scheme,
        )

    @classmethod
    def preview_client_config(cls, **context):
        domain = context.get("domain") or cls.get_domain()
        return {
            "headers": cls.build_site_headers(domain, cls.headers,
                referer_url=cls.preview_origin(domain),
            ),
        }

    @classmethod
    def preview_transport_config(cls) -> dict:
        return {"verify": False, "retries": 2}

    @classmethod
    async def preview_search(cls,keyword,cli,**kw):
        page = max(1, int(kw.pop("page", 1) or 1))
        domain = kw.pop("domain", None) or cls.get_domain()
        spec = cls.build_basic_search_request(
            keyword,
            page=page,
            domain=domain,
            search_url_head=f"https://{domain}/search/?f=_all&s=create_time_DESC&syn=yes&q=",
            turn_page_info=cls.turn_page_info,
            turn_page_search=cls.turn_page_search,
            mappings=cls.mappings,
            custom_map=kw.pop("custom_map", None),
            headers=cls.build_site_headers(
                domain, cls.headers, referer_url=cls.preview_origin(domain),
            ),
            state={"domain": domain},
        )
        resp = await cls.perform_preview_request(cli, spec)
        return await asyncio.to_thread(cls.parser.parse_preview_books, resp.text, spec.state["domain"])

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        return [book]
