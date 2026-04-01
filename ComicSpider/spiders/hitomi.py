# -*- coding: utf-8 -*-
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import scrapy

from ComicSpider.runtime.job_models import iter_download_items

from utils import PresetHtmlEl, conf
from utils.website import HitomiUtils, get_loop
from utils.processed_class import PreviewHtml
from ComicSpider.items import ComicspiderItem

from .basecomicspider import BaseComicSpider, font_color

domain = HitomiUtils.index


class HitomiSpider(BaseComicSpider):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {
        'ComicSpider.middlewares.ComicDlProxyMiddleware': 5,
        # 'ComicSpider.middlewares.ScrapyDoHProxyMiddleware': 8,
        'ComicSpider.middlewares.UAMiddleware': 10,
        'ComicSpider.middlewares.FakeMiddleware': 30,
    }}
    name = 'hitomi'
    domain = domain
    ua = HitomiUtils.headers
    backend_domain = "ltn.gold-usergeneratedcontent.net"
    frame_book_format = ["lang", "title", "preview_url", "pics"]
    deferred_list = []
    async_cli = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(HitomiSpider, cls).from_crawler(crawler, *args, **kwargs)
        try:
            spider.async_cli = spider.site.get_cli(conf, is_async=True)
        except Exception as e:
            if spider.crawler and spider.crawler.engine:
                spider.crawler.engine.close_spider(spider, reason=f"[error]{str(e)}")
            else:
                spider.logger.error(f"Failed to initialize HitomiUtils: {str(e)}")
                raise e
        return spider

    def _get_nozomi_sync(self, nozomi_url, page):
        """同步包装的异步nozomi获取方法"""
        async def _async_get():
            headers = {**HitomiUtils.headers, "Range": self.site.runtime.get_range(page)}
            return await self.async_cli.get(nozomi_url, headers=headers)

        try:
            running_loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(_async_get(), running_loop)
            return future.result()
        except RuntimeError:
            loop = get_loop()
            return loop.run_until_complete(_async_get())

    def start_requests(self):
        self.preready()
        yield from self.iter_download_requests(self.current_job)

    # ==============================================
    def parse(self, response, meta):
        self._emit_process('parse')
        result = HitomiUtils.parse_nozomi(response.content)
        
        meta = meta or {}
        meta['results'] = []
        meta['total_requests'] = len(result)
        
        async def fetch_gallery(i, gallery_id):
            url = f"https://{self.backend_domain}/galleries/{gallery_id}.js"
            resp = await self.async_cli.get(url)
            return i, resp

        async def fetch_all():
            tasks = [fetch_gallery(i, gallery_id) for i, gallery_id in enumerate(result)]
            return await asyncio.gather(*tasks)

        try:
            running_loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(fetch_all(), running_loop)
            resps = future.result()
        except RuntimeError:
            loop = get_loop()
            resps = loop.run_until_complete(fetch_all())
        
        # 整合actual_parse的功能
        for _, resp in sorted(resps, key=lambda x: x[0]):  # 按原始索引排序
            meta['results'].append({
                "text": resp.text,
                "meta": {k: v for k, v in meta.items() if k != 'results'}
            })
        yield from self.defer_parse(meta['results'])

    def defer_parse(self, rets):
        self._emit_process('defer_parse')
        if not rets:
            self.logger.error("No results to process")
            return

    def parse_section(self, meta):
        self._emit_process('parse section')

        book = meta.get('book')
        this_uuid, this_md5 = book.id_and_md5()
        self._assert_task_not_downloaded(book)
        self.set_task(book)
        for index, pic_info in enumerate(book.pics, 1):
            item = ComicspiderItem()
            item['title'] = book.name
            item['page'] = str(index)
            item['section'] = None
            img_url = self.site.runtime.get_img_url(pic_info['hash'], pic_info['hasavif'])
            item['image_urls'] = [img_url]
            item['uuid'] = this_uuid
            item['uuid_md5'] = this_md5
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{img_url}', callback=self.process_item, meta={'item': item},
                dont_filter=True
            )
        self._emit_process('fin')

    def iter_download_requests(self, job):
        self._emit_process('start_requests')
        for book in iter_download_items(job):
            if not getattr(book, 'pics', None):
                raise ValueError(f"hitomi runtime item is missing pics payload: {book!r}")
            yield from self.parse_section({'book': book})

    # ==============================================
    def frame_book(self, rets, meta):
        frame_results = {}
        texts = [target['text'] for target in rets]
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(self.site.parser.parse_search_item, texts))
        for x, book in enumerate(books):
            book.idx = x + 1
            book.preview_url = f"{self.domain}{book.preview_url}"
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, url=meta.get("Url"))

    def process_item(self, response):
        item = response.meta['item']
        yield item
