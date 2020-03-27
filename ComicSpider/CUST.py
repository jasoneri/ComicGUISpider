
settings = {
        'DUPEFILTER_CLASS': "scrapy_redis.dupefilter.RFPDupeFilter",
        'SCHEDULER': "scrapy_redis.scheduler.Scheduler",  # 使用scrapy-redis组件自己的调度器(核心代码共享调度器)
        'MYEXT_ENABLED': True,  # 开启扩展
        'IDLE_NUMBER': 36,  # 配置空闲持续时间单位 ，一个时间单位为5s
        # 在 EXTENSIONS 配置，激活扩展
        'EXTENSIONS': {
                'ComicSpider.extensions.RedisSpiderSmartIdleClosedExensions': 500,
        },
        'ITEM_PIPELINES': {
                'ComicSpider.pipelines.ComicSlavePipeline': 300,
                # 'scrapy_redis.pipelines.RedisPipeline': 301,
        },
        'DOWNLOAD_DELAY': 0.2,
        'DOWNLOAD_TIMEOUT': 20,
        'RETRY_TIMES': 2,

        'REDIS_HOST': '192.168.199.223',
        'REDIS_PORT': 6379,
        # 'REDIS_ENCODING': 'utf-8',

        'MONGO_URI': '192.168.199.223:27017',
        'MONGO_DB': 'ComicTestDB',
        'MONGO_COLL': 'comicTest分布式',
}
