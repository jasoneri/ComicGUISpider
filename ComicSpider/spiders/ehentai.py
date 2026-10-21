# -*- coding: utf-8 -*-
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from scrapy import Request

from utils import conf, re, PresetHtmlEl
from utils.processed_class import Url
from utils.website.providers.ehentai import EHentaiKits as EK
from assets import res
from .basecomicspider import BaseComicSpider3
from ..items import ComicspiderItem

domain = "exhentai.org"


class EHentaiSpider(BaseComicSpider3):
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.ComicDlProxyMiddleware': 5,
                                   'ComicSpider.middlewares.UAMiddleware': 6},
        "COOKIES_ENABLED": False,
        "ITEM_PIPELINES": {"ComicSpider.pipelines.EHentaiComicPipeline": 50},
        "AUTOTHROTTLE_ENABLED": False,
        "DOWNLOAD_DELAY": 0.4,
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "DOWNLOAD_TIMEOUT": 25,
        "RETRY_TIMES": 2,
    }
    hath_image_download_timeout = 21
    hath_image_download_timeout_fast = 15
    hath_image_retry_times = 0
    name = 'ehentai'
    num_of_row = 25
    domain = domain
    search_url_head = f'https://{domain}/?f_search='
    mappings = {
        res.SPIDER.Completer.index_: f'https://{domain}',
        res.SPIDER.Completer.popular: f'https://{domain}/popular'
    }
    frame_book_format = ['title', 'book_pages', 'preview_url']  # , 'book_idx']
    turn_page_info = (r"page=\d+",)
    book_id_url = f'https://{domain}/g/%s'

    @property
    def ua(self):
        return {**EK.headers, "cookie": EK.to_str_(conf.cookies.get(self.name))}

    def preready(self):
        self._eh_view_ctx = {}

    def image_request_meta(self, *, url, item=None):
        hostname = (urlparse(url).hostname or "").lower()
        if not hostname.endswith("hath.network"):
            return {}
        view_ctx = {}
        if item is not None:
            view_ctx = self._eh_view_ctx.get((item.get('uuid_md5'), item.get('page'))) or {}
        return {
            "download_timeout": self.hath_image_download_timeout_fast,
            "max_retry_times": self.hath_image_retry_times,
            "view_page_url": view_ctx.get('view_url'),
            "nl_token": view_ctx.get('nl'),
        }

    def frame_book(self, response):
        frame_results = {}
        targets = response.xpath('//table[contains(@class, "itg")]//td[contains(@class, "glcat")]/..')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(self.spider_site_runtime.parser.parse_search_item, targets))
        for x, book in enumerate(books):
            book.idx = x + 1
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, extra=f"<br>{res.EHentai.JUMP_TIP}", url=response.url)

    def parse_section(self, response):
        self._emit_process('parse section')
        book = response.meta.get('book')
        sec_page = response.meta.get('sec_page', 1)

        if 'task_validated' not in response.meta:
            if not response.meta.get('sec_page'):
                book.name = self._gallery_title(response, book.name)
            if book.pages is None:
                book.pages = int(re.search(r">(\d+) pages<", response.text).group(1))
            book.name = PresetHtmlEl.sub(book.name)
            self.set_task(book)

        self.say(f'<br>📜 《{book.name}》 page-of-{sec_page}')

        seen_pages = set(response.meta.get('frame_results', {}))
        results, next_flag = self.frame_section(response)
        new_pages = {page: url for page, url in results.items() if page not in seen_pages}

        for page, url in self._filter_page_results(book, new_pages).items():
            yield Request(
                url=url, callback=self.parse_fin_page,
                meta={'book': book, 'page': page}, dont_filter=True,
            )

        if next_flag:
            meta = deepcopy(response.meta)
            meta.update(frame_results=results, sec_page=sec_page + 1, task_validated=1)
            yield Request(url=next_flag, callback=self.parse_section, meta=meta)

    @staticmethod
    def _gallery_title(response, search_title):
        primary = response.xpath('//h1[@id="gj"]/text()').get()
        if primary:
            return primary
        titles = response.xpath("//h1/text()").getall()
        if search_title in titles and len(titles) > 1:
            titles.remove(search_title)
            return titles[0]
        return search_title

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
            nl_match = re.search(r"return nl\('([^']*)'\)", response.text)
            self._eh_view_ctx[(book.u_md5, str(page))] = {
                'view_url': response.url.split('?', 1)[0],
                'nl': nl_match.group(1) if nl_match else None,
            }
            item = ComicspiderItem()
            item.update(**book.get_group_infos())
            item['page'] = str(page)
            item['image_urls'] = [url]
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item
