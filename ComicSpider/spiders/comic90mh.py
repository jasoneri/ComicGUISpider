# -*- coding: utf-8 -*-
import ast
import re
from copy import deepcopy

import requests
from lxml import etree
from scrapy.http import Request
from ComicSpider.items import ComicspiderItem
from .basecomicspider import BaseComicSpider


class Comic90mhSpider(BaseComicSpider):
    name = 'comic90mh'
    allowed_domains = ['m.90mh.com']

    def start_requests(self):
        start_search = self.search
        self.start_search = deepcopy(start_search)
        yield Request(start_search, dont_filter=True)

    @property
    def search(self):
        self.step = 'search'
        self.step_put(self.step)
        self.keyword = self.current_Q.get()['keyword']
        return f'http://m.90mh.com/search/?keywords={self.keyword}'

    def frame_book(self, response):
        frame_results = {}
        # example_b = '{0:^3}\t{1:{5}<25}\t{2:{5}<18}\t{3:^10}\t{4:{5}^20}'
        example_b = r' {}、   《{}》   【{}】    [{}]   <{}>'
        self.print_Q.put(example_b.format('序号', '漫画名', '作者', '更新时间', '最新章节') + '\n')
        targets = response.xpath('//div[@class="itemBox"]')                          # sign -*-
        for x in range(len(targets)):
            title = targets[x].xpath('.//a[@class="title"]/text()').get().strip()
            url = targets[x].xpath('.//a[@class="title"]/@href').get()
            author = targets[x].xpath('.//p[@class="txtItme"]/text()').get()
            refresh_time = targets[x].xpath('.//span[@class="date"]/text()').get().strip()
            refresh_section = targets[x].xpath('.//a[@class="coll"]/text()').get().strip()
            self.print_Q.put(example_b.format(str(x + 1), title, author, refresh_time, refresh_section, chr(12288)))
            frame_results[x + 1] = [title, url]
        self.print_Q.put('✈' * 20 + '什么意思呢？ 唔……就是你的搜索在放✈(飞机)，retry拯救') if not len(frame_results) else None
        self.print_Q.put(''.join(self.exp_txt)+' →_→ 选book时可多选，但禁止用 0 全选\n')
        return frame_results

    def frame_section(self, response):
        example_s = ' -{}、<{}> '
        targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
        self.print_Q.put(example_s.format('序号', '章节') + '\n')
        frame_results = {}
        print_npc = []
        for x in range(len(targets)):
            section_url = targets[x].xpath('./a/@href').get()
            section = targets[x].xpath('.//span/text()').get()
            frame_results[x + 1] = [section, section_url]
            print_npc.append(example_s.format(str(x + 1), section))
            print_len = 4
            if (x + 1) % print_len==0:
                self.print_Q.put(print_npc)
                print_npc = []
        self.print_Q.put(print_npc) if len(print_npc) else None
        self.print_Q.put(''.join(self.exp_txt)+' ←_← 直接[点开爬][再点OK] == 不爬这本了\n')
        return frame_results

    def middle_utils(self, _type='listurl', **kw):
        todo = _type
        if todo == 'listurl':
            response = requests.get(kw['url'])
            response.raise_for_status()
            total_page = int(etree.HTML(response.text).xpath('//span[@id="k_total"]/text()')[0])
            compile = re.compile(r'(-[\d])*\.html')
            url_list = list(map(lambda x: compile.sub(f'-{x}.html', kw['url']), range(total_page + 1)[1:]))
            return url_list

    def parse_fin_page(self, response):
        item = ComicspiderItem()
        target = response.xpath('//div[@class="UnderPage"]/div/mip-link')  # sign -*-
        item['title'] = response.meta.get('info')[0]
        item['section'] = response.meta.get('info')[1]
        item['page'] = response.xpath('//span[@id="k_page"]/text()').get()
        item['image_urls'] = target.xpath('.//mip-img/@src').getall()
        yield item
        # if re.match(r'.*?-[\d]+\.html', next_url):
        #     yield response.follow(next_url, callback=self.parse_page, meta={'info': [item['title'], item['section']]})
