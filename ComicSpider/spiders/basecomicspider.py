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
from GUI.core.font import font_color
from utils import Queues, QueuesManager, PresetHtmlEl, temp_p, conf
from utils.processed_class import (
     TextBrowserState, ProcessState, QueueHandler, refresh_state, Url
)
from utils.website import (
    correct_domain, spider_utils_map, 
    InfoMinix, BookInfo, Episode
)
from utils.sql import SqlUtils


class SayToGui:
    res = ori_res.SPIDER.SayToGui
    exp_txt = res.exp_txt
    exp_turn_page = font_color(res.exp_turn_page, cls='theme-success')
    exp_preview = font_color(res.exp_preview, color='chocolate')
    exp_extra = f"{exp_turn_page}<br>{exp_preview}<br>{res.exp_replace_keyword}"

    def __init__(self, spider, queue, state):
        self.spider = spider
        if spider.name in SPECIAL_WEBSITES:
            self.exp_txt = self.exp_txt.replace(self.res.exp_replace_keyword, self.exp_extra)
        self.text_browser = self.TextBrowser(queue, state)

    def __call__(self, *args, **kwargs):
        self.text_browser.send(*args, **kwargs)

    class TextBrowser:
        def __init__(self, queue, state):
            self.queue = queue
            self.state = state

        def error(self, *args):
            _ = SayToGui.res.TextBrowser_error.format(*args)
            self.send(f"{_:=>15}")

        def send(self, _text):
            self.state.text = _text
            Queues.send(self.queue, self.state, wait=True)

    def frame_book_print(self, rets, fm=None, url=None, extra=None, make_preview=False):
        fm = fm or self.spider.say_fm
        fk = sorted(rets.keys())
        for idx in fk:
            self(fm.format(*rets[idx].say))
        extra = extra or self.res.frame_book_print_extra
        self(url or self.spider.search_start)  # 每个爬虫不一样，进这里自动吧
        if len(rets):
            self(rets)  
            # 向gui传送rets并赋值需要比exp_txt(crawl_only的flag) 和 PreviewBookInfoEnd 早才行
            if make_preview:
                self(f"[PreviewBookInfoEnd]{url}")
            self(f"""<hr><p class="theme-text">{''.join(self.exp_txt)}
                {font_color(extra, cls='theme-tip')}</p><br>""")
            self("[ShowKeepBooks]")  # 由于 keep_books 现放在 gui 上，所以最后用 flag 形式触发
        else:
            self(f"""{'✈' * 15}
                {font_color(self.res.frame_book_print_retry_tip, cls='theme-err', size=5)}""")
        return rets

    def frame_section_print(self, rets, fm, print_limit=5, extra=None):
        extra = extra or self.res.frame_section_print_extra
        formatted_items = [fm.format(x, ep.name).strip() for x, ep in rets.items()]
        for i in range(0, len(formatted_items), print_limit):
            batch = formatted_items[i:i + print_limit]
            self(", ".join(batch))
        self(rets)
        self(f"""<hr><p class="theme-text">{''.join(self.exp_txt)}{font_color(extra, cls='theme-highlight')}</p><br>""")
        return rets


class BaseComicSpider(scrapy.Spider):
    """ComicSpider基类
    执行顺序为：： 1、GUI获得keyword >> 每个爬虫编写的mapping与search_url_head（网站搜索头）>>> 得到self.search_start开始常规scrapy\n
    2、清洗，然后parse执行顺序为(1)parse -- frame_book --> (2)parse_section -- frame_section -->
    (3)frame_section --> yield item\n
    3、存文件：略（统一标题命名）"""

    res = ori_res.SPIDER
    input_state = None
    text_browser_state = TextBrowserState(text='')
    process_state = ProcessState(process='init')
    queue_port: int = None
    manager: QueuesManager = None
    Q: QueueHandler = None
    say: SayToGui = None
    ut = None
    sql_handler: SqlUtils = None
    ua = {}
    total = 0
    tasks = {}
    tasks_path = {}
    # 以下为继承变量
    num_of_row = 5
    search_url_head = NotImplementedError(res.search_url_head_NotImplementedError)
    domain = None  # REMARK(2024-08-16): 使用时用self.domain, 保留作出更改的余地
    book_id_url = ""  # book链接中id用%s转换符的形态，此为preview_url
    transfer_url = staticmethod(lambda _:_)  # 由preview_url转化为机器读的url
    kind = {}
    # e.g. kind={'作者':'xx_url_xx/artist/', ...}  当输入为'作者张三'时，self.search='xx_url_xx/artist/张三'
    mappings = {}  # mappings自定义关键字对应"固定"uri
    say_fm = r' [ {} ]、【 {} 】'
    frame_book_format = ['title', 'preview_url']
    turn_page_search: str = None
    turn_page_info: tuple = None

    def preready(self):
        ...

    def start_requests(self):
        self.refresh_state('input_state', 'InputFieldQueue')
        self.process_state.process = 'start_requests'
        self.preready()
        indexes = self.input_state.indexes
        if isinstance(indexes, list) and all(isinstance(s, InfoMinix) for s in indexes):
            self.process_state.process = 'parse'
            self.Q('ProcessQueue').send(self.process_state)
            self.refresh_state('input_state', 'InputFieldQueue')
            for info in indexes:
                url = info.url if info.url and info.url.startswith("http") else self.book_id_url % info.id
                yield scrapy.Request(
                    url=self.transfer_url(url), callback=self.parse_section,
                    headers={**self.ua, 'Referer': self.domain},
                    meta={'book': info} if isinstance(info, BookInfo) else {'episode': info},
                    dont_filter=True)
        else:
            search_start = self.search
            if self.domain not in search_start:
                search_start = Url(correct_domain(self.domain, search_start)).set_next(*search_start.info)
            self.search_start = deepcopy(search_start)
            meta = {"Url": self.search_start}
            yield scrapy.Request(self.search_start, dont_filter=True, meta=meta)

    @property
    def search(self) -> t.Union[Url, tuple]:
        self.process_state.process = 'search'
        self.Q('ProcessQueue').send(self.process_state)
        keyword = self.input_state.keyword
        # kind = re.search(rf"(({')|('.join(self.kind)}))(.*)", keyword) if bool(self.kind) else None
        if keyword in self.mappings.keys():
            url = self.mappings[keyword]
            search_start = Url(f"https://{self.domain}{urlparse(url).path}").set_next(*self.turn_page_info)
        # elif bool(kind):    # 应对get请求非QueryParams形式，例子如`BaseComicSpider.kind`下面注释的e.g.
        #     search_start = f"{self.kind[kind.group(1)]}{kind.group(len(self.kind) + 2)}/"
        else:
            __next_info = (self.turn_page_search,) if self.turn_page_search else self.turn_page_info
            search_start = Url(self.search_url_head + keyword).set_next(*__next_info)
        return search_start

    # ==============================================
    def parse(self, response):
        self.process_state.process = 'parse'
        self.Q('ProcessQueue').send(self.process_state)
        frame_book_results = self.frame_book(response)

        self.refresh_state('input_state', 'InputFieldQueue', monitor_change=True)
        if self.input_state.pageTurn:
            yield from self.page_turn(response)
        else:
            for book in self.input_state.indexes:
                yield scrapy.Request(url=book.url, callback=self.parse_section, meta={"book": book}, dont_filter=True)

    def page_turn(self, response):
        if not self.input_state.pageTurn:
            yield scrapy.Request(url=self.search, callback=self.parse, meta=response.meta, dont_filter=True)
        elif 'next' in self.input_state.pageTurn:
            yield from self.page_turn_(response.meta['Url'].next)
        elif 'previous' in self.input_state.pageTurn:
            yield from self.page_turn_(response.meta['Url'].prev)
        elif self.input_state.pageTurn:
            url = response.meta['Url'].jump(int(self.input_state.pageTurn))
            yield from self.page_turn_(url)

    def page_turn_(self, url, **kw):
        yield scrapy.Request(url=url, callback=self.parse, meta={"Url": url},
                             dont_filter=True, **kw)

    @abstractmethod
    def frame_book(self, response) -> dict:
        """parse book list page
        最终返回值按此数据格式返回
        :return dict: {1: book1, 2: book2……} 
        """
        pass

    # ==============================================
    def parse_section(self, response):
        """ ！！！！ 解决非漫画无章节情况下直接下最终页面"""
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)

        need_sec_next_page = self.need_sec_next_page(response)
        if need_sec_next_page:
            yield scrapy.Request(url=need_sec_next_page, callback=self.parse_section, meta=response.meta)
            return

        book = response.meta.get('book')
        self.say(f'📜 《{book.name}》')
        frame_eps_result = self.frame_section(response)

        self.refresh_state('input_state', 'InputFieldQueue', monitor_change=True)
        book = self.input_state.indexes
        if not book.episodes:
            self.say(font_color(f'<br><br>{self.res.parse_sec_not_match}<br>', cls='theme-err'))
            self.logger.info(f'no result return, choose_input is wrong')
            return
        choose = ','.join(map(str, book.episodes))
        self.say(f'📜《{book.name}》 {self.res.parse_sec_selected}: {choose}')
        if book.episodes and len(book.episodes) > 1 and int(conf.concurr_num) > 10:
            concurr_num = 8
            for slot in self.crawler.engine.downloader.slots.values():
                slot.concurrency = concurr_num
            if hasattr(self.crawler.engine.scraper, 'slot') and self.crawler.engine.scraper.slot:
                self.crawler.engine.scraper.slot.max_active_size = concurr_num
            conf.update(concurr_num=concurr_num)
            self.say(res.SPIDER.reduce_concurrency_tip % concurr_num)
        for ep in book.episodes:
            url_list = self.mk_page_tasks(url=ep.url)
            now_start_crawl_desc = self.res.parse_sec_now_start_crawl_desc % book.name
            self.say(font_color(f"📢\t{now_start_crawl_desc}：{ep}", cls='theme-tip', size=5))
            for url in url_list:
                yield scrapy.Request(url=url, callback=self.parse_fin_page, meta={'ep': ep})

    def need_sec_next_page(self, resp):
        pass

    @abstractmethod
    def frame_section(self, response) -> dict:
        """parse section list page
        最终返回值按此数据格式返回
        :return dict: {1: [section1, section1_url], 2: [section2, section2_url]……} 
        """
        pass

    # ==============================================
    def parse_fin_page(self, response):
        pass

    def mk_page_tasks(self, *arg, **kw) -> iter:
        """做这个中间件预想是：1、每一话预请求第一页，从resp中直接清洗获取items信息;
        2、设立规则处理response.follow也许可行"""
        return [kw['url']]

    def set_task(self, task_info: t.Union[BookInfo, Episode]):
        tasks_obj = task_info.to_tasks_obj()
        self.tasks[tasks_obj.taskid] = tasks_obj
        self.Q('TasksQueue').send(tasks_obj, wait=True)

    def makesure_tasks_status(self):
        if conf.isDeduplicate:
            for taskid, _ in self.tasks.items():
                if self.sql_handler.check_dupe(taskid):
                    continue
                elif len(tuple(self.tasks_path.get(taskid).iterdir())) >= self.tasks[taskid].tasks_count:
                    self.sql_handler.add(taskid)

    def refresh_state(self, state_name, queue_name, monitor_change=False):
        try:
            refresh_state(self, state_name, queue_name, monitor_change)
        except ConnectionResetError:
            # logger.warning('gui非正常关闭停止爬虫(gui重启的话无视此信息)')
            self.close('ConnectionResetError')

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        spider.mappings.update(spider.settings.get('CUSTOM_MAP') or {})

        spider.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue', 'TasksQueue',
            address=('127.0.0.1', spider.queue_port), authkey=b'abracadabra'
        )
        spider.manager.connect()
        q = getattr(spider.manager, 'TextBrowserQueue')()
        spider.Q = QueueHandler(spider.manager)
        spider.process_state.process = 'spider_init'
        spider.Q('ProcessQueue').send(spider.process_state)

        spider.say = SayToGui(spider, q, spider.text_browser_state)
        spider.sql_handler = SqlUtils()
        spider.ut = spider_utils_map[spider.name]
        return spider

    def _remove_cache(self):
        domain_cache = temp_p.joinpath(f"{self.name}_domain.txt")
        if domain_cache.exists():
            os.remove(domain_cache)

    def close(self, reason):
        stats = self.crawler.stats
        resources_to_close = (('manager', lambda: delattr(self, 'manager')),)
        try:
            for attr_name, close_func in resources_to_close:
                if hasattr(self, attr_name):
                    close_func()
            self.makesure_tasks_status()
        except Exception as e:
            self.logger.error(f"Error closing resources: {e}")
            reason = "error"
        sleep(0.3)
        self.sql_handler.close()
        if reason == "ConnectionResetError":
            return
        elif reason == "finished":
            self._handle_finished_status(stats)
        elif "error" in reason:
            self._handle_error_status(reason)
            self._remove_cache()

    def _handle_finished_status(self, stats):
        if 'init' in self.process_state.process:
            self.say(font_color('unknown init end,<br>if error occur, please contact maintainer with operation-process', cls='theme-err', size=6))
            return
        downloaded_count = stats.get_value('image/downloaded', 0)
        exception_count = stats.get_value('process_exception/count', 0)
        if self.total != 0 and downloaded_count > 0:
            self.say(font_color(f'<br>{self.res.finished_success % downloaded_count}', cls='theme-success', size=6))
        elif not downloaded_count and exception_count > 0:
            last_exception = stats.get_value("process_exception/last_exception", "")
            self.say(font_color(
                f'<br>{self.res.finished_err % last_exception}<br>log path/日志文件地址: [{self.settings.get("LOG_FILE")}]', 
            cls='theme-err', size=4))
            self._remove_cache()
        else:
            self.say(font_color(f'{self.res.finished_empty}<br>', cls='theme-highlight', size=6))

    def _handle_error_status(self, reason):
        if reason.startswith("[error]"):
            self.say(font_color(f"[httpok]{reason}" if "http" in reason else reason, cls='theme-err', size=4))
        error_guides = (self.res.close_check_log_guide1, self.res.close_check_log_guide2, self.res.close_check_log_guide3)
        self.say(
            font_color(f'{self.res.close_backend_error}<br>', size=5) +
            font_color('<br>'.join(error_guides), cls='theme-tip', size=4) + "<br>" +
            font_color(f'log path/日志文件地址: [{self.settings.get("LOG_FILE")}]', cls='theme-err', size=4)
        )


class BaseComicSpider2(BaseComicSpider):
    """skip find page from book_page"""

    def parse_section(self, response):
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)

        meta = response.meta
        # clip 流程时，meta 传送的可能是 episode
        ep = meta.get('episode')
        if ep:
            book = ep.from_book
            this_uuid, this_md5 = ep.id_and_md5()
            ep_name = ep.name
            this_info = ep
        else:
            book = meta.get('book')
            this_uuid, this_md5 = book.id_and_md5()
            ep_name = 'meaningless'
            this_info = book
        book.name = PresetHtmlEl.sub(book.name)
        if not conf.isDeduplicate or not (conf.isDeduplicate and self.sql_handler.check_dupe(this_md5)):
            self.say(f'''📜 《{this_info.display_title}》''')
            results = self.frame_section(response)  # {1: url1……}
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
                self.total += 1
                yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)


class BaseComicSpider3(BaseComicSpider):
    """Antique grade! No episode, but three or more jump
    e.g. ehentai
    """

    def parse_section(self, response):
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)
        book = response.meta.get('book')
        
        if "check_dupe_pass" in response.meta:
            check_dupe_pass = 1
        else:
            _, this_md5 = book.id_and_md5()
            check_dupe_pass = not conf.isDeduplicate or not self.sql_handler.check_dupe(this_md5)
        
        if check_dupe_pass:
            sec_page = response.meta.get('sec_page', 1)
            self.say(f'<br>📜 《{book.name}》 page-of-{sec_page}')
            results, next_page_flag = self.frame_section(response)
            if next_page_flag:
                meta = deepcopy(response.meta)
                meta.update(frame_results=results, sec_page=sec_page + 1, check_dupe_pass=1)
                yield scrapy.Request(url=next_page_flag, callback=self.parse_section, meta=meta)
            else:
                book.name = PresetHtmlEl.sub(book.name)
                book.pages = len(results)
                self.set_task(book)
                for page, url in results.items():
                    meta = {'book': book, 'page': page}
                    yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=meta)


class BodyFormat:
    page_index_field = "pageindex"
    dic = {}

    def __init__(self, **dic):
        self.dic.update(**dic)

    def update(self, **dic):
        self.dic.update(**dic)


class FormReqBaseComicSpider(BaseComicSpider):
    """e.g. mangabz"""
    body = BodyFormat()

    def start_requests(self):
        self.refresh_state('input_state', 'InputFieldQueue')
        try:
            self.process_state.process = 'start_requests'
            self.preready()
            search_start = self.search
            if self.domain not in search_start:
                search_start = correct_domain(self.domain, search_start)
        except Exception as e:
            raise e
        else:
            self.search_start = deepcopy(search_start)
            yield scrapy.FormRequest(self.search_start, formdata=self.body.dic,
                                     dont_filter=True, meta={"Body": self.body})

    def page_turn(self, response):
        _ = int(response.meta['Body'].dic[self.body.page_index_field])
        if not self.input_state.pageTurn:
            yield scrapy.FormRequest(url=self.search, callback=self.parse, formdata=response.meta['Body'].dic,
                                     meta=response.meta, dont_filter=True)
        elif 'next' in self.input_state.pageTurn:
            response.meta['Body'].dic[self.body.page_index_field] = f"{_ + 1}"
            yield from self.page_turn_(response)
        elif 'previous' in self.input_state.pageTurn:
            if _ - 1 <= 0:
                response.meta['Body'].dic[self.body.page_index_field] = 1
                self.say(self.res.page_less_than_one)
            else:
                response.meta['Body'].dic[self.body.page_index_field] = f"{_ - 1}"
            yield from self.page_turn_(response)
        elif self.input_state.pageTurn:
            response.meta['Body'].dic[self.body.page_index_field] = str(self.input_state.pageTurn)
            yield from self.page_turn_(response)

    def page_turn_(self, resp, **kw):
        yield scrapy.FormRequest(url=resp.request.url, callback=self.parse, formdata=resp.meta['Body'].dic,
                                 meta={"Body": resp.meta['Body']}, dont_filter=True, **kw)
