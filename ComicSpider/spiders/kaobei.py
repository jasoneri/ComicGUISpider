# -*- coding: utf-8 -*-
import re
import typing as t
import jsonpath_rw as jsonp
from urllib.parse import urlencode

from utils import font_color
from .basecomicspider import BaseComicSpider, ComicspiderItem

domain = "api.mangacopy.com"


class FrameBook:
    url = f'https://{domain}/api/v3/search/comic?platform=1&limit=30&offset=0&q_type=&_update=false&q='
    example_b = ' {}、\t《{}》\t【{}】\t[{}]'
    print_head = ['book_path', '漫画名', '作者', '热度']
    target_json_path = ['path_word', 'name', 'author.[*].name', 'popular']
    expand_map = None

    def rendering_map(self):
        return dict(zip(self.print_head, list(map(jsonp.parse, self.target_json_path))))

    def byRefresh(self):
        self.url = f'https://{domain}/api/v3/update/newest?limit=30&offset=0&_update=false'
        self.example_b = FrameBook.example_b + '\t[{}]\t[{}]'
        self.print_head = FrameBook.print_head + ['更新时间', '最新章节']
        self.target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name',
                                 'comic.popular', 'comic.datetime_updated', 'comic.last_chapter_name']

    def byRank(self):
        self.url = f'https://{domain}/api/v3/ranks?offset=0&limit=30&_update=false'
        self.target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name', 'comic.popular']
        self.expand_map: t.Dict[str, dict] = {
            "日": {'date_type': 'day'}, "周": {'date_type': 'week'}, "月": {'date_type': 'month'},
            "总": {'date_type': 'total'},
            "轻小说": {'type': 5}, "男": {'audience_type': 'male'}, "女": {'audience_type': 'female'}
        }

    def byQingXiaoShuo(self):
        self.target_json_path = ['book.path_word', 'book.name', 'book.author.[*].name', 'book.popular']


class KaobeiSpider(BaseComicSpider):
    name = 'manga_copy'
    domain = domain
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.KaobeiMiddleware': 5},
                       "REFERER_ENABLED": False}
    search_url_head = ''

    preset_book_frame = FrameBook()
    mappings = {'更新': "byRefresh",
                '排名': "byRank"}

    @property
    def search(self):
        keyword = self.input_state.keyword
        url = self.preset_book_frame.url + keyword
        what = re.search(r".*?(排名|更新)", keyword)
        if bool(what):
            getattr(self.preset_book_frame, self.mappings[what.group(1)])()
            url = self.preset_book_frame.url
        if "轻小说" in keyword:
            self.preset_book_frame.byQingXiaoShuo()
        if "排名" in keyword:
            param = {'type': 1}
            time_search = re.search(r".*?([日周月总])", keyword)
            kind_search = re.search(r".*?(轻小说|男|女)", keyword)
            param.update(self.preset_book_frame.expand_map[kind_search.group(1)] if bool(kind_search) else
                         self.preset_book_frame.expand_map["男"])  # 默认男性向
            param.update(self.preset_book_frame.expand_map[time_search.group(1)] if bool(time_search) else
                         self.preset_book_frame.expand_map["日"])  # 默认日榜
            url = self.preset_book_frame.url + f"&{urlencode(param)}"
        return url

    def frame_book(self, response):
        frame_results = {}
        example_b = self.preset_book_frame.example_b
        self.say(example_b.format('序号', *self.preset_book_frame.print_head[1:]) + '<br>')
        targets = response.json().get('results', {}).get('list', [])
        for index, target in enumerate(targets):
            rendered = {
                attr_name: ",".join(map(lambda __: str(__.value), _path.find(target)))
                for attr_name, _path in self.preset_book_frame.rendering_map().items()
            }
            url = rf"""https://{domain}/api/v3/comic/{rendered.pop('book_path')}/group/default/chapters?limit=300&offset=0&_update=false"""
            # url = rf"""https://{domain}/api/v3/comic/{rendered.pop('book_path')}/group/tankobon/chapters?limit=300&offset=0&_update=false"""
            # todo: 额外卷请求，写req做到frame_section上合并
            self.say(example_b.format(str(index + 1), *rendered.values(), chr(12288)))
            frame_results[index + 1] = [rendered['漫画名'], url]
        return self.say.frame_book_print(frame_results, extra=" →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选<br>")

    def frame_section(self, response):
        frame_results = {}
        example_s = ' -{}、【{}】'
        self.say(example_s.format('序号', '章节') + '<br>')
        targets = response.json().get('results', {}).get('list', [])
        for x, target in enumerate(targets):
            section_url = rf"""https://{domain}/api/v3/comic/{target['comic_path_word']}/chapter2/{target['uuid']}?_update=false&format=json&platform=4"""
            section = target['name']
            frame_results[x + 1] = [section, section_url]
        return self.say.frame_section_print(frame_results, print_example=example_s)

    def mk_page_tasks(self, **kw):
        return [kw['url']]

    def parse_fin_page(self, response):
        result = response.json().get('results', {})
        if result.get("show_app"):
            self.say(font_color(f'[{response.meta.get("title")}_{response.meta.get('section')}] 被风控了我擦呢',
                                color='orange'))
        chapter = result.get('chapter', {})
        targets = dict(zip(chapter.get('words', []), chapter.get('contents', [])))
        for page, url_item in targets.items():
            item = ComicspiderItem()
            item['title'] = response.meta.get('title')
            item['section'] = response.meta.get('section')
            item['page'] = page + 1
            item['image_urls'] = [url_item['url']]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
