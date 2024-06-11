#!/usr/bin/python
# -*- coding: utf-8 -*-
import pathlib
import shutil

from tqdm import tqdm


def combine_then_mv(ori, target):
    p = pathlib.Path(ori)
    target_p = pathlib.Path(target)
    for i in tqdm(p.iterdir()):
        ___ = target_p.joinpath(f"{p.name}_{i.name}")
        if ___.exists():
            shutil.rmtree(___)
        shutil.move(i, ___)
    shutil.rmtree(ori)


def restore(ori):
    p = pathlib.Path(ori)
    book_p = None
    for i in tqdm(p.iterdir()):
        book, section = i.name.split('_')
        if not p.parent.joinpath(book).exists():
            book_p = p.parent.joinpath(book)
            book_p.mkdir(exist_ok=True)
        shutil.move(i, book_p.joinpath(section))


if __name__ == '__main__':
    # 破鞋神二世(怪怪守护神)
    combine_then_mv(r"D:\Comic\后宫露营", r"D:\Comic\web")
    # restore(r"D:\Comic\web")
