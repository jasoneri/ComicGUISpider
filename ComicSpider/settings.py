# -*- coding: utf-8 -*-

# Scrapy settings for ComicSpider project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html
import os

import redis
from loguru import logger

BOT_NAME = 'ComicSpider'

SPIDER_MODULES = ['ComicSpider.spiders']
NEWSPIDER_MODULE = 'ComicSpider.spiders'


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'ComicSpider (+http://www.yourdomain.com)'

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

DEFAULT_REQUEST_HEADERS = {
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en',
}

DOWNLOADER_MIDDLEWARES = {
   # 'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
   'ComicSpider.middlewares.ComicspiderDownloaderMiddleware': 605,
}

ITEM_PIPELINES = {
   'ComicSpider.pipelines.H90comicPipeline': 300,
   # 'scrapy_redis.pipelines.RedisPipeline': 301,
}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = 'httpcache'
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'

DOWNLOAD_DELAY = 0.2
DOWNLOAD_TIMEOUT = 13
RETRY_TIMES = 3

# REDIS_HOST = '127.0.0.1'
# REDIS_PORT = 6379
# REDIS_ENCODING = 'utf-8'
REDIS_URL = 'redis://json@127.0.0.1:6379'
redis_conn = redis.StrictRedis(host='127.0.0.1', port=6379)
redis_conn.lpush('comic90mh:start_urls', 'http://m.90mh.com/search/?keywords=异世界')

DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"
SCHEDULER = "scrapy_redis.scheduler.Scheduler"  # 使用scrapy-redis组件自己的调度器(核心代码共享调度器)
# SCHEDULER_PERSIST = True    # 是否允许暂停
SCHEDULER_FLUSH_ON_START = True     # 开始前清洗redis的key

MYEXT_ENABLED=True      # 开启扩展
IDLE_NUMBER=24           # 配置空闲持续时间单位为 360个 ，一个时间单位为5s
# 在 EXTENSIONS 配置，激活扩展
EXTENSIONS = {
            'ComicSpider.extensions.RedisSpiderSmartIdleClosedExensions': 499,
        }

MONGO_URI = '127.0.0.1:27017'
MONGO_DB = 'ComicTestDB'
MONGO_COLL = 'comic_异世界三本'


UA = [r"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:70.0) Gecko/20100101 Firefox/70.0",
      r'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:64.0) Gecko/20100101 Firefox/64.0',
      r'Mozilla/5.0 (Windows NT 6.2; WOW64; rv:63.0) Gecko/20100101 Firefox/63.0',
      r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ',
      r'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML like Gecko) Chrome/44.0.2403.155 Safari/537.36',
      r'Opera/9.80 (Windows NT 6.0) Presto/2.12.388 Version/12.14',
      r'Mozilla/5.0 (Windows NT 6.0; rv:2.0) Gecko/20100101 Firefox/4.0 Opera 12.14'
                   ]

os.makedirs('log', exist_ok=True)
log_file_path = "log/scrapy.log"

# 日志输出
LOG_LEVEL = 'INFO'
# LOG_LEVEL = 'DEBUG'
LOG_FILE = log_file_path

logger.add('log/runtime.log', level='DEBUG', rotation='1 week', retention='5 days')
logger.add('log/error.log', level='ERROR', rotation='1 week')
