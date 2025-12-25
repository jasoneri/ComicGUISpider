#!/usr/bin/python
# -*- coding: utf-8 -*-
import typing as t
import pathlib
import re
from dataclasses import dataclass

from assets import res
from utils import conf

expect_dir = ('_save', res.SPIDER.ERO_BOOK_FOLDER)
record_file = conf.sv_path.joinpath("web_handle/record.txt")

SUPPORTED_COMIC_FORMATS = {'.cbz', '.cb7', '.pdf'}


@dataclass
class BookShow:
    name: str
    show_max: str = ""
    dl_max: str = ""

    @property
    def show(self):
        return f"🔖matched-record「{self.name}」\treaded: 【{self.show_max}】\tdownloaded: 【{self.dl_max}】"


def show_max() -> t.Dict[str, BookShow]:
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

    for book_dir in filter(lambda x: x.is_dir() and x.name not in expect_dir, conf.sv_path.iterdir()):
        for section in book_dir.iterdir():
            section_name = None
            if section.is_dir():
                section_name = section.name
            elif section.is_file() and section.suffix.lower() in SUPPORTED_COMIC_FORMATS:
                section_name = section.stem  # 去除后缀，例如 "第100話.cbz" -> "第100話"
            if section_name:
                if book_dir.name not in dl_map_raw:
                    dl_map_raw[book_dir.name] = []
                dl_map_raw[book_dir.name].append(section_name)

    def _get_max_sections(raw_map):
        processed_map = {}
        for book, sections in raw_map.items():
            processed_map[book] = max(sections,
                key=lambda x: float(sec_regex.search(x).group(1)) if sec_regex.search(x) else 0)
        return processed_map

    show_map = _get_max_sections(show_map_raw)
    dl_map = _get_max_sections(dl_map_raw)

    all_books = show_map.keys() | dl_map.keys()
    result = {book: BookShow(name=book, show_max=show_map.get(book, ""), dl_max=dl_map.get(book, "")) for book in all_books}
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
