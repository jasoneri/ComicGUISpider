# -*- coding: utf-8 -*-
import asyncio
import inspect
import os
import pathlib
import re
import threading
from io import BytesIO
from time import sleep

from curl_cffi import requests as curl_requests
import pillow_avif
from itemadapter import ItemAdapter
from scrapy import signals
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.images import ImagesPipeline, ImageException
from scrapy.utils.defer import deferred_from_coro
from twisted.internet.defer import maybeDeferred
from twisted.internet.threads import deferToThread

from utils import conf, TaskObj, TasksObj
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
        self._emit_task(spider, tasks_obj)
        # cache file_folder
        spider.tasks_path[uuid_md5] = path
        return path

    def _emit_task(self, spider, tasks_obj):
        spider.emit(TasksObjEvent(job_id=getattr(spider, '_job_id', None), task_obj=tasks_obj, is_new=True))

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


class EHentaiComicPipeline(ComicPipeline):
    """H@H 图片失败转移。行为契约见 CGS019"""

    eh_node_switch_max = 3
    eh_view_page_timeout = 15
    eh_node_reroll_max = 1
    eh_transient_retry_max = 1
    eh_transient_backoff_base = 1.5
    eh_transient_backoff_max = 6.0
    _TRANSIENT_ERROR_NAMES = frozenset(
        {"ConnectionLost", "ConnectionDone", "ConnectionAborted", "ConnectionReset", "IndexError"}
    )

    async def _check_media_to_download(self, request, info, item):
        spider = info.spider

        result, failure = await self._attempt_with_transient_retry(
            request, info, item, spider.hath_image_download_timeout_fast, spider
        )
        if failure is None:
            return result
        return await self._download_via_node_switch(request, info, item, spider)

    async def _download_via_node_switch(self, request, info, item, spider):
        view_page_url = request.meta.get("view_page_url")
        if not view_page_url:
            raise ImageException(
                f"ehentai image failed fast-probe and no /s/ page context to switch node: {request.url}"
            )

        page = item.get("page")
        nl_token = request.meta.get("nl_token")
        failed_hosts = {self._host_of(request.url)}
        for attempt in range(1, self.eh_node_switch_max + 1):
            try:
                image_url, nl_token = await self._switch_to_fresh_host(
                    view_page_url, nl_token, spider, failed_hosts, page
                )
            except Exception as exc:
                spider.logger.warning(
                    "[eh] view-page reload failed (attempt %s/%s) | url=%s | error=%s: %s",
                    attempt, self.eh_node_switch_max, view_page_url, type(exc).__name__, exc,
                )
                break

            host = self._host_of(image_url)
            timeout = (
                spider.hath_image_download_timeout_fast
                if host in failed_hosts
                else self._switch_timeout(attempt, spider)
            )
            spider.logger.info(
                "[eh] switch hath node %s/%s | page=%s | new_url=%s",
                attempt, self.eh_node_switch_max, page, image_url,
            )
            retry_request = Request(image_url, callback=NO_CALLBACK, meta={
                "download_timeout": timeout,
                "max_retry_times": 0,
                "view_page_url": view_page_url,
                "nl_token": nl_token,
            })
            result, failure = await self._attempt_with_transient_retry(retry_request, info, item, timeout, spider)
            if failure is None:
                return result
            failed_hosts.add(host)

        raise ImageException(
            f"ehentai image failed after fast-probe and {self.eh_node_switch_max} node switches: {request.url}"
        )

    async def _switch_to_fresh_host(self, view_page_url, nl_token, spider, failed_hosts, page):
        image_url, nl_token = await self._reload_view_page(view_page_url, nl_token, spider)
        for _ in range(self.eh_node_reroll_max):
            host = self._host_of(image_url)
            if host not in failed_hosts:
                break
            spider.logger.info(
                "[eh] reload handed back a host that already failed, reloading again | page=%s | host=%s",
                page, host,
            )
            image_url, nl_token = await self._reload_view_page(view_page_url, nl_token, spider)
        return image_url, nl_token

    @staticmethod
    def _host_of(url):
        from urllib.parse import urlparse

        return (urlparse(url).hostname or "").lower()

    async def _attempt_with_transient_retry(self, request, info, item, timeout, spider):
        result, failure = await self._attempt_once(request, info, item, timeout)
        if failure is None:
            return result, None
        for index in range(1, self.eh_transient_retry_max + 1):
            if not self._is_transient(failure):
                return None, failure
            delay = self._transient_backoff(index)
            spider.logger.info(
                "[eh] transient link error, backoff %.1fs then retry same node (%s/%s) | url=%s",
                delay, index, self.eh_transient_retry_max, request.url,
            )
            await asyncio.sleep(delay)
            result, failure = await self._attempt_once(request, info, item, timeout)
            if failure is None:
                return result, None
        return None, failure

    async def _attempt_once(self, request, info, item, timeout):
        try:
            return await super()._check_media_to_download(self._retimed(request, timeout), info, item), None
        except Exception as exc:
            return None, exc

    @classmethod
    def _is_transient(cls, failure):
        if failure is None:
            return False
        exc = getattr(failure, "value", failure)
        return type(exc).__name__ in cls._TRANSIENT_ERROR_NAMES

    def _transient_backoff(self, index):
        delay = self.eh_transient_backoff_base * (2 ** (index - 1))
        return min(delay, self.eh_transient_backoff_max)

    @staticmethod
    def _retimed(request, timeout):
        new_meta = dict(request.meta)
        new_meta["download_timeout"] = timeout
        new_meta["max_retry_times"] = 0
        return request.replace(meta=new_meta)

    def _switch_timeout(self, attempt, spider):
        fast = spider.hath_image_download_timeout_fast
        long_timeout = spider.hath_image_download_timeout
        span = self.eh_node_switch_max
        if span <= 1 or attempt >= span:
            return long_timeout
        if attempt == 1:
            return fast
        step = (long_timeout - fast) / (span - 1)
        return fast + round(step * (attempt - 1))

    async def _reload_view_page(self, view_page_url, nl_token, spider):
        url = f"{view_page_url}?nl={nl_token}" if nl_token else view_page_url
        view_request = Request(
            url, callback=NO_CALLBACK,
            headers=dict(getattr(spider, "ua", {}) or {}),
            meta={"download_timeout": self.eh_view_page_timeout, "handle_httpstatus_all": True},
        )
        response = await self.crawler.engine.download_async(view_request)
        image_url = response.xpath('//img[@id="img"]/@src').get()
        if not image_url or image_url.endswith("509.gif"):
            raise ImageException(
                f"view page returned no usable image | status={response.status} | url={url}"
            )
        match = re.search(r"return nl\('([^']*)'\)", response.text)
        return image_url, (match.group(1) if match else None)


class CurlComicPipeline(ComicPipeline):
    """Download uncached images with curl_cffi while retaining ImagesPipeline storage.

    curl_cffi.Session is not safe for concurrent use across deferToThread workers.
    Scrapy CONCURRENT_REQUESTS fans out many media_to_download calls; a shared
    session serializes/corrupts completions so ProgressCard jumps in batches.
    Use one Session per worker thread.
    """

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
        pipe._curl_thread_local = threading.local()
        pipe._curl_sessions_lock = threading.Lock()
        pipe._curl_all_sessions: list = []
        pipe._curl_session_identity = None
        crawler.signals.connect(pipe._close_curl_sessions, signal=signals.spider_closed)
        return pipe

    def get_media_requests(self, item, info):
        urls = ItemAdapter(item).get(self.images_urls_field, [])
        return [Request(url, callback=NO_CALLBACK) for url in urls]

    @staticmethod
    def _progress_card_tasks_snapshot(tasks_obj: TasksObj) -> TasksObj:
        """Metadata-only TasksObj for is_new ProgressCard mount.

        Emitting the live spider.tasks entry shares its downloaded list with the
        GUI; concurrent curl completions then look like an N-page jump. Snapshot
        keeps identity/path/cover fields and an empty downloaded list.
        """
        snapshot = TasksObj(
            tasks_obj.taskid,
            tasks_obj.title,
            tasks_obj.tasks_count,
            title_url=getattr(tasks_obj, "title_url", None),
            episode_name=getattr(tasks_obj, "episode_name", None),
            cover_url=getattr(tasks_obj, "cover_url", None),
            meta_info=getattr(tasks_obj, "meta_info", None),
            source=getattr(tasks_obj, "source", None),
        )
        snapshot.local_path = getattr(tasks_obj, "local_path", None)
        snapshot.cover_bytes = getattr(tasks_obj, "cover_bytes", None)
        page_name_count = getattr(tasks_obj, "page_name_count", None)
        if page_name_count is not None:
            snapshot.page_name_count = page_name_count
        download_pages = getattr(tasks_obj, "download_pages", None)
        if download_pages is not None:
            snapshot.download_pages = download_pages
        return snapshot

    def _emit_task(self, spider, tasks_obj):
        spider.emit(TasksObjEvent(
            job_id=getattr(spider, '_job_id', None),
            task_obj=self._progress_card_tasks_snapshot(tasks_obj),
            is_new=True,
        ))

    def _close_curl_sessions(self, spider=None, reason=None):
        with self._curl_sessions_lock:
            sessions = list(self._curl_all_sessions)
            self._curl_all_sessions.clear()
            self._curl_session_identity = None
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass
        local = getattr(self, "_curl_thread_local", None)
        if local is not None:
            local.session = None
            local.identity = None

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

    def _build_session_identity(self, spider):
        timeout = getattr(spider, "image_download_timeout", self.curl_image_timeout)
        proxy_url = self._resolve_curl_proxy_url(spider)
        return {
            "impersonate_candidates": tuple(self._resolve_impersonate_candidates(spider)),
            "timeout": timeout,
            "proxy": proxy_url,
        }

    def _open_curl_session(self, spider, session_identity):
        last_error = None
        for impersonate_profile in session_identity["impersonate_candidates"]:
            session_kwargs = {"impersonate": impersonate_profile, "timeout": session_identity["timeout"]}
            if session_identity["proxy"]:
                session_kwargs["proxy"] = session_identity["proxy"]
            try:
                session = curl_requests.Session(**session_kwargs)
                if impersonate_profile != session_identity["impersonate_candidates"][0]:
                    spider.logger.warning(
                        "%s image curl impersonate fallback | preferred=%s | active=%s",
                        self._curl_image_label,
                        session_identity["impersonate_candidates"][0],
                        impersonate_profile,
                    )
                return session
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

    def _get_curl_session(self, spider):
        """Per-worker-thread Session; never share across concurrent curl gets."""
        session_identity = self._build_session_identity(spider)
        local = self._curl_thread_local
        if getattr(local, "session", None) is not None and getattr(local, "identity", None) == session_identity:
            return local.session

        old_session = getattr(local, "session", None)
        if old_session is not None:
            with self._curl_sessions_lock:
                if old_session in self._curl_all_sessions:
                    self._curl_all_sessions.remove(old_session)
            try:
                old_session.close()
            except Exception:
                pass

        session = self._open_curl_session(spider, session_identity)
        local.session = session
        local.identity = session_identity
        with self._curl_sessions_lock:
            self._curl_session_identity = session_identity
            self._curl_all_sessions.append(session)
        return session

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

    def _media_downloaded_deferred(self, response, request, info, *, item=None):
        """Scrapy 2.15 media_downloaded is async; schedule via deferred_from_coro."""
        result = self.media_downloaded(response, request, info, item=item)
        if inspect.isawaitable(result):
            return deferred_from_coro(result)
        return maybeDeferred(lambda: result)

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
                return self._media_downloaded_deferred(
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
