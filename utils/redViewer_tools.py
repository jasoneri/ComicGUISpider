#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import typing as t
import pathlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

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
    is_file: bool


@dataclass(frozen=True)
class ScanContext:
    root: pathlib.Path
    mode: int | None
    rule: str

    @classmethod
    def capture(cls, _conf, mode: int | None):
        return cls(pathlib.Path(_conf.sv_path), mode, CgsRuleMgr.get_download_handle(_conf))


@dataclass(frozen=True)
class ScanEntry:
    local_path: pathlib.Path
    relative_path: pathlib.Path
    mode: int
    kind: t.Literal["dir", "cbz"]
    book: str
    ep: str | None


@dataclass(frozen=True)
class ScanSnapshot:
    root: pathlib.Path
    mode: int | None
    rule: str
    entries: tuple[ScanEntry, ...]


@dataclass
class BookShow:
    name: str
    show_max: str = ""
    dl_max: str = ""

    @property
    def show(self):
        return f"🔖matched-record「{self.name}」\treaded: 【{self.show_max}】\tdownloaded: 【{self.dl_max}】"


class Handler:
    def __init__(self, ero=None, *, scan_context: ScanContext | None = None):
        self.ero = ero if scan_context is None else scan_context.mode
        self.scan_context = scan_context
        self.strategy = None
        self.snapshot: ScanSnapshot | None = None

    def sql(self):
        sql = SqlrV(self.ero)
        if self.scan_context is not None:
            sql.db = self.scan_context.root / "rV.db"
        return sql

    def scan(self, _conf, init: bool = False) -> int:
        context = self.scan_context or ScanContext.capture(_conf, self.ero)
        self.strategy = ScanStrategyFactory.create(context.rule)
        entries = self._scan_filesystem(context.root)
        fs_episodes = {(entry.book, entry.ep, entry.mode) for entry in entries}

        database = self.sql()
        database.db = context.root / "rV.db"
        with database as sql:
            if init:
                sql.reset_exist()
            sql.sync_episodes(fs_episodes)

        self.snapshot = ScanSnapshot(context.root, context.mode, context.rule, entries)
        return len(fs_episodes)

    def _scan_filesystem(self, sv_path: pathlib.Path) -> tuple[ScanEntry, ...]:
        entries = []
        roots = self._list_entries(sv_path)
        if self.ero != 1:
            entries.extend(self._scan_normal_comics(sv_path, roots))
        if self.ero != 0:
            for root in roots:
                if root.is_dir and root.name in ("_本子", "_Doujinshi"):
                    entries.extend(self._scan_ero_books(sv_path / root.name))
        return tuple(entries)

    def _scan_normal_comics(self, sv_path: pathlib.Path, roots: list[DirEntryInfo]):
        for book in roots:
            if not book.is_dir or not accpect_dir(book.name):
                continue
            for episode in self._list_entries(sv_path / book.name):
                if self.strategy.should_scan_as_episode(episode):
                    relative = pathlib.Path(book.name, episode.name)
                    yield ScanEntry(sv_path / relative, relative, 0, "dir" if episode.is_dir else "cbz",
                        book.name, self.strategy.get_episode_name(episode))

    def _scan_ero_books(self, ero_folder: pathlib.Path):
        for entry in self._list_entries(ero_folder):
            entry_path = ero_folder / entry.name
            if entry.is_dir and accpect_dir(entry.name):
                book_name = strip_uuid(entry.name)
                episodes = [ep for ep in self._list_entries(entry_path) if self.strategy.should_scan_as_episode(ep)]
                if episodes:
                    for episode in episodes:
                        episode_alias = strip_uuid(self.strategy.get_episode_name(episode))
                        relative = pathlib.Path(entry.name, episode.name)
                        yield ScanEntry(ero_folder / relative, relative, 1, "dir" if episode.is_dir else "cbz",
                            book_name, None if episode_alias == book_name else episode_alias)
                else:
                    yield ScanEntry(entry_path, pathlib.Path(entry.name), 1, "dir", book_name, None)
            elif self.strategy.should_scan_as_episode(entry):
                yield ScanEntry(entry_path, pathlib.Path(entry.name), 1, "dir" if entry.is_dir else "cbz",
                    strip_uuid(self.strategy.get_episode_name(entry)), None)

    def _list_entries(self, root: pathlib.Path) -> list[DirEntryInfo]:
        with os.scandir(root) as entries:
            return [DirEntryInfo(entry.name, entry.is_dir(), entry.is_file()) for entry in entries]

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
                processed_map[book] = max(sections, key=lambda x: float(sec_regex.search(x).group(1)) if sec_regex.search(x) else 0)
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
    def should_scan_as_episode(self, item: DirEntryInfo) -> bool:
        pass

    @abstractmethod
    def get_episode_name(self, item: DirEntryInfo) -> str:
        pass


class FolderStrategy(ScanStrategy):
    def should_scan_as_episode(self, item: DirEntryInfo) -> bool:
        return item.is_dir

    def get_episode_name(self, item: DirEntryInfo) -> str:
        return item.name


class CbzStrategy(ScanStrategy):
    def should_scan_as_episode(self, item: DirEntryInfo) -> bool:
        return item.is_file and item.name.lower().endswith('.cbz')

    def get_episode_name(self, item: DirEntryInfo) -> str:
        return item.name[:-4]


class ScanStrategyFactory:
    _strategies = {"-": FolderStrategy, ".cbz": CbzStrategy}

    @classmethod
    def create(cls, downloaded_handle: str) -> ScanStrategy:
        return cls._strategies.get(downloaded_handle, FolderStrategy)()
