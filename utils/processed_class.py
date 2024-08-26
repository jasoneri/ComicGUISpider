#!/usr/bin/python
# -*- coding: utf-8 -*-
import tempfile
import time
import typing as t
import socket
from dataclasses import dataclass
from multiprocessing import Queue, freeze_support

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from utils import State, QueuesManager, Queues, ori_path, re
from variables import SPIDERS


@dataclass
class InputFieldState(State):
    keyword: str
    bookSelected: int
    indexes: t.Union[str, list]
    pageTurn: t.Union[str, int]


@dataclass
class TextBrowserState(State):
    text: str


@dataclass
class ProcessState(State):
    process: str


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

    def create_server_manager(self):
        InputFieldQueue = Queue()
        TextBrowserQueue = Queue(2)
        ProcessQueue = Queue()
        BarQueue = Queue()
        QueuesManager.register('InputFieldQueue', callable=lambda: InputFieldQueue)  # GUI > 爬虫
        QueuesManager.register('TextBrowserQueue', callable=lambda: TextBrowserQueue)  # 爬虫 > GUI.thread
        QueuesManager.register('ProcessQueue', callable=lambda: ProcessQueue)  # 爬虫 > GUI
        QueuesManager.register('BarQueue', callable=lambda: BarQueue)  # 爬虫 > GUI.thread
        manager = QueuesManager(address=('127.0.0.1', self.queue_port), authkey=b'abracadabra')
        self.s = manager.get_server()
        self.s.serve_forever()

    def find_free_port(self):
        for i in range(50000, 50020):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            try:
                result = sock.connect_ex(('localhost', i))
                if result == 0:
                    sock.close()
                    continue
                else:
                    self.queue_port = i
                    sock.close()
                    break
            except Exception as e:
                sock.close()
        else:
            raise ConnectionError('no free port between 50000 and 50020 ')
        del sock
        return self.queue_port


def crawl_what(what, queue_port, **settings_kw):
    spider_what = SPIDERS
    freeze_support()
    s = get_project_settings()
    s.update(settings_kw)
    process = CrawlerProcess(s)
    process.crawl(spider_what[what], queue_port=queue_port)
    process.start()
    process.join()
    process.stop()


class PreviewHtml:
    format_path = ori_path.joinpath("GUI/src/preview_format")

    class bootstrap:
        @staticmethod
        def create_element(idx, img_src, title, url):
            max_width = 170
            title_thumbnail = title[:18] + "..."
            el = f"""<div class="col-md-3" style="max-width:{max_width}px"><div class="form-check">
            <input class="form-check-input" type="checkbox" name="img" id="{idx}">
            <label class="form-check-label" for="{idx}">
              <img src="{img_src}" title="{title}" alt="{title}" class="img-thumbnail"/>
            </label></div>
            <a href="{url}"><p>[{idx}]、{title_thumbnail}</p></a>
            </div>"""
            return el

    def __init__(self, url=None, html_style="bootstrap"):
        self.contents = []
        self.html_style = html_style
        self.url = url

    def add(self, *args):
        self.contents.append(getattr(self, self.html_style).create_element(*args))

    @property
    def created_temp_html(self):
        temp_p = ori_path.joinpath("__temp")
        temp_p.mkdir(exist_ok=True)
        with open(self.format_path.joinpath(rf"{self.html_style}.html"), 'r', encoding='utf-8') as f:
            format_text = f.read()
        _content = "\n".join(self.contents)
        if self.url:
            _content += f'\n<div class="col-md-3"><p>for check current page</p><p>检查当前页数</p><p>{self.url}</p></div>'
        html = format_text.replace("{body}", _content)
        tf = tempfile.TemporaryFile(suffix=".html", delete=False, dir=temp_p)
        tf.write(bytes(html, 'utf-8'))
        f = str(tf.name)
        tf.close()
        return f


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

    def __add__(self, _str):  # must before next/previous/jump
        return Url(self.url + _str).set_next(*self.info)

    @property
    def next(self):
        return self.turn_page(func=lambda page: page + self.step)

    @property
    def previous(self):
        return self.turn_page(func=lambda page: page - self.step)

    def jump(self, p):
        return self.turn_page(_p=p)

    def turn_page(self, func=None, _p: int = None):
        if_next = re.search(self.next_suffix, self)
        if if_next:
            match = if_next.group()
            current_page = int(re.search(r"\d+", match).group())
            if self.step == 1 and current_page <= 0:
                raise ValueError("current page is less than zero")
            new = match.replace(str(current_page), str(_p or func(current_page)))
            _url = self.url.replace(match, new)
        else:
            page2 = self.next_suffix.replace(r"\d+", str(_p or self.page))
            if self.replace_format:
                new = self.replace_format % page2
                _url = self.replace(self.replace_format.replace("%s", ""), new)
            else:
                _url = self + f'&{page2}'
        return Url(_url).set_next(*self.info)
