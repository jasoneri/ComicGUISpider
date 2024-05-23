# -*- coding: utf-8 -*-
import os
import re
from re import sub

from scrapy.pipelines.images import ImagesPipeline


class ComicPipeline(ImagesPipeline):
    now = 0
    threshold = 95
    err_flag = 0
    _sub = re.compile(r'([|.:<>?*"\\/])')
    _sub_index = re.compile(r"^\(.*?\)")

    # media_requests
    def get_media_requests(self, item, info):
        request_objs = super(ComicPipeline, self).get_media_requests(item, info)
        for request_obj in request_objs:
            request_obj.item = item
        return request_objs

    # 图片存储前调用
    def file_path(self, request, response=None, info=None):
        title = self._sub.sub('-', request.item.get('title'))
        # section = sub(r'([|.:<>?*"\\/])', '-', request.item.get('section'))
        section = self._sub.sub('-', request.item.get('section'))
        page = '第%s页.jpg' % request.item.get('page')
        spider = self.spiderinfo.spider
        basepath = spider.settings.get('IMAGES_STORE')
        path = f"{basepath}\\本子\\{self._sub_index.sub('', title)}" \
            if spider.name in spider.settings.get('SPECIAL') \
            else f"{basepath}\\{title}\\{section}\\"
        os.makedirs(path, exist_ok=True)  # 还有标题不能创建的话我吐血
        fin = os.path.join(path, page)
        return fin

    def image_downloaded(self, response, request, info):
        self.now += 1
        spider = self.spiderinfo.spider
        try:
            percent = int((self.now / spider.total) * 100)
            if percent > self.threshold:
                percent -= int((percent / self.threshold) * 100)  # 进度缓存
            # spider.bar.put(int(percent))  # 后台打印百分比进度扔回GUI界面
            spider.Q('Bar').send(int(percent))
        except Exception as e:
            spider.logger.error(f'traceback: {str(type(e))}:: {str(e)}')
        # # 控制台专用
        # sign = {1: '→', 2: '↘', 3: '↓', 4: '↙', 5: '←', 6: '↖', 7: '↑', 0: '↗', 999: '\n'}
        # p = sign[self.now % (len(sign.keys()) - 1)] if self.now % 50 else sign[999]
        # print(p, end='', flush=True)

        super(ComicPipeline, self).image_downloaded(response=response, request=request, info=info)
