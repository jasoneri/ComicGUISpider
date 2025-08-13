#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import ast
import time
import html
import hashlib
import asyncio
import pathlib as p
import typing as t
from dataclasses import asdict
import multiprocessing.managers as m

from utils.config import *

temp_p = ori_path.joinpath("__temp")
temp_p.mkdir(exist_ok=True)

conf = Conf()


class PresetHtmlEl:
    _rule = ['em', ]
    _compile = '|'.join(map(lambda _: f"<[/]?{_}>", _rule)) + "|&nbsp;"
    regex = re.compile(_compile)

    @classmethod
    def sub(cls, string):
        return cls.regex.sub('', html.unescape(string)).rstrip('.')


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


minus_regex = re.compile(r'^-\d+$')


def fin_transfer(_elect, _results_keys):
    if _elect == '0':
        return _results_keys
    elif isinstance(_elect, list):
        return _elect
    elif bool(minus_regex.search(_elect)):
        return sorted(_results_keys)[int(_elect):]
    elif _elect.startswith('[combine]'):
        brower_input, _input = _elect[9:].split(' and ')
        return list(set(ast.literal_eval(brower_input)) | (
            set(transfer_input(_input)) if not bool(minus_regex.search(_input)) else 
            set(sorted(_results_keys)[int(_input):])))
    return transfer_input(_elect)


cn_character = r'，。！？；：（）《》【】“”\‘\’、'
en_character = r',.!?;:()<>[]""\'\' '
character_table = str.maketrans(cn_character, en_character)


def convert_punctuation(text):
    return text.translate(character_table)


def clean_escape_chars(text):
    return text.replace('\\\\', '\\').replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')

class State:
    """gui与后端需要共用的一个状态变量时，使用此类；
    由于处于不同进程，需要创建一个对应的Queues做通讯"""
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
        loop = 0
        while loop < 25:
            try:
                super(QueuesManager, self).connect()
            except ConnectionRefusedError:
                time.sleep(0.2)
                loop += 1
            else:
                return
        raise ConnectionRefusedError("Failed to connect to manager")


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


def md5(_str):
    return hashlib.md5(_str.encode()).hexdigest()


def get_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop
