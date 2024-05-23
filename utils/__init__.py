#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import re
import logging
import time
from logging.handlers import TimedRotatingFileHandler
from dataclasses import dataclass, asdict
import multiprocessing.managers as m
from copy import deepcopy
import typing as t


def get_info():
    sv_path, log_path, proxies, level = r'D:\Comic', './log', [], 'WARNING'
    erocool_domain = []
    try:
        with open(f'./setting.txt', 'r', encoding='utf-8') as fp:
            text = fp.read()
            try:
                sv_path = re.findall(r'<([\s\S]*)>', text)[0]
            except IndexError:
                pass
            try:
                level = re.findall('(DEBUG|INFO|ERROR)', text)[0]
            except IndexError:
                pass
            proxies = re.findall(r'(\d+\.\d+\.\d+\.\d+:\d+?)', text)
            erocool_domain = re.findall(r"#([\s\S]*)#", text)
    except FileNotFoundError:
        # print(f"occur exception: {str(type(e))}:: {str(e)}")
        pass
    return sv_path, log_path, proxies, level, erocool_domain


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


def cLog(name: str, level: str = 'INFO', **kw) -> logging.Logger:
    """
    :return: customize obj(log)
    """
    try:
        with open(f'./setting.txt', 'r', encoding='utf-8') as fp:
            text = fp.read()
            level = re.search('(DEBUG|WARNING|ERROR)', text).group(1)
    except:
        pass
    LEVEL = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING}
    os.makedirs('log', exist_ok=True)
    logfile = F"log/{name}.log"
    format = f'%(asctime)s | %(levelname)s | [{name}]: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S '
    formatter = logging.Formatter(fmt=format, datefmt=datefmt)

    log_file_handler = TimedRotatingFileHandler(filename=logfile, when="D", interval=1, backupCount=3)
    log_file_handler.setFormatter(formatter)
    log_file_handler.setLevel(LEVEL[level])

    log = logging.getLogger(logfile)
    log.addHandler(log_file_handler)
    log.setLevel(LEVEL[level])
    return log


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
    pass

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
