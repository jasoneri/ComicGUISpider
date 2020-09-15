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


def font_color(string, colour='red', size=None):
    size = f" size='{size}'" if size else None
    return f"<font color='{colour}'{size}>{string}</font>"


def judge_input(_input):
    """
    6 return [6]
    1+3+5 return [1,3,5]
    4-6 return [4,5,6] | 1-4+6 return [1,4,5,6]

    :param _input: _str
    :return: [int，]
    """

    def f(s):                                           # example '4-8' turn to [4,5,6,7,8]
        l = []
        ranges = s.split(r'-')
        if len(ranges)==1:
            l.append(ranges[0])
        else:
            for i in range(int(ranges[0]), int(ranges[1]) + 1):
                l.append(i)
        return l

    i_tnsfr = []
    i_group = re.findall(r'(\d{1,4}-\d{1,4})', _input)  # filter out '/d-/d'
    for i_g_s in i_group:
        _input = _input.replace(i_g_s, '')
        i_tnsfr.extend(f(i_g_s))                        # extract '/d-/d'
    _input = re.findall(r'(\d{1,4})', _input)           # get except filter out of '/d-/d'
    i_tnsfr.extend(_input)
    i_fin = sorted(set(map(lambda x: int(x), i_tnsfr)))
    return i_fin


def clear_queue(queues):
    for queue in queues:
        try:
            while True:
                queue.get_nowait()
        except:
            pass


def cLog(name, level='INFO', **kw):
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
    log_name = "log/GUI.log"
    format = f'%(asctime)s | %(levelname)s | [{name}]: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S '
    formatter = logging.Formatter(fmt=format, datefmt=datefmt)

    log_file_handler = TimedRotatingFileHandler(filename=log_name, when="D", interval=1, backupCount=3)
    log_file_handler.setFormatter(formatter)
    log_file_handler.setLevel(LEVEL[level])

    log = logging.getLogger(log_name)
    log.addHandler(log_file_handler)
    log.setLevel(LEVEL[level])
    return log
