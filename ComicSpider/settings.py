# -*- coding: utf-8 -*-
import os
from loguru import logger

BOT_NAME = 'ComicSpider'

SPIDER_MODULES = ['ComicSpider.spiders']
NEWSPIDER_MODULE = 'ComicSpider.spiders'

ROBOTSTXT_OBEY = False

DEFAULT_REQUEST_HEADERS = {
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en',
}

DOWNLOADER_MIDDLEWARES = {
   'ComicSpider.middlewares.ComicspiderUAMiddleware': 604,
   'ComicSpider.middlewares.ComicspiderProxyMiddleware': 605,
   'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
}

ITEM_PIPELINES = {
   'ComicSpider.pipelines.ComicMasterPipeline': 300,
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

# SCHEDULER_PERSIST = True    # 是否允许暂停
MYEXT_ENABLED = True

USER_AGENT = [r"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:70.0) Gecko/20100101 Firefox/70.0",
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

logger.add('log/run.log', level='DEBUG', rotation='1 week', retention='5 days')
logger.add('log/error.log', level='ERROR', rotation='1 week')
