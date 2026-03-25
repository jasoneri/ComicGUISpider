import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
from scrapy import Selector

from assets import res
from variables import COOKIES_SUPPORT
from utils import conf
from utils.website.core import EroUtils, Req, Cookies, Previewer, PreviewRequestSpec, ProviderContext
from utils.website.info import EhBookInfo


class EHentaiKits(EroUtils, Req, Cookies, Previewer):
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
    mappings = {
        res.EHentai.MAPPINGS_INDEX: f"https://{domain}",
        res.EHentai.MAPPINGS_POPULAR: f"https://{domain}/popular",
    }

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

    @classmethod
    def display_meta(cls, *args, **kw) -> dict:
        return {'extra': f"<br>{res.EHentai.JUMP_TIP}",}

    @classmethod
    def preview_client_config(cls, context: ProviderContext):
        if not context.cookies:
            raise ValueError("preview cookies are required for ehentai")
        cookie_str = cls.to_str_(context.cookies)
        return {
            'headers': {**cls.book_hea, 'Cookie': cookie_str},
        }

    @classmethod
    def _build_preview_search_request(
        cls,
        keyword: str,
        *,
        page: int = 1,
        context: ProviderContext,
    ) -> PreviewRequestSpec:
        if not context.cookies:
            raise ValueError("preview cookies are required for ehentai")
        domain = context.domain or cls.domain
        mappings = cls.merge_search_mappings(cls.mappings, context.custom_map)
        if keyword in mappings:
            url = cls.normalize_mapping_url(domain, mappings[keyword])
        else:
            url = f"https://{domain}/?f_search={keyword}"
        page = max(1, int(page or 1))
        if page > 1:
            sep = "&" if urlparse(url).query else "?"
            url = f"{url}{sep}page={page - 1}"
        headers = {**cls.book_hea, "Cookie": cls.to_str_(context.cookies)}
        return PreviewRequestSpec(url=url, headers=headers)

    @classmethod
    def _parse_preview_books(cls, text):
        _html = Selector(text=text)
        targets = _html.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(cls.parse_search_item, targets))
        for idx, book in enumerate(books, start=1):
            book.idx = idx
        return books

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        *,
        page=1,
        context: ProviderContext,
    ):
        spec = cls._build_preview_search_request(keyword, page=page, context=context)
        resp = await cls.perform_preview_request(client, spec)
        return await asyncio.to_thread(cls._parse_preview_books, resp.text)

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
