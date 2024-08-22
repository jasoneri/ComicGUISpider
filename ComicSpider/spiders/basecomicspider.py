import re
from abc import abstractmethod
from copy import deepcopy
from time import sleep

import httpx
import scrapy

from variables import *
from assets import res as ori_res
from ComicSpider.items import ComicspiderItem
from utils import font_color, Queues, QueuesManager, PresetHtmlEl, correct_domain
from utils.processed_class import (
    TextBrowserState, ProcessState, QueueHandler, refresh_state
)


class SayToGui:
    res = ori_res.SPIDER.SayToGui
    exp_txt = res.exp_txt
    exp_preview = font_color(res.exp_preview, color='chocolate') + res.exp_replace_keyword

    def __init__(self, spider, queue, state):
        self.spider = spider
        if spider.name in SPECIAL_WEBSITES:
            self.exp_txt = self.exp_txt.replace(self.res.exp_replace_keyword, self.exp_preview)
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

    def frame_book_print(self, frame_results, extra=None):
        extra = extra or self.res.frame_book_print_extra
        self(self.spider.search_start)  # 每个爬虫不一样，进这里自动吧
        self(
            f"{''.join(self.exp_txt)}{font_color(extra, color='blue')}"
            if len(frame_results) else
            f"{'✈' * 15}{font_color(self.res.frame_book_print_retry_tip, color='red', size=5)}"
        )
        return frame_results

    def frame_section_print(self, frame_results, print_example, print_limit=5, extra=None):
        extra = extra or self.res.frame_section_print_extra
        print_npc = []
        for x, result in frame_results.items():
            print_npc.append(print_example.format(str(x), result[0]).strip())
            if x % print_limit == 0:
                self(str(print_npc).replace("'", "").replace("[", "").replace("]", ""))
                print_npc = []
        self(str(print_npc).replace("'", "").replace("[", "").replace("]", "")) if len(
            print_npc) else None
        self(''.join(self.exp_txt) + font_color(extra, color="purple"))
        return frame_results


class BaseComicSpider(scrapy.Spider):
    """ComicSpider基类
    执行顺序为：： 1、GUI获得keyword >> 每个爬虫编写的mapping与search_url_head（网站搜索头）>>> 得到self.search_start开始常规scrapy\n
    2、清洗，然后parse执行顺序为(1)parse -- frame_book --> (2)parse_section -- frame_section -->
    (3)frame_section --> yield item\n
    3、存文件：略（统一标题命名）"""

    __res = ori_res.SPIDER
    input_state = None
    text_browser_state = TextBrowserState(text='')
    process_state = ProcessState(process='init')
    queue_port: int = None
    manager: QueuesManager = None
    Q: QueueHandler = None
    say: SayToGui = None
    ua = {}

    num_of_row = 5
    total = 0
    search_url_head = NotImplementedError(__res.search_url_head_NotImplementedError)
    domain = None  # REMARK(2024-08-16): 使用时用self.domain, 保留作出更改的余地
    kind = {}
    # e.g. kind={'作者':'xx_url_xx/artist/', ...}  当输入为'作者张三'时，self.search='xx_url_xx/artist/张三'
    mappings = {}  # mappings自定义关键字对应"固定"uri

    def start_requests(self):
        self.refresh_state('input_state', 'InputFieldQueue')
        search_start = self.search
        if self.domain not in search_start:
            search_start = correct_domain(self.domain, search_start)
        self.search_start = deepcopy(search_start)
        yield scrapy.Request(self.search_start, dont_filter=True)

    @property
    def search(self):
        self.process_state.process = 'search'
        self.Q('ProcessQueue').send(self.process_state)
        keyword = self.input_state.keyword
        kind = re.search(rf"(({')|('.join(self.kind)}))(.*)", keyword) if bool(self.kind) else None
        if keyword in self.mappings.keys():
            search_start = self.mappings[keyword]
        elif bool(kind):
            search_start = f"{self.kind[kind.group(1)]}{kind.group(len(self.kind) + 2)}/"
        else:
            search_start = f'{self.search_url_head}{keyword}'
        return search_start

    # ==============================================
    def parse(self, response):
        self.process_state.process = 'parse'
        self.Q('ProcessQueue').send(self.process_state)
        frame_book_results = self.frame_book(response)

        self.refresh_state('input_state', 'InputFieldQueue', monitor_change=True)
        results = self.elect_res(self.input_state.indexes, frame_book_results, step=self.__res.parse_step)
        if results is None or not len(results):
            yield scrapy.Request(url=self.search, callback=self.parse, dont_filter=True)
        else:
            for title, title_url in results:
                meta = {"title": title}
                yield scrapy.Request(url=title_url, callback=self.parse_section, meta=meta, dont_filter=True)

    @abstractmethod
    def frame_book(self, response) -> dict:
        """最终返回值按此数据格式返回
        :return dict: {1: [title1, title1_url], 2: [title2, title2_url]……} 
        """
        pass

    # ==============================================
    def parse_section(self, response):
        """ ！！！！ 解决非漫画无章节情况下直接下最终页面"""
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)

        title = response.meta.get('title')
        self.say(f'<br>{"{:=^65}".format("message")}')
        self.say(f'<br>{"=" * 15} 《{title}》')
        frame_sec_result = self.frame_section(response)

        self.refresh_state('input_state', 'InputFieldQueue', monitor_change=True)
        choose = self.input_state.indexes
        results = self.elect_res(choose, frame_sec_result, step=self.__res.parse_sec_step)
        if results is None or not len(results):
            self.say(f'<br><br><br>{self.__res.parse_sec_not_match}')
            self.logger.info(f'no result return, choose_input is wrong: {choose}')
        else:
            self.say(f'{"-" * 10}《{title}》 {self.__res.parse_sec_selected}: {choose}')
            for result in results:
                self.say(f"{result[0]:>>55}")
            self.session = httpx.Client()
            for section, section_url in results:
                url_list = self.mk_page_tasks(url=section_url, session=self.session)  # 用scrapy的next吧
                now_start_crawl_desc = self.__res.parse_sec_now_start_crawl_desc % title
                self.say(font_color(f"{'=' * 15}\t{now_start_crawl_desc}：{section}<br>", color='blue', size=5))
                meta = {'title': title, 'section': section}
                for url in url_list:
                    yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=meta)

    @abstractmethod
    def frame_section(self, response) -> dict:
        """最终返回值按此数据格式返回
        :return dict: {1: [section1, section1_url], 2: [section2, section2_url]……} 
        """
        pass

    # ==============================================
    def parse_fin_page(self, response):
        pass

    def mk_page_tasks(self, *arg, **kw) -> iter:
        """做这个中间件预想是：1、每一话预请求第一页，从resp中直接清洗获取items信息;
        2、设立规则处理response.follow也许可行"""
        ...

    def elect_res(self, elect: list, frame_results: dict, **kw) -> list:
        """简单判断elect，返回选择的frame
        :param elect: [1,2,3,4,……]
        :param frame_results: {1: [title1, title1_url], 2: [title2, title2_url]……}
        :return: [[title1, title1_url], [title2, title2_url]……]
        """
        selected = frame_results.keys() if elect == [0] else elect
        self.say(kw['extra_info']) if 'extra_info' in kw else None
        try:
            results = [frame_results[i] for i in selected]
        except Exception as e:
            self.logger.error(f'error elect: {e.args}, traceback:{str(type(e))}:: {str(e)}')
        else:
            return results

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        spider.mappings.update(spider.settings.get('CUSTOM_MAP') or {})

        spider.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue',
            address=('127.0.0.1', spider.queue_port), authkey=b'abracadabra'
        )
        spider.manager.connect()
        q = getattr(spider.manager, 'TextBrowserQueue')()
        spider.Q = QueueHandler(spider.manager)
        spider.process_state.process = 'spider_init'
        spider.Q('ProcessQueue').send(spider.process_state)

        spider.say = SayToGui(spider, q, spider.text_browser_state)
        return spider

    def close(self, reason):
        try:
            del self.manager
            self.session.close()
        except:
            pass
        sleep(0.3)
        if reason == "ConnectionResetError":
            return
        elif 'init' not in self.process_state.process:
            self.say(
                font_color(f'<br>~~~{self.__res.close_success} ヾ(￣▽￣ )Bye~Bye~<br>', color='green', size=6)
                if self.total != 0 else
                font_color(f'~~~…(￣┰￣*)………{self.__res.close_backend_error}<br>', size=5) +
                font_color(self.__res.close_check_log_guide1, color='blue', size=4) +
                font_color(self.__res.close_check_log_guide2, color='blue', size=4) +
                font_color(self.__res.close_check_log_guide3, color='blue', size=4) +
                font_color(f'log path/日志文件地址: [{self.settings.get("LOG_FILE")}]', color='red', size=4)
            )

    def refresh_state(self, state_name, queue_name, monitor_change=False):
        try:
            refresh_state(self, state_name, queue_name, monitor_change)
        except ConnectionResetError:
            # logger.warning('gui非正常关闭停止爬虫(gui重启的话无视此信息)')
            self.close('ConnectionResetError')


class BaseComicSpider2(BaseComicSpider):
    """skip find page from book_page"""

    def parse_section(self, response):
        self.process_state.process = 'parse section'
        self.Q('ProcessQueue').send(self.process_state)

        title = PresetHtmlEl.sub(response.meta.get('title'))
        self.say(f'<br>{"=" * 15} 《{title}》')
        results = self.frame_section(response)  # {1: url1……}
        referer = response.url
        for page, url in results.items():
            item = ComicspiderItem()
            item['title'] = title
            item['page'] = str(page)
            item['section'] = 'meaningless'
            item['image_urls'] = [url]
            item['referer'] = referer
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
