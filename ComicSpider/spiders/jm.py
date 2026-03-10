# -*- coding: utf-8 -*-
import re
import typing as t
from urllib.parse import urlencode, urlparse
from concurrent.futures import ThreadPoolExecutor

from ComicSpider.runtime.job_models import iter_download_items

from utils import convert_punctuation, conf
from utils.website import JmUtils, correct_domain, JmBookInfo
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
            'ComicSpider.middlewares.DisableSystemProxyMiddleware': 4,
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
        self.domain = JmUtils.get_domain()
        self.book_id_url = correct_domain(self.domain, self.book_id_url)

    def start_requests(self):
        self.preready()
        if self._runtime_mode():
            if not self.current_job:
                self.logger.warning("No job assigned, spider will idle")
                return
            yield from self.iter_download_requests(self.current_job)
            return
        self.refresh_state('input_state', 'InputFieldQueue')
        keyword = convert_punctuation(self.input_state.keyword).replace(" ", "")
        if ',' in keyword or keyword.isdecimal():
            for key in filter(lambda x: x.isdecimal(), keyword.split(',')):
                yield scrapy.Request(url=self.book_id_url % key, callback=self.parse_section,
                                        headers={**self.ua, 'Referer': self.domain},
                                        meta={'book_id': key}, dont_filter=True)
        else:
            yield from super(JmSpider, self).start_requests()

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
            if getattr(item, 'url', None):
                yield from self._process_episode(item)
                continue
            book = getattr(item, 'from_book', None)
            if book and getattr(book, 'url', None):
                yield scrapy.Request(
                    url=self.transfer_url(book.url),
                    callback=self.parse_section,
                    headers={**self.ua, 'Referer': self.domain},
                    meta={'book': book},
                    dont_filter=True,
                )
                continue
            raise ValueError(f"jm runtime item is missing download url: {item!r}")

    @property
    def search(self):
        self.domain = JmUtils.get_domain()
        keyword = self.input_state.keyword
        __t = self.time_regex.search(keyword)
        __k = self.kind_regex.search(keyword)
        if keyword in self.mappings.keys():
            url = self.mappings[keyword]
            return Url(f"https://{self.domain}{urlparse(url).path}").set_next(*self.turn_page_info)
        elif not bool(__k):  # 不好说标题匹配到关键字情况，视情况返至前置带*触发
            return Url(f"{self.search_url_head}{keyword}").set_next(*self.turn_page_info)
        _t = __t.group(1) if bool(__t) else '周'
        _k = __k.group(1) if bool(__k) else '点击'
        params = {**self.expand_map[_t], **self.expand_map[_k]}
        url = f"https://{self.domain}/albums?{urlencode(params)}"
        if len(keyword) > 4:
            url += keyword[4:]
        return Url(url).set_next(*self.turn_page_info)

    def frame_book(self, response):
        frame_results = {}
        targets = response.xpath('//div[contains(@class,"thumb-overlay") and not(@class="thumb-overlay-guess_likes")]')
        with ThreadPoolExecutor() as executor:
            books = list(executor.map(JmUtils.parse_search_item, targets))
        for x, book in enumerate(books):
            book.idx = x + 1
            book.preview_url = f'https://{self.domain}{book.preview_url}'
            book.url = f'https://{self.domain}{book.url}'
            frame_results[book.idx] = book
        self.say.frame_book_print(frame_results, url=response.url, make_preview=True)
        self.say(font_color("jm预览图加载懂得都懂，加载不出来是正常现象哦", cls='theme-highlight'))

    def frame_section(self, response):
        targets = response.xpath(".//img[contains(@id,'album_photo_')]")
        frame_results = {}
        for x, target in enumerate(targets):
            img_url = target.xpath('./@data-original').get()
            frame_results[x + 1] = img_url
        self.say("📢" + font_color(' 这本已经扔进任务了', cls='theme-tip'))
        return frame_results
