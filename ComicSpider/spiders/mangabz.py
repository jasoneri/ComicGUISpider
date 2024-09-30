# -*- coding: utf-8 -*-
import re
import datetime
import jsonpath_rw as jsonp
from collections import OrderedDict

from utils.processed_class import execute_js
from .basecomicspider import FormReqBaseComicSpider, ComicspiderItem, BodyFormat

domain = "www.mangabz.com"


def curr_time_format():
    return datetime.datetime.now().strftime('%a %b %d %Y %H:%M:%S GMT 0800 (中国标准时间)')


class Body(BodyFormat):
    page_index_field = "pageindex"
    dic = {
        "action": "getclasscomics",
        "pageindex": "1",
        "pagesize": "21",
        "tagid": "0",
        "status": "0",
        "sort": "2"
    }
    example_b = ' {}、\t《{}》\t【{}】\t[{}]'
    print_head = ['book_path', '漫画名', '作者', '最新话']
    target_json_path = ['UrlKey', 'Title', 'Author.[*]', 'ShowLastPartName']

    def rendering_map(self):
        return dict(zip(self.print_head, list(map(jsonp.parse, self.target_json_path))))


class SearchBody(Body):
    dic = {
        "t": "3",
        "pageindex": "1",
        "pagesize": "12",
        "f": "0",
        "title": "廢淵"
    }
    target_json_path = ['Url', 'Title', 'Author.[*]', 'LastPartShowName']


class MangabzSpider(FormReqBaseComicSpider):
    name = 'mangabz'
    ua = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "TE": "trailers"
    }
    num_of_row = 50
    domain = domain
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.MangabzUAMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlAllProxyMiddleware': 6},
        "ITEM_PIPELINES": {'ComicSpider.pipelines.MangabzComicPipeline': 50}
    }
    search_url_head = f"https://{domain}/pager.ashx"
    mappings = {"更新": ["manga-list-0-0-2", "2"],
                "人气": ["manga-list", "10"],
                }
    body = Body()

    @property
    def search(self):
        self.process_state.process = 'search'
        self.Q('ProcessQueue').send(self.process_state)
        keyword = self.input_state.keyword.strip()
        if keyword in self.mappings.keys():
            search_start_path, body_sort = self.mappings[keyword]  # TODO[5](2024-09-30): 后续支持状态：全部/连载中/完结，排序：上架时间
            search_start = f"https://{domain}/{search_start_path}/mangabz.ashx?d={curr_time_format()}"
            self.body.update(sort=body_sort)
        else:
            search_start = f"{self.search_url_head}?d={curr_time_format()}"
            self.body = SearchBody(title=keyword)
        return search_start

    def frame_book(self, response):
        frame_results = {}
        example_b = self.body.example_b
        self.say(example_b.format('序号', *self.body.print_head[1:]) + '<br>')
        targets = response.json() if isinstance(self.body, SearchBody) \
            else response.json().get('UpdateComicItems')
        rendering_map = self.body.rendering_map().items()
        for x, target in enumerate(targets):
            rendered = OrderedDict()
            for attr_name, _path in rendering_map:
                rendered[attr_name] = ",".join(map(lambda __: str(__.value), _path.find(target))).strip()
            url = f"https://{self.domain}/{rendered.pop('book_path').strip('/')}/"
            self.say(example_b.format(str(x + 1), *rendered.values(), chr(12288)))
            self.say('') if (x + 1) % self.num_of_row == 0 else None
            frame_results[x + 1] = [url, rendered['漫画名']]
        return self.say.frame_book_print(frame_results, url=response.url)

    def frame_section(self, response):
        frame_results = {}
        example_s = ' -{}、【{}】'
        self.say(example_s.format('序号', '章节') + '<br>')
        targets = response.xpath('//div[@class="detail-list-item"]/a')
        for x, target in enumerate(reversed(targets)):
            section_url = rf"https://{domain}{target.xpath('./@href').get()}"
            section = "".join(target.xpath('./text()').get()).strip()
            frame_results[x + 1] = [section, section_url]
        return self.say.frame_section_print(frame_results, print_example=example_s)

    def parse_fin_page(self, response):
        js = response.xpath('//script[@type="text/javascript"]/text()').getall()
        target_js = next(filter(lambda t: t.strip().startswith('eval'), js), None)
        real_js = execute_js(
            r"""function run(code){var ret="";eval('ret = '+code.replace(/^;*?\s*(window(\.|\[(["'])))?eval(\3\])?/, 
            function ($0) {return 'String';}));   return ret }""",
            "run", target_js)
        img_list_ = re.search(r'\[(.*?)]', real_js).group(1)
        img_list = [re.sub(r"""['"]""", '', _) for _ in re.split(', ?', img_list_)]
        title = response.meta.get('title')
        sec = response.meta.get('section')
        for img_url in img_list:
            item = ComicspiderItem()
            item['title'] = title
            item['section'] = sec
            page = int(re.search(r'/(\d+)_\d+\.', img_url).group(1))
            item['page'] = page
            item['image_urls'] = [img_url]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
