# -*- coding: utf-8 -*-
import os
import re
import pathlib
import warnings
from io import BytesIO

from scrapy.pipelines.images import ImagesPipeline, ImageException
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.python import get_func_args

from utils.special import JmUtils, set_author_ahead
from assets import res


class ComicPipeline(ImagesPipeline):
    now = 0
    threshold = 95
    err_flag = 0
    _sub = re.compile(r'([|:<>?*"\\/])')
    _sub_index = re.compile(r"^\(.*?\)")

    def get_media_requests(self, item, info):
        request_objs = super(ComicPipeline, self).get_media_requests(item, info)
        for request_obj in request_objs:
            request_obj.item = item
            request_obj.meta['referer'] = item.get('referer')
        return request_objs

    # 图片存储前调用
    def file_path(self, request, response=None, info=None, *, item=None):
        title = self._sub.sub('-', item.get('title'))
        section = self._sub.sub('-', item.get('section'))
        page = res.SPIDER.PAGE_NAMING % item.get('page')
        spider = self.spiderinfo.spider
        basepath: pathlib.Path = spider.settings.get('SV_PATH')
        path = self.file_folder(basepath, section, spider, title, request.meta)
        os.makedirs(path, exist_ok=True)
        fin = os.path.join(path, page)
        return fin

    def file_folder(self, basepath, section, spider, title, meta: dict):
        path = basepath.joinpath(f"{res.SPIDER.ERO_BOOK_FOLDER}/web/{self._sub_index.sub('', set_author_ahead(title))}") \
            if spider.name in spider.settings.get('SPECIAL') \
            else basepath.joinpath(f"{title}/{section}")
        return path

    def image_downloaded(self, response, request, info, *, item=None):
        self.now += 1
        spider = self.spiderinfo.spider
        try:
            percent = int((self.now / spider.total) * 100)
            if percent > self.threshold:
                percent -= int((percent / self.threshold) * 100)  # 进度缓存
            spider.Q('BarQueue').send(int(percent))  # 后台打印百分比进度扔回GUI界面
        except Exception as e:
            spider.logger.error(f'traceback: {str(type(e))}:: {str(e)}')
        # # 控制台专用
        super(ComicPipeline, self).image_downloaded(response, request, info, item=item)


class JmComicPipeline(ComicPipeline):
    def file_folder(self, basepath, section, spider, title, meta: dict):
        path = super(JmComicPipeline, self).file_folder(basepath, section, spider, title, meta)
        # jm上传者太多命名规范太杂有重名情况出现(例如'満开开花-催眠で')，重名时加上车号确保不重
        _epsId = re.search(r"(\d+)$", meta.get("referer", ""))
        if bool(_epsId):
            path = f"{path}[{_epsId.group(1)}]"
        return path

    def get_images(self, response, request, info, *, item=None):
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = JmUtils.JmImage.by_url(item['image_urls'][0]).convert_img(response.body)

        width, height = orig_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException(
                "Image too small "
                f"({width}x{height} < "
                f"{self.min_width}x{self.min_height})"
            )

        if self._deprecated_convert_image is None:
            self._deprecated_convert_image = "response_body" not in get_func_args(
                self.convert_image
            )
            if self._deprecated_convert_image:
                warnings.warn(
                    f"{self.__class__.__name__}.convert_image() method overridden in a deprecated way, "
                    "overridden method does not accept response_body argument.",
                    category=ScrapyDeprecationWarning,
                )

        if self._deprecated_convert_image:
            image, buf = self.convert_image(orig_image)
        else:
            image, buf = self.convert_image(
                orig_image, response_body=BytesIO(response.body)
            )
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(
                request, thumb_id, response=response, info=info, item=item
            )
            if self._deprecated_convert_image:
                thumb_image, thumb_buf = self.convert_image(image, size)
            else:
                thumb_image, thumb_buf = self.convert_image(image, size, buf)
            yield thumb_path, thumb_image, thumb_buf
