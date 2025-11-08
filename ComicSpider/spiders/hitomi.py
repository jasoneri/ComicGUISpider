# -*- coding: utf-8 -*-
import json
import asyncio
import scrapy

from utils import PresetHtmlEl, conf
from utils.website import HitomiUtils, get_loop
from utils.processed_class import PreviewHtml
from utils.website import HitomiBookInfo
from ComicSpider.items import ComicspiderItem

from .basecomicspider import BaseComicSpider, font_color

domain = HitomiUtils.index


class HitomiSpider(BaseComicSpider):
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {
        'ComicSpider.middlewares.ComicDlProxyMiddleware': 5,
        'ComicSpider.middlewares.UAMiddleware': 10,
        'ComicSpider.middlewares.FakeMiddleware': 30,
    }}
    name = 'hitomi'
    domain = domain
    ua = HitomiUtils.headers
    backend_domain = "ltn.gold-usergeneratedcontent.net"
    say_fm = r' [ {} ], lang_{}, p_{}, ⌈ {} ⌋ '
    frame_book_format = ["lang", "title", "preview_url", "pics"]
    ut = None
    deferred_list = []
    async_cli = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(HitomiSpider, cls).from_crawler(crawler, *args, **kwargs)
        try:
            spider.ut = HitomiUtils(conf)
        except Exception as e:
            if spider.crawler and spider.crawler.engine:
                spider.crawler.engine.close_spider(spider, reason=f"[error]{str(e)}")
            else:
                spider.logger.error(f"Failed to initialize HitomiUtils: {str(e)}")
                raise e
        spider.async_cli = spider.ut.get_cli(conf, is_async=True)
        return spider

    def _get_nozomi_sync(self, nozomi_url, page):
        """同步包装的异步nozomi获取方法"""
        async def _async_get():
            headers = {**HitomiUtils.headers, "Range": self.ut.get_range(page)}
            return await self.async_cli.get(nozomi_url, headers=headers)

        try:
            running_loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(_async_get(), running_loop)
            return future.result()
        except RuntimeError:
            loop = get_loop()
            return loop.run_until_complete(_async_get())

    def start_requests(self):
        self.refresh_state('input_state', 'InputFieldQueue')
        self.process_state.process = 'start_requests'
        self.Q('ProcessQueue').send(self.process_state)

        keyword = self.input_state.keyword
        self.search_start = f"{self.domain}{keyword}.html"
        page = 1
        nozomi = f"https://{self.backend_domain}/{keyword}.nozomi"
        meta = {"Url": self.search_start, "nozomi": nozomi, "page": page}
        resp = self._get_nozomi_sync(nozomi, page)
        yield from self.parse(response=resp, meta=meta)
    
    # ==============================================
    def parse(self, response, meta):
        self.process_state.process = 'parse'
        self.Q('ProcessQueue').send(self.process_state)
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

    def page_turn(self, meta):
        if not self.input_state.pageTurn:
            resp = self._get_nozomi_sync(meta.get("nozomi"), meta.get("page"))
            yield from self.parse(response=resp, meta=meta)
            # yield scrapy.Request(url=meta.get("nozomi"), callback=self.parse, meta=meta, dont_filter=True)
        elif 'next' in self.input_state.pageTurn:
            yield from self.page_turn_(meta['page']+1, meta)
        elif 'previous' in self.input_state.pageTurn:
            yield from self.page_turn_(meta['page']-1, meta)
        elif self.input_state.pageTurn:
            yield from self.page_turn_(int(self.input_state.pageTurn), meta)

    def page_turn_(self, page, meta, **kw):
        meta={"Url": meta.get("Url"), "nozomi": meta.get("nozomi"), "page": page}
        resp = self._get_nozomi_sync(meta.get("nozomi"), page)
        yield from self.parse(response=resp, meta=meta)

    def actual_parse(self, response):
        self.logger.info("actual_parse called")
        meta = response.meta
        meta['results'].append({
            "text": response.text,
            "meta": {k: v for k, v in meta.items() if k != 'results'}
        })
        self.say(self.ut.get_uuid(response.request.url))
        if len(meta['results']) == meta['total_requests']:
            self.logger.info("All requests completed, processing results")
            yield from self.defer_parse(meta['results'])

    def defer_parse(self, rets):
        self.process_state.process = 'defer_parse'
        self.Q('ProcessQueue').send(self.process_state)
        if not rets:
            self.logger.error("No results to process")
            return
        meta = json.loads(
            {json.dumps(ret.pop('meta')) for ret in rets}.pop()
        )
        frame_book_results = self.frame_book(rets, meta)
        self.refresh_state('input_state', 'InputFieldQueue', monitor_change=True)
        if self.input_state.pageTurn:
            yield from self.page_turn(meta)
        else:
            for book in self.input_state.indexes:
                meta = {'book': book}
                yield from self.parse_section(meta)

    def parse_section(self, meta):
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)

        book = meta.get('book')
        this_uuid, this_md5 = book.id_and_md5()
        if not conf.isDeduplicate or not (conf.isDeduplicate and self.sql_handler.check_dupe(this_md5)):
            self.say(f'📜 《{book.name}》')
            self.set_task(book)
            for pic_info in book.pics:
                item = ComicspiderItem()
                item['title'] = book.name
                item['page'] = str(pic_info['name'])
                item['section'] = 'meaningless'
                img_url = self.ut.get_img_url(pic_info['hash'], pic_info['hasavif'])
                item['image_urls'] = [img_url]
                item['uuid'] = this_uuid
                item['uuid_md5'] = this_md5
                self.total += 1
                # 使用一个空的请求来触发item处理
                yield scrapy.Request(
                    url=f'https://fakefakefa.com/{img_url}',callback=self.process_item,meta={'item': item},
                    dont_filter=True
                )
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)

    # ==============================================
    def frame_book(self, rets, meta):
        frame_results = {}
        self.say(self.say_fm.format('index', 'lang', 'pages', 'name') + '<br>')
        for x, target in enumerate(rets):
            datum = self.ut.parse_galleries(target['text'])
            gallery_id = datum['id']
            pics = datum['files']
            first_pic = pics[0]
            btype = datum['type']
            _title = datum['title']
            book = HitomiBookInfo(
                id=gallery_id, idx=x+1,
                name=_title.split(' | ')[-1] if ' | ' in _title else _title,
                preview_url=f"{self.domain}{btype}/{gallery_id}.html",
                pages=len(pics), pics=pics, btype=btype,
                img_preview=self.ut.get_img_url(first_pic['hash'], 0, preview=True),
                lang=datum['language_localname'],
            )
            frame_results[book.idx] = book
        return self.say.frame_book_print(frame_results, url=meta.get("Url"), make_preview=True)

    def process_item(self, response):
        item = response.meta['item']
        yield item
