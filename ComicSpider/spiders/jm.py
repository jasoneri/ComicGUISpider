# -*- coding: utf-8 -*-

from ComicSpider.runtime.job_models import iter_download_items

from utils import conf
from utils.website import JmBookInfo, BookInfo, Episode
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
                yield scrapy.Request(
                    url=item.url,
                    callback=self.parse_section,
                    headers={**self.ua, 'Referer': self.request_referer(item.url)},
                    meta={'book': item},
                    dont_filter=True,
                )
                continue
            raise ValueError(f"jm runtime item is missing download url: {item!r}")

    def frame_section(self, response):
        targets = response.xpath(".//img[contains(@id,'album_photo_')]")
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = target.xpath('./@data-original').get()
            frame_results[x + 1] = img_url
        self.say("📢" + font_color(' 这本已经扔进任务了', cls='theme-tip'))
        return frame_results
