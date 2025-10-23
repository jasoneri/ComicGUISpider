# -*- coding: utf-8 -*-
import re
import typing as t
from urllib.parse import urlencode

import jsonpath_rw as jsonp

from utils.processed_class import Url
from utils.website import KaobeiUtils, KbBookInfo, Episode
from .basecomicspider import BaseComicSpider, ComicspiderItem, conf

pc_domain = "www.2025copy.com"
domain = "api.2025copy.com"


class FrameBook:
    say_fm = ' {}、《{}》\t【{}】\t[{}]'
    print_head = ['book_path', 'name', 'artist', 'popular']
    target_json_path = ['path_word', 'name', 'author.[*].name', 'popular']
    expand_map = None

    def __init__(self, _domain):
        self.url = f'https://{_domain}/api/v3/search/comic?platform=1&limit=30&offset=0&q_type=&_update=false&q='
        self.domain = _domain

    def rendering_map(self):
        return dict(zip(self.print_head, list(map(jsonp.parse, self.target_json_path))))

    def byRefresh(self):
        self.url = f'https://{self.domain}/api/v3/update/newest?limit=30&offset=0&_update=false'
        self.say_fm = FrameBook.say_fm + '\t[{}]\t[{}]'
        self.print_head = FrameBook.print_head + ['datetime_updated', 'last_chapter_name']
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'dnts': '2',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
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
        say_fm = self.preset_book_frame.say_fm
        render_keys = self.preset_book_frame.print_head[1:]
        self.say(say_fm.format('序号', *render_keys) + '<br>')
        targets = response.json().get('results', {}).get('list', [])
        for x, target in enumerate(targets):
            rendered = {
                attr_name: ",".join(map(lambda __: str(__.value), _path.find(target)))
                for attr_name, _path in self.preset_book_frame.rendering_map().items()
            }
            # url = rf"""https://{self.domain}/api/v3/comic/{rendered.pop('book_path')}/group/default/chapters?limit=300&offset=0&_update=false"""
            book_path = rendered.pop('book_path')
            book = KbBookInfo(
                idx=x+1, render_keys = render_keys,
                url=f"https://{pc_domain}/comicdetail/{book_path}/chapters",
                preview_url=f"https://{pc_domain}/comic/{book_path}",
            )
            for k in render_keys:
                setattr(book, k, rendered.get(k))
            frame_results[book.idx] = book
        return self.say.frame_book_print(
            frame_results, fm=say_fm, url=response.url,
            extra=" →_→ 鼠标移到序号栏有教输入规则，此步特殊禁止用全选，想多选请多开<br>" +
                  "拷贝漫画翻页使用的是条目序号，并不是页数，一页有30条，类推计算")

    def frame_section(self, response):
        book = response.meta.get("book")
        frame_results = {}
        say_ep_fm = ' -{}、【{}】'
        self.say(say_ep_fm.format('序号', '章节') + '<br>')
        resp_data = KaobeiUtils.decrypt_chapter_data(response.json()['results'], url=response.url)
        comic_path_word = resp_data['build']['path_word']
        chapters_data = resp_data['groups']['default']['chapters']
        if conf.kbShowDhb:
            for _ in ("tankobon", "other_group"):
                if resp_data['groups'].get(_):
                    chapters_data.extend(resp_data['groups'][_]['chapters'])
        for x, chapter_datum in enumerate(chapters_data):
            # section_url = rf"""https://{self.domain}/api/v3/comic/{comic_path_word}/chapter2/{chapter_datum['id']}?_update=false&platform=1"""
            ep = Episode(
                from_book=book,
                id=chapter_datum['id'],
                idx=x+1,
                url=rf"""https://{self.pc_domain}/comic/{comic_path_word}/chapter/{chapter_datum['id']}""",
                name=chapter_datum['name'],
            )
            frame_results[ep.idx] = ep
        self.say.frame_section_print(frame_results, fm=say_ep_fm)

    def mk_page_tasks(self, **kw):
        return [kw['url']]

    def parse_fin_page(self, response):
        ep = response.meta['ep']
        book = ep.from_book
        uid, u_md5 = ep.id_and_md5()
        group_infos = {'title':book.name,'section':ep.name,'uuid':uid,'uuid_md5':u_md5}
        contentKey_script = response.xpath('//script[contains(text(), "var contentKey =")]/text()').get()
        if not contentKey_script:
            raise ValueError("拷贝更改了contentKey xpath")
        contentKey = re.search(r"""var contentKey = ["']([^']*)["']""", contentKey_script).group(1)
        imageData = KaobeiUtils.decrypt_chapter_data(contentKey, url=response.url, group_infos=group_infos)
        ep.pages = len(imageData)
        self.set_task(ep)
        for page, url_item in enumerate(imageData):
            item = ComicspiderItem()
            item.update(**group_infos)
            item['page'] = page + 1
            item['image_urls'] = [url_item['url']]
            self.total += 1
            yield item
        self.process_state.process = 'fin'
        self.Q('ProcessQueue').send(self.process_state)
