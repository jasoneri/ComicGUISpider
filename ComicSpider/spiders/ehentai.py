# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from scrapy import Request

from utils import conf, re
from utils.processed_class import Url
from utils.website import EHentaiKits as EK
from assets import res
from .basecomicspider import BaseComicSpider3
from ..items import ComicspiderItem

domain = "exhentai.org"


class EHentaiSpider(BaseComicSpider3):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.ComicDlProxyMiddleware': 5,
                                                  'ComicSpider.middlewares.UAMiddleware': 6},
                       "COOKIES_ENABLED": False}
    hath_image_download_timeout = 20
    hath_image_retry_times = 1
    name = 'ehentai'
    num_of_row = 25
    domain = domain
    search_url_head = f'https://{domain}/?f_search='
    mappings = {
        res.EHentai.MAPPINGS_INDEX: f'https://{domain}',
        res.EHentai.MAPPINGS_POPULAR: f'https://{domain}/popular'
    }
    frame_book_format = ['title', 'book_pages', 'preview_url']  # , 'book_idx']
    turn_page_info = (r"page=\d+",)
    book_id_url = f'https://{domain}/g/%s'

    @property
    def ua(self):
        return {**EK.headers, "cookie": EK.to_str_(conf.cookies.get(self.name))}

    def image_request_meta(self, *, url, item=None):
        hostname = (urlparse(url).hostname or "").lower()
        if not hostname.endswith("hath.network"):
            return {}
        return {
            "download_timeout": self.hath_image_download_timeout,
            "max_retry_times": self.hath_image_retry_times,
        }

    def frame_book(self, response):
        frame_results = {}
        targets = response.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(self.site.parser.parse_search_item, targets))
        for x, book in enumerate(books):
            book.idx = x + 1
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, extra=f"<br>{res.EHentai.JUMP_TIP}", url=response.url)

    def parse_section(self, response):
        if not response.meta.get('sec_page'):
            title_gj = response.xpath('//h1[@id="gj"]/text()')
            if title_gj:
                response.meta['book'].name = title_gj.get()
            else:
                titles = response.xpath("//h1/text()").getall()
                if response.meta['book'].name in titles and len(titles) > 1:
                    titles.remove(response.meta['book'].name)
                    response.meta['book'].name = titles[0]
        yield from super(EHentaiSpider, self).parse_section(response)

    def frame_section(self, response):
        next_flag = None
        frame_results = response.meta.get('frame_results', {})
        sec_page = response.meta.get('sec_page', 1)
        this_book_pages = response.meta.get('book_pages') or re.search(r">(\d+) pages<", response.text).group(1)
        targets = response.xpath('//div[@id="gdt"]/a')
        first_idx = max(frame_results.keys()) if frame_results else 0
        for x, target in enumerate(targets):
            idx = first_idx + x
            url = target.xpath('./@href').get()
            frame_results[idx + 1] = url
        if int(max(frame_results.keys())) < int(this_book_pages):
            if "/?p=" in response.url:
                next_flag = re.sub(r'\?p=\d+', rf'?p={sec_page}', response.url)
            else:
                next_flag = response.url.strip('/') + f"/?p={sec_page}"  # ... book-page-index start with 0，not 1
        return frame_results, next_flag

    def parse_fin_page(self, response):
        url = response.xpath('//img[@id="img"]/@src').get() or ""
        page = response.meta.get('page')
        book = response.meta.get('book')
        if url.endswith('509.gif'):
            self.log(f'[509] https://ehgt.org/g/509.gif: [page-{page}] of [{book.name}]', level=30)
        else:
            item = ComicspiderItem()
            item.update(**book.get_group_infos())
            item['page'] = str(page)
            item['image_urls'] = [url]
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item
