import os
import re
import logging
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import SimpleQueue
from dataclasses import dataclass, asdict
from copy import deepcopy


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


def judge_input(_input: str) -> list:
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


def clear_queue(queues):
    for queue in queues:
        try:
            while True:
                queue.get_nowait()
        except:
            pass


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
    LEVEL = {'DEBUG':logging.DEBUG, 'INFO':logging.INFO, 'WARNING':logging.WARNING}
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


class Queues:
    def __init__(self, *args):
        for k in args:
            self.__setattr__(k, SimpleQueue())


class State:
    buffer: dict = None

    def sv_cache(self):
        """take snapshot when sth occur"""
        # 应用：用来对比属性是否变化
        self.buffer = asdict(self)
        return self.buffer

    def __eq__(self, other):
        return asdict(self) == other.buffer


@dataclass
class InputFieldState(State):
    keyword: str
    selected: str
    indexes: str


@dataclass
class TextBrowserState(State):
    text: str


if __name__=='__main__':
    i = InputFieldState(keyword='1', selected='2', indexes='3')
    # t = TextBrowserState(text='111')
    ...  # 将i推进queue

    ...  # 改变了操作
    i.keyword = '1_change'
    i.sv_cache()

    ...  # 别的地方
    else_i = InputFieldState(keyword='1', selected='2', indexes='3')
    print(else_i == i)
    pass
