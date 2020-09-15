# -*- coding: utf-8 -*-
import re
from lxml import etree
from ComicSpider.items import ComicspiderItem
from .basecomicspider import BaseComicSpider


class Comic90mhSpider(BaseComicSpider):
    name = 'comic90mh'
    allowed_domains = ['m.90mh.com']
    search_url_head = 'http://m.90mh.com/search/?keywords='
    mappings = {'更新': 'http://m.90mh.com/update/',
                '排名': 'http://m.90mh.com/rank/'}

    def frame_book(self, response):
        frame_results = {}
        example_b = r' {}、   《{}》   【{}】    [{}]   [{}]'
        self.print_Q.put(example_b.format('序号', '漫画名', '作者', '更新时间', '最新章节') + '<br>')
        targets = response.xpath('//div[@class="itemBox"]')  # sign -*-
        for x, target in enumerate(targets):
            title = target.xpath('.//a[@class="title"]/text()').get().strip()
            url = target.xpath('.//a[@class="title"]/@href').get()
            author = target.xpath('.//p[@class="txtItme"]/text()').get()
            refresh_time = target.xpath('.//span[@class="date"]/text()').get().strip()
            refresh_section = target.xpath(
                './/a[@class="coll"]/text()').get().strip() if 'rank' not in self.search_start else '-*-*-'
            self.print_Q.put(example_b.format(str(x + 1), title, author, refresh_time, refresh_section, chr(12288)))
            frame_results[x + 1] = [title, url]
        return self.frame_book_print(frame_results, extra=" →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选<br>")

    def frame_section(self, response):
        frame_results = {}
        example_s = ' -{}、【{}】'
        self.print_Q.put(example_s.format('序号', '章节') + '<br>')
        targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
        for x, target in enumerate(targets):
            section_url = target.xpath('./a/@href').get()
            section = target.xpath('.//span/text()').get()
            frame_results[x + 1] = [section, section_url]
        return self.frame_section_print(frame_results, print_example=example_s)

    def mk_page_tasks(self, **kw):
        response = kw['session'].get(kw['url'])
        response.raise_for_status()
        total_page = int(etree.HTML(response.text).xpath('//span[@id="k_total"]/text()')[0])
        compile = re.compile(r'(-[\d])*\.html')
        url_list = list(map(lambda x: compile.sub(f'-{x}.html', kw['url']), range(total_page + 1)[1:]))
        return url_list

    def parse_fin_page(self, response):
        item = ComicspiderItem()
        target = response.xpath('//div[@class="UnderPage"]/div/mip-link')  # sign -*-
        item['title'] = response.meta.get('title')
        item['section'] = response.meta.get('section')
        item['page'] = response.xpath('//span[@id="k_page"]/text()').get()
        item['image_urls'] = target.xpath('.//mip-img/@src').getall()
        self.total += 1
        yield item
        # if re.match(r'.*?-[\d]+\.html', next_url):
        #     yield response.follow(next_url, callback=self.parse_page, meta={'info': [item['title'], item['section']]})
