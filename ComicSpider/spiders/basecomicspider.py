import logging
from copy import deepcopy
import scrapy
from scrapy import Request
from utils import clear_queue


class BaseComicSpider(scrapy.Spider):
    exp_txt = (f"""\n{'{:=^65}'.format('message')}\n
            请于【 选择序号框输入要选的序号  """)
    current_status = {}

    step = 'loop'
    print_Q = None
    current_Q = None
    step_Q = None
    bar = None

    def print_error_text(self, *args):
        self.print_Q.put('=' * 15, """进行{1}步骤时错误输入了： {0}\n也可能有一部分{2}了,接下来{3}""".format(*args))

    def step_put(self, step):
        if self.step_Q.full():
            a = self.step_Q.get_nowait()
        self.step_Q.put_nowait(step)

    def start_requests(self):
        start_search = self.search
        self.start_search = deepcopy(start_search)
        yield Request(start_search, dont_filter=True)

    @property
    def search(self):
        self.step = 'search'
        self.step_put(self.step)
        self.keyword = self.current_Q.get()['keyword']
        return f'sample/search.asp?kw={self.keyword}'

    # ==============================================
    def parse(self, response):
        self.step = 'parse'  # parse_book == parse
        self.step_put(self.step)
        frame_book = self.frame_book(response)

        if self.current_Q.get()['retry']:               # -*- 判断GUI的retry_btn与crawl/next_btn 分岔
            yield scrapy.Request(url=self.search, callback=self.parse, dont_filter=True)
        else:
            self.choose = self.current_Q.get()['choose']
            results = self.__yield_what(self.choose, frame_book, yield_url_frame='frame_[i][1]', meta_frame="{'title': frame_[i][0]}",
                                        error_text=['漫画', '进入下一步选章节', '继续下一步骤选章节'], )
            if not len(results) or results is None:
                self.print_Q.put(f'\n{"=" * 10}info: 输入错了吧？无结果返回耶，点击retry拯救\n')
                logging.info(f'no result return, choose_input is wrong: {self.choose}')
                self.current_Q.get()
                yield scrapy.Request(url=self.search, callback=self.parse, dont_filter=True)
            else:
                for result in results:
                    yield scrapy.Request(url=result[0], callback=self.parse_section, meta=result[1], dont_filter=True)

    def frame_book(self, response):
        raise ValueError(f'class {self.__class__.__name__} haven\'t been define frame_func')

    # ==============================================
    def parse_section(self, response):
        self.step = 'parse section'
        self.step_put(self.step)
        self.print_Q.put(f'\n{"{:=^65}".format("message")}')

        title = response.meta.get('title')
        self.print_Q.put(f'\n{"="*15} 《{title}》')
        frame_section = self.frame_section(response)

        if self.current_Q.get()['retry']:                # -*- 判断GUI的retry_btn与crawl/next_btn 分岔
            self.print_Q.put('<br>notice !! 多选书的情况下重选相当于死亡， 单选书的话请无视')
            yield scrapy.Request(url=self.start_search, callback=self.parse, dont_filter=True)
        else:
            self.choose = self.current_Q.get()['choose']
            results = self.__yield_what(self.choose, frame_section, yield_url_frame='frame_[i][1]',
                                        meta_frame="{'info': ['%s', frame_[i][0]]}" % title,
                                        error_text=['章节', '开爬', '选对的章节将开爬'], )

            if not len(results) or results is None:
                self.print_Q.put(f'\n{"=" * 10}info: {self.choose} ? 输入错了吧？无结果返回耶 ~')
                self.print_Q.put('<br><br><br>notice !! OK 视为放弃此步骤 / cancel 视为重选'*3)
                logging.info(f'no result return, choose_input is wrong: {self.choose}')
                if self.current_Q.get()['retry']:
                    yield scrapy.Request(url=response.url, callback=self.parse_section, dont_filter=True, meta={'title': title})
            else:
                self.print_Q.put(f'{"{:*^55}".format("最后确认选择")}\n\n{"-"*10}《{title}》 所选序号: {self.choose}')
                for result in list(results):
                    self.print_Q.put(f"{'>'*7} {result[1]['info'][1]}")
                self.print_Q.put(f"<br>notice !! OK 视为爬取上述内容 / cancel 视为放弃此步骤")
                if self.current_Q.get()['retry']:                               # -*- ensure dia 分岔
                    # yield scrapy.Request(url=response.url, callback=self.parse_section, meta={'title': title}, dont_filter=True)
                    pass
                else:
                    for result in list(results):
                        url_list = self.middle_utils(url=result[0])
                        self.print_Q.put(f"\n{'=' * 15}\tnow start 爬取《{title}》章节：{result[1]['info'][1]}")
                        for url in url_list:
                            yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=result[1])
                self.step = 'fin'
                self.step_put(self.step)

    def frame_section(self, response):
        raise ValueError(f'class {self.__class__.__name__} haven\'t been define frame_func')

    # ==============================================
    def parse_fin_page(self, response):
        raise ValueError(f'class {self.__class__.__name__} haven\'t been define fin_parse_func')

    def middle_utils(self, _type='listurl', *arg, **kw):
        # do something schedule..then
        # return params // yield scrapy.Request

        def list_url(**kw):
            return list(kw['url'])
        utils = {'listurl': list_url}
        schedule = utils[_type]
        return schedule(**kw)

    def __yield_what(self, _input, frame_, **kw):
        result = list()
        try:
            _input = frame_.keys() if _input == [0] else _input
            self.print_Q.put(kw['extra_info']) if 'extra_info' in kw else None
            for i in _input:
                result.append([eval(kw['yield_url_frame']), eval(kw['meta_frame']), ])
        except Exception as e:
            self.print_error_text(e, *kw['error_text'])
            logging.error(f'input error from yield_what : {e}')
        finally:
            return result

    def close(spider, reason):
        clear_queue((spider.print_Q, spider.step_Q, spider.current_Q))
        spider.print_Q.put('\n~~~spider（后台）完成任务光荣死去了 ヾ(￣▽￣)Bye~Bye~\n\n')
