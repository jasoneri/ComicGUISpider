#!/usr/bin/python
# -*- coding: utf-8 -*-
import pathlib
import re
import shutil
from pprint import pprint

from tqdm import tqdm


def combine_then_mv(root_dir, target_dir, order_book=None):
    expect_dir = ('web', 'web_handle')
    p = pathlib.Path(root_dir)
    target_p = pathlib.Path(target_dir)
    for order_dir in filter(lambda x: x.is_dir() and x.name not in expect_dir, p.iterdir()):
        for ordered_section in tqdm(order_dir.iterdir()):
            ___ = target_p.joinpath(f"{order_dir.name}_{ordered_section.name}")
            if ___.exists():
                shutil.rmtree(___)
            shutil.move(ordered_section, ___)
        shutil.rmtree(order_dir)


def restore(ori):
    p = pathlib.Path(ori)
    book_p = None
    for i in tqdm(p.iterdir()):
        book, section = i.name.split('_')
        if not p.parent.joinpath(book).exists():
            book_p = p.parent.joinpath(book)
            book_p.mkdir(exist_ok=True)
        shutil.move(i, book_p.joinpath(section))


def show_max(record_file):
    sec_regex = re.compile(r'.*?(\d+\.?\d?)')
    format_regex = re.compile('<(del|save|remove)>')
    temp = {}
    with open(record_file, 'r', encoding='utf-8') as f:
        for line in f.readlines():
            book, section = format_regex.sub('', line.strip()).split('_')
            if book not in temp:
                temp[book] = []
            temp[book].append(section)
    for book, sections in temp.items():
        temp[book] = max(temp[book],
                         key=lambda x: float(sec_regex.search(x).group(1)) if sec_regex.search(x) else 0)
    pprint(temp)


if __name__ == '__main__':
    # 破鞋神二世(怪怪守护神)
    combine_then_mv(r"D:\Comic\后宫露营", r"D:\Comic\web")
    # restore(r"D:\Comic\web")
    # show_max(r"D:\Comic\web_handle\record.txt")
