#!/usr/bin/python
# -*- coding: utf-8 -*-
import sqlite3

from utils import conf, conf_dir, md5
from utils.website.chore import set_author_ahead


class SqlRecorder:
    init_flag = False

    def __init__(self):
        self.db = conf_dir.joinpath("record.db")
        if not self.db.exists():
            self.init_flag = True
        self.conn = sqlite3.connect(self.db)
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA busy_timeout=5000")
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
        self.db = conf.sv_path.joinpath("rV.db")
        if not self.db.exists():
            self.init_flag = True
        self.written_meta = set()
        self.conn = None
        self.cursor = None
        self.meta_tb = "metainfos"
        self.eps_tb = "episodes"
        self.ero = ero

    def __enter__(self):
        self.conn = sqlite3.connect(self.db)
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA journal_mode=WAL")
        self.cursor.execute("PRAGMA busy_timeout=5000")
        if self.init_flag or not self.table_exists():
            self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def connect(self):
        if self.conn is None:
            return self.__enter__()
        return self

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
            `btype` TEXT,
            `ero` INTEGER NOT NULL DEFAULT 0
        );'''
        
        # episodes 表：存储章节/本子信息，(book, ep) 组合为唯一键
        eps_tb_sql = f'''CREATE TABLE IF NOT EXISTS `{self.eps_tb}` (
            `id` INTEGER PRIMARY KEY AUTOINCREMENT,
            `book` TEXT NOT NULL,
            `ep` TEXT NOT NULL DEFAULT '',
            `exist` INTEGER NOT NULL DEFAULT 1,
            `rv_handle` TEXT,
            `ero` INTEGER NOT NULL DEFAULT 0,
            `mtime` REAL,
            `first_img` TEXT,
            UNIQUE(`book`, `ep`)
        );'''
        
        self.cursor.execute(meta_tb_sql)
        self.cursor.execute(eps_tb_sql)
        self.conn.commit()

    def write_meta(self, **sql_kw):
        """严格对应 self.meta_tb 表字段名的参数"""
        book_name = sql_kw.get('book')
        if not book_name:
            raise ValueError("book_name is required")
        book_name = set_author_ahead(book_name)
        book_md5 = md5(book_name)
        if book_md5 in self.written_meta:
            return
        tags_str = ','.join(sql_kw.get('tags') or []) or None
        
        sql = f'''INSERT OR REPLACE INTO {self.meta_tb}
                  (md5, book, artist, source, preview_url, public_date, tags, pages, btype, ero)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);'''
        self.cursor.execute(sql, (
            book_md5, book_name,
            sql_kw.get('artist'), sql_kw.get('source'), sql_kw.get('preview_url'), sql_kw.get('public_date'),
            tags_str, sql_kw.get('pages'), sql_kw.get('btype'), self.ero))
        self.conn.commit()
        self.written_meta.add(book_md5)

    def write_episode(self, book: str, ep: str = None, exist: int = 1):
        sql = f'''INSERT INTO {self.eps_tb} (book, ep, exist, rv_handle, ero)
                  VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(book, ep) DO UPDATE SET
                      exist = excluded.exist,
                      rv_handle = excluded.rv_handle,
                      ero = excluded.ero;'''
        self.cursor.execute(sql, (set_author_ahead(book), ep or '', exist, None, self.ero))
        self.conn.commit()

    def batch_write_episodes(self, episodes: list):
        """episodes: [(book, ep, exist, rv_handle, ero), ...]"""
        normalized_episodes = [
            (book, ep or '', exist, rv_handle, ero)
            for book, ep, exist, rv_handle, ero in episodes
        ]
        sql = f'''INSERT INTO {self.eps_tb} (book, ep, exist, rv_handle, ero)
                  VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(book, ep) DO UPDATE SET
                      exist = excluded.exist,
                      rv_handle = excluded.rv_handle,
                      ero = excluded.ero;'''
        self.cursor.executemany(sql, normalized_episodes)
        self.conn.commit()

    def get_meta(self, books: list) -> dict:
        """used by rv
        placeholders = ','.join('?' * len(books))
        sql = f'''SELECT book, md5, artist, source, preview_url, public_date, tags, pages, ero
                  FROM `metainfos` WHERE book IN ({placeholders});'''
        self.cursor.execute(sql, books)
        """

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

    def reset_exist(self):
        if self.ero is not None:
            sql = f'''UPDATE {self.eps_tb} SET exist = 0 WHERE ero = ?;'''
            self.cursor.execute(sql, (self.ero,))
        else:
            sql = f'''UPDATE {self.eps_tb} SET exist = 0;'''
            self.cursor.execute(sql)
        self.conn.commit()

    def sync_episodes(self, fs_episodes: set):
        """同步文件系统状态到数据库
        
        Args:
            fs_episodes: 文件系统中的章节集合 {(book, ep, ero), ...}
            
        职责：
        1. 新增：本地存在但表中没有的记录
        2. 更新：表中存在且本地存在的记录（exist=1）
        3. 标记删除：表中存在但本地已删的记录（exist=0）
        """
        fs_episodes_normalized = {(book, ep or '', ero) for book, ep, ero in fs_episodes}
        db_episodes = self.get_episodes()
        db_episodes_map = {(book, ep, ero): (exist, rv_handle)
                         for book, ep, exist, rv_handle, ero in db_episodes}
        episodes_to_update = []
        
        for book, ep, ero in fs_episodes_normalized:
            key = (book, ep, ero)
            if key in db_episodes_map:
                # 记录存在，如果 exist 不是 1，则更新为 1
                old_exist, rv_handle = db_episodes_map[key]
                if old_exist != 1:
                    episodes_to_update.append((book, ep, 1, rv_handle, ero))
            else:
                # 记录不存在，插入新记录
                episodes_to_update.append((book, ep, 1, None, ero))
        # 检查数据库中存在但文件系统中不存在的记录，将 exist 设为 0
        for (book, ep, ero), (exist, rv_handle) in db_episodes_map.items():
            if (book, ep, ero) not in fs_episodes_normalized and exist != 0:
                # 文件已被删除，更新 exist=0
                episodes_to_update.append((book, ep, 0, rv_handle, ero))
        # 批量写入/更新
        if episodes_to_update:
            self.batch_write_episodes(episodes_to_update)

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        self.conn = None
        self.cursor = None
