import asyncio
from collections import OrderedDict

import httpx
from scrapy import Selector

from utils.website.core import Utils, Req, MangaPreview
from utils.website.info import MangabzBookInfo, Episode
from utils.website.req_schema import MbSearchBody, mb_curr_time_format


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
