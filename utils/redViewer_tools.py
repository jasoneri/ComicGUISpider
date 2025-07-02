#!/usr/bin/python
# -*- coding: utf-8 -*-
import pathlib
import re
import shutil
from dataclasses import dataclass

from tqdm import tqdm

from assets import res
from utils import conf

expect_dir = ('web', 'web_handle', 'log', res.SPIDER.ERO_BOOK_FOLDER)
record_file = conf.sv_path.joinpath("web_handle/record.txt")


def combine_then_mv(root_dir, target_dir, order_book=None) -> list:
    p = pathlib.Path(root_dir)
    target_p = pathlib.Path(target_dir)
    done = []
    for order_dir in filter(lambda x: x.is_dir() and x.name not in expect_dir, p.iterdir()):
        for ordered_section in tqdm(order_dir.iterdir()):
            ___ = target_p.joinpath(f"{order_dir.name}_{ordered_section.name}")
            if ___.exists():
                shutil.rmtree(___)
            shutil.move(ordered_section, ___)
        shutil.rmtree(order_dir)
        done.append(order_dir.name)
    return done


def restore(ori):
    p = pathlib.Path(ori)
    book_p = None
    for i in tqdm(p.iterdir()):
        book, section = i.name.split('_')
        if not p.parent.joinpath(book).exists():
            book_p = p.parent.joinpath(book)
            book_p.mkdir(exist_ok=True)
        shutil.move(i, book_p.joinpath(section))


@dataclass
class BookShow:
    name: str
    show_max: str = ""
    dl_max: str = ""


def show_max() -> list[BookShow]:
    sec_regex = re.compile(r'.*?(\d+\.?\d*)')
    format_regex = re.compile('<(del|save|remove)>')
    show_map_raw = {}
    if record_file.exists():
        with open(record_file, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                book, section = format_regex.sub('', line.strip()).split('_')
                if book not in show_map_raw:
                    show_map_raw[book] = []
                show_map_raw[book].append(section)

    dl_map_raw = {}
    web_path = conf.sv_path.joinpath("web")
    if web_path.exists():
        for item in web_path.iterdir():
            try:
                book, section = item.name.split('_')
                if book not in dl_map_raw:
                    dl_map_raw[book] = []
                dl_map_raw[book].append(section)
            except ValueError:
                continue

    for book_dir in filter(lambda x: x.is_dir() and x.name not in expect_dir, conf.sv_path.iterdir()):
        for section in book_dir.iterdir():
            if section.is_dir():
                if book_dir.name not in dl_map_raw:
                    dl_map_raw[book_dir.name] = []
                dl_map_raw[book_dir.name].append(section.name)

    def _get_max_sections(raw_map):
        processed_map = {}
        for book, sections in raw_map.items():
            processed_map[book] = max(sections,
                key=lambda x: float(sec_regex.search(x).group(1)) if sec_regex.search(x) else 0)
        return processed_map

    show_map = _get_max_sections(show_map_raw)
    dl_map = _get_max_sections(dl_map_raw)

    all_books = show_map.keys() | dl_map.keys()
    result = [BookShow(name=book, show_max=show_map.get(book, ""), dl_max=dl_map.get(book, "")) for book in all_books]
    return result


def delete_record(bn):
    regex = re.compile(f'{bn}.*')
    temp_file = record_file.with_suffix('.tmp')
    with open(record_file, 'r', encoding='utf-8') as f_in, \
            open(temp_file, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            if bool(regex.search(line)):
                continue
            f_out.write(line)
    temp_file.replace(record_file)


if __name__ == '__main__':
    results = show_max()
