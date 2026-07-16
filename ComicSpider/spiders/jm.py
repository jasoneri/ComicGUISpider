# -*- coding: utf-8 -*-

from ComicSpider.runtime.job_models import iter_download_items

from utils import conf, PresetHtmlEl
from utils.website import JmBookInfo, BookInfo, Episode
from ComicSpider.items import ComicspiderItem
from .basecomicspider import BaseComicSpider2, font_color, scrapy

domain = "18comic-zzz.xyz"


class JmSpider(BaseComicSpider2):
    name = 'jm'
    custom_settings = {
        "ITEM_PIPELINES": {'ComicSpider.pipelines.JmComicPipeline': 50},
        "DOWNLOADER_MIDDLEWARES": {
            'ComicSpider.middlewares.UAMiddleware': 5,
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': None,
            'ComicSpider.middlewares.ComicDlProxyMiddleware': 4,
            # 'ComicSpider.middlewares.ScrapyDoHProxyMiddleware': 8,
            'ComicSpider.middlewares.RefererMiddleware': 10,
            'ComicSpider.middlewares.FakeMiddleware': 30,
        }, "COOKIES_ENABLED": not conf.cookies.get(name),
    }
    num_of_row = 4
    domain = domain

    @property
    def ua(self):
        provider = self.spider_site_runtime.provider
        _ua = {'Host': self.domain, **provider.headers}
        if conf.cookies.get("jm"):
            _ua.update({'cookie': provider.to_str_(conf.cookies.get(self.name))})
        return _ua

    def start_requests(self):
        yield from self.iter_download_requests(self.current_job)

    def parse_section(self, response):
        def _get_bid():
            if 'book_id' in meta:
                _bid = meta.get('book_id')
            elif 'book' in meta:
                _bid = meta.get('book').id
            else:
                _bid = self.provider_descriptor.get_uuid(response.request.url, only_id=True) or ''
            return _bid
        meta = response.meta
        bid = _get_bid()
        self._emit_process('parse section')
        if response.url.endswith('album_missing'):
            yield self.say(font_color(f'➖ 无效车号：{bid}', cls='theme-err'))
        elif response.url.endswith('login'):
            yield self.say(font_color(f'⚠️ 需要登录/甚至JCoins：{bid}', cls='theme-err'))
        else:
            if not meta.get('title'):
                title = response.xpath('//title/text()').extract_first()
                meta['title'] = title.rsplit('|', 1)[0]
            if not meta.get('book'):
                meta['book'] = JmBookInfo(name=meta['title'], url=response.url).get_id(response.url)
            yield from super(JmSpider, self).parse_section(response)

    def iter_download_requests(self, job):
        self._emit_process('start_requests')
        for item in iter_download_items(job):
            if isinstance(item, Episode):
                yield from self._process_episode(item)
                continue
            if isinstance(item, BookInfo):
                if getattr(item, 'episodes', None):
                    yield from self._dispatch_episodes(item)
                    continue
                yield from self._process_book(item)
                continue
            raise ValueError(f"jm runtime item is missing download url: {item!r}")

    def _iter_target_page_urls(self, item):
        page_urls = getattr(item, "page_urls", None) or []
        for page, url in enumerate(page_urls, start=1):
            if self._should_download_page(item, page):
                yield page, url

    def _process_book(self, item):
        if not getattr(item, "page_urls", None):
            yield scrapy.Request(
                url=item.url,
                callback=self.parse_section,
                headers={**self.ua, 'Referer': self.request_referer(item.url)},
                meta={'book': item},
                dont_filter=True,
            )
            return
        yield from self._process_prefetched_pages(item)

    def _process_episode(self, item):
        if getattr(item, "page_urls", None):
            yield from self._process_prefetched_pages(item)
            return
        yield from super()._process_episode(item)

    def _process_prefetched_pages(self, item):
        if getattr(item, "pages", None) is None:
            item.pages = len(getattr(item, "page_urls", None) or [])
        book = item.from_book if isinstance(item, Episode) else item
        this_uuid, this_md5 = item.id_and_md5()
        ep_name = item.name if isinstance(item, Episode) else None
        book.name = PresetHtmlEl.sub(book.name)
        self._assert_task_not_downloaded(item)
        self.say(f'''📜 《{item.display_title}》''')
        self.set_task(item)
        for page, url in self._iter_target_page_urls(item):
            spider_item = ComicspiderItem()
            spider_item['title'] = book.name
            spider_item['page'] = str(page)
            spider_item['section'] = ep_name
            spider_item['image_urls'] = [url]
            spider_item['uuid'] = this_uuid
            spider_item['uuid_md5'] = this_md5
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{url}',
                callback=self.process_item,
                meta={'item': spider_item},
                dont_filter=True,
            )
        self._emit_process('fin')

    def process_item(self, response):
        yield response.meta['item']

    def frame_section(self, response):
        targets = response.xpath(".//img[contains(@id,'album_photo_')]")
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = target.xpath('./@data-original').get()
            frame_results[x + 1] = img_url
        self.say("📢" + font_color(' 这本已经扔进任务了', cls='theme-tip'))
        return frame_results
