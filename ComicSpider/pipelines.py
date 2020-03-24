# -*- coding: utf-8 -*-
from pymongo import MongoClient
from redis import StrictRedis


class ComicMasterPipeline(object):
    def open_spider(self, spider):
        self.db = StrictRedis()

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        for url in item['urls']:
            self.db.lpush('comic90mh:start_urls', url)
        return item


class ComicSalvePipeline(object):
    total = 0

    def __init__(self, mongo_url, mongo_db, connection):
        self.mongo_url = mongo_url
        self.DB = mongo_db
        self.collection_name = connection

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

    def close_spider(self, spider):
        self.client.close()

    def process_item(self, item, spider):
        # self.total = print_dynamic(self.total)
        self.db[self.collection_name].insert(dict(item))
        return item
