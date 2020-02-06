# -*- coding: utf-8 -*-
import ast
import re
from copy import deepcopy

import requests
from lxml import etree
from urllib.parse import quote
from scrapy.http import Request
from ComicSpider.items import ComicspiderItem
from ComicSpider.spiders.basecomicspider import BaseComicSpider


class ComickukudmSpider(BaseComicSpider):
    name = 'comickukudm'
    allowed_domains = ['m.kukudm.com']
    num = 0
    
    def start_requests(self):
        start_search = self.search
        self.start_search = deepcopy(start_search)
        yield Request(start_search, dont_filter=True)

    @property
    def search(self):
        self.step = 'search'
        self.step_put(self.step)
        keyword = self.current_Q.get()['keyword']
        self.keyword = quote(f'{keyword}'.encode('gb2312'))
        return f'http://so.kukudm.com/m_search.asp?kw={self.keyword}'

    def parse_book(self, response):
        return response

    def frame_book(self, response):
        frame_results = {}
        # example = '{0:^3}\t{1:{5}<25}\t{2:{5}<18}\t{3:^10}\t{4:{5}^20}'
        example_b = '-{}   《{}》   【{}】   /{}/   <{}>'
        self.print_Q.put(example_b.format('序号', '漫画名', '作者', '更新时间', '最新章节') + '\n')
        targets = response.xpath('//div[@class="imgBox"]//li')  # sign -*-

        for x in range(len(targets)):
            title = targets[x].xpath('.//a[@class="txtA"]/text()').get().strip()
            url = targets[x].xpath('.//a[contains(@class, "ImgA")]/@href').get()
            resp = requests.get(url)
            # resp = scrapy.Request(url=url, callback=self.parse_book, dont_filter=True)
            resp.raise_for_status()
            resp.encoding = "gbk"
            _resp = etree.HTML(resp.text)
            author = _resp.xpath('.//p[@class="txtItme"]/text()')[0].strip()
            refresh_time = _resp.xpath('.//span[@class="date"]/text()')[0].strip()
            refresh_section = _resp.xpath('.//div[@id="list"]//a/text()')[0].strip()
            self.print_Q.put(example_b.format(str(x + 1), title, author, refresh_time, refresh_section, chr(12288)))
            frame_results[x + 1] = [title, url]
        self.print_Q.put('✈' * 20 + '什么意思呢？ 唔……就是你的搜索在放✈(飞机)，retry拯救') if not len(frame_results) else None
        self.print_Q.put(''.join(self.exp_txt) + ' →_→ 选book时可多选，但最好不要用 0 全选\n')
        return frame_results

    def frame_section(self, response):
        example_s = ' {}、<{}> '
        targets = response.xpath('//div[@id="list"]//a')  # sign -*-
        self.print_Q.put(example_s.format('序号', '章节') + '\n')
        frame_results = {}
        print_npc = []
        for x in range(len(targets)):
            section_url = targets[x].xpath('./@href').get()
            section_url = f"http://{self.allowed_domains[0]}/{section_url}"
            section = targets[x].xpath('./text()').get()
            frame_results[x + 1] = [section, section_url]
            print_npc.append(example_s.format(str(x + 1), section))
            print_len = 4
            if (x + 1) % print_len==0:
                self.print_Q.put(print_npc)
                print_npc = []
        self.print_Q.put(print_npc) if len(print_npc) else None
        self.print_Q.put(''.join(self.exp_txt))
        return frame_results

    def middle_utils(self, _type='listurl', *args, **kw):
        super(ComickukudmSpider, self).middle_utils(_type, *args, **kw)

        def list_url(**kwargs):
            _response = etree.HTML(requests.get(kwargs['url']).text)
            total_page_div = _response.xpath('//ul[@class="subNav"]/li/following-sibling::li[1]/text()')[0]
            total_page = int(re.search(r'(\d+)/(\d+)', total_page_div).group(2))
            _compile = re.compile(r'[\\/][\d]+\.htm')
            url_list = list(map(lambda x: _compile.sub(f'/{x}.htm', kwargs['url']), range(total_page + 1)[1:]))
            return url_list
        schedule = list_url if _type == 'listurl' else None
        return schedule(*args, **kw)
            
    def parse_fin_page(self, response):
        item = ComicspiderItem()
        title = response.meta.get('info')[0]
        item['title'] = title
        item['section'] = response.meta.get('info')[1]

        page_div = response.xpath('//ul[@class="subNav"]/li/following-sibling::li[1]/text()').get()
        item['page'] = re.search(r'(\d+)/(\d+)', page_div).group(1)

        # 该网站url规则：urlencode化
        short_url = re.search(r"""<IMG SRC='"(.*?)"(.*?kuku.*?\.(jpg|png))'>?""", response.text)[2]
        transfer_url = "".join(('https://s1.kukudm.com/', quote(f'{short_url}'.encode('utf-8'))))
        image_urls = [f"{transfer_url}"]
        self.bar.put(self.num)
        self.num = 1 if self.num > 100 else self.num + 1
        item['image_urls'] = image_urls
        yield item

