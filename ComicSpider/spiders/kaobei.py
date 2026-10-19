# -*- coding: utf-8 -*-
import random

from twisted.internet import reactor
from twisted.internet.defer import CancelledError, Deferred

import scrapy

from utils.website.providers.kaobei import KaobeiUtils
from utils.website.schema import KbFrameBook as FrameBook
from .basecomicspider import BaseComicSpider, ComicspiderItem


class _ChapterGate:
    """Chapter admission state for one KaobeiSpider job.

    One active chapter slot plus a FIFO queue. The next chapter's fake
    requests are produced as the result of a Deferred that fires after the
    inter-chapter delay; Scrapy schedules Deferred output from callbacks
    without any crawler-engine API. Stop cancels the pending Deferred.
    """

    def __init__(self, spider, chapter_delay: float, chapter_delay_jitter: float):
        self.spider = spider
        self.chapter_delay = chapter_delay
        self.chapter_delay_jitter = chapter_delay_jitter
        self.pending_episodes: list[tuple] = []
        self.active_episode = None
        self.active_total = 0
        self.active_drained = 0
        self.admission_deferred: Deferred | None = None
        self.stopped = False

    def register(self, ep, page_urls: list, page_request_count: int):
        if page_request_count <= 0:
            return False
        if self.active_episode is None:
            self._activate(ep, page_urls, page_request_count)
            return True
        self.pending_episodes.append((ep, page_urls, page_request_count))
        return False

    def _activate(self, ep, page_urls, page_request_count):
        self.active_episode = ep
        self.active_total = page_request_count
        self.active_drained = 0

    def record_drained(self) -> bool:
        self.active_drained += 1
        return self.active_drained >= self.active_total

    def pop_admission_deferred(self) -> Deferred | None:
        """Deferred resolving to the next chapter's requests after the delay."""
        if self.stopped or not self.pending_episodes:
            return None
        ep, page_urls, page_request_count = self.pending_episodes.pop(0)
        deferred = Deferred(lambda d: self._discard_pending(d))

        def _admit():
            self.admission_deferred = None
            if self.stopped:
                deferred.cancel()
                return
            self._activate(ep, page_urls, page_request_count)
            deferred.callback(list(self._build_requests(ep, page_urls)))

        if self.chapter_delay > 0:
            self.admission_deferred = deferred
            # A fixed interval is trivially fingerprintable as crawler pacing;
            # community-measured safe band is 2.0-3.5s, so the delay is drawn
            # per chapter from [chapter_delay, chapter_delay + jitter].
            delay = random.uniform(self.chapter_delay, self.chapter_delay + self.chapter_delay_jitter)
            reactor.callLater(delay, _admit)
        else:
            _admit()
        return deferred

    def _build_requests(self, ep, page_urls):
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title': book.name, 'section': ep.name, 'uuid': uid, 'uuid_md5': u_md5}
        ep.pages = len(page_urls)
        self.spider.set_task(ep)
        for page, image_url in self.spider._iter_target_page_urls(ep, page_urls):
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page
            item['image_urls'] = [image_url]
            if self.spider.job_context:
                self.spider.job_context.total += 1
            self.spider.total += 1
            yield scrapy.Request(
                url=f'https://fakefakefa.com/{image_url}', callback=self.spider.process_item,
                meta={'item': item}, dont_filter=True,
            )

    def _discard_pending(self, deferred: Deferred):
        if self.admission_deferred is deferred:
            self.admission_deferred = None

    def stop(self):
        self.stopped = True
        self.pending_episodes.clear()
        if self.admission_deferred is not None:
            self.admission_deferred.cancel()
            self.admission_deferred = None


class KaobeiSpider(BaseComicSpider):
    name = 'manga_copy'
    ua = KaobeiUtils.ua
    headers = KaobeiUtils.headers
    page_headers = {**KaobeiUtils.ua_mapi, **KaobeiUtils.headers}
    ua_mapi = KaobeiUtils.ua_mapi
    domain = KaobeiUtils.api_domain
    pc_domain = KaobeiUtils.pc_domain
    proxy_domains = [domain, pc_domain]  # 需要代理的域名列表
    # CopyManga risk-control pacing: one chapter admitted at a time plus a
    # configurable inter-chapter delay. Image fan-out stays bounded by the
    # shared CONCURRENT_REQUESTS lane; do not read chapter_delay as image pacing.
    # chapter_delay is the floor; the actual wait is drawn uniformly from
    # [chapter_delay, chapter_delay + chapter_delay_jitter] per chapter.
    chapter_delay = 2.0
    chapter_delay_jitter = 1.5
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.UAKaobeiMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlProxyMiddleware': 6,
                                   'ComicSpider.middlewares.FakeMiddleware': 30},
        "REFERER_ENABLED": False
    }
    search_url_head = ''
    preset_book_frame = FrameBook(domain)
    turn_page_info = (r"offset=\d+", None, 30)
    section_limit = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._chapter_gate = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider._on_spider_closed, signal=scrapy.signals.spider_closed)
        spider.spider_site_runtime.reqer.get_aes_key()
        return spider

    def _on_spider_closed(self, _spider):
        if self._chapter_gate is not None:
            self._chapter_gate.stop()

    def _gate(self) -> _ChapterGate:
        if self._chapter_gate is None:
            self._chapter_gate = _ChapterGate(self, self.chapter_delay, self.chapter_delay_jitter)
        return self._chapter_gate

    def _process_episode(self, ep):
        if not getattr(ep, 'page_urls', None):
            raise ValueError(f"kaobei episode requires page_urls: {ep!r}")
        page_urls = list(ep.page_urls)
        page_request_count = sum(1 for _page, _url in self._iter_target_page_urls(ep, page_urls))
        gate = self._gate()
        admitted = gate.register(ep, page_urls, page_request_count)
        if admitted:
            yield from gate._build_requests(ep, page_urls)

    def process_item(self, response):
        item = response.meta['item']
        gate = self._gate()
        if gate.active_episode is None or not gate.record_drained():
            return item
        self._emit_process('fin')
        gate.active_episode = None
        admission = gate.pop_admission_deferred()
        if admission is None:
            return item

        def _emit_admitted(outputs):
            return [item, *outputs]

        def _cancelled(failure):
            failure.trap(CancelledError)
            return [item]

        admission.addCallbacks(_emit_admitted, _cancelled)
        return admission
