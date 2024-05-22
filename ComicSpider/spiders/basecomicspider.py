import re
import time
from abc import abstractmethod
import scrapy
import requests
from time import sleep
from copy import deepcopy
from utils import font_color, Queues, State
from ComicSpider.items import ComicspiderItem


class BaseComicSpider(scrapy.Spider):
    """ComicSpider基类
    执行顺序为：： 1、GUI获得keyword >> 每个爬虫编写的mapping与search_url_head（网站搜索头）>>> 得到self.search_start开始常规scrapy\n
    2、清洗，然后parse执行顺序为(1)parse -- frame_book --> (2)parse_section -- frame_section -->
    (3)frame_section --> yield item\n
    3、存文件：略（统一标题命名）"""
    exp_txt = (f"""<br>{'{:=^80}'.format('message')}<br>请于【 输入序号 】框输入要选的序号  """)

    input_state = None
    text_browser_state = None
    process_state = None
    queues = None

    num_of_row = 5
    total = 0
    search_url_head = NotImplementedError('需要自定义搜索网址')
    img_domain = None
    # mappings自定义关键字对应网址
    kind = {}
    mappings = {}

    class TextBrowser:
        def __init__(self, queue, state):
            self.queue = queue
            self.state = state

        def error_text(self, *args):
            _ = """选择{1}步骤时错误的输入：{0}<br> {2}""".format(*args)
            self.send(f"{_:=>15}")

        def send(self, _text):
            self.state.text = _text
            Queues.send(self.queue, '', self.state)

    text_browser: TextBrowser = None

    def send(self, queue_name, state: State):
        return Queues.send(self.queues, queue_name, state)

    def recv(self, queue_name) -> State:
        flag = False
        while not flag:
            flag = Queues.recv(self.queues, queue_name)
            time.sleep(1)
        return flag

    def refresh_state(self, state_name, state):
        _ = getattr(self, state_name)
        if state != _:
            self.__setattr__(state_name, state)

    def start_requests(self):
        search_start = self.search
        self.search_start = deepcopy(search_start)
        yield scrapy.Request(self.search_start, dont_filter=True)

    @property
    def search(self):
        self.process_state.process = 'search'
        self.send('ProcessState', self.process_state)
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
        self.send('ProcessState', self.process_state)
        frame_book_results = self.frame_book(response)

        # GUI交互产生的凌乱逻辑，待优化
        # 每get一次阻塞scrapy，等GUI操作

        # selected = self.get_current('choose')  # 阻塞scrapy，等GUI选择
        self.refresh_state('input_state', self.recv('InputFieldState'))
        results = self.elect_res(self.input_state.indexes, frame_book_results, step='漫画')
        if results is None or not len(results):
            # self.get_current()
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

    def frame_book_print(self, frame_results, extra=" →_→ 鼠标移到序号栏有教输入规则<br>"):
        self.text_browser.send(self.search_start)
        self.text_browser.send(f"{''.join(self.exp_txt)}{font_color(extra, color='blue')}"
                               if len(frame_results) else
                               f"{'✈' * 15}{font_color('什么意思？唔……就是你搜的在放✈(飞机)，retry拯救', color='red', size=5)}")
        return frame_results

    # ==============================================
    def parse_section(self, response):
        """ ！！！！ 解决非漫画无章节情况下直接下最终页面"""
        self.process_state.process = 'parse section'
        self.send('ProcessState', self.process_state)

        self.text_browser.send(f'<br>{"{:=^65}".format("message")}')

        title = response.meta.get('title')
        self.text_browser.send(f'<br>{"=" * 15} 《{title}》')
        frame_sec_result = self.frame_section(response)

        if None:  # -*- 判断GUI的retry_btn与crawl/next_btn 分岔
            self.text_browser.send(
                font_color('<br>notice !! 多选书的情况下retry后台会相当复杂，单选无视此条信息<br>', size=5))
            yield scrapy.Request(url=self.search_start, callback=self.parse, dont_filter=True)
        else:
            # choose = self.get_current('choose')
            self.refresh_state('input_state', self.recv('InputFieldState'))
            choose = self.input_state.indexes
            results = self.elect_res(choose, frame_sec_result, step='章节')
            if results is None or not len(results):
                self.text_browser.send('<br><br><br>notice !! OK 视为放弃此书 / cancel 视为重选' * 3)
                self.logger.info(f'no result return, choose_input is wrong: {choose}')
                if None:  # self.get_current('retry'):
                    yield scrapy.Request(url=response.url, callback=self.parse_section, dont_filter=True, meta={'title': title})
            else:
                self.text_browser.send(f'{"{:*^55}".format("最后确认选择")}<br>{"-" * 10}《{title}》 所选序号: {choose}')
                for result in results:
                    self.text_browser.send(f"{result[0]:>>55}")
                self.text_browser.send(f"<br>notice !! OK 视为爬取上述内容 / cancel 视为放弃此步骤<br>")
                if None:  # self.get_current('retry'):  # -*- ensure dia 分岔
                    # yield scrapy.Request(url=response.url, callback=self.parse_section, meta={'title': title}, dont_filter=True)
                    pass
                else:
                    self.session = requests.session()
                    for section, section_url in results:
                        url_list = self.mk_page_tasks(url=section_url, session=self.session)  # 用scrapy的next吧
                        self.text_browser.send(
                            font_color(f"<br>{'=' * 15}\tnow start 爬取《{title}》章节：{section}<br>", color='blue', size=5))
                        meta = {'title': title, 'section': section}
                        for url in url_list:
                            yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=meta)
                self.process_state.process = 'fin'
                self.send('ProcessState', self.process_state)

    @abstractmethod
    def frame_section(self, response) -> dict:
        """最终返回值按此数据格式返回
        :return dict: {1: [section1, section1_url], 2: [section2, section2_url]……} 
        """
        pass

    def frame_section_print(self, frame_results, print_example, print_limit=5, extra=' ←_← 点击【开始爬取！】 <br>'):
        print_npc = []
        for x, result in frame_results.items():
            print_npc.append(print_example.format(str(x), result[0]).strip())
            if x % print_limit==0:
                self.text_browser.send(str(print_npc).replace("'", "").replace("[", "").replace("]", ""))
                print_npc = []
        self.text_browser.send(str(print_npc).replace("'", "").replace("[", "").replace("]", "")) if len(
            print_npc) else None
        self.text_browser.send(''.join(self.exp_txt) + font_color(extra, color="purple"))
        return frame_results

    # ==============================================
    def parse_fin_page(self, response):
        pass

    def mk_page_tasks(self, *arg, **kw):
        """做这个中间件预想是：1、每一话预请求第一页，从resp中直接清洗获取items信息;
        2、设立规则处理response.follow也许可行"""
        pass

    def elect_res(self, elect: list, frame_results: dict, **kw) -> list:
        """简单判断elect，返回选择的frame
        :param elect: [1,2,3,4,……]
        :param frame_results: {1: [title1, title1_url], 2: [title2, title2_url]……}
        :return: [[title1, title1_url], [title2, title2_url]……]
        """
        selected = frame_results.keys() if elect==[0] else elect
        self.text_browser.send(kw['extra_info']) if 'extra_info' in kw else None
        try:
            results = [frame_results[i] for i in selected]
        except Exception as e:
            # self.print_error_text(e.args, kw['step'], font_color("点击retry这步重来，不要选没得选的!", size=5))
            self.text_browser.error_text(e.args, kw['step'], font_color("点击retry这步重来，不要选没得选的!", size=5))
            self.logger.error(f'error elect: {e.args}, traceback:{str(type(e))}:: {str(e)}')
        else:
            return results

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        spider.text_browser = spider.TextBrowser(getattr(spider.queues, 'TextBrowser'), spider.text_browser_state)
        return spider

    def close(self, reason):
        Queues.clear(iter(self.queues))
        try:
            self.session.close()
        except:
            pass
        sleep(0.3)
        self.text_browser.send(font_color('<br>~~~后台完成任务了 ヾ(￣▽￣ )Bye~Bye~<br>', color='green', size=6)
                         if self.total!=0 else font_color('~~~后台挂了…(￣┰￣*)………若非自己取消可去看日志文件报错', size=5))


class BaseComicSpider2(BaseComicSpider):
    """skip find page from book_page"""

    def parse_section(self, response):
        self.process_state.process = 'parse section'
        self.send('ProcessState', self.process_state)

        title = response.meta.get('title')
        self.text_browser.send(f'<br>{"=" * 15} 《{title}》')
        results = self.frame_section(response)  # {1: url1……}
        for page, url in results.items():
            item = ComicspiderItem()
            item['title'] = title
            item['page'] = str(page)
            item['section'] = 'meaningless'
            item['image_urls'] = [f'{url}']
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.send('ProcessState', self.process_state)
