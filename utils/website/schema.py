import datetime
import typing as t

import jsonpath_rw as jsonp


class BodyFormat:
    page_index_field = "pageindex"
    dic = {}

    def __init__(self, **dic):
        self.dic = {**self.__class__.dic, **dic}

    def update(self, **dic):
        self.dic.update(**dic)


class KbFrameBook:
    print_head = ['book_path', 'name', 'artist', 'popular']
    target_json_path = ['path_word', 'name', 'author.[*].name', 'popular']
    cover_path = 'cover'
    expand_map = None

    def __init__(self, _domain):
        self.url = f'https://{_domain}/api/v3/search/comic?platform=1&limit=30&offset=0&q_type=&_update=false&q='
        self.domain = _domain
        self.cover_path = self.__class__.cover_path

    def rendering_map(self):
        return dict(zip(self.print_head, list(map(jsonp.parse, self.target_json_path))))

    def extract_cover(self, target: dict) -> str | None:
        obj = target
        for key in self.cover_path.split('.'):
            if not isinstance(obj, dict):
                return None
            obj = obj.get(key)
        return obj if isinstance(obj, str) else None

    def byRefresh(self):
        self.url = f'https://{self.domain}/api/v3/update/newest?limit=30&offset=0&_update=false'
        self.print_head = KbFrameBook.print_head + ['datetime_updated', 'last_chapter_name']
        self.target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name',
                                 'comic.popular', 'comic.datetime_updated', 'comic.last_chapter_name']
        self.cover_path = 'comic.cover'

    def byRank(self):
        self.url = f'https://{self.domain}/api/v3/ranks?offset=0&limit=30&_update=false'
        self.target_json_path = ['comic.path_word', 'comic.name', 'comic.author.[*].name', 'comic.popular']
        self.cover_path = 'comic.cover'
        self.expand_map: t.Dict[str, dict] = {
            "日": {'date_type': 'day'}, "周": {'date_type': 'week'}, "月": {'date_type': 'month'},
            "总": {'date_type': 'total'},
            "轻小说": {'type': 5}, "男": {'audience_type': 'male'}, "女": {'audience_type': 'female'}
        }

    def byQingXiaoShuo(self):
        self.target_json_path = ['book.path_word', 'book.name', 'book.author.[*].name', 'book.popular']
        self.cover_path = 'book.cover'


class MbBody(BodyFormat):
    page_index_field = "pageindex"
    dic = {
        "action": "getclasscomics",
        "pageindex": "1",
        "pagesize": "21",
        "tagid": "0",
        "status": "0",
        "sort": "2"
    }
    print_head = ['book_path', 'name', 'artist', 'last_chapter_name']
    target_json_path = ['UrlKey', 'Title', 'Author.[*]', 'ShowLastPartName']

    def rendering_map(self):
        return dict(zip(self.print_head, list(map(jsonp.parse, self.target_json_path))))


class MbSearchBody(MbBody):
    dic = {
        "t": "3",
        "pageindex": "1",
        "pagesize": "12",
        "f": "0",
        "title": "廢淵"
    }
    target_json_path = ['Url', 'Title', 'Author.[*]', 'LastPartShowName']


def mb_curr_time_format():
    return datetime.datetime.now().strftime('%a %b %d %Y %H:%M:%S') + ' GMT 0800 (中国标准时间)'
