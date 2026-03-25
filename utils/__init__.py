#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import ast
import ssl
import sys
import time
import html
import builtins
import hashlib
import asyncio
import platform
import contextlib
from functools import lru_cache
import pathlib as p
import typing as t
from dataclasses import asdict

from utils.config import *
from utils.core import *

temp_p = ori_path.joinpath("__temp")
temp_p.mkdir(exist_ok=True)

conf = Conf()


@lru_cache(maxsize=1)
def get_httpx_verify():
    if platform.system() == "Windows":
        with contextlib.suppress(ssl.SSLError):
            ctx = ssl.create_default_context()
            if ctx.get_ca_certs():
                return ctx
    return True


def bs_theme():
    return "dark" if conf.darkTheme else "light"


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


def fin_transfer(_elect, _results_keys) -> list:
    def _transfer():
        if _elect == '0':
            return _results_keys
        elif isinstance(_elect, list):
            return _elect
        elif bool(minus_regex.search(_elect)):
            return sorted(_results_keys)[int(_elect):]
        elif _elect.startswith('[combine]'):
            brower_input, _input = _elect[9:].split(' and ')
            cb_tra = list(set(ast.literal_eval(brower_input)) | (
                set(transfer_input(_input)) if not bool(minus_regex.search(_input)) else 
                set(fin_transfer(_input, _results_keys))))
            return [int(x) for x in cb_tra]
        return transfer_input(_elect)
    return _transfer()


def select(elect, infos: dict, **kw) -> list:
    """简单判断elect，返回选择的frame
    注: 剪贴板模式用SpiderGUI.clip_mgr.create_selected_list，无需在这兼容处理str
    :param elect: [1,2,3,4,……], [0], -3, "1+5-7", "[combine]['3'] and "
    :param infos: {1: InfoMinix1, 2: InfoMinix2……}
    :return: [book1, book2……]
    """
    _selected = fin_transfer(elect, sorted(infos.keys()))
    results = [infos[i] for i in _selected]
    return results


def extract_eps_range(text) -> str:
    matches = re.findall(r'-(\d+)', text)
    if not matches:
        return ""
    numbers = [int(num) for num in matches]
    first_num = numbers[0]
    if len(numbers) > 1 and numbers[-1] < first_num:
        numbers = numbers[:-1]
    if len(numbers) == 1:
        return f"{first_num}"
    return f"{min(numbers)}-{max(numbers)}"


cn_character = r'，。！？；：（）《》【】“”\‘\’、'
en_character = r',.!?;:()<>[]""\'\' '
character_table = str.maketrans(cn_character, en_character)


def convert_punctuation(text):
    return text.translate(character_table)


def clean_escape_chars(text):
    return text.replace('\\\\', '\\').replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')


def md5(_str):
    return hashlib.md5(_str.encode()).hexdigest()


def get_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


_QFLUENT_PRO_MARKERS = (
    "QFluentWidgets Pro is now released",
    "qfluentwidgets.com/pages/pro",
)
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def install_qfluentwidgets_notice_filter():
    """Drop the import-time QFluentWidgets Pro notice without muting other prints."""
    current_print = builtins.print
    if getattr(current_print, "_cgs_qfluent_notice_filter", False):
        return

    def filtered_print(*args, **kwargs):
        output = kwargs.get("file")
        if output is None or output is sys.stdout:
            sep = kwargs.get("sep")
            if sep is None:
                sep = " "
            text = sep.join(str(arg) for arg in args)
            normalized = _ANSI_ESCAPE_RE.sub("", text)
            if all(marker in normalized for marker in _QFLUENT_PRO_MARKERS):
                return
        return current_print(*args, **kwargs)

    filtered_print._cgs_qfluent_notice_filter = True
    builtins.print = filtered_print
