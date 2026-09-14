#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import typing as t
import pathlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from assets import res
from utils import conf
from utils.config.rule import CgsRuleMgr
from utils.sql import SqlrV

expect_dir_regex = re.compile(r"^_")
accpect_dir = lambda _: not bool(expect_dir_regex.search(_))
uuid_suffix_regex = re.compile(r'\[([a-f0-9]{32})\]$')
record_file = conf.sv_path.joinpath("web_handle/record.txt")


def strip_uuid(name: str) -> str:
    """书籍/章节目录名去掉下载器附加的 `[32位hex]` 标记"""
    return uuid_suffix_regex.sub('', name).strip()


@dataclass(frozen=True)
class DirEntryInfo:
    """`os.DirEntry` 仅在 scandir 迭代期间有效,这里只保留后续需要的字段"""
    name: str
    is_dir: bool


@dataclass
class BookShow:
    name: str
    show_max: str = ""
    dl_max: str = ""

    @property
    def show(self):
        return f"🔖matched-record「{self.name}」\treaded: 【{self.show_max}】\tdownloaded: 【{self.dl_max}】"


class Handler:
    def __init__(self, ero=None):
        self.ero = ero
        self.strategy = None

    def sql(self):
        return SqlrV(self.ero)

    def scan(self, _conf, init: bool = False) -> int:
        sv_path = _conf.sv_path
        self.strategy = ScanStrategyFactory.create(CgsRuleMgr.get_download_handle(_conf))
        fs_episodes = self._scan_filesystem(sv_path)

        with self.sql() as sql:
            if init:
                sql.reset_exist()
            sql.sync_episodes(fs_episodes)

        return len(fs_episodes)

    def _scan_filesystem(self, sv_path: pathlib.Path) -> set:
        """扫描文件系统,返回所有章节信息

        根据 self.ero 决定扫描范围:
        - ero=0: 仅扫描普通漫画
        - ero=1: 仅扫描同人本
        - ero=None: 扫描所有类型

        Returns:
            {(book, ep, ero), ...}
        """
        fs_episodes = set()
        # ero=1 只扫同人本,ero=0 只扫普通漫画,None(及其它)=两者都扫
        if self.ero != 1:
            fs_episodes.update(self._scan_normal_comics(sv_path))
        if self.ero != 0:
            fs_episodes.update(self._scan_ero_books(sv_path))
        return fs_episodes

    def _scan_normal_comics(self, sv_path: pathlib.Path) -> set:
        fs_episodes = set()
        for book_name in self._list_subdir_names(sv_path):
            for episode_name in self._list_episode_names(sv_path / book_name):
                fs_episodes.add((book_name, episode_name, 0))
        return fs_episodes

    def _scan_ero_books(self, sv_path: pathlib.Path) -> set:
        fs_episodes = set()
        ero_folder = sv_path.joinpath(res.SPIDER.ERO_BOOK_FOLDER)
        if not ero_folder.is_dir():
            return fs_episodes
        for entry in self._list_entries(ero_folder):
            entry_path = ero_folder / entry.name
            if entry.is_dir and accpect_dir(entry.name):
                book_name = strip_uuid(entry.name)
                episode_names = self._list_episode_names(entry_path)
                if episode_names:
                    for episode_name in episode_names:
                        episode_alias = strip_uuid(episode_name)
                        # 单章节:章节名与书名重合时不重复展示
                        fs_episodes.add((book_name, None if episode_alias == book_name else episode_alias, 1))
                else:
                    fs_episodes.add((book_name, None, 1))
            elif self.strategy.should_scan_as_episode(entry_path):
                fs_episodes.add((strip_uuid(self.strategy.get_episode_name(entry_path)), None, 1))
        return fs_episodes

    def _list_entries(self, root: pathlib.Path) -> t.List[DirEntryInfo]:
        with os.scandir(root) as entries:
            return [DirEntryInfo(entry.name, entry.is_dir()) for entry in entries]

    def _list_subdir_names(self, root: pathlib.Path) -> t.List[str]:
        return [entry.name for entry in self._list_entries(root) if entry.is_dir and accpect_dir(entry.name)]

    def _list_episode_names(self, book_path: pathlib.Path) -> t.List[str]:
        """按当前 strategy 取出该书下所有章节名"""
        names = [entry.name for entry in self._list_entries(book_path)]
        paths = [book_path / name for name in names]
        return [self.strategy.get_episode_name(path) for path in paths if self.strategy.should_scan_as_episode(path)]

    def show_max(self) -> t.Dict[str, BookShow]:
        """从 episodes 表读取已读和已下载的最大章节信息"""
        sec_regex = re.compile(r'.*?(\d+\.?\d*)')

        with self.sql() as sql:
            all_episodes = sql.get_episodes()

        show_map_raw = {}  # 已读记录(rv_handle 非空)
        dl_map_raw = {}    # 已下载记录(exist=1)

        for book, ep, exist, rv_handle, _ in all_episodes:
            if rv_handle:
                if book not in show_map_raw:
                    show_map_raw[book] = []
                show_map_raw[book].append(ep)
            if exist:
                if book not in dl_map_raw:
                    dl_map_raw[book] = []
                dl_map_raw[book].append(ep)

        def _get_max_sections(raw_map):
            """提取每本书的最大章节"""
            processed_map = {}
            for book, sections in raw_map.items():
                if not sections:
                    continue
                processed_map[book] = max(sections,
                    key=lambda x: float(sec_regex.search(x).group(1)) if sec_regex.search(x) else 0)
            return processed_map

        show_map = _get_max_sections(show_map_raw)
        dl_map = _get_max_sections(dl_map_raw)

        all_books = show_map.keys() | dl_map.keys()
        result = {book: BookShow(name=book, show_max=show_map.get(book, ""), dl_max=dl_map.get(book, "")) for book in all_books}
        return result

    def delete_record(self, bn):
        with self.sql() as sql:
            sql.delete_episodes(bn)


# Strategy
class ScanStrategy(ABC):
    @abstractmethod
    def should_scan_as_episode(self, item: pathlib.Path) -> bool:
        pass

    @abstractmethod
    def get_episode_name(self, item: pathlib.Path) -> str:
        pass


class FolderStrategy(ScanStrategy):
    def should_scan_as_episode(self, item: pathlib.Path) -> bool:
        return item.is_dir()

    def get_episode_name(self, item: pathlib.Path) -> str:
        return item.name


class CbzStrategy(ScanStrategy):
    def should_scan_as_episode(self, item: pathlib.Path) -> bool:
        return item.is_file() and item.suffix.lower() == '.cbz'

    def get_episode_name(self, item: pathlib.Path) -> str:
        return item.stem


class ScanStrategyFactory:
    _strategies = {"-": FolderStrategy, ".cbz": CbzStrategy}

    @classmethod
    def create(cls, downloaded_handle: str) -> ScanStrategy:
        return cls._strategies.get(downloaded_handle, FolderStrategy)()
