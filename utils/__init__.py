#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import re
import logging
import time
import yaml
import pathlib as p
import typing as t
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, asdict, field
import multiprocessing.managers as m

ori_path = p.Path(__file__).parent.parent
yaml.warnings({'YAMLLoadWarning': False})


@dataclass
class Conf:
    sv_path: t.Union[p.Path, str] = r'D:\Comic'
    cv_proj_path: t.Union[p.Path, str] = r'D:\comic_viewer'
    log_path = ori_path.joinpath('log')
    proxies: list = field(default_factory=list)
    log_level: str = 'WARNING'
    custom_map: dict = field(default_factory=dict)
    file = None

    def __init__(self):
        super(Conf).__init__()
        self.init_conf()

    def init_conf(self):  # 脱敏，储存路径和代理等用外部文件读
        try:
            with open(self.file, 'r', encoding='utf-8') as fp:
                cfg = fp.read()
            yml_config = yaml.load(cfg, Loader=yaml.FullLoader)
            for k, v in yml_config.items():
                self.__setattr__(k, v or getattr(self, k, None))
            self.sv_path = p.Path(self.sv_path)
        except FileNotFoundError:
            pass

    def update(self, **kwargs):
        def path_like_handle(_p):
            return str(_p) if isinstance(_p, p.Path) else _p
        for k, v in kwargs.items():
            self.__setattr__(k, p.Path(v) if k == "sv_path" else v)
        props = asdict(self)
        props['sv_path'] = path_like_handle(props['sv_path'])
        props['cv_proj_path'] = path_like_handle(props['cv_proj_path'])
        with open(self.file, 'w', encoding='utf-8') as fp:
            yaml_data = yaml.dump(props, allow_unicode=True)
            fp.write(yaml_data)

    def cLog(self, name: str, level: str = None, **kw) -> logging.Logger:
        """
        :return: customize obj(log)
        """
        LEVEL = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING, "ERROR": logging.ERROR}
        os.makedirs(self.log_path, exist_ok=True)
        logfile = self.log_path.joinpath(f"{name}.log")
        format = f'%(asctime)s | %(levelname)s | [{name}]: %(message)s'
        datefmt = '%Y-%m-%d %H:%M:%S'
        formatter = logging.Formatter(fmt=format, datefmt=datefmt)

        log_file_handler = TimedRotatingFileHandler(filename=logfile, when="D", interval=1, backupCount=3)
        log_file_handler.setFormatter(formatter)
        log_file_handler.setLevel(LEVEL[level or self.log_level])

        log = logging.getLogger(str(logfile))
        log.addHandler(log_file_handler)
        log.setLevel(LEVEL[level or self.log_level])
        return log

    @property
    def settings(self):
        return self.sv_path, self.log_path, self.proxies, self.log_level, self.custom_map

    def __new__(cls, *args, path: t.Optional[p.Path] = None, **kwargs):
        _instance = f"_instance_{path.name}" if path else "_instance"
        if not hasattr(Conf, _instance):
            setattr(Conf, _instance, object.__new__(cls))
            getattr(Conf, _instance).file = (path or ori_path).joinpath('conf.yml')
        return getattr(Conf, _instance)


conf = Conf()


class PresetHtmlEl:
    _rule = ['em', ]
    _compile = '|'.join(map(lambda _: f"<[/]?{_}>", _rule)) + "|&nbsp;"
    regex = re.compile(_compile)

    @classmethod
    def sub(cls, string):
        return cls.regex.sub('', string)


def font_color(string, **attr):
    attr = re.findall(r"'(.*?)': (.*?)[,\}]", str(attr))  # 看正则group(2),将dict的value为str时的引号带进去了,dict.items()不行
    return f"""<font {" ".join([f"{_[0]}={_[1]}" for _ in attr])}>{string}</font>"""


def transfer_input(_input: str) -> list:
    """
    "6" return [6]       |   "1+3+5" return [1,3,5]  |
    "4-6" return [4,5,6] | "1+4-6" return [1,4,5,6]

    :param _input: _str
    :return: [int，]
    """

    def f(s):  # example '4-8' turn to {4,5,6,7,8}
        ranges = s.split(r'-')
        return set(range(int(ranges[0]), int(ranges[1]) + 1))

    out1 = set(map(int, re.findall(r'(\d{1,4})', _input)))
    out2 = set()
    for i in re.findall(r'(\d{1,4}-\d{1,4})', _input):
        out2 |= f(i)
    return sorted(out1 | out2)


domain_regex = re.compile("https?://(.*?)/")


def correct_domain(spider_domain, url) -> str:
    _domain = domain_regex.search(url).group(1)
    return url.replace(_domain, spider_domain)


cn_character = r'，。！？；：（）《》【】“”\‘\’、'
en_character = r',.!?;:()<>[]""\'\' '
character_table = str.maketrans(cn_character, en_character)


def convert_punctuation(text):
    return text.translate(character_table)


class State:
    buffer: dict = None

    def sv_cache(self):
        """take snapshot when sth occur
        run before sent
        """
        try:
            self.buffer = asdict(self)
        except AttributeError:
            ...

    def __eq__(self, other):
        return asdict(self) == other.buffer

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if key != 'buffer':
            self.sv_cache()


class QueuesManager(m.BaseManager):
    @staticmethod
    def create_manager(*register_fields, **cls_kwargs):
        for field in register_fields:
            QueuesManager.register(field)
        m = QueuesManager(**cls_kwargs)
        return m

    def connect(self):
        while 1:
            try:
                super(QueuesManager, self).connect()
            except ConnectionRefusedError:
                time.sleep(0.2)
            else:
                break


class Queues:
    @staticmethod
    def send(queue, state: State, wait=False):
        try:
            if wait:
                while not queue.empty():
                    time.sleep(0.01)
            else:
                if not queue.empty():
                    queue.get()
        except Exception as e:
            raise e
        queue.put(state)

    @staticmethod
    def recv(queue) -> t.Optional[State]:
        try:
            if queue.empty():
                return None
            state = queue.get()
            queue.put_nowait(state)
        except Exception as e:
            raise e
        return state

    @staticmethod
    def clear(queues: iter):
        for queue in queues:
            try:
                while True:
                    queue.get_nowait()
            except:
                pass
