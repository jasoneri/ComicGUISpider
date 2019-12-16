# -*- coding: utf-8 -*-
import scrapy
import re
from ComicSpider.items import ComicspiderItem
from time import sleep
from scrapy.http import Request

class Comic90mhSpider(scrapy.Spider):
    name = 'comic90mh'
    allowed_domains = ['m.90mh.com']
    cb_re_txt = ('\n',
                 '{:=^70}'.format('message'),
                 '\n如上述列表显示内容不理想，可在以下网址搜索想要的内容再返回下载\n'
                 r'http://m.90mh.com/search/?keywords=' + '\n',
                 '{:=^70}'.format('message'))
    # cs_exp_txt = ('\n',
    #               '{:=^70}'.format('message'),
    #               '\n章节示例：-1、<第一话>  -2、<第2、3话>  -3、<第4话>  -4、<第5~7话> -5、<第8话>\n\n'
    #               '输入   -1-3-5   表示下载 <第一话>与<第4话>与<第8话>\n'
    #               '输入   -2~-4   表示下载 <第2、3话>与<第4话>与<第5~7话> （中间符合为~）\n'
    #               '输入   -3  表示下载 <第4话>  || （输入均为英标） PS：直接回车表示全部集数下载\n',
    #               '{:=^70}'.format('message'),)
    cs_exp_txt = ('\n',
                  '{:=^70}'.format('message'),
                  '\n{:-^63}\n'.format('关于输入移步参考[1图流示例.jpg]\n'
                                       '用‘-’号识别的，别漏了打！ \t用‘-’号识别的，别漏了打！ \t用‘-’号识别的，别漏了打！ \t'),
                  '{:=^70}'.format('message'),)

    def start_requests(self):
        yield Request(self.search, dont_filter=True)

    @property
    def search(self):
        keyword = input('\n' + '>' * 15 + '输入你想要搜索的漫画关键字：')
        return r'http://m.90mh.com/search/?keywords=%s' % keyword

    @property
    def error_text(self):
        return self._error_text

    @error_text.setter
    def error_text(self, args):
        error_text = ('=' * 10,
                      '\t出错原因为...你输入了不存在的这个 >>> %s <<<' % args[0],
                      '\n但是！！！ 如果你前面输对序号，对应{}将在10秒后{}\n'.format(args[1], args[2]),
                      '如想重来就右上角 X 或 {} (以后序号不要乱填！) \n'.format(args[3]),
                      '{:=^70}'.format('message') + '\n')
        print(''.join(error_text))

    def parse(self, response):
        print('\n', '{:=^70}'.format('message'), '\n')
        i_b, c_b = self.choose_book(response)
        try:
            if len(i_b):
                if i_b=='re':
                    print(''.join(self.cb_re_txt))
                    yield scrapy.Request(self.search, callback=self.parse)
                else:
                    for i in i_b:
                        yield scrapy.Request(c_b[i][1], callback=self.parse_book, meta={'title': c_b[i][0]})
            else:
                for i in list(c_b.keys()):
                    yield scrapy.Request(c_b[i][1], callback=self.parse_book, meta={'title': c_b[i][0]})
        except Exception as e:
            self.error_text(e, '漫画', '进入下一步选章节', '继续下一步骤选章节')
            sleep(10)

    def choose_book(self, response):
        c_b = {}
        # example = '{0:^3}\t{1:{5}<25}\t{2:{5}<18}\t{3:^10}\t{4:{5}^20}'
        example_b = '-{}\t《{}》\t【{}】\t/{}/\t<{}>'
        print(example_b.format('序号', '漫画名', '作者', '更新时间', '最新章节') + '\n')
        targets = response.xpath('//div[@class="itemBox"]')  # sign -*-
        for x in range(len(targets)):
            title = targets[x].xpath('.//a[@class="title"]/text()').get().strip()
            url = targets[x].xpath('.//a[@class="title"]/@href').get()
            author = targets[x].xpath('.//p[@class="txtItme"]/text()').get()
            refresh_time = targets[x].xpath('.//span[@class="date"]/text()').get().strip()
            refresh_section = targets[x].xpath('.//a[@class="coll"]/text()').get().strip()
            print(example_b.format(str(x + 1), title, author, refresh_time, refresh_section, chr(12288)))
            c_b[x + 1] = [title, url]
        print(''.join(self.cs_exp_txt))
        i_b = input('\n' + '>' * 15 + '输入要下载的漫画序号（重新新搜索输入re）：')
        self.judge_input = i_b
        return [self.judge_input, c_b]

    def parse_book(self, response):
        print('\n', '{:=^70}'.format('message'), '\n')
        title = response.meta.get('title')
        i_s, c_s = self.choose_section(response, title)
        try:
            if len(i_s):
                if i_s=='re':
                    print(''.join(self.cb_re_txt))
                    yield scrapy.Request(response.url, callback=self.parse_book)
                else:
                    print('\n' + '=' * 15 + '\t即将开始爬取漫画《%s》\n' % title)
                    for i in i_s:
                        yield scrapy.Request(c_s[i][1], callback=self.parse_page, meta={'info': [title, c_s[i][0]]})
            else:
                print('\n' + '=' * 15 + '\t即将开始爬取漫画《%s》\n' % title)
                for i in list(c_s.keys()):
                    yield scrapy.Request(c_s[i][1], callback=self.parse_page, meta={'info': [title, c_s[i][0]]})
        except Exception as e:
            self.error_text = (e, '章节', '开爬', '等待选对了的章节爬完')
            sleep(10)

    def choose_section(self, response, *args):
        example_s = ' -{}、<{}> '
        targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
        print(example_s.format('序号', '章节') + '\n')
        c_s = {}
        print_npc = []
        for x in range(len(targets)):
            section_url = targets[x].xpath('./a/@href').get()
            section = targets[x].xpath('.//span/text()').get()
            c_s[x + 1] = [section, section_url]
            print_npc.append(example_s.format(str(x + 1), section))
            print_len = 4
            if (x + 1) % print_len==0:
                print(print_npc)
                print_npc = []
        print(print_npc)
        print(''.join(self.cs_exp_txt))
        i_s = input('\n' + '>' * 15 + '输入要下载的漫画《{}》的章节序号：'.format(args[0]))
        self.judge_input = i_s
        return [self.judge_input, c_s]

    @property
    def judge_input(self):
        return self._judge_input

    @judge_input.setter
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
            self._judge_input = _input
        else:
            while '-' not in _input:
                print(''.join(self.cs_exp_txt))
                _input = _input('\n' + '>' * 15 + '再给次机会输入，再错...（重新新搜索输入re）：')
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
            self._judge_input = i_fin

    def parse_page(self, response):
        item = ComicspiderItem()
        target = response.xpath('//div[@class="UnderPage"]/div/mip-link')  # sign -*-
        next_url = target.xpath('./@href').get()
        item['title'] = response.meta.get('info')[0]
        item['section'] = response.meta.get('info')[1]
        item['page'] = response.xpath('//span[@id="k_page"]/text()').get()
        item['image_urls'] = target.xpath('.//mip-img/@src').getall()
        yield item
        if re.match(r'.*?-[\d]+\.html', next_url):
            yield response.follow(next_url, callback=self.parse_page, meta={'info': [item['title'], item['section']]})
