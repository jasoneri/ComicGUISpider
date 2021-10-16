import os
import re
import logging
from logging.handlers import TimedRotatingFileHandler


def get_info():
    sv_path, log_path, proxies, level = r'D:\Comic', './log', [], 'WARNING'
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
    except FileNotFoundError:
        # print(f"occur exception: {str(type(e))}:: {str(e)}")
        pass
    return sv_path, log_path, proxies, level


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


if __name__=='__main__':
    judge_input('1+4-5-10+15-18-20+25')
    pass
