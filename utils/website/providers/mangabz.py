import asyncio
import re
from collections import OrderedDict

import httpx
from scrapy import Selector

from utils.website.core import Previewer, Req, Utils
from utils.website.info import Episode, MangabzBookInfo
from utils.website.schema import MbBody, MbSearchBody, mb_curr_time_format


class _MangabzContract:
    name = "mangabz"
    proxy_policy = "proxy"
    domain = "www.mangabz.com"
    index = "https://www.mangabz.com"
    search_url_head = f"https://{domain}/pager.ashx"
    mappings = {
        "更新": ["manga-list-0-0-2", "2"],
        "人气": ["manga-list", "10"],
    }
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
        "TE": "trailers",
    }
    book_hea = ua
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
        "TE": "trailers",
    }


class MangabzParser(_MangabzContract):
    @staticmethod
    def parse_book_item(target, rendering_map, render_keys, idx, domain):
        rendered = OrderedDict()
        for attr_name, path in rendering_map.items():
            rendered[attr_name] = ",".join(map(lambda value: str(value.value), path.find(target))).strip()
        url = f"https://{domain}/{rendered.pop('book_path').strip('/')}/"
        book = MangabzBookInfo(idx=idx, render_keys=render_keys, url=url, preview_url=url)
        for key in render_keys:
            setattr(book, key, rendered.get(key))
        return book

    @staticmethod
    def parse_ep_item(target, book, domain, idx):
        return Episode(
            from_book=book,
            idx=idx,
            url=f"https://{domain}{target.xpath('./@href').get()}",
            name="".join(target.xpath("./text()").get()).strip(),
        )

    @classmethod
    def parse_episodes(cls, sel, book, domain):
        targets = list(reversed(sel.xpath('//div[@class="detail-list-item"]/a')))
        return [cls.parse_ep_item(target, book, domain, idx + 1) for idx, target in enumerate(targets)]

    @classmethod
    def parse_search_targets(cls, json_data, body, *, domain):
        rendering_map = body.rendering_map()
        render_keys = body.print_head[1:]
        books = []
        for idx, target in enumerate(json_data, start=1):
            book = cls.parse_book_item(target, rendering_map, render_keys, idx, domain)
            book.img_preview = target.get("Pic")
            books.append(book)
        return books

    @staticmethod
    def parse_page_urls_from_html(html_text: str) -> list[str]:
        from utils.processed_class import execute_js

        sel = Selector(text=html_text)
        js = sel.xpath('//script[@type="text/javascript"]/text()').getall()
        target_js = next(filter(lambda text: text.strip().startswith("eval"), js), None)
        if not target_js:
            raise ValueError("mangabz image eval script not found")
        real_js = execute_js(
            r"""function run(code){var ret="";eval('ret = '+code.replace(/^;*?\s*(window(\.|\[(["'])))?eval(\3\])?/,
            function ($0) {return 'String';}));   return ret }""",
            "run",
            target_js,
        )
        img_list_match = re.search(r"\[(.*?)]", real_js)
        if not img_list_match:
            raise ValueError("mangabz image list script not found")
        img_list = img_list_match.group(1)
        return [re.sub(r"""['"]""", "", item) for item in re.split(", ?", img_list)]


class MangabzReqer(_MangabzContract, Req):
    def __init__(self, _conf):
        self.cli = self.get_cli(_conf)

    @classmethod
    def build_search_request(
        cls,
        keyword: str,
        *,
        domain: str = None,
        custom_map: dict | None = None,
        page: int = 1,
    ):
        domain = domain or cls.domain
        keyword = keyword.strip()
        mappings = Previewer.merge_search_mappings(cls.mappings, custom_map)
        if keyword in mappings:
            search_start_path, body_sort = mappings[keyword]
            url = f"https://{domain}/{search_start_path}/mangabz.ashx?d={mb_curr_time_format()}"
            body = MbBody()
            body.update(sort=body_sort)
        else:
            url = f"https://{domain}/pager.ashx?d={mb_curr_time_format()}"
            body = MbSearchBody(title=keyword)
        body.dic[body.page_index_field] = str(max(1, int(page or 1)))
        headers = {**cls.ua, "Content-Type": "application/x-www-form-urlencoded"}
        return url, body, headers

    def test_index(self):
        try:
            resp = self.cli.head(
                self.index, follow_redirects=True, timeout=3.5, 
                headers={ "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1" },
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True


class MangabzUtils(_MangabzContract, Utils, Previewer):
    parser = MangabzParser
    reqer_cls = MangabzReqer

    def __init__(self, _conf):
        self.reqer = self.reqer_cls(_conf)
        self.parser = self.__class__.parser

    @classmethod
    def preview_client_config(cls, **context):
        return {
            "headers": cls.ua,
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
        url, body, headers = cls.reqer_cls.build_search_request(
            keyword,
            domain=site_kw["domain"] or cls.domain,
            custom_map=site_kw["custom_map"],
            page=page,
        )
        resp = await client.post(url, data=dict(body.dic), headers=headers, follow_redirects=True, timeout=12, **kw)
        resp.raise_for_status()
        return await asyncio.to_thread(
            cls.parser.parse_search_targets,
            resp.json(),
            body,
            domain=site_kw["domain"] or cls.domain,
        )

    @classmethod
    async def preview_fetch_episodes(cls, book, client, **kw):
        resp = await client.get(book.url, headers=cls.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        domain = kw.pop("domain", None) or cls.domain

        def parse_episodes(resp_text, parsed_book, parsed_domain):
            return cls.parser.parse_episodes(Selector(text=resp_text), parsed_book, parsed_domain)

        return await asyncio.to_thread(parse_episodes, resp.text, book, domain)

    @classmethod
    async def preview_fetch_pages(cls, episode, client, **kw) -> list[str]:
        resp = await client.get(episode.url, headers=cls.ua, follow_redirects=True, timeout=12)
        resp.raise_for_status()
        urls = await asyncio.to_thread(cls.parser.parse_page_urls_from_html, resp.text)
        episode.pages = len(urls)
        return urls
