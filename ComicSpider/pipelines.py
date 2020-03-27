# -*- coding: utf-8 -*-
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from redis import StrictRedis


class ComicMasterPipeline(object):
    def open_spider(self, spider):
        self.db = StrictRedis()

    def process_item(self, item, spider):
        for url in item['urls']:
            self.db.lpush('comic90mh:start_urls', url)
        return item


class ComicSlavePipeline(object):
    total = 0

    def __init__(self, mongo_url, mongo_db, connection):
        self.mongo_url = mongo_url
        self.DB = mongo_db
        self.coll_name = connection

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_url=crawler.settings.get('MONGO_URI'),
            mongo_db=crawler.settings.get('MONGO_DB'),
            connection=crawler.settings.get('MONGO_COLL')
        )

    def open_spider(self, spider):
        self.client = MongoClient(self.mongo_url)
        self.db = self.client[self.DB]
        self.coll = self.db[self.coll_name]
        # 添加唯一索引
        # self.coll.create_index('no.', unique=True)

    def close_spider(self, spider):
        self.client.close()

    def process_item(self, item, spider):
        try:
            self.coll.insert_one(dict(item))
            return item
        except DuplicateKeyError:
            spider.logger.debug('duplicate key error collection')
            return item
