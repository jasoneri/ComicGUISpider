# -*- coding: utf-8 -*-

# Define here the models for your scraped Extensions
import logging
import time
import redis
from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class RedisSpiderSmartIdleClosedExensions(object):

    def __init__(self, idle_number, crawler):
        self.crawler = crawler
        self.idle_number = idle_number
        self.idle_list = []
        self.idle_count = 0

    @classmethod
    def from_crawler(cls, crawler):
        # first check if the extension should be enabled and raise

        # NotConfigured otherwise

        if not crawler.settings.getbool('MYEXT_ENABLED'):
            raise NotConfigured

        # 配置仅仅支持RedisSpider
        if not 'redis_key' in crawler.spidercls.__dict__.keys():
            raise NotConfigured('Only supports RedisSpider')

        # get the number of items from settings

        idle_number = crawler.settings.getint('IDLE_NUMBER', 360)

        # instantiate the extension object

        ext = cls(idle_number, crawler)

        # connect the extension object to signals

        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)

        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)

        crawler.signals.connect(ext.spider_idle, signal=signals.spider_idle)

        # return the extension object

        return ext

    def spider_opened(self, spider):
        logger.info("opened spider %s redis spider Idle, Continuous idle limit： %d", spider.name, self.idle_number)

    def spider_closed(self, spider):
        logger.info("closed spider %s, idle count %d , Continuous idle count %d",
                    spider.name, self.idle_count, len(self.idle_list))

    def spider_idle(self, spider):
        self.idle_count += 1
        self.idle_list.append(time.time())
        idle_list_len = len(self.idle_list)

        # 判断 redis 中是否存在关键key, 如果key 被用完，则key就会不存在
        if idle_list_len > 2 and spider.server.exists(spider.redis_key):
            self.idle_list = [self.idle_list[-1]]

        elif idle_list_len > self.idle_number:
            logger.info('\n continued idle number exceed {} Times'
                        '\n meet the idle shutdown conditions, will close the reptile operation'
                        '\n idle start time: {},  close spider time: {}'.format(self.idle_number,
                                                                                self.idle_list[0], self.idle_list[0]))
            # 执行关闭爬虫操作
            self.crawler.engine.close_spider(spider, 'closespider_pagecount')


class RedisSpiderClosedExensions(object):
    def __init__(self, crawler, host, port, pwd, db):
        self.crawler = crawler
        self.r = redis.Redis(host=host, port=port, db=db, password=pwd, decode_responses=True)

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler,
                  host=crawler.settings.get("REDIS_HOST"),
                  port=crawler.settings.get("REDIS_PORT"),
                  pwd=crawler.settings.get("REDIS_PARAMS")['password'],
                  db=crawler.settings.get("REDIS_PARAMS")['db']
                  )
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.spider_idle, signal=signals.spider_idle)
        return ext

    def spider_opened(self, spider):
        print('-----spider开启-----')

    def spider_closed(self, spider):
        print('-----spider关闭-----')

    def spider_idle(self, spider):
        # 获取队列的长度
        length = self.r.llen(spider.redis_key)
        if length==0:
            # 如果redis长度为0，则关闭该spider
            self.crawler.engine.close_spider(spider, 'closespider_pagecount')
