# -*- coding: utf-8 -*-
import os
import re
import pathlib
from io import BytesIO
from time import sleep

from curl_cffi import requests as curl_requests
import pillow_avif
from itemadapter import ItemAdapter
from scrapy import signals
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.images import ImagesPipeline, ImageException
from twisted.internet.defer import maybeDeferred
from twisted.internet.threads import deferToThread

from utils import conf, TaskObj
from utils.core import sanitize_for_path
from utils.website import JmUtils, MangabzUtils, set_author_ahead
from utils.config.rule import CgsRuleMgr
from assets import res
from utils.protocol import BarProgressEvent, TasksObjEvent


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
    _sub_index = re.compile(r"^\(.*?\)")
    
    @classmethod
    def from_crawler(cls, crawler):
        pipe = super(ComicPipeline, cls).from_crawler(crawler)
        pipe.page_naming = PageNamingMgr()
        return pipe

    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        return [
            Request(url,callback=NO_CALLBACK,headers=dict(getattr(info.spider, "image_ua", {}) or {}),)
            for url in urls
        ]

    # 图片存储前调用
    def file_path(self, request, response=None, info=None, *, item=None):
        title = sanitize_for_path(item.get('title'))
        section = sanitize_for_path(item.get('section') or '')
        taskid = item.get('uuid_md5')
        page = self.page_naming(taskid, item.get('page'), info)
        spider = self.spiderinfo.spider
        basepath: pathlib.Path = spider.settings.get('SV_PATH')
        path = self.file_folder(basepath, section, spider, title, item)
        fin = os.path.join(path, page)
        return fin

    def file_folder(self, basepath, section, spider, title, item):
        uuid_md5 = item['uuid_md5']
        if uuid_md5 in spider.tasks_path:
            return spider.tasks_path[uuid_md5]
        if spider.name in spider.settings.get('SPECIAL'):
            parent_p = basepath.joinpath(f"{res.SPIDER.ERO_BOOK_FOLDER}")
            _title = self._sub_index.sub('', set_author_ahead(title))
            if section:
                base_title_path = parent_p.joinpath(_title)
                path = base_title_path.joinpath(f"{section}[{item['uuid']}]" if conf.addUuid else section)
            else:
                path = parent_p.joinpath(f"{_title}[{item['uuid']}]" if conf.addUuid else _title)
        else:
            path = basepath.joinpath(f"{title}/{section}")
        
        os.makedirs(path, exist_ok=True)
        # init .cgsRule
        CgsRuleMgr.create(basepath, conf.downloaded_handle)
        # sv metaInfo
        tasks_obj = spider.tasks.get(uuid_md5)
        if tasks_obj and getattr(tasks_obj, 'meta_info', None):
            tasks_obj.meta_info.sv_meta_in(path)
        tasks_obj.local_path = str(path)
        spider.emit(TasksObjEvent(job_id=getattr(spider, '_job_id', None), task_obj=tasks_obj, is_new=True))
        # cache file_folder
        spider.tasks_path[uuid_md5] = path
        return path

    def image_downloaded(self, response, request, info, *, item=None):
        spider = info.spider
        try:
            super(ComicPipeline, self).image_downloaded(response, request, info, item=item)
            stats = spider.crawler.stats
            self._sync_item_progress(spider, stats, item, count_download_stat=True)
        except Exception as e:
            spider.logger.error(f'traceback: {str(type(e))}:: {str(e)}')

    @staticmethod
    def _processed_file_count(stats):
        return (
            stats.get_value('file_status_count/downloaded', default=0) +
            stats.get_value('file_status_count/uptodate', default=0)
        )

    def _sync_item_progress(self, spider, stats, item, *, count_download_stat):
        total = getattr(spider, 'total', 0) or 0
        processed = self._processed_file_count(stats)
        percent = int((processed / total) * 100) if total else 0
        spider.emit(BarProgressEvent(job_id=getattr(spider, '_job_id', None), percent=percent))
        task_obj = TaskObj(item.get('uuid_md5'), item.get('page'), item['image_urls'][0])
        self._record_task_progress(spider, stats, task_obj, count_download_stat=count_download_stat)

    @staticmethod
    def _record_task_progress(spider, stats, task_obj, *, count_download_stat=True):
        _tasks = spider.tasks[task_obj.taskid]
        _tasks.downloaded.append(task_obj)
        curr_progress = int(len(_tasks.downloaded) / _tasks.tasks_count * 100)
        if curr_progress >= 100:
            tasks_obj = spider.tasks[task_obj.taskid]
            if getattr(tasks_obj, 'meta_info', None):
                tasks_obj.meta_info.fin_callback(spider.tasks_path[tasks_obj.taskid])
            if conf.isDeduplicate:
                spider.record_sql.add(task_obj.taskid)
            spider.rv_sql.write_episode(tasks_obj.title, tasks_obj.episode_name)
            
        spider.emit(TasksObjEvent(
            job_id=getattr(spider, '_job_id', None),
            task_obj=task_obj,
            is_new=False,
        ))
        if count_download_stat:
            stats.inc_value('image/downloaded')

    def media_to_download(self, request: Request, info, *, item=None):
        dfd = maybeDeferred(super().media_to_download, request, info, item=item)

        def _track_uptodate(file_info):
            if (
                item is not None and
                isinstance(file_info, dict) and
                file_info.get('status') == 'uptodate'
            ):
                self._sync_item_progress(info.spider, info.spider.crawler.stats, item, count_download_stat=False)
            return file_info

        dfd.addCallback(_track_uptodate)
        return dfd

    def item_completed(self, results, item, info):
        _item = super(ComicPipeline, self).item_completed(results, item, info)
        return _item


class WnacgComicPipeline(ComicPipeline):
    curl_image_impersonate = "chrome124"
    curl_image_timeout = 20
    curl_image_proxy_policy = "direct"
    curl_image_retries = 3
    curl_image_retry_delay = 3.0

    @classmethod
    def from_crawler(cls, crawler):
        pipe = super().from_crawler(crawler)
        pipe._curl_session = None
        pipe._curl_session_config = None
        crawler.signals.connect(pipe._close_curl_session, signal=signals.spider_closed)
        return pipe

    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        return [Request(url, callback=NO_CALLBACK) for url in urls]

    def _close_curl_session(self, spider=None, reason=None):
        if getattr(self, "_curl_session", None) is None:
            return
        self._curl_session.close()
        self._curl_session = None
        self._curl_session_config = None

    def _get_curl_session(self, spider):
        session_kwargs = {
            "impersonate": getattr(spider, "image_impersonate", self.curl_image_impersonate),
            "timeout": getattr(spider, "image_download_timeout", self.curl_image_timeout),
        }
        proxy_policy = getattr(spider, "curl_image_proxy_policy", self.curl_image_proxy_policy)
        if proxy_policy == "proxy":
            if not conf.proxies:
                raise RuntimeError("WnacgComicPipeline requires conf.proxies when proxy mode is enabled")
            session_kwargs["proxy"] = f"http://{conf.proxies[0]}"
        if getattr(self, "_curl_session_config", None) != session_kwargs:
            self._close_curl_session()
            self._curl_session = curl_requests.Session(**session_kwargs)
            self._curl_session_config = session_kwargs
        return self._curl_session

    @staticmethod
    def _curl_request_context(request, spider):
        headers = request.headers.to_unicode_dict()
        referer = headers.pop("Referer", None) or headers.pop("referer", None)
        if not referer:
            referer = request.meta.get("referer")
        if not referer:
            referer_resolver = getattr(spider, "request_referer", None)
            if callable(referer_resolver):
                referer = referer_resolver()
        return referer, headers or None

    def media_to_download(self, request: Request, info, *, item=None):
        dfd = maybeDeferred(super().media_to_download, request, info, item=item)
        spider = info.spider
        attempts = max(1, int(getattr(spider, "curl_image_retries", self.curl_image_retries)))
        retry_delay = float(getattr(spider, "curl_image_retry_delay", self.curl_image_retry_delay))
        referer, headers = self._curl_request_context(request, spider)

        def _fallback(file_info):
            if file_info is not None:
                return file_info

            def _download_via_curl():
                session = self._get_curl_session(spider)
                for attempt in range(1, attempts + 1):
                    try:
                        response = session.get(request.url, referer=referer, headers=headers)
                        response.raise_for_status()
                        return response.status_code, response.content
                    except Exception as exc:
                        if attempt >= attempts:
                            raise
                        spider.logger.warning(
                            "Wnacg image curl retry %s/%s | url=%s | referer=%s | error=%s: %s",
                            attempt,
                            attempts - 1,
                            request.url,
                            referer or "-",
                            type(exc).__name__,
                            exc,
                        )
                        sleep(retry_delay)

            def _handle_curl_result(result):
                status_code, content = result
                return self.media_downloaded(
                    Response(
                        url=request.url,
                        status=status_code,
                        body=content,
                        request=request,
                    ),
                    request,
                    info,
                    item=item,
                )

            thread_dfd = deferToThread(_download_via_curl)
            thread_dfd.addCallback(_handle_curl_result)
            return thread_dfd

        dfd.addCallback(_fallback)
        return dfd


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
