import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import httpx
from scrapy import Selector

from assets import res
from variables import COOKIES_SUPPORT
from utils.website.core import Cookies, EroUtils, Previewer, Req
from utils.website.core.err import EhResp
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
        res.SPIDER.Completer.index: f"https://{domain}",
        res.SPIDER.Completer.popular: f"https://{domain}/popular",
    }
    book_url_regex = r"^https://exhentai\.org/g/[0-9a-z]+/[0-9a-z]+"

    browser_referer_mode = "domain_origin_slash"
    browser_cookie_set_enabled = True


class EHentaiParser(_EHentaiContract):
    @classmethod
    def parse_search_navigation(cls, resp_text):
        html_doc = Selector(text=resp_text)
        next_url = html_doc.xpath('//a[@id="unext"]/@href').get()
        prev_url = html_doc.xpath('//a[@id="uprev"]/@href').get()
        if not next_url:
            next_match = re.search(r'var nexturl\s*=\s*"([^"]*)"', resp_text)
            next_url = next_match.group(1) if next_match else None
        if not prev_url:
            prev_match = re.search(r'var prevurl\s*=\s*"([^"]*)"', resp_text)
            prev_url = prev_match.group(1) if prev_match else None
        return {
            "next": next_url or None,
            "prev": prev_url or None,
        }

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
        pages = next(filter(lambda _: "pages" in _, item_elem.xpath(".//div/text()").getall())).replace(" pages", "")
        url = target.xpath('./td[contains(@class, "glname")]/a/@href').get()
        btype = " ".join(map(str.strip, target.xpath('./td[contains(@class, "gl1c")]/div/text()').getall())) or None
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
        EhResp.catch(text)
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
        self._reset_preview_search_state()

    @classmethod
    def get_cli(cls, _conf, is_async=False, **kwargs):
        cli = super().get_cli(_conf, is_async=is_async, **kwargs)
        cli.headers = {**cls.book_hea, "Cookie": cls.to_str_(_conf.cookies.get(cls.name))}
        return cli

    def bind_preview_runtime(self, *, owner, site_config, preview_client: httpx.AsyncClient | None = None):
        super().bind_preview_runtime(owner=owner, site_config=site_config, preview_client=preview_client)
        self._reset_preview_search_state()
        return self

    def _reset_preview_search_state(self):
        self._preview_search_state = {
            "keyword": None,
            "base_url": None,
            "current_page": 0,
            "next_url": None,
            "page_urls": {},
        }

    def _resolve_preview_search_url(self, *, keyword: str, page: int, base_url: str) -> str:
        state = self._preview_search_state
        if page == 1 or state["keyword"] != keyword or state["base_url"] != base_url:
            self._reset_preview_search_state()
            state = self._preview_search_state
            state["keyword"] = keyword
            state["base_url"] = base_url
            state["page_urls"][1] = base_url
            return base_url
        cached_url = state["page_urls"].get(page)
        if cached_url:
            return cached_url
        if page == state["current_page"] + 1 and state["next_url"]:
            state["page_urls"][page] = state["next_url"]
            return state["next_url"]
        raise ValueError(
            f"ehentai preview search page {page} requires a cached page URL or sequential next-page navigation"
        )

    def test_index(self):
        try:
            resp = self.cli.get(self.index, follow_redirects=True, timeout=3.5)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return bool(resp.text)

    def build_search_url(self, key):
        return f"https://{self.domain}/?f_search={key}"

    async def preview_search(self, keyword: str, *, page: int = 1):
        owner = self._require_preview_owner()
        owner_type = type(owner)
        site_kw = self.preview_site_kwargs()
        page = max(1, int(page or 1))
        cookies = site_kw.get("cookies") or {}
        domain = site_kw.get("domain") or getattr(self, "domain", None) or owner_type.domain
        mappings = owner_type.merge_search_mappings(self.mappings, site_kw.get("custom_map"))
        if keyword in mappings:
            base_url = owner_type.normalize_mapping_url(domain, mappings[keyword])
        else:
            self.domain = domain
            base_url = self.build_search_url(keyword)
        url = self._resolve_preview_search_url(keyword=keyword, page=page, base_url=base_url)
        headers = {**self.book_hea, "Cookie": self.to_str_(cookies)}
        resp = await self.ensure_preview_client().get(url, headers=headers, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        navigation = owner.parser.parse_search_navigation(resp.text)
        self._preview_search_state.update(
            keyword=keyword,
            base_url=base_url,
            current_page=page,
            next_url=urljoin(str(resp.url), navigation["next"]) if navigation["next"] else None,
        )
        self._preview_search_state["page_urls"][page] = str(resp.url)
        return await asyncio.to_thread(owner.parser.parse_preview_books, resp.text)


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
