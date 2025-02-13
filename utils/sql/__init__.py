#!/usr/bin/python
# -*- coding: utf-8 -*-
import sqlite3

from utils import ori_path
from variables import SPECIAL_WEBSITES


class SqlUtils:
    db = ori_path.joinpath("record.db")
    init_flag = False

    def __init__(self, tb):
        if not self.db.exists():
            self.init_flag = True
        self.conn = sqlite3.connect(self.db)
        self.cursor = self.conn.cursor()
        self.table = f"{tb}_title_md5"
        if self.init_flag:
            self.create()

    def create(self):
        for _ in SPECIAL_WEBSITES:
            sql = f'''CREATE TABLE {_}_title_md5 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_md5 TEXT NOT NULL UNIQUE
            );'''
            self.cursor.execute(sql)
            self.conn.commit()

    def add(self, title_md5):
        sql = f'''INSERT OR IGNORE INTO {self.table} (title_md5) VALUES (?);'''
        self.cursor.execute(sql, (title_md5,))
        self.conn.commit()
        return title_md5

    def batch_check_dupe(self, title_md5s):
        placeholders = ','.join('?' * len(title_md5s))
        sql = f'''SELECT title_md5 FROM {self.table} WHERE title_md5 IN ({placeholders});'''
        self.cursor.execute(sql, title_md5s)
        result = set(row[0] for row in self.cursor.fetchall())
        return result

    def check_dupe(self, title_md5):
        sql = f'''SELECT EXISTS (SELECT 1 FROM {self.table} WHERE title_md5 = ?);'''
        self.cursor.execute(sql, (title_md5,))
        result = self.cursor.fetchone()[0]
        return bool(result)

    def close(self):
        self.cursor.close()
        self.conn.close()
        del self.conn
