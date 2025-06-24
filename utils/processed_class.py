#!/usr/bin/python
# -*- coding: utf-8 -*-
import time
import typing as t
import socket
from dataclasses import dataclass
from multiprocessing import Queue, freeze_support
import urllib.parse as up

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from utils import State, QueuesManager, Queues, re
from utils.preview import PreviewHtml, PreviewByClipHtml
from variables import SPIDERS


@dataclass
class Selected(State):
    """仅替代[clip]JSON格式的结构化数据传输类，作为附带必要少量信息的input_state.indexes
    一个章节一个Selected！[Selected1-1,Selected1-2,Selected1-3]
    以往的无章节会归为[Selected2]
    """
    title: str
    bid: str
    episode_name: t.Optional[str] = None

    def __post_init__(self):
        """确保数据格式正确并缓存"""
        if not self.title or not self.bid:
            raise ValueError("title and bid are required")
        self.sv_cache()

    @property
    def section(self) -> str:
        return self.episode_name if self.episode_name else 'meaningless'

    def __str__(self):
        if self.episode_name:
            return f"Selected({self.title} - {self.episode_name})"
        return f"Selected({self.title})"


@dataclass
class InputFieldState(State):
    """
    indexes: preference 'def select... param elect'
    """
    keyword: str
    bookSelected: int
    indexes: t.Union[str, list, t.List[Selected]]
    pageTurn: t.Union[str, int]


@dataclass
class TextBrowserState(State):
    text: str


@dataclass
class ProcessState(State):
    process: str


class TasksObj:
    def __init__(self, taskid: str, title: str, tasks_count: int, title_url: str = None, episode_name: str = None):
        self.taskid = taskid
        self.title = title
        self.tasks_count = tasks_count
        self.title_url = title_url
        self.episode_name = episode_name
        self.downloaded = []

    @property
    def display_title(self) -> str:
        return f"{self.title} - {self.episode_name}" if self.episode_name else self.title


class TaskObj:
    success: bool = True

    def __init__(self, taskid: str, page: str, url: str = None):
        self.taskid = taskid
        self.page = page
        self.url = url


def refresh_state(self, state_name, queue_name, monitor_change=False):
    _ = getattr(self, state_name)
    state = self.Q(queue_name).recv()
    while monitor_change:
        if state == _:
            state = self.Q(queue_name).recv()
        else:
            break
    setattr(self, state_name, state)


class QueueHandler:
    def __init__(self, manager):
        self.manager = manager

    class Q:
        def __init__(self, queue):
            self.queue = queue

        def send(self, state: State, **kw):
            return Queues.send(self.queue, state, **kw)

        def recv(self) -> State:
            flag = False
            while not flag:
                flag = Queues.recv(self.queue)
                time.sleep(0.2)
            return flag

    def __call__(self, queue_name, *args, **kwargs):
        _inner_attr = f'_instance_{queue_name}'
        if not hasattr(self, _inner_attr):
            setattr(self, f'_instance_{queue_name}', self.Q(getattr(self.manager, queue_name)()))
        return getattr(self, _inner_attr)


class GuiQueuesManger(QueuesManager):
    queue_port: int = None

    def create_server_manager(self, **extra):
        InputFieldQueue = Queue()
        TextBrowserQueue = Queue(2)
        ProcessQueue = Queue()
        BarQueue = Queue()
        TasksQueue = Queue()
        QueuesManager.register('InputFieldQueue', callable=lambda: InputFieldQueue)  # GUI > 爬虫
        QueuesManager.register('TextBrowserQueue', callable=lambda: TextBrowserQueue)  # 爬虫 > GUI.thread
        QueuesManager.register('ProcessQueue', callable=lambda: ProcessQueue)  # 爬虫 > GUI
        QueuesManager.register('BarQueue', callable=lambda: BarQueue)  # 爬虫 > GUI.thread
        QueuesManager.register('TasksQueue', callable=lambda: TasksQueue)  # 爬虫 > GUI.thread
        for k, w in extra.items():
            QueuesManager.register(k, lambda: w)
        self.manager = QueuesManager(address=('127.0.0.1', self.queue_port), authkey=b'abracadabra')
        self.s = self.manager.get_server()
        self.s.serve_forever()

    def find_free_port(self, start_port=50000):
        for port in range(start_port, start_port + 20):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(('127.0.0.1', port))
                    self.queue_port = port
                    return port
                except Exception as e:
                    if isinstance(e, socket.error):  # Address in use
                        continue
        raise ConnectionError(f'no free port between {start_port} and {start_port + 20}')


def crawl_what(what, queue_port, **settings_kw):
    spider_what = SPIDERS
    freeze_support()
    s = get_project_settings()
    s.setmodule("ComicSpider.settings")
    s.update(settings_kw)
    process = CrawlerProcess(s)
    process.crawl(spider_what[what], queue_port=queue_port)
    process.start()
    process.join()
    process.stop()


class Url(str):
    """class for next page
    do not use fstring"""
    page = 2  # if use it, always start on page2
    step = 1
    next_suffix = NotImplementedError("not support for next page")
    replace_format: str = None
    info = None

    def __init__(self, _url):
        self.url = _url

    def set_next(self, *info):
        """info support(keep sort):
        next_suffix, replace_format, step
        """
        self.info = info
        if info and len(info) == 2:
            self.next_suffix, self.replace_format = info
        elif info and len(info) == 3:
            self.next_suffix, _, self.step = info
        else:
            self.next_suffix = info[0]
        return self

    def __str__(self):
        return self.url

    def __add__(self, _str):  # must before next/prev/jump
        return Url(f"{self.url}{_str}").set_next(*self.info)

    @property
    def next(self):
        return self.turn_page(func=lambda page: page + self.step)

    @property
    def prev(self):
        return self.turn_page(func=lambda page: page - self.step)

    def jump(self, p):
        return self.turn_page(_p=p)

    def turn_page(self, func=None, _p: int = None, match_replace: str = None):
        is_str = isinstance(self.next_suffix, str)
        if_next = re.search(self.next_suffix, self) if is_str else self.next_suffix.search(self)
        if bool(if_next):
            match = if_next.group()
            if match_replace:
                _url = self.url.replace(match, match_replace)
            else:
                current_page = int(re.search(r"\d+", match).group())
                if self.step == 1 and current_page <= 0:
                    raise ValueError("current page is less than zero")
                new = match.replace(str(current_page), str(_p or func(current_page)))
                _url = self.url.replace(match, new)
        else:
            page2 = (self.next_suffix if is_str else str(self.next_suffix.pattern)).replace(r"\d+",
                                                                                            str(_p or self.page))
            query = up.urlparse(self).query
            if self.replace_format:
                new = self.replace_format % page2
                _url = self.replace(self.replace_format.replace("%s", ""), new)
            else:
                _url = f'{self}{"&" if query else "?"}{match_replace or page2}'
        return Url(_url).set_next(*self.info)


def execute_js(js_code, func, arg):
    import execjs
    _js = execjs.compile(js_code)
    out = _js.call(func, arg)
    return out


class ClipManager:
    def __init__(self, db, sql, regex_string):
        """
        :param db, sql: by OS System
        :param regex_string: by spider
        """
        self.db = db
        self.sql = sql
        self.regex = re.compile(regex_string)

    def get_clip_items(self):
        import sqlite3
        conn = sqlite3.connect(self.db)
        cursor = conn.cursor()
        cursor.execute(self.sql)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        del conn
        return [r[0] for r in results]

    def match(self, rets):
        return list(set(filter(lambda x: bool(self.regex.search(x)), rets)))

    def main(self):
        match_items = self.match(self.get_clip_items())
        tf = PreviewByClipHtml.created_temp_html(self.regex.pattern, len(match_items))
        return tf, match_items
