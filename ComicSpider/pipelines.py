# -*- coding: utf-8 -*-
import os
import re
import pathlib
from io import BytesIO

import pillow_avif
from itemadapter import ItemAdapter
from scrapy.http import Request
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.images import ImagesPipeline, ImageException

from utils import conf
from utils.website import JmUtils, MangabzUtils, set_author_ahead
from utils.processed_class import TaskObj
from assets import res


class PageNamingMgr:
    img_sv_type = getattr(conf, 'img_sv_type', 'jpg')
    img_suffix_regex = re.compile(r'\.(jpg|png|gif|jpeg|bmp|webp|tiff|tif|ico|avif|svg)$')

    def __init__(self):
        self.digits_map = {}

    def __call__(self, taskid, page, info):
        if isinstance(page, str) and bool(self.img_suffix_regex.search(page)):
            return page
        elif not self.digits_map.get(taskid):
            self.digits_map[taskid] = len(str(info.spider.tasks[taskid].tasks_count))
        digits = self.digits_map[taskid]
        return f"{str(page).zfill(digits)}.{self.img_sv_type}"


class ComicPipeline(ImagesPipeline):
    err_flag = 0
    _sub = re.compile(r'([|:<>?*"\\/])')
    _sub_index = re.compile(r"^\(.*?\)")
    
    @classmethod
    def from_crawler(cls, crawler):
        pipe = super(ComicPipeline, cls).from_crawler(crawler)
        pipe.page_naming = PageNamingMgr()
        return pipe

    # 图片存储前调用
    def file_path(self, request, response=None, info=None, *, item=None):
        title = self._sub.sub('-', item.get('title'))
        section = self._sub.sub('-', item.get('section'))
        taskid = item.get('uuid_md5')
        page = self.page_naming(taskid, item.get('page'), info)
        spider = self.spiderinfo.spider
        basepath: pathlib.Path = spider.settings.get('SV_PATH')
        path = self.file_folder(basepath, section, spider, title, item)
        os.makedirs(path, exist_ok=True)
        fin = os.path.join(path, page)
        return fin

    def file_folder(self, basepath, section, spider, title, item):
        if item['uuid_md5'] in spider.tasks_path:
            return spider.tasks_path[item['uuid_md5']]
        if spider.name in spider.settings.get('SPECIAL'):
            parent_p = basepath.joinpath(f"{res.SPIDER.ERO_BOOK_FOLDER}/web")
            _title = self._sub_index.sub('', set_author_ahead(title))
            if section != 'meaningless':
                base_title_path = parent_p.joinpath(_title)
                path = base_title_path.joinpath(f"{section}[{item['uuid']}]" if conf.addUuid else section)
            else:
                path = parent_p.joinpath(f"{_title}[{item['uuid']}]" if conf.addUuid else _title)
        else:
            path = basepath.joinpath(f"{title}/{section}")
        spider.tasks_path[item['uuid_md5']] = path
        return path

    def image_downloaded(self, response, request, info, *, item=None):
        spider = info.spider
        try:
            super(ComicPipeline, self).image_downloaded(response, request, info, item=item)
            stats = spider.crawler.stats
            percent = int((stats.get_value('file_status_count/downloaded', default=0) / spider.total) * 100)
            spider.Q('BarQueue').send(int(percent))  # 后台打印百分比进度扔回GUI界面
            task_obj = TaskObj(item.get('uuid_md5'), item.get('page'), item['image_urls'][0])
            self.handle_task(spider, stats, task_obj)
        except Exception as e:
            spider.logger.error(f'traceback: {str(type(e))}:: {str(e)}')

    @staticmethod
    def handle_task(spider, stats, task_obj):
        _tasks = spider.tasks[task_obj.taskid]
        _tasks.downloaded.append(task_obj)
        curr_progress = int(len(_tasks.downloaded) / _tasks.tasks_count * 100)
        if conf.isDeduplicate and curr_progress >= 100:
            spider.sql_handler.add(task_obj.taskid)
        spider.Q('TasksQueue').send(task_obj, wait=True)
        stats.inc_value('image/downloaded')

    def item_completed(self, results, item, info):
        _item = super(ComicPipeline, self).item_completed(results, item, info)
        return _item


class JmComicPipeline(ComicPipeline):
    def get_images(self, response, request, info, *, item=None):
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = JmUtils.JmImage.by_url(item['image_urls'][0]).convert_img(response.body)

        width, height = orig_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < {self.min_width}x{self.min_height})"
            )

        image, buf = self.convert_image(
            orig_image, response_body=BytesIO(response.body)
        )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            thumb_image, thumb_buf = self.convert_image(image, size, buf)
            yield thumb_path, thumb_image, thumb_buf


class MangabzComicPipeline(ComicPipeline):

    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        return [Request(u, callback=NO_CALLBACK, headers=MangabzUtils.image_ua) for u in urls]
