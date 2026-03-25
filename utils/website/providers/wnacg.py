import re
import asyncio
from concurrent.futures import ThreadPoolExecutor

from lxml import etree
from scrapy import Selector

from assets import res
from utils import ori_path
from utils.website.core import EroUtils, DomainUtils, Req, Previewer, ProviderContext
from utils.website.info import WnacgBookInfo


class WnacgUtils(EroUtils, DomainUtils, Req, Previewer):
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5',
    }
    book_hea = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
    }
    uuid_regex = re.compile(r"-(\d+)\.html$")
    cate_mappings = {"cate-5": "同人誌","cate-1": "同人誌 / 漢化","cate-12": "同人誌 / 日語","cate-16": "同人誌 / English","cate-2": "同人誌 / CG畫集","cate-37": "同人誌 / AI圖集","cate-22": "同人誌 / 3D漫畫","cate-3": "同人誌 / Cosplay","cate-6": "單行本","cate-9": "單行本 / 漢化","cate-13": "單行本 / 日語","cate-17": "單行本 / English","cate-7": "雜誌&短篇","cate-10": "雜誌&短篇 / 漢化","cate-14": "雜誌&短篇 / 日語","cate-18": "雜誌&短篇 / English","cate-19": "韓漫","cate-20": "韓漫 / 漢化","cate-21": "韓漫 / 其他",}
    search_url_head = "https://wnacg.com/search/?f=_all&s=create_time_DESC&syn=yes&q="
    mappings = {
        "更新": "https://wnacg.com/albums-index.html",
        "汉化": "https://wnacg.com/albums-index-cate-1.html",
    }
    turn_page_search = r"p=\d+"
    turn_page_info = (r"-page-\d+", "albums-index%s")

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

    @classmethod
    def preview_client_config(cls, context: ProviderContext):
        domain = cls._domain_from(context)
        hea = {'Host': domain, **cls.headers, 'Referer': f'https://{domain}'}
        return {'headers': hea, 'verify': False}

    @classmethod
    def _domain_from(cls, context: ProviderContext | None) -> str:
        if context and context.domain:
            return context.domain
        return cls.get_domain()

    @classmethod
    def _build_preview_search_request(
        cls,
        keyword: str,
        *,
        page: int = 1,
        context: ProviderContext,
    ):
        domain = cls._domain_from(context)
        headers = {"Host": domain, **cls.headers, "Referer": f"https://{domain}"}
        return cls.build_basic_search_request(
            keyword,
            page=page,
            domain=domain,
            search_url_head=f"https://{domain}/search/?f=_all&s=create_time_DESC&syn=yes&q=",
            turn_page_info=cls.turn_page_info,
            turn_page_search=cls.turn_page_search,
            mappings=cls.mappings,
            custom_map=context.custom_map,
            headers=headers,
            state={"domain": domain},
        )

    @classmethod
    def _parse_preview_books(cls, text, domain):
        _html = Selector(text=text)
        targets = _html.xpath('//li[contains(@class, "gallary_item")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(cls.parse_search_item, targets))
        for idx, book in enumerate(books, start=1):
            book.idx = idx
            book.preview_url = f'https://{domain}{book.preview_url}'
            book.url = f'https://{domain}{book.url}'
        return books

    @classmethod
    async def preview_search(
        cls,
        keyword,
        cli,
        *,
        page=1,
        context: ProviderContext,
    ):
        spec = cls._build_preview_search_request(keyword, page=page, context=context)
        resp = await cls.perform_preview_request(cli, spec)
        return await asyncio.to_thread(cls._parse_preview_books, resp.text, spec.state["domain"])

    @classmethod
    async def preview_fetch_episodes(cls, book, client, *, context: ProviderContext):  
        # FIXME fuck,谁让你转Episode的，追溯上下文的狗屎！wnacg,ehentai,hcomic都没有这狗屎需要转的
        # return [Episode(from_book=book, idx=1, name=book.name or "全本")]
        return [book]

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
