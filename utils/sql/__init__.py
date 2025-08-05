#!/usr/bin/python
# -*- coding: utf-8 -*-
import sqlite3

from utils import conf_dir
from variables import SPECIAL_WEBSITES


class SqlUtils:
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
