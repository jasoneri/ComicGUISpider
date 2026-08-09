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
from utils.chore import set_author_ahead
from utils.website.providers.jm import JmUtils
from utils.website.providers.mangabz import MangabzUtils
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
            task = info.spider.tasks[taskid]
            self.digits_map[taskid] = len(str(getattr(task, "page_name_count", None) or task.tasks_count))
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
        spider = info.spider
        headers = dict(getattr(spider, "image_ua", {}) or {})
        resolver = getattr(spider, "image_request_meta", None)
        requests = []
        for url in urls:
            meta = {}
            if callable(resolver):
                meta = resolver(url=url, item=item)
                if meta is None:
                    meta = {}
                elif not isinstance(meta, dict):
                    raise TypeError(f"{type(spider).__name__}.image_request_meta() must return dict or None")
                else:
                    meta = dict(meta)
            request_headers = dict(headers)
            extra_headers = meta.get("headers") if isinstance(meta, dict) else None
            if extra_headers is not None:
                if not isinstance(extra_headers, dict):
                    raise TypeError(f"{type(spider).__name__}.image_request_meta()['headers'] must return dict when provided")
                request_headers.update(dict(extra_headers))
            requests.append(Request(url,callback=NO_CALLBACK,headers=request_headers,meta=meta))
        return requests

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

    @staticmethod
    def _processed_file_count(stats):
        return stats.get_value('file_status_count/downloaded', default=0) + stats.get_value('file_status_count/uptodate', default=0)

    def _sync_item_progress(self, spider, stats, item):
        total = getattr(spider, 'total', 0) or 0
        processed = self._processed_file_count(stats)
        percent = int((processed / total) * 100) if total else 0
        spider.emit(BarProgressEvent(job_id=getattr(spider, '_job_id', None), percent=percent))
        task_obj = TaskObj(item.get('uuid_md5'), item.get('page'), item['image_urls'][0])
        self._record_task_progress(spider, task_obj)

    @staticmethod
    def _record_task_progress(spider, task_obj):
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
            
        spider.emit(TasksObjEvent(job_id=getattr(spider, '_job_id', None), task_obj=task_obj, is_new=False))

    def item_completed(self, results, item, info):
        completed_item = super(ComicPipeline, self).item_completed(results, item, info)
        if not any(
            ok and isinstance(file_info, dict) and file_info.get('status') in {'downloaded', 'uptodate'}
            for ok, file_info in results
        ):
            return completed_item
        self._sync_item_progress(info.spider, info.spider.crawler.stats, item)
        return completed_item


class CurlComicPipeline(ComicPipeline):
    """Download uncached images with curl_cffi while retaining ImagesPipeline storage."""

    curl_image_impersonate = "chrome146"
    curl_image_impersonate_fallbacks = ("chrome", "chrome131")
    curl_image_timeout = 20
    curl_image_proxy_policy = "follow_conf"
    curl_image_retries = 4
    curl_image_retry_base_delay = 1.0
    curl_image_retry_max_delay = 8.0
    curl_image_retryable_status_codes = frozenset({403, 408, 429, 500, 502, 503, 504})

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

    def _resolve_impersonate_candidates(self, spider):
        preferred = getattr(spider, "image_impersonate", None) or self.curl_image_impersonate
        candidates = [preferred]
        for fallback_profile in self.curl_image_impersonate_fallbacks:
            if fallback_profile not in candidates:
                candidates.append(fallback_profile)
        return candidates

    def _resolve_curl_proxy_url(self, spider):
        proxy_policy = getattr(spider, "curl_image_proxy_policy", self.curl_image_proxy_policy)
        if proxy_policy == "direct":
            return None
        if proxy_policy == "proxy":
            if not conf.proxies:
                raise RuntimeError(f"{type(self).__name__} requires conf.proxies when proxy mode is enabled")
            return f"http://{conf.proxies[0]}"
        if proxy_policy == "follow_conf":
            if conf.proxies:
                return f"http://{conf.proxies[0]}"
            return None
        raise ValueError(
            f"{type(self).__name__} unsupported curl_image_proxy_policy={proxy_policy!r}; "
            f"expected 'follow_conf', 'proxy', or 'direct'"
        )

    def _get_curl_session(self, spider):
        timeout = getattr(spider, "image_download_timeout", self.curl_image_timeout)
        proxy_url = self._resolve_curl_proxy_url(spider)

        session_identity = {"impersonate_candidates": self._resolve_impersonate_candidates(spider), "timeout": timeout, "proxy": proxy_url}
        if getattr(self, "_curl_session_config", None) == session_identity and self._curl_session is not None:
            return self._curl_session

        self._close_curl_session()
        last_error = None
        for impersonate_profile in session_identity["impersonate_candidates"]:
            session_kwargs = {"impersonate": impersonate_profile, "timeout": timeout}
            if proxy_url:
                session_kwargs["proxy"] = proxy_url
            try:
                self._curl_session = curl_requests.Session(**session_kwargs)
                self._curl_session_config = session_identity
                if impersonate_profile != session_identity["impersonate_candidates"][0]:
                    spider.logger.warning(
                        "%s image curl impersonate fallback | preferred=%s | active=%s",
                        self._curl_image_label,
                        session_identity["impersonate_candidates"][0],
                        impersonate_profile,
                    )
                return self._curl_session
            except Exception as session_error:
                last_error = session_error
                spider.logger.warning(
                    "%s image curl session init failed | impersonate=%s | error=%s: %s",
                    self._curl_image_label,
                    impersonate_profile,
                    type(session_error).__name__,
                    session_error,
                )
        raise RuntimeError(
            f"{type(self).__name__} could not create curl session with candidates "
            f"{session_identity['impersonate_candidates']}: {last_error}"
        )

    @property
    def _curl_image_label(self):
        return type(self).__name__.removesuffix("ComicPipeline")

    @staticmethod
    def _curl_request_referer(request, spider):
        # Only pass Referer into curl; leave UA/Client-Hints to impersonate defaults.
        headers = request.headers.to_unicode_dict()
        referer = headers.get("Referer") or headers.get("referer")
        if not referer:
            referer = request.meta.get("referer")
        if not referer:
            referer_resolver = getattr(spider, "request_referer", None)
            if callable(referer_resolver):
                referer = referer_resolver()
        return referer

    def _retry_delay_seconds(self, spider, attempt):
        base_delay = float(getattr(spider, "curl_image_retry_base_delay", self.curl_image_retry_base_delay))
        max_delay = float(getattr(spider, "curl_image_retry_max_delay", self.curl_image_retry_max_delay))
        delay = base_delay * (2 ** max(0, attempt - 1))
        return min(delay, max_delay)

    @staticmethod
    def _extract_http_status(exc):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            return int(status_code)
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            try:
                return int(status_code)
            except (TypeError, ValueError):
                return None
        return None

    def _is_retryable_curl_error(self, spider, exc):
        status_code = self._extract_http_status(exc)
        if status_code is not None:
            retryable_codes = getattr(spider, "curl_image_retryable_status_codes", self.curl_image_retryable_status_codes)
            return int(status_code) in retryable_codes
        # Transport / timeout / connection failures have no HTTP status.
        return True

    def media_to_download(self, request: Request, info, *, item=None):
        # super(): local uptodate only (None => need bytes). Never rewrite request.url.
        dfd = maybeDeferred(super().media_to_download, request, info, item=item)
        spider = info.spider
        attempts = max(1, int(getattr(spider, "curl_image_retries", self.curl_image_retries)))
        referer = self._curl_request_referer(request, spider)
        image_url = str(request.url)

        def _fetch_uncached(file_info):
            if file_info is not None:
                return file_info

            def _download_via_curl():
                session = self._get_curl_session(spider)
                for attempt in range(1, attempts + 1):
                    try:
                        response = session.get(image_url, referer=referer)
                        response.raise_for_status()
                        return response.status_code, response.content
                    except Exception as exc:
                        retryable = self._is_retryable_curl_error(spider, exc)
                        if (not retryable) or attempt >= attempts:
                            status_code = self._extract_http_status(exc)
                            raise RuntimeError(
                                f"{self._curl_image_label} image curl failed | url={image_url} | "
                                f"status={status_code if status_code is not None else '-'} | "
                                f"proxy_policy={getattr(spider, 'curl_image_proxy_policy', self.curl_image_proxy_policy)} | "
                                f"error={type(exc).__name__}: {exc}"
                            ) from exc
                        next_delay = self._retry_delay_seconds(spider, attempt)
                        status_code = self._extract_http_status(exc)
                        spider.logger.warning(
                            "%s image curl retry %s/%s | status=%s | delay=%.1fs | url=%s | referer=%s | error=%s: %s",
                            self._curl_image_label,
                            attempt,
                            attempts,
                            status_code if status_code is not None else "-",
                            next_delay,
                            image_url,
                            referer or "-",
                            type(exc).__name__,
                            exc,
                        )
                        sleep(next_delay)

            def _handle_curl_result(result):
                status_code, content = result
                return maybeDeferred(
                    self.media_downloaded,
                    Response(url=image_url, status=status_code, body=content, request=request),
                    request,
                    info,
                    item=item,
                )

            thread_dfd = deferToThread(_download_via_curl)
            thread_dfd.addCallback(_handle_curl_result)
            return thread_dfd

        dfd.addCallback(_fetch_uncached)
        return dfd


class WnacgComicPipeline(CurlComicPipeline):
    """Use the gallery CDN URL and configured proxy for WNACG image downloads."""

    curl_image_proxy_policy = "follow_conf"


class Dm5ComicPipeline(CurlComicPipeline):
    """Use direct curl_cffi requests for DM5 reader images."""

    curl_image_proxy_policy = "direct"


class JmComicPipeline(ComicPipeline):
    def get_images(self, response, request, info, *, item=None):
        path = self.file_path(request, response=response, info=info, item=item)
        orig_image = JmUtils.JmImage.by_url(item['image_urls'][0]).convert_img(response.body)

        width, height = orig_image.size
        if width < self.min_width or height < self.min_height:
            raise ImageException("Image too small " f"({width}x{height} < {self.min_width}x{self.min_height})")

        image, buf = self.convert_image(orig_image, response_body=BytesIO(response.body))
        yield path, image, buf

        for thumb_id, size in self.thumbs.items():
            thumb_path = self.thumb_path(request, thumb_id, response=response, info=info, item=item)
            thumb_image, thumb_buf = self.convert_image(image, size, buf)
            yield thumb_path, thumb_image, thumb_buf


class MangabzComicPipeline(ComicPipeline):

    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        return [Request(u, callback=NO_CALLBACK, headers=MangabzUtils.image_ua) for u in urls]
