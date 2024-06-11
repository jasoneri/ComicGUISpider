# -*- coding: utf-8 -*-
import re
from .basecomicspider import BaseComicSpider, ComicspiderItem

domain = "m.90mh.org"  # 注意mk_page_tasks有域名转换


class Comic90mhSpider(BaseComicSpider):
    name = 'comic90mh'
    search_url_head = f'http://{domain}/search/?keywords='
    mappings = {'更新': f'http://{domain}/update/',
                '排名': f'http://{domain}/rank/'}

    def frame_book(self, response):
        frame_results = {}
        example_b = r' {}、   《{}》   【{}】    [{}]   [{}]'
        self.say(example_b.format('序号', '漫画名', '作者', '更新时间', '最新章节') + '<br>')
        targets = response.xpath('//div[@class="itemBox"]')  # sign -*-
        for x, target in enumerate(targets):
            title = target.xpath('.//a[@class="title"]/text()').get().strip()
            url = target.xpath('.//a[@class="title"]/@href').get()
            author = target.xpath('.//p[@class="txtItme"]/text()').get()
            refresh_time = target.xpath('.//span[@class="date"]/text()').get().strip()
            refresh_section = target.xpath(
                './/a[@class="coll"]/text()').get().strip() if 'rank' not in self.search_start else '-*-*-'
            self.say(example_b.format(str(x + 1), title, author, refresh_time, refresh_section, chr(12288)))
            frame_results[x + 1] = [title, url]
        return self.say.frame_book_print(frame_results, extra=" →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选<br>")

    def frame_section(self, response):
        frame_results = {}
        example_s = ' -{}、【{}】'
        self.say(example_s.format('序号', '章节') + '<br>')
        targets = response.xpath('//ul[contains(@id, "chapter")]/li')  # sign -*-
        for x, target in enumerate(targets):
            section_url = target.xpath('./a/@href').get()
            section = target.xpath('.//span/text()').get()
            frame_results[x + 1] = [section, section_url]
        return self.say.frame_section_print(frame_results, print_example=example_s)

    def mk_page_tasks(self, **kw):
        return [kw['url'].replace(domain, 'www.90mh.org')]

    def parse_fin_page(self, response):
        doc_vars = re.split(r';var', response.text)
        img_doc = next(filter(lambda _: "chapterImages" in _, doc_vars))
        img_path_doc = next(filter(lambda _: "chapterPath" in _, doc_vars))  # var chapterPath="images/comic/35/69927/"
        page_image_doc = next(filter(lambda _: "pageImage" in _, doc_vars))  # var pageImage="http://xx/images/xx.jpg"
        img_path = re.search(r"""['"](.*?)['"]""", img_path_doc).group(1)
        img_domain = re.search(r"""['"](https?://.*?/).*?['"]""", page_image_doc).group(1)
        for page, (img_name, img_type) in enumerate(re.findall(r"""['"](.*?(jp[e]?g|png|webp))['"]""", img_doc)):
            item = ComicspiderItem()
            item['title'] = response.meta.get('title')
            item['section'] = response.meta.get('section')
            item['page'] = page + 1
            item['image_urls'] = [f"{img_domain}{img_path}{img_name}"]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
