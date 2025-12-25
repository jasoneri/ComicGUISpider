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


class Handler:
    def __init__(self, rv_sql):
        self.sql = rv_sql

    def scan(self, sv_path: pathlib.Path, init: bool = False) -> int:
        """扫描目录下的所有漫画和同人本，更新到 episodes 表
        
        Args:
            sv_path: 扫描路径，默认使用 conf.sv_path
            init: 是否为初始化扫描（清空现有数据）
        
        Returns:
            扫描到的章节总数
        """
        # 正则提取UUID（用于判断是否为同人本）
        uuid_regex = re.compile(r'\[([a-f0-9]{32})\]$')
        
        # 获取文件系统中实际存在的章节
        fs_episodes = set()  # 存储 (book, ep, ero) 元组
        
        # 扫描普通漫画目录
        for book_dir in filter(lambda x: x.is_dir() and x.name not in expect_dir, sv_path.iterdir()):
            book_name = book_dir.name
            for section in book_dir.iterdir():
                ep_name = None
                if section.is_dir():
                    ep_name = section.name
                elif section.is_file() and section.suffix.lower() in SUPPORTED_COMIC_FORMATS:
                    ep_name = section.stem
                if ep_name:
                    fs_episodes.add((book_name, ep_name, 0))
        
        # 扫描同人本目录（ERO_BOOK_FOLDER）
        ero_folder = sv_path.joinpath(res.SPIDER.ERO_BOOK_FOLDER)
        if ero_folder.exists() and ero_folder.is_dir():
            for item in ero_folder.iterdir():
                if item.is_dir():
                    # 检查是否为系列本（有子目录）
                    has_subdirs = any(sub.is_dir() for sub in item.iterdir())
                    
                    if has_subdirs:
                        # 系列本：目录名为 book，子目录/文件为 ep
                        book_name = uuid_regex.sub('', item.name).strip()
                        for sub in item.iterdir():
                            ep_name = None
                            if sub.is_dir():
                                ep_name = uuid_regex.sub('', sub.name).strip()
                            elif sub.is_file() and sub.suffix.lower() in SUPPORTED_COMIC_FORMATS:
                                ep_name = uuid_regex.sub('', sub.stem).strip()
                            if ep_name:
                                fs_episodes.add((book_name, ep_name, 1))
                    else:
                        # 单本：目录名即为 book，ep 为 'meaningless'
                        book_name = uuid_regex.sub('', item.name).strip()
                        fs_episodes.add((book_name, None, 1))
                
                elif item.is_file() and item.suffix.lower() in SUPPORTED_COMIC_FORMATS:
                    # 文件形式的单本
                    book_name = uuid_regex.sub('', item.stem).strip()
                    fs_episodes.add((book_name, None, 1))
        
        if init:
            # 初始化模式：清空表后重新写入
            self.sql.cursor.execute(f"DELETE FROM {self.sql.eps_tb}")
            self.sql.conn.commit()
            episodes_to_write = [(book, ep, 1, None, ero) for book, ep, ero in fs_episodes]
            if episodes_to_write:
                self.sql.batch_write_episodes(episodes_to_write)
        else:
            # 非初始化模式：对比数据库和文件系统
            # 1. 获取数据库中的所有记录
            db_episodes = self.sql.get_episodes()
            db_episodes_map = {(book, ep, ero): (exist, rv_handle)
                             for book, ep, exist, rv_handle, ero in db_episodes}
            
            episodes_to_update = []
            
            # 2. 遍历文件系统中的章节
            for book, ep, ero in fs_episodes:
                key = (book, ep, ero)
                if key in db_episodes_map:
                    # 记录存在，如果 exist 不是 1，则更新为 1
                    old_exist, rv_handle = db_episodes_map[key]
                    if old_exist != 1:
                        episodes_to_update.append((book, ep, 1, rv_handle, ero))
                else:
                    # 记录不存在，插入新记录
                    episodes_to_update.append((book, ep, 1, None, ero))
            
            # 3. 检查数据库中存在但文件系统中不存在的记录，将 exist 设为 0
            for (book, ep, ero), (exist, rv_handle) in db_episodes_map.items():
                if (book, ep, ero) not in fs_episodes and exist != 0:
                    # 文件已被删除，更新 exist=0
                    episodes_to_update.append((book, ep, 0, rv_handle, ero))
            
            # 4. 批量写入/更新
            if episodes_to_update:
                self.sql.batch_write_episodes(episodes_to_update)
        
        return len(fs_episodes)


    def show_max(self) -> t.Dict[str, BookShow]:
        """从 episodes 表读取已读和已下载的最大章节信息"""
        sec_regex = re.compile(r'.*?(\d+\.?\d*)')
        
        # 从数据库读取数据
        all_episodes = self.sql.get_episodes()
        
        show_map_raw = {}  # 已读记录（rv_handle 非空）
        dl_map_raw = {}    # 已下载记录（exist=1）
        
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
        self.sql.delete_episodes(bn)
