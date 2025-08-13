# -*- coding: utf-8 -*-
import json
import asyncio
import scrapy

from utils import PresetHtmlEl, conf
from utils.website import HitomiUtils, get_loop
from utils.processed_class import PreviewHtml
from utils.website import Uuid
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

    def page_turn(self, elected_results, meta):
        if not self.input_state.pageTurn:
            resp = self._get_nozomi_sync(meta.get("nozomi"), meta.get("page"))
            yield from self.parse(response=resp, meta=meta)
            # yield scrapy.Request(url=meta.get("nozomi"), callback=self.parse, meta=meta, dont_filter=True)
        elif 'next' in self.input_state.pageTurn:
            yield from self.page_turn_(elected_results, meta['page']+1, meta)
        elif 'previous' in self.input_state.pageTurn:
            yield from self.page_turn_(elected_results, meta['page']-1, meta)
        elif self.input_state.pageTurn:
            yield from self.page_turn_(elected_results, int(self.input_state.pageTurn), meta)

    def page_turn_(self, elected_results, page, meta, **kw):
        all_elected_res = [*elected_results, *meta.get("selected", [])]
        meta={"Url": meta.get("Url"), "nozomi": meta.get("nozomi"), "selected": all_elected_res, "page": page}
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
        selected = meta.get("selected", [])
        if selected:
            elected_titles = list(map(lambda x: x[1], selected))
            self.say(font_color(f"<br>{self.res.choice_list_before_turn_page}<br>"
                                f"{'<br>'.join(elected_titles)}", cls='theme-success'))
        self.refresh_state('input_state', 'InputFieldQueue', monitor_change=True)
        results = self.select(self.input_state.indexes, frame_book_results, step=self.res.parse_step)
        if self.input_state.pageTurn:
            yield from self.page_turn(results, meta)
        else:
            for result in [*results, *meta.get("selected", [])]:
                meta = dict(zip(self.frame_book_format, result))
                yield from self.parse_section(meta)

    def parse_section(self, meta):
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)

        title = PresetHtmlEl.sub(meta['title'])
        this_uuid, this_md5 = Uuid(self.name).id_and_md5(meta.get('preview_url'))
        if not conf.isDeduplicate or not (conf.isDeduplicate and self.sql_handler.check_dupe(this_md5)):
            self.say(f'{"=" * 15} 《{title}》')
            self.set_task((this_md5, title, len(meta['pics']), meta.get('preview_url'), None))
            for pic_info in meta['pics']:
                item = ComicspiderItem()
                item['title'] = title
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
        example_b = r' [ {} ], lang_{}, p_{}, ⌈ {} ⌋ '
        self.say(example_b.format('index', 'lang', 'pages', 'name') + '<br>')
        preview = PreviewHtml(meta.get("Url"))
        
        for x, target in enumerate(rets):
            datum = self.ut.parse_galleries(target['text'])
            gallery_id = datum['id']
            pics = datum['files']
            first_pic = pics[0]
            btype = datum['type']
            lang = datum['language_localname']
            _title = datum['title']
            title = _title.split(' | ')[-1] if ' | ' in _title else _title
            preview_url = f"{self.domain}{btype}/{gallery_id}.html"
            img_preview = self.ut.get_img_url(first_pic['hash'], 0, preview=True)
            
            self.say(example_b.format(str(x + 1), lang, len(pics), title, chr(12288)))
            frame_results[x + 1] = [lang, title, preview_url, pics]
            preview.add(x + 1, img_preview, title, preview_url, pages=len(pics), lang=lang, btype=btype)
        self.say(preview.created_temp_html)
        return self.say.frame_book_print(frame_results, url=meta.get("Url"))

    def process_item(self, response):
        item = response.meta['item']
        yield item
