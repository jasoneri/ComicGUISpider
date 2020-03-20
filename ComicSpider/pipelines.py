# -*- coding: utf-8 -*-
from utils import print_dynamic
from pymongo import MongoClient


class H90comicPipeline(object):
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

    def close_spider(self):
        self.client.close()

    def process_item(self, item, spider):
        self.total = print_dynamic(self.total)
        self.db[self.collection_name].insert(dict(item))
        return item


# class DuplicatesPipeline(object):
#     def __init__(self):
#         self.ids_seen = set()
#
#     def process_item(self, item, spider):
#         if item['id'] in self.ids_seen:
#             raise DropItem("Duplicate item found: %s" % item)
#         else:
#             self.ids_seen.add(item['id'])
#             return item