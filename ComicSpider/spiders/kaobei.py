# -*- coding: utf-8 -*-
import re
import typing as t
from urllib.parse import urlencode

import jsonpath_rw as jsonp

from utils.processed_class import Url
from utils.website import KaobeiUtils
from .basecomicspider import BaseComicSpider, ComicspiderItem, font_color

pc_domain = "www.2025copy.com"
domain = "api.2025copy.com"


class FrameBook:
    example_b = ' {}、\t《{}》\t【{}】\t[{}]'
    print_head = ['book_path', '漫画名', '作者', '热度']
    target_json_path = ['path_word', 'name', 'author.[*].name', 'popular']
    expand_map = None

    def __init__(self, _domain):
        self.url = f'https://{_domain}/api/v3/search/comic?platform=1&limit=30&offset=0&q_type=&_update=false&q='
        self.domain = _domain

    def rendering_map(self):
        return dict(zip(self.print_head, list(map(jsonp.parse, self.target_json_path))))

    def byRefresh(self):
        self.url = f'https://{self.domain}/api/v3/update/newest?limit=30&offset=0&_update=false'
        self.example_b = FrameBook.example_b + '\t[{}]\t[{}]'
        self.print_head = FrameBook.print_head + ['更新时间', '最新章节']
        self.target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name',
                                 'comic.popular', 'comic.datetime_updated', 'comic.last_chapter_name']

    def byRank(self):
        self.url = f'https://{self.domain}/api/v3/ranks?offset=0&limit=30&_update=false'
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
    ua = headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'Connection': 'keep-alive',
    }
    ua_mapi = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'Accept': 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Origin': f'https://{pc_domain}',
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, compress, br',
        'platform': '1',
        'version': '2025.07.15',
        'webp': '1',
        'region': '0'
    }
    domain = domain
    pc_domain = pc_domain
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {'ComicSpider.middlewares.UAKaobeiMiddleware': 5,
                                   'ComicSpider.middlewares.ComicDlProxyMiddleware': 6},
        "REFERER_ENABLED": False
    }
    search_url_head = ''
    mappings = {'更新': "byRefresh",
                '排名': "byRank"}
    preset_book_frame = FrameBook(domain)
    turn_page_info = (r"offset=\d+", None, 30)
    section_limit = 300

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        KaobeiUtils.get_aes_key()
        return super().from_crawler(crawler, *args, **kwargs)

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
        return Url(url).set_next(*self.turn_page_info)

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
            # url = rf"""https://{self.domain}/api/v3/comic/{rendered.pop('book_path')}/group/default/chapters?limit=300&offset=0&_update=false"""
            url = rf"""https://{pc_domain}/comicdetail/{rendered.pop('book_path')}/chapters"""
            self.say(example_b.format(str(index + 1), *rendered.values(), chr(12288)))
            frame_results[index + 1] = [url, rendered['漫画名'], response.url]
        return self.say.frame_book_print(
            frame_results, url=response.url,
            extra=" →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选，想多选请多开<br>" +
                  "拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算")

    def need_sec_next_page(self, response):
        """discard, 当前接口返回完全数据，并不需要额外用offset整合章节请求
        e.g. 海贼王haizeiwang 火影忍者huoyingrenzhe 葬送的芙莉蓮zangsongdefulilian"""
        ...

    def frame_section(self, response):
        frame_results = {}
        example_s = ' -{}、【{}】'
        self.say(example_s.format('序号', '章节') + '<br>')
        resp_data = KaobeiUtils.decrypt_chapter_data(response.json()['results'])
        comic_path_word = resp_data['build']['path_word']
        chapters_data = resp_data['groups']['default']['chapters']
        for x, chapter_datum in enumerate(chapters_data):
            # section_url = rf"""https://{self.domain}/api/v3/comic/{comic_path_word}/chapter2/{chapter_datum['id']}?_update=false&platform=1"""
            section_url = rf"""https://{self.pc_domain}/comic/{comic_path_word}/chapter/{chapter_datum['id']}"""
            section = chapter_datum['name']
            frame_results[x + 1] = [section, section_url]
        return self.say.frame_section_print(frame_results, print_example=example_s)

    def mk_page_tasks(self, **kw):
        return [kw['url']]

    def mapi_parse_fin_page(self, response):
        self.logger.warning("mapi_parse_fin_page is deprecated")
        result = response.json().get('results', {})
        meta = response.meta
        if result.get("show_app"):
            self.say(font_color(f'[{meta.get("title")}-{meta.get('section')}] 被风控了我擦呢',
                                cls='theme-err'))
        chapter = result.get('chapter', {})
        targets = dict(zip(chapter.get('words', []), chapter.get('contents', [])))
        group_infos = ComicspiderItem.get_group_infos(meta)
        self.set_task((meta['uuid_md5'], f"{meta['title']}-{meta['section']}", len(targets), meta['title_url']))
        for page, url_item in targets.items():
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page + 1
            item['image_urls'] = [url_item['url']]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)

    def parse_fin_page(self, response):
        meta = response.meta
        group_infos = ComicspiderItem.get_group_infos(meta)
        contentKey = response.xpath('//div[@contentkey]/@contentkey').get()
        imageData = KaobeiUtils.decrypt_chapter_data(contentKey)
        self.set_task((meta['uuid_md5'], f"{meta['title']}-{meta['section']}", len(imageData), meta['title_url']))
        for page, url_item in enumerate(imageData):
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page + 1
            item['image_urls'] = [url_item['url']]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
