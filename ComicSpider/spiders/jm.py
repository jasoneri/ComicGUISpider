# -*- coding: utf-8 -*-
import re
import typing as t
from urllib.parse import urlencode, urlparse
from concurrent.futures import ThreadPoolExecutor

from ComicSpider.runtime.job_models import iter_download_items

from utils import convert_punctuation, conf
from utils.website import JmUtils, correct_domain, JmBookInfo, BookInfo, Episode
from utils.processed_class import Url
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
    search_url_head = f'https://{domain}/search/photos?main_tag=0&search_query='
    book_id_url = f'https://{domain}/photo/%s'
    transfer_url = staticmethod(lambda url: url.replace('album', 'photo'))
    mappings = {}

    time_regex = re.compile(r".*?([日周月总])")
    kind_regex = re.compile(r".*?(更新|点击|评分|评论|收藏)")
    expand_map: t.Dict[str, dict] = {
        "日": {'t': 't'}, "周": {'t': 'w'}, "月": {'t': 'm'}, "总": {'t': 'a'},
        "更新": {'o': 'mr'}, "点击": {'o': 'mv'}, "评分": {'o': 'tr'}, "评论": {'o': 'md'}, "收藏": {'o': 'tf'}
    }
    turn_page_info = (r"page=\d+",)

    @property
    def ua(self):
        _ua = {'Host': self.domain, **JmUtils.headers}
        if conf.cookies.get("jm"):
            _ua.update({'cookie': JmUtils.to_str_(conf.cookies.get(self.name))})
        return _ua

    def preready(self):
        if self._runtime_origin:
            return
        self.domain = JmUtils.get_domain()
        self.book_id_url = correct_domain(self.domain, self.book_id_url)

    def start_requests(self):
        self.preready()
        yield from self.iter_download_requests(self.current_job)

    def parse_section(self, response):
        def _get_bid():
            if 'book_id' in meta:
                _bid = meta.get('book_id')
            elif 'book' in meta:
                _bid = meta.get('book').id
            else:
                _bid = self.ut.get_uuid(response.request.url, only_id=True) or ''
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
                meta['book'] = JmBookInfo(
                    name=meta['title'],
                    url=response.url,
                ).get_id(response.url)
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
                    url=self.transfer_url(item.url),
                    callback=self.parse_section,
                    headers={**self.ua, 'Referer': self.request_referer(item.url)},
                    meta={'book': item},
                    dont_filter=True,
                )
                continue
            raise ValueError(f"jm runtime item is missing download url: {item!r}")

    def frame_book(self, response):
        frame_results = {}
        targets = response.xpath('//div[contains(@class,"thumb-overlay") and not(@class="thumb-overlay-guess_likes")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(self.ut.parser.parse_search_item, targets))
        for x, book in enumerate(books):
            book.idx = x + 1
            book.preview_url = f'https://{self.domain}{book.preview_url}'
            book.url = f'https://{self.domain}{book.url}'
            frame_results[book.idx] = book
        self.say.frame_book_print(frame_results, url=response.url)
        self.say(font_color("jm预览图加载懂得都懂，加载不出来是正常现象哦", cls='theme-highlight'))

    def frame_section(self, response):
        targets = response.xpath(".//img[contains(@id,'album_photo_')]")
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = target.xpath('./@data-original').get()
            frame_results[x + 1] = img_url
        self.say("📢" + font_color(' 这本已经扔进任务了', cls='theme-tip'))
        return frame_results
