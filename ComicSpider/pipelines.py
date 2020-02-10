# -*- coding: utf-8 -*-
import os
from scrapy.pipelines.images import ImagesPipeline
# from ComicSpider import settings


class ComicPipeline(ImagesPipeline):
    total = 0
    percent = 0.0
    threshold = 70

    def __init__(self, store_uri, IMAGES_STORE):
        super(ComicPipeline, self).__init__(store_uri)
        self.IMAGES_STORE = IMAGES_STORE

    def process_item(self, item, spider):
        if int(self.percent) < 97:
            if self.total<40:
                self.percent = self.total
            elif self.total<self.threshold:
                self.percent += (self.threshold / self.total)
            else:
                self.percent += ((self.threshold / self.total) - 0.2)
            spider.bar.put(int(self.percent))
        return super(ComicPipeline, self).process_item(item, spider)

    # media_requests
    def get_media_requests(self, item, info):
        request_objs = super(ComicPipeline, self).get_media_requests(item, info)
        for request_obj in request_objs:
            self.total += 1     # 后台看进度打印
            sign = {1: '→', 2: '↘', 3: '↓', 4: '↙', 5: '←', 6: '↖', 7: '↑', 0: '↗', 999: '\n'}
            p = sign[self.total % (len(sign.keys()) - 1)] if self.total % 50 else sign[999]
            print(p, end='', flush=True)
            request_obj.item = item
        return request_objs

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        IMAGES_STORE = settings.get('IMAGES_STORE')
        return cls(IMAGES_STORE)

    # 图片存储前调用
    def file_path(self, request, response=None, info=None):
        title = request.item.get('title').replace('\\', ' ').replace('/', ' ')
        section = '%s' % request.item.get('section').replace('\\', ' ').replace('/', ' ')
        page = '第%s页.jpg' % request.item.get('page')
        # images_store = settings.IMAGES_STORE
        images_store = self.IMAGES_STORE
        path = r"{}\{}\{}".format(images_store, title, section)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, page)
