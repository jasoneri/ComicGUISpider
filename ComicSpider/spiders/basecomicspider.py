import logging
import re
from time import sleep
import scrapy
from scrapy import Request


class BaseComicSpider(scrapy.Spider):
    re_txt = None
    exp_txt = (f"\n{'{:=^70}'.format('message')}\n",
               '{:-^63}'.format(f"关于输入移步参考[1图流示例.jpg]\n{'用‘-’号识别的，别漏了打！ '*3}\t"),
               f"\n{'{:=^70}'.format('message')}")

    def print_error_text(self, *args):
        print('='*15, """进行{1}步骤时错误输入了： {0}\n也可能有一部分{2}了,接下来{3}""".format(*args))

    def start_requests(self):
        yield Request(self.search, dont_filter=True)

    @property
    def search(self):
        keyword = input(f'\n{">" * 15}输入你想要搜索的漫画关键字：')
        return f'sample/search.asp?kw={keyword}'

    # ==============================================
    def parse(self, response):
        print(f'\n{"{:=^70}".format("message")}\n')
        frame_book, input_choose = self.frame_book(response), self.judge_input(input(f'\n{">" * 15}输入要下载的漫画序号（重新新搜索输入re）：'))
        results = self.yield_what(input_choose, frame_book, yield_url_frame='frame_[i][1]', meta_frame="{'title': frame_[i][0]}",
                                  error_text=['漫画', '进入下一步选章节', '继续下一步骤选章节'], )
        if not len(results) or results is None:
            print(f'\n{"=" * 10}info: no resulr return, later will redo this book step')
            yield scrapy.Request(url=self.search, callback=self.parse)
        for result in results:
            yield scrapy.Request(url=result[0], callback=self.parse_section, meta=result[1])

    def frame_book(self, response):
        raise ValueError(f'class {self.__name__} haven\'t been define frame_func')

    # ==============================================
    def parse_section(self, response):
        print(f'\n{"{:=^70}".format("message")}\n')
        title = response.meta.get('title')
        frame_section, input_choose = self.frame_section(response), self.judge_input(
            input(f'\n{">" * 15}输入要下载的《{title}》章节序号（重新新搜索输入re）：'))
        results = self.yield_what(input_choose, frame_section, yield_url_frame='frame_[i][1]',
                                  meta_frame="{'info': ['%s', frame_[i][0]]}" % title, error_text=['章节', '开爬', '选对的章节将开爬'],)
        if results is None or not len(results):
            print(f'\n{"=" * 10}info: no result return, later will redo this 章节 step')
            yield scrapy.Request(url=response.url, callback=self.parse_section)

        for result in list(results):
            url_list = self.middle_utils(url=result[0])
            print(f"\n{'='*15}\tnow start 爬取《{title}》章节：{result[1]['info'][1]}\n")
            for url in url_list:
                yield scrapy.Request(url=url, callback=self.parse_fin_page, meta=result[1])

    def frame_section(self, response):
        raise ValueError(f'class {self.__name__} haven\'t been define frame_func')

    # ==============================================
    def parse_fin_page(self, response):
        raise ValueError(f'class {self.__name__} haven\'t been define fin_parse_func')

    def middle_utils(self, _type='listurl', **kw):
        # do something schedule..then
        # return params // yield scrapy.Request
        def list_url(**kw):
            return list(kw['url'])
        schedule = list_url if _type == 'listurl' else None
        return schedule(kw)

    def judge_input(self, _input):
        # -6 return [6]
        # -1-3-5 return [1,3,5]
        # -4~-6 return [4,5,6] | -1-4~-6 return [1,4,5,6]
        def f(s):  # example '4~-6' turn to [4,5,6]
            l = []
            ranges = s.split(r'~-')
            if len(ranges) == 1:
                l.append(ranges[0])
            else:
                for i in range(int(ranges[0]), int(ranges[1]) + 1):
                    l.append(i)
            return l
        if _input =='re':
            i_fin = _input
        else:
            while len(_input) and '-' not in _input:
                print(''.join(self.exp_txt))
                _input = input('\n' + '>' * 15 + '再给次机会输入，再错...（重新新搜索输入re）：')
            i_tnsfr = []
            i_bs = re.findall(r'(\d{1,4}~-\d{1,4})', _input)  # filter out '/d~-/d'
            for i_b in i_bs:
                _input = _input.replace(i_b, '')
                i_tnsfr.extend(f(i_b))  # extract '/d~-/d'
            _input = re.findall(r'-(\d{1,4})', _input)  # get except filter out of '/d~-/d'
            i_tnsfr.extend(_input)
            i_fin = sorted(set(map(lambda x: int(x), i_tnsfr)))
            if len(i_fin):
                print('\n=====这是你选的序号 >>>>>>>> %s <<<<<<<<\n' % i_fin)
            sleep(1.2)
        return i_fin

    def yield_what(self, _input, frame_, **kw):
        result = list()
        try:
            _input = _input if len(_input) else frame_.keys()
            if _input == 're':
                print(''.join(self.re_txt))
                sleep(1.5)
            else:
                print(kw['extra_info']) if 'extra_info' in kw else None
                for i in _input:
                    result.append([eval(kw['yield_url_frame']), eval(kw['meta_frame']), ])
        except Exception as e:
            self.print_error_text(e, *kw['error_text'])
            logging.error(f'input error from yield_what : {e}')
            sleep(2)
        finally:
            return result
