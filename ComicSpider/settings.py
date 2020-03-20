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
import re

BOT_NAME = 'ComicSpider'

SPIDER_MODULES = ['ComicSpider.spiders']
NEWSPIDER_MODULE = 'ComicSpider.spiders'


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'ComicSpider (+http://www.yourdomain.com)'

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
DOWNLOAD_DELAY = 0.15
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en',
}

DOWNLOADER_MIDDLEWARES = {
   'ComicSpider.middlewares.ComicspiderDownloaderMiddleware': 5,
}

ITEM_PIPELINES = {
   'ComicSpider.pipelines.ComicPipeline': 50
}

# 图片储存原始路径
def images_store_and_proxy():
    proxies = []
    if os.path.exists(r'./setting.txt'):
        with open(r'./setting.txt', 'r', encoding='utf-8') as fp:
            text = fp.read()
            try:
                proxies = re.findall(r'(\d+\.\d+\.\d+\.\d+:\d+?)', text)
                path = re.search(r'path=[\"\']([\s\S]*)[\"\']$', text).group(1)
            except AttributeError:
                # logging.info("haven't create dir")
                path = r'D:\comic'
                pass
    return path, proxies


IMAGES_STORE, PROXY_CUST = images_store_and_proxy()

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
# LOG_FILE = log_file_path

