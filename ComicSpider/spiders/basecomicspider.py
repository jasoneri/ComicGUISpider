# -*- coding: utf-8 -*-
import os
import typing as t
from abc import abstractmethod
from copy import deepcopy
from time import sleep
from urllib.parse import urlparse

import scrapy

from variables import *
from assets import res as ori_res
from ComicSpider.items import ComicspiderItem
from ComicSpider.runtime.job_models import create_job_context, iter_download_items
from GUI.core.font import font_color
from utils import PresetHtmlEl, temp_p, conf
from utils.processed_class import TextBrowserState, ProcessState
        
from utils.protocol import SpiderDownloadJob, JobContext, LogEvent, ProcessStateEvent
from utils.website import (
    correct_domain, BookInfo, Episode
)
from utils.website.registry import resolve_spider_adapter
from utils.website.schema import BodyFormat
from utils.sql import SqlRecorder, SqlrV
from utils.meta import MetaRecorder


class SayToGui:
    res = ori_res.SPIDER.SayToGui
    exp_txt = res.exp_txt
    exp_turn_page = font_color(res.exp_turn_page, cls='theme-success')
    exp_preview = font_color(res.exp_preview, color='chocolate')
    exp_extra = f"{exp_turn_page}<br>{exp_preview}<br>{res.exp_replace_keyword}"

    def __init__(self, spider, state=None, *, event_q, job_id=None):
        self.spider = spider
        if spider.name in {s.spider_name for s in Spider.specials()}:
            self.exp_txt = self.exp_txt.replace(self.res.exp_replace_keyword, self.exp_extra)
        self.text_browser = self.TextBrowser(state or spider.text_browser_state, event_q=event_q, job_id=job_id)

    def __call__(self, *args, **kwargs):
        self.text_browser.send(*args, **kwargs)

    class TextBrowser:
        def __init__(self, state, *, event_q, job_id=None):
            self.state = state
            self.event_q = event_q
            self.job_id = job_id

        def error(self, *args):
            _ = SayToGui.res.TextBrowser_error.format(*args)
            self.send(f"{_:=>15}")

        def send(self, _text):
            self.state.text = _text
            self.event_q.put_nowait(LogEvent(job_id=self.job_id, level="info", message=_text))

    def frame_section_print(self, rets, extra=None):
        extra = extra or self.res.frame_section_print_extra
        self(rets)
        self(f"""<hr><p class="theme-text">{''.join(self.exp_txt)}<br>{font_color(extra, cls='theme-highlight')}</p>""")
        return rets


class BaseComicSpider(scrapy.Spider):
    """ComicSpider基类"""

    res = ori_res.SPIDER
    text_browser_state = TextBrowserState(text='')
    process_state = ProcessState(process='init')
    say: SayToGui = None
    adapter = None
    site = None
    record_sql: SqlRecorder = None
    rv_sql: SqlrV = None
    ua = {}
    total = 0
    tasks = {}
    tasks_path = {}
    mr: MetaRecorder = None
    job_context: JobContext = None
    current_job: SpiderDownloadJob = None
    _runtime_thread = None
    _runtime_origin = None
    num_of_row = 5
    search_url_head = NotImplementedError(res.search_url_head_NotImplementedError)
    domain = None  # REMARK(2024-08-16): 使用时用self.domain, 保留作出更改的余地
    book_id_url = ""  # book链接中id用%s转换符的形态，此为preview_url
    transfer_url = staticmethod(lambda _:_)  # 由preview_url转化为机器读的url
    kind = {}
    # e.g. kind={'作者':'xx_url_xx/artist/', ...}  当输入为'作者张三'时，self.search='xx_url_xx/artist/张三'
    mappings = {}  # mappings自定义关键字对应"固定"uri
    frame_book_format = ['title', 'preview_url']
    turn_page_search: str = None
    turn_page_info: tuple = None
    _enable_episode_dispatch = False
    remove_domain_cache_on_finished_miss = True

    def preready(self):
        ...

    @staticmethod
    def _url_origin(url: str) -> t.Optional[str]:
        if not isinstance(url, str) or not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return None

    def request_referer(self, url: str = None) -> str:
        if origin := self._url_origin(url):
            return origin
        if self._runtime_origin:
            return self._runtime_origin
        if isinstance(self.domain, str) and self.domain:
            if origin := self._url_origin(self.domain):
                return origin
            return f"https://{self.domain}"
        raise ValueError(f"{self.__class__.__name__} cannot determine request referer")

    def _to_absolute_url(self, url: str) -> str:
        if not isinstance(url, str) or not url:
            return url
        if url.startswith("http"):
            return url
        try:
            referer = self.request_referer()
        except ValueError:
            return url
        if url.startswith("//"):
            return f"{urlparse(referer).scheme}:{url}"
        prefix = "" if url.startswith("/") else "/"
        return f"{referer}{prefix}{url}"

    def _normalize_book_urls(self, book: BookInfo):
        for attr in ("url", "preview_url", "img_preview"):
            value = getattr(book, attr, None)
            normalized = self._to_absolute_url(value) if value else value
            if normalized != value:
                setattr(book, attr, normalized)

    def _bind_runtime_context(self, job: SpiderDownloadJob):
        items = list(iter_download_items(job))
        for item in items:
            candidates = []
            if isinstance(item, Episode):
                candidates.extend([
                    getattr(item, "url", None),
                    getattr(getattr(item, "from_book", None), "url", None),
                    getattr(getattr(item, "from_book", None), "preview_url", None),
                ])
            elif isinstance(item, BookInfo):
                candidates.extend([
                    getattr(item, "url", None),
                    getattr(item, "preview_url", None),
                ])
            for candidate in candidates:
                if origin := self._url_origin(candidate):
                    self._runtime_origin = origin
                    self.domain = urlparse(origin).netloc
                    existing_proxy_domains = list(getattr(self, "proxy_domains", None) or [])
                    if self.domain and self.domain not in existing_proxy_domains:
                        self.proxy_domains = [*existing_proxy_domains, self.domain] if existing_proxy_domains else [self.domain]
                    if isinstance(self.book_id_url, str) and self.book_id_url.startswith("http"):
                        self.book_id_url = correct_domain(self.domain, self.book_id_url)
                    break
            if self._runtime_origin:
                break

        for item in items:
            if isinstance(item, Episode):
                if item.from_book is not None:
                    self._normalize_book_urls(item.from_book)
                item.url = self._to_absolute_url(item.url) if item.url else item.url
            elif isinstance(item, BookInfo):
                self._normalize_book_urls(item)
                for ep in list(getattr(item, "episodes", None) or []):
                    if ep.from_book is None:
                        ep.from_book = item
                    if item.url and not getattr(ep.from_book, "url", None):
                        ep.from_book.url = item.url
                    ep.url = self._to_absolute_url(ep.url) if ep.url else ep.url

    def emit(self, event):
        if self._runtime_thread:
            self._runtime_thread.event_q.put_nowait(event)

    def _emit_process(self, process: str):
        self.process_state.process = process
        job_id = self.current_job.job_id if self.current_job else None
        if self._runtime_thread:
            self.emit(ProcessStateEvent(job_id=job_id, process=process))

    def _task_store(self):
        return self.job_context if self.job_context else self

    @property
    def tasks_store(self):
        return self._task_store().tasks

    @property
    def tasks_path_store(self):
        return self._task_store().tasks_path

    def _dispatch_episodes(self, book):
        episodes = book.episodes
        if not isinstance(episodes, list) or not episodes:
            raise ValueError("episode dispatch requires a non-empty list[Episode]")
        if not all(isinstance(ep, Episode) for ep in episodes):
            raise TypeError("episode dispatch requires list[Episode]")
        self._emit_process('parse section')
        for ep in episodes:
            yield from self._process_episode(ep)

    def iter_download_requests(self, job: SpiderDownloadJob):
        self._emit_process('start_requests')
        for item in iter_download_items(job):
            if isinstance(item, Episode):
                yield from self._process_episode(item)
            elif isinstance(item, BookInfo):
                if item.episodes:
                    yield from self._dispatch_episodes(item)
                else:
                    yield from self._process_book(item)

    def _process_episode(self, ep: Episode):
        if not ep.url:
            raise ValueError(f"episode dispatch: url is required, got {ep!r}")
        for url in self.mk_page_tasks(url=ep.url):
            final_url = url if self._enable_episode_dispatch else self.transfer_url(url)
            meta = {'ep': ep} if self._enable_episode_dispatch else {'episode': ep}
            callback = self.parse_fin_page if self._enable_episode_dispatch else self.parse_section
            yield scrapy.Request(
                url=final_url,
                callback=callback,
                headers={**self.ua, 'Referer': self.request_referer(final_url)},
                meta=meta,
                dont_filter=True,
            )

    def _process_book(self, book: BookInfo):
        url = book.url if book.url and book.url.startswith("http") else self.book_id_url % book.id
        final_url = self.transfer_url(url)
        yield scrapy.Request(
            url=final_url, callback=self.parse_section,
            headers={**self.ua, 'Referer': self.request_referer(final_url)},
            meta={'book': book}, dont_filter=True)

    def start_requests(self):
        self.preready()
        yield from self.iter_download_requests(self.current_job)

    @abstractmethod
    def frame_book(self, response) -> dict:
        pass

    def parse_section(self, response):
        self._emit_process('parse section')

        need_sec_next_page = self.need_sec_next_page(response)
        if need_sec_next_page:
            yield scrapy.Request(url=need_sec_next_page, callback=self.parse_section, meta=response.meta)
            return

        book = response.meta.get('book')
        if book:
            self.say(f'📜 《{book.name}》')
        frame_eps_result = self.frame_section(response)
        if not frame_eps_result:
            self.logger.warning("frame_section returned empty results")
            return
        for page, url_or_ep in frame_eps_result.items():
            if isinstance(url_or_ep, Episode):
                yield from self._process_episode(url_or_ep)
            elif isinstance(url_or_ep, str):
                yield scrapy.Request(
                    url=url_or_ep,
                    callback=self.parse_fin_page,
                    meta={'book': book, 'page': page},
                    dont_filter=True,
                )

    def need_sec_next_page(self, resp):
        pass

    @abstractmethod
    def frame_section(self, response) -> dict:
        pass

    def parse_fin_page(self, response):
        pass

    def mk_page_tasks(self, *arg, **kw) -> iter:
        """做这个中间件预想是：1、每一话预请求第一页，从resp中直接清洗获取items信息;
        2、设立规则处理response.follow也许可行"""
        return [kw['url']]

    @staticmethod
    def _task_md5(task_info: t.Union[BookInfo, Episode]) -> str:
        if hasattr(task_info, 'id_and_md5'):
            return task_info.id_and_md5()[1]
        return task_info.to_tasks_obj().taskid

    def _assert_task_not_downloaded(self, task_info: t.Union[BookInfo, Episode]):
        if conf.isDeduplicate:
            taskid = self._task_md5(task_info)
            assert not self.record_sql.check_dupe(taskid), (
                f"duplicate task reached spider runtime: {taskid} / {task_info.display_title}"
            )

    def set_task(self, task_info: t.Union[BookInfo, Episode]):
        book = task_info.from_book if isinstance(task_info, Episode) else task_info
        if book.preview_url and not book.preview_url.startswith("http"):
            prefix = "" if book.preview_url.startswith("/") else "/"
            book.preview_url = f"https://{self.domain}{prefix}{book.preview_url}"
        if getattr(book, "img_preview", None) and not book.img_preview.startswith("http"):
            prefix = "" if book.img_preview.startswith("/") else "/"
            book.img_preview = f"https://{self.domain}{prefix}{book.img_preview}"
        canonical = task_info.to_tasks_obj()
        ctx = self._task_store()
        tasks_obj = ctx.tasks.get(canonical.taskid)
        tasks_obj.meta_info = self.mr.toMetaInfo(task_info)

        self.rv_sql.write_meta(**book.to_sql())

    def makesure_tasks_status(self):
        if conf.isDeduplicate:
            ctx = self._task_store()
            for taskid, _ in ctx.tasks.items():
                if self.record_sql.check_dupe(taskid):
                    continue
                elif ctx.tasks_path.get(taskid) and len(tuple(ctx.tasks_path.get(taskid).iterdir())) >= ctx.tasks[taskid].tasks_count:
                    self.record_sql.add(taskid)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        spider.mappings.update(spider.settings.get('CUSTOM_MAP') or {})

        runtime_thread = kwargs.get('runtime_thread') or spider.settings.get('_RUNTIME_THREAD')
        job = kwargs.get('job') or spider.settings.get('_CURRENT_JOB')

        if not runtime_thread:
            raise RuntimeError(f"{cls.__name__} requires runtime_thread")

        spider._runtime_thread = runtime_thread
        job_id = job.job_id if job else None
        spider.emit(ProcessStateEvent(job_id=job_id, process='spider_init'))
        spider.say = SayToGui(spider, state=spider.text_browser_state, event_q=runtime_thread.event_q, job_id=job_id)

        spider.record_sql = SqlRecorder()
        spider.rv_sql = SqlrV(1 if spider.name in spider.settings.get('SPECIAL') else 0).connect()
        spider.adapter = resolve_spider_adapter(spider.name)
        spider.site = spider.adapter.create_session(conf)
        spider.mr = MetaRecorder(conf)

        if job:
            spider.current_job = job
            spider._job_id = job.job_id
            spider._bind_runtime_context(job)
            spider.job_context = create_job_context(job, spider.record_sql, spider.rv_sql, spider.mr)
            spider.tasks = spider.job_context.tasks
            spider.tasks_path = spider.job_context.tasks_path

        return spider

    def _remove_cache(self):
        domain_cache = temp_p.joinpath(f"{self.name}_domain.txt")
        if domain_cache.exists():
            os.remove(domain_cache)

    def _finish_counters(self, stats):
        downloaded_count = stats.get_value('file_status_count/downloaded', 0)
        uptodate_count = stats.get_value('file_status_count/uptodate', 0)
        total = self.job_context.total if self.job_context else self.total
        return downloaded_count, uptodate_count, downloaded_count + uptodate_count, total

    def close(self, reason):
        stats = self.crawler.stats
        downloaded_count, uptodate_count, processed_count, total = self._finish_counters(stats)
        if self.current_job:
            self.current_job.finish_reason = reason
            incomplete = reason == "finished" and total and processed_count < total
            self.current_job.runtime_success = reason == "finished" and not incomplete
            self.current_job.runtime_error = (
                f"incomplete download: processed={processed_count}/{total}, downloaded={downloaded_count}, uptodate={uptodate_count}"
                if incomplete else
                reason if "error" in reason else None
            )
        try:
            self.makesure_tasks_status()
        except Exception as e:
            self.logger.error(f"Error closing resources: {e}")
            reason = "error"
        sleep(0.3)
        self.record_sql.close()
        self.rv_sql.close()
        if reason == "ConnectionResetError":
            return
        elif reason == "finished":
            self._handle_finished_status(stats)
        elif "error" in reason:
            self._handle_error_status(reason)
            self._remove_cache()

    def _handle_finished_status(self, stats):
        if 'init' in self.process_state.process:
            self.say(font_color('unknown init end, if cgs not work, please contact maintainer with log', cls='theme-tip'))
            return
        downloaded_count, uptodate_count, processed_count, total = self._finish_counters(stats)
        exception_count = stats.get_value('process_exception/count', 0)
        remove_domain_cache = bool(self.remove_domain_cache_on_finished_miss)
        if total and processed_count < total:
            missing_count = total - processed_count
            self.say(font_color(f'miss: new[{downloaded_count}], cache[{uptodate_count}], miss[{missing_count}]<br>',
                cls='theme-err', size=3))
            if remove_domain_cache:
                self._remove_cache()
        elif total != 0 and processed_count > 0:
            if downloaded_count:
                _str = f'{self.res.finished_success % downloaded_count}'
                if uptodate_count:
                    _str = f'cache[{uptodate_count}] / {_str}'
            self.say(font_color(_str, cls='theme-success', size=4))
        elif not downloaded_count and exception_count > 0:
            last_exception = stats.get_value("process_exception/last_exception", "")
            self.say(font_color(
                f'<br>{self.res.finished_err % last_exception}<br>log path/日志文件地址: [{self.settings.get("LOG_FILE")}]',
                cls='theme-err', size=3))
            if remove_domain_cache:
                self._remove_cache()
        else:
            self.say(font_color(f'{self.res.finished_empty}<br>', cls='theme-highlight', size=4))

    def _handle_error_status(self, reason):
        if reason.startswith("[error]"):
            self.say(font_color(f"[httpok]{reason}" if "http" in reason else reason, cls='theme-err', size=4))
        error_guides = (self.res.close_check_log_guide1, self.res.close_check_log_guide2, self.res.close_check_log_guide3)
        self.say(
            font_color(f'{self.res.close_backend_error}<br>', size=4) +
            font_color('<br>'.join(error_guides), cls='theme-tip', size=3) + "<br>" +
            font_color(f'log path/日志文件地址: [{self.settings.get("LOG_FILE")}]', cls='theme-err', size=3)
        )


class BaseComicSpider2(BaseComicSpider):
    """skip find page from book_page"""

    def parse_section(self, response):
        self._emit_process('parse section')

        meta = response.meta
        ep = meta.get('episode')
        if ep:
            book = ep.from_book
            this_uuid, this_md5 = ep.id_and_md5()
            ep_name = ep.name
            this_info = ep
        else:
            book = meta.get('book')
            this_uuid, this_md5 = book.id_and_md5()
            ep_name = None
            this_info = book
        book.name = PresetHtmlEl.sub(book.name)
        self._assert_task_not_downloaded(this_info)
        self.say(f'''📜 《{this_info.display_title}》''')
        results = self.frame_section(response)
        this_info.pages = len(results)
        self.set_task(this_info)
        for page, url in results.items():
            item = ComicspiderItem()
            item['title'] = book.name
            item['page'] = str(page)
            item['section'] = ep_name
            item['image_urls'] = [url]
            item['uuid'] = this_uuid
            item['uuid_md5'] = this_md5
            if self.job_context:
                self.job_context.total += 1
            self.total += 1
            yield item
        self._emit_process('fin')


class BaseComicSpider3(BaseComicSpider):
    """Antique grade! No episode, but three or more jump"""

    def parse_section(self, response):
        self._emit_process('parse section')
        book = response.meta.get('book')

        if "task_validated" not in response.meta:
            self._assert_task_not_downloaded(book)

        sec_page = response.meta.get('sec_page', 1)
        self.say(f'<br>📜 《{book.name}》 page-of-{sec_page}')
        results, next_page_flag = self.frame_section(response)
        if next_page_flag:
            meta = deepcopy(response.meta)
            meta.update(frame_results=results, sec_page=sec_page + 1, task_validated=1)
            yield scrapy.Request(url=next_page_flag, callback=self.parse_section, meta=meta)
        else:
            book.name = PresetHtmlEl.sub(book.name)
            book.pages = len(results)
            self.set_task(book)
            for page, url in results.items():
                meta = {'book': book, 'page': page}
                yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=meta)


class FormReqBaseComicSpider(BaseComicSpider):
    """e.g. mangabz"""
    body = BodyFormat()

    def start_requests(self):
        self.preready()
        yield from self.iter_download_requests(self.current_job)
