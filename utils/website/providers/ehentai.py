import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
from scrapy import Selector

from assets import res
from variables import COOKIES_SUPPORT
from utils.website.core import Cookies, EroUtils, Previewer, Req
from utils.website.info import EhBookInfo


class _EHentaiContract:
    name = "ehentai"
    login_url = "https://forums.e-hentai.org/index.php?act=Login"
    home_url = "https://e-hentai.org/home.php"
    domain = "exhentai.org"
    index = f"https://{domain}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": res.Vars.ua_accept_language,
        "Accept-Encoding": "gzip, deflate, br",
    }
    book_hea = headers
    uuid_regex = re.compile(r"/g/(\d+)/")
    cookies_field = COOKIES_SUPPORT[name]
    mappings = {
        res.EHentai.MAPPINGS_INDEX: f"https://{domain}",
        res.EHentai.MAPPINGS_POPULAR: f"https://{domain}/popular",
    }
    book_url_regex = r"^https://exhentai\.org/g/[0-9a-z]+/[0-9a-z]+"


class EHentaiParser(_EHentaiContract):
    @classmethod
    def parse_search_item(cls, target):
        def _parse_tags(tag_divs):
            artist = language = None
            tags = []
            for tag_div in tag_divs:
                title = tag_div.xpath("./@title").get()
                if not title or ":" not in title:
                    continue
                tag_type, tag_value = title.split(":", 1)
                if tag_type == "language" and tag_value != "translated":
                    language = tag_value
                elif tag_type == "artist":
                    artist = tag_value
                elif tag_type in ["character", "female", "parody", "male", "group"]:
                    tags.append(tag_value)
            return language, tags, artist

        item_elem = target.xpath('./td/div[@class="glthumb"]')
        pages = (
            next(filter(lambda _: "pages" in _, item_elem.xpath(".//div/text()").getall()))
            .replace(" pages", "")
        )
        url = target.xpath('./td[contains(@class, "glname")]/a/@href').get()
        btype = " ".join(
            map(str.strip, target.xpath('./td[contains(@class, "gl1c")]/div/text()').getall())
        ) or None
        language, tags, artist = _parse_tags(target.xpath('.//div[@class="gt"]'))
        return EhBookInfo(
            name=item_elem.xpath(".//img/@title").get(),
            preview_url=url,
            url=url,
            pages=int(pages),
            btype=btype,
            img_preview=(item_elem.xpath(".//img/@data-src") or item_elem.xpath(".//img/@src")).get(),
            lang=language,
            tags=tags,
            artist=artist,
        ).get_id(url)

    @classmethod
    def parse_search(cls, resp_text):
        html_doc = Selector(text=resp_text)
        targets = html_doc.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        with ThreadPoolExecutor() as executor:
            return list(executor.map(cls.parse_search_item, targets))

    @classmethod
    def parse_preview_books(cls, text):
        books = cls.parse_search(text)
        for idx, book in enumerate(books, start=1):
            book.idx = idx
        return books

    @classmethod
    def parse_book(cls, resp_text):
        html_doc = Selector(text=resp_text)
        script_string = html_doc.xpath('//script[contains(text(), "var base_url")]/text()').get()
        gid = re.search(r"gid = ([0-9a-z]+)", script_string).group(1)
        token = re.search(r"""token = "?([0-9a-z]+)""", script_string).group(1)
        tags_ = html_doc.xpath('//td[@class="tc" and text()="female:"]/following-sibling::td/div/a/@id').getall()
        author_ = html_doc.xpath('//div[contains(@id, "td_artist:")]/@id').getall()
        img_src_el = html_doc.xpath('//div[@id="gleft"]/div/div/@style').get()
        gdd_div_str = html_doc.xpath('//div[@id="gdd"]').get()
        public_date = re.search(r"\d{4}-\d{2}-\d{2}", gdd_div_str).group() if gdd_div_str else None
        pages = re.search(r">(\d+) pages<", gdd_div_str).group(1) if gdd_div_str else None
        btype = " ".join(map(str.strip, html_doc.xpath('//div[@id="gdc"]/div/text()').getall())) or None
        return EhBookInfo(
            id=gid,
            name=(html_doc.xpath('//h1[@id="gj"]/text()').get() or html_doc.xpath('//div[@id="gd2"]/h1/text()').get()),
            artist=author_[0].split(":")[-1] if author_ else None,
            url=f"/g/{gid}/{token}/",
            preview_url=f"{cls.index}g/{gid}/{token}/",
            tags=[tag.split(":")[-1] for tag in tags_],
            img_preview=re.search(r"url\((.*?)\)", img_src_el.replace("&quot;", "").replace('"', "")).group(1),
            btype=btype,
            public_date=public_date,
            pages=pages,
            episodes=[],
        )


class EHentaiReqer(_EHentaiContract, Req, Cookies):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        cli = super().get_cli(_conf, is_async=is_async, **kwargs)
        cli.headers = {**cls.book_hea, "Cookie": cls.to_str_(_conf.cookies.get(cls.name))}
        return cli

    def test_index(self):
        try:
            resp = self.cli.get(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return bool(resp.text)

    def build_search_url(self, key):
        return f"https://{self.domain}/?f_search={key}"


class EHentaiKits(_EHentaiContract, EroUtils, Cookies, Previewer):
    parser = EHentaiParser
    reqer_cls = EHentaiReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def display_meta(cls, *args, **kw) -> dict:
        return {"extra": f"<br>{res.EHentai.JUMP_TIP}"}

    @classmethod
    def preview_client_config(cls, **context):
        cookie_str = cls.to_str_(context.get("cookies") or {})
        return {
            "headers": {**cls.book_hea, "Cookie": cookie_str},
        }

    @classmethod
    async def preview_search(
        cls,
        keyword,
        client,
        **kw,
    ):
        page = max(1, int(kw.pop("page", 1) or 1))
        site_kw = cls.pop_site_kwargs(kw)
        cookies = site_kw["cookies"] or {}
        domain = site_kw["domain"] or cls.domain
        mappings = cls.merge_search_mappings(cls.mappings, site_kw["custom_map"])
        if keyword in mappings:
            url = cls.normalize_mapping_url(domain, mappings[keyword])
        else:
            url = f"https://{domain}/?f_search={keyword}"
        if page > 1:
            sep = "&" if urlparse(url).query else "?"
            url = f"{url}{sep}page={page - 1}"
        headers = {**cls.book_hea, "Cookie": cls.to_str_(cookies)}
        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()
        return await asyncio.to_thread(cls.parser.parse_preview_books, resp.text)
