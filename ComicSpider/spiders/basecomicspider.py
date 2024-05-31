import re
import time
from abc import abstractmethod
import scrapy
import requests
from time import sleep
from copy import deepcopy
from utils import font_color, Queues, State, QueuesManager, PresetHtmlEl
from utils.processed_class import (
    TextBrowserState, ProcessState, QueueHandler, refresh_state
)
from ComicSpider.items import ComicspiderItem


class SayToGui:
    exp_txt = (f"""<br>{'{:=^80}'.format('message')}<br>请于【 输入序号 】框输入要选的序号  """)

    def __init__(self, spider, queue, state):
        self.spider = spider
        self.text_browser = self.TextBrowser(queue, state)

    def __call__(self, *args, **kwargs):
        self.text_browser.send(*args, **kwargs)

    class TextBrowser:
        def __init__(self, queue, state):
            self.queue = queue
            self.state = state

        def error(self, *args):
            _ = """选择{1}步骤时错误的输入：{0}<br> {2}""".format(*args)
            self.send(f"{_:=>15}")

        def send(self, _text):
            self.state.text = _text
            Queues.send(self.queue, self.state, wait=True)

    def frame_book_print(self, frame_results, extra=" →_→ 鼠标移到序号栏有教输入规则<br>"):
        self(self.spider.search_start)  # 每个爬虫不一样，进这里自动吧
        self(
            f"{''.join(self.exp_txt)}{font_color(extra, color='blue')}"
            if len(frame_results) else
            f"{'✈' * 15}{font_color('什么意思？唔……就是你搜的在放✈(飞机)，retry拯救', color='red', size=5)}"
        )
        return frame_results

    def frame_section_print(self, frame_results, print_example, print_limit=5, extra=' ←_← 点击【开始爬取！】 <br>'):
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

    input_state = None
    text_browser_state = TextBrowserState(text='')
    process_state = ProcessState(process='init')
    queue_port: int = None
    manager = None
    Q = None
    say: SayToGui = None

    num_of_row = 5
    total = 0
    search_url_head = NotImplementedError('需要自定义搜索网址')
    domain = None
    # mappings自定义关键字对应网址
    _kind = {}
    mappings = {}

    def start_requests(self):
        search_start = self.search
        self.search_start = deepcopy(search_start)
        yield scrapy.Request(self.search_start, dont_filter=True)

    @property
    def kind(self):
        return self.settings.get('CUSTOM_KIND') or self._kind


    @property
    def search(self):
        self.process_state.process = 'search'
        self.Q('ProcessQueue').send(self.process_state)
        keyword = self.input_state.keyword
        kind = re.search(f"(({')|('.join(self.kind.keys())}))(.*)", keyword) if bool(self.kind) else None
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

        refresh_state(self, 'input_state', 'InputFieldQueue', monitor=True)
        results = self.elect_res(self.input_state.indexes, frame_book_results, step='漫画')
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

        refresh_state(self, 'input_state', self.Q('InputFieldQueue').recv(), monitor=True)
        choose = self.input_state.indexes
        results = self.elect_res(choose, frame_sec_result, step='章节')
        if results is None or not len(results):
            self.say('<br><br><br>没匹配到结果')
            self.logger.info(f'no result return, choose_input is wrong: {choose}')
        else:
            self.say(f'{"{:*^55}".format("最后确认选择")}<br>{"-" * 10}《{title}》 所选序号: {choose}')
            for result in results:
                self.say(f"{result[0]:>>55}")
            self.session = requests.session()
            for section, section_url in results:
                url_list = self.mk_page_tasks(url=section_url, session=self.session)  # 用scrapy的next吧
                self.say(font_color(f"<br>{'=' * 15}\tnow start 爬取《{title}》章节：{section}<br>", color='blue', size=5))
                meta = {'title': title, 'section': section}
                for url in url_list:
                    yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=meta)
            self.process_state.process = 'fin'
            self.Q('ProcessQueue').send(self.process_state)

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
        selected = frame_results.keys() if elect==[0] else elect
        self.say(kw['extra_info']) if 'extra_info' in kw else None
        try:
            results = [frame_results[i] for i in selected]
        except Exception as e:
            # self.print_error_text(e.args, kw['step'], font_color("点击retry这步重来，不要选没得选的!", size=5))
            self.say.text_browser.error(e.args, kw['step'], font_color("点击retry这步重来，不要选没得选的!", size=5))
            self.logger.error(f'error elect: {e.args}, traceback:{str(type(e))}:: {str(e)}')
        else:
            return results

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)

        spider.manager = QueuesManager.create_manager(
            'InputFieldQueue', 'TextBrowserQueue', 'ProcessQueue', 'BarQueue',
            address=('127.0.0.1', spider.queue_port), authkey=b'abracadabra'
        )
        spider.manager.connect()
        q = getattr(spider.manager, 'TextBrowserQueue')()
        spider.Q = QueueHandler(spider.manager)
        spider.input_state = spider.Q('InputFieldQueue').recv()

        spider.say = SayToGui(spider, q, spider.text_browser_state)
        return spider

    def close(self, reason):
        try:
            del self.manager
            self.session.close()
        except:
            pass
        sleep(0.3)
        self.say(font_color('<br>~~~后台完成任务了 ヾ(￣▽￣ )Bye~Bye~<br>', color='green', size=6)
                 if self.total != 0 else font_color('~~~后台挂了…(￣┰￣*)………若非自己取消可去看日志文件报错', size=5))


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
            item['image_urls'] = [f'{url}']
            item['referer'] = referer
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
