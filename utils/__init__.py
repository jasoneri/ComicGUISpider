#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import re
import logging
import time
import pathlib as p
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, asdict
import multiprocessing.managers as m
import typing as t

ori_path = p.Path(__file__).parent.parent


class Conf:
    sv_path = r'D:\Comic'
    log_path = ori_path.joinpath('log')
    proxies = []
    level = 'WARNING'
    custom_kind = {}

    def get_info(self):  # 脱敏，储存路径和代理等用外部文件读
        try:
            with open(ori_path.joinpath('setting.txt'), 'r', encoding='utf-8') as fp:
                text = fp.read()
                try:
                    self.sv_path = re.findall(r'<([\s\S]*)>', text)[0]
                except IndexError:
                    pass
                try:
                    self.level = re.findall('(DEBUG|INFO|ERROR)', text)[0]
                except IndexError:
                    pass
                self.proxies = re.findall(r'(\d+\.\d+\.\d+\.\d+:\d+)', text)
                # TODO(2024-05-31): custom_kind
        except FileNotFoundError:
            pass

    def cLog(self, name: str, level: str = None, **kw) -> logging.Logger:
        """
        :return: customize obj(log)
        """
        LEVEL = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING}
        os.makedirs(self.log_path, exist_ok=True)
        logfile = self.log_path.joinpath(f"{name}.log")
        format = f'%(asctime)s | %(levelname)s | [{name}]: %(message)s'
        datefmt = '%Y-%m-%d %H:%M:%S '
        formatter = logging.Formatter(fmt=format, datefmt=datefmt)

        log_file_handler = TimedRotatingFileHandler(filename=logfile, when="D", interval=1, backupCount=3)
        log_file_handler.setFormatter(formatter)
        log_file_handler.setLevel(LEVEL[level or self.level])

        log = logging.getLogger(str(logfile))
        log.addHandler(log_file_handler)
        log.setLevel(LEVEL[level or self.level])
        return log

    @property
    def settings(self):
        return self.sv_path, self.log_path, self.proxies, self.level, self.custom_kind

    def __new__(cls, *args, **kwargs):
        if not hasattr(Conf, "_instance"):
            Conf._instance = object.__new__(cls)
            Conf._instance.get_info()
        return Conf._instance


conf = Conf()


class PresetHtmlEl:
    _rule = ['em', ]
    _compile = '|'.join(map(lambda _: f"<[/]?{_}>", _rule))
    regex = re.compile(_compile)

    @classmethod
    def sub(cls, string):
        return cls.regex.sub('', string)


def font_color(string, **attr):
    attr = re.findall(r"'(.*?)': (.*?)[,\}]", str(attr))
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


if __name__ == '__main__':
    ...
