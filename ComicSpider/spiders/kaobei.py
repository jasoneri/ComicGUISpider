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

    @classmethod
    def rendering_map(cls):
        return dict(zip(cls.print_head, list(map(jsonp.parse, cls.target_json_path))))


class FrameBookByRefresh(FrameBook):
    url = f'https://{domain}/api/v3/update/newest?limit=30&offset=0&_update=false'
    example_b = FrameBook.example_b + '\t[{}]\t[{}]'
    print_head = FrameBook.print_head + ['更新时间', '最新章节']
    target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name',
                        'popular', 'datetime_updated', 'last_chapter_name']


class FrameBookByRank(FrameBook):
    url = f'https://{domain}/api/v3/ranks?offset=0&limit=30&_update=false'
    target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name', 'popular']
    expand_map: t.Dict[str, dict] = {
        "日": {'date_type': 'day'}, "周": {'date_type': 'week'}, "月": {'date_type': 'month'},
        "总": {'date_type': 'total'},
        "轻小说": {'type': 5}, "男": {'audience_type': 'male'}, "女": {'audience_type': 'female'}
    }


class KaobeiSpider(BaseComicSpider):
    name = 'manga_copy'
    domain = domain
    custom_settings = {"DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.KaobeiMiddleware': 5},
                       "REFERER_ENABLED": False}
    search_url_head = ''

    preset_book_frame: FrameBook = FrameBook
    mappings = {'更新': FrameBookByRefresh,
                '排名': FrameBookByRank}

    @property
    def search(self):
        keyword = self.input_state.keyword
        url = self.preset_book_frame.url + keyword
        what = re.search(r".*?(排名|更新)", keyword)
        if bool(what):
            self.preset_book_frame = self.mappings[what.group(1)]
            url = self.preset_book_frame.url
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
        for x, target in enumerate(targets):
            dohe = {}
            for _, _path in self.preset_book_frame.rendering_map().items():
                dohe[_] = ",".join(map(lambda __: str(__.value), _path.find(target)))
            url = rf"""https://{domain}/api/v3/comic/{dohe.pop('book_path')}/group/default/chapters?limit=300&offset=0&_update=false"""
            self.say(example_b.format(str(x + 1), *dohe.values(), chr(12288)))
            frame_results[x + 1] = [dohe['漫画名'], url]
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
