#!/usr/bin/python
# -*- coding: utf-8 -*-
import sqlite3

from utils import conf_dir, md5
from variables import SPECIAL_WEBSITES


class SqlRecorder:
    init_flag = False

    def __init__(self):
        self.db = conf_dir.joinpath("record.db")
        if not self.db.exists():
            self.init_flag = True
        self.conn = sqlite3.connect(self.db)
        self.cursor = self.conn.cursor()
        self.table = "identity_md5_table"
        if self.init_flag or not self.table_exists():
            self.create()

    def table_exists(self):
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.table,))
        return self.cursor.fetchone() is not None

    def create(self):
        sql = f'''CREATE TABLE IF NOT EXISTS `{self.table}` (
            `id` INTEGER PRIMARY KEY AUTOINCREMENT,
            `identity_md5` TEXT NOT NULL UNIQUE
        );'''
        self.cursor.execute(sql)
        self.conn.commit()

    def add(self, identity_md5):
        sql = f'''INSERT OR IGNORE INTO {self.table} (identity_md5) VALUES (?);'''
        self.cursor.execute(sql, (identity_md5,))
        self.conn.commit()
        return identity_md5

    def batch_check_dupe(self, identity_md5s):
        placeholders = ','.join('?' * len(identity_md5s))
        sql = f'''SELECT identity_md5 FROM {self.table} WHERE identity_md5 IN ({placeholders});'''
        self.cursor.execute(sql, identity_md5s)
        result = set(row[0] for row in self.cursor.fetchall())
        return result

    def check_dupe(self, identity_md5):
        sql = f'''SELECT EXISTS (SELECT 1 FROM {self.table} WHERE identity_md5 = ?);'''
        self.cursor.execute(sql, (identity_md5,))
        result = self.cursor.fetchone()[0]
        return bool(result)

    def close(self):
        self.cursor.close()
        self.conn.close()
        del self.conn


class SqlrV:
    init_flag = False

    def __init__(self, ero=0):
        self.db = conf_dir.joinpath("rV.db")
        if not self.db.exists():
            self.init_flag = True
        self.written_meta = set()
        self.conn = sqlite3.connect(self.db)
        self.cursor = self.conn.cursor()
        self.meta_tb = "metainfos"
        self.eps_tb = "episodes"
        self.ero = ero
        if self.init_flag or not self.table_exists():
            self.create()

    def table_exists(self):
        """检查两个表是否都存在"""
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
            (self.meta_tb, self.eps_tb)
        )
        return len(self.cursor.fetchall()) == 2

    def create(self):
        """创建 metainfos 和 episodes 表"""
        # metainfos 表：存储漫画元数据信息
        meta_tb_sql = f'''CREATE TABLE IF NOT EXISTS `{self.meta_tb}` (
            `md5` TEXT PRIMARY KEY,
            `book` TEXT NOT NULL,
            `artist` TEXT,
            `source` TEXT,
            `preview_url` TEXT,
            `public_date` TEXT,
            `tags` TEXT,
            `pages` INTEGER,
            `ero` INTEGER NOT NULL DEFAULT 0
        );'''
        
        # episodes 表：存储章节/本子信息，(book, ep) 组合为唯一键
        eps_tb_sql = f'''CREATE TABLE IF NOT EXISTS `{self.eps_tb}` (
            `id` INTEGER PRIMARY KEY AUTOINCREMENT,
            `book` TEXT NOT NULL,
            `ep` TEXT NOT NULL DEFAULT 'meaningless',
            `exist` INTEGER NOT NULL DEFAULT 1,
            `rv_handle` TEXT,
            `ero` INTEGER NOT NULL DEFAULT 0,
            UNIQUE(`book`, `ep`)
        );'''
        
        self.cursor.execute(meta_tb_sql)
        self.cursor.execute(eps_tb_sql)
        self.conn.commit()

    def write_meta(self, book_name: str, artist: str = None, source: str = None,
                   preview_url: str = None, public_date: str = None,
                   tags: list = None, pages: int = None):
        book_md5 = md5(book_name)
        if book_md5 in self.written_meta:
            return
        tags_str = ','.join(tags) if tags else None
        
        sql = f'''INSERT OR REPLACE INTO {self.meta_tb}
                  (md5, book, artist, source, preview_url, public_date, tags, pages, ero)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);'''
        self.cursor.execute(sql, (book_md5, book_name, artist, source, preview_url,
                                   public_date, tags_str, pages, self.ero))
        self.conn.commit()
        self.written_meta.add(book_md5)

    def write_episode(self, book: str, ep: str = None, exist: int = 1):
        sql = f'''INSERT OR REPLACE INTO {self.eps_tb}
                  (book, ep, exist, rv_handle, ero)
                  VALUES (?, ?, ?, ?, ?);'''
        self.cursor.execute(sql, (book, ep, exist, None, self.ero))
        self.conn.commit()

    def batch_write_episodes(self, episodes: list):
        """批量写入章节信息
        episodes: [(book, ep, exist, rv_handle, ero), ...]
        """
        sql = f'''INSERT OR REPLACE INTO {self.eps_tb}
                  (book, ep, exist, rv_handle, ero)
                  VALUES (?, ?, ?, ?, ?);'''
        self.cursor.executemany(sql, episodes)
        self.conn.commit()

    def handle(self):
        """used by rv
        sql = '''UPDATE `episodes` SET rv_handle = ? WHERE book = ? AND ep = ?;'''
        """
        ...

    def get_meta(self, books: list) -> dict:
        """used by rv
        placeholders = ','.join('?' * len(books))
        sql = f'''SELECT book, md5, artist, source, preview_url, public_date, tags, pages, ero
                  FROM `metainfos` WHERE book IN ({placeholders});'''
        self.cursor.execute(sql, books)
        """
        ...

    def get_episodes(self, book: str = None) -> list:
        """获取章节信息
        返回: [(book, ep, exist, rv_handle, ero), ...]
        """
        conditions = []
        params = []
        
        if book is not None:
            conditions.append("book = ?")
            params.append(book)
        if self.ero is not None:
            conditions.append("ero = ?")
            params.append(self.ero)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f'''SELECT book, ep, exist, rv_handle, ero
                  FROM {self.eps_tb} {where_clause}
                  ORDER BY book, ep;'''
        
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()

    def delete_episodes(self, book: str):
        sql = f'''DELETE FROM {self.eps_tb} WHERE book = ?;'''
        self.cursor.execute(sql, (book,))
        self.conn.commit()

    def close(self):
        self.cursor.close()
        self.conn.close()
        del self.conn
