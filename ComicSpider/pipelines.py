# -*- coding: utf-8 -*-
import os
from scrapy.pipelines.images import ImagesPipeline
from ComicSpider import settings


class H90comicPipeline(ImagesPipeline):
    # 下载请求前附加item配料
    def get_media_requests(self, item, info):
        request_objs = super(H90comicPipeline, self).get_media_requests(item, info)
        for request_obj in request_objs:
            request_obj.item = item
        return request_objs

    # 图片存储前调用
    def file_path(self, request, response=None, info=None):
        title = request.item.get('title')
        section = '章节：%s' % request.item.get('section')
        page = '第%s页.jpg' % request.item.get('page')
        images_store = settings.IMAGES_STORE

        def _path(origin_path, target=''):
            path = os.path.join(origin_path, target)
            os.mkdir(path) if not os.path.exists(path) else None
            return path

        return os.path.join(_path(_path(_path(images_store), title), section), page)
