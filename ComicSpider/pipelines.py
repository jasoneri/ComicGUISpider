# -*- coding: utf-8 -*-
import os
from scrapy.pipelines.images import ImagesPipeline
from ComicSpider import settings


class ComicPipeline(ImagesPipeline):
    page = 0

    # media_requests
    def get_media_requests(self, item, info):
        request_objs = super(ComicPipeline, self).get_media_requests(item, info)
        for request_obj in request_objs:
            self.page += 1      # 后台看进度打印
            sign = {1: '→', 2: '↘', 3: '↓', 4: '↙', 5: '←', 6: '↖', 7: '↑', 0: '↗', 999: '\n'}
            p = sign[self.page % (len(sign.keys()) - 1)] if self.page % 50 else sign[999]
            print(p, end='', flush=True)
            request_obj.item = item
        return request_objs

    # 图片存储前调用
    def file_path(self, request, response=None, info=None):
        title = request.item.get('title').replace('\\', ' ').replace('/', ' ')
        section = '章节：%s' % request.item.get('section').replace('\\', ' ').replace('/', ' ')
        page = '第%s页.jpg' % request.item.get('page')
        images_store = settings.IMAGES_STORE
        path = r"{}\{}\{}".format(images_store, title, section)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, page)
