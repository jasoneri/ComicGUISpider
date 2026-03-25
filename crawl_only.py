# -*- coding: utf-8 -*-
"""CLI download entry using SpiderRuntimeThread + event_q."""
import argparse
import asyncio
import os
import queue
import sys
from uuid import uuid4

import httpx
from loguru import logger

from ComicSpider.runtime import SpiderRuntimeThread
from utils import conf, select
from utils.protocol import (
    SpiderDownloadJob,
    JobAcceptedEvent,
    LogEvent,
    ErrorEvent,
    JobFinishedEvent,
    BarProgressEvent,
    ProcessStateEvent,
    TasksObjEvent,
)
from utils.website import spider_utils_map
from utils.website.core import Previewer, ProviderContext, build_proxy_transport
from variables import Spider, SPIDERS

is_debugging = os.getenv("CGS_DEBUG") == "1"


class PreviewRuntime:
    def __init__(self, site_index: int):
        preview_cls = spider_utils_map.get(site_index)
        if preview_cls is None:
            raise ValueError(f"unsupported site index: {site_index}")
        if not issubclass(preview_cls, Previewer):
            raise TypeError(f"{preview_cls.__name__} does not support preview search")
        self.preview_cls = preview_cls
        self.site_index = site_index
        self.client: httpx.AsyncClient | None = None
        self.context = ProviderContext.create(
            proxies=conf.proxies,
            cookies=conf.cookies.get(preview_cls.name),
            custom_map=conf.custom_map,
        )

    async def __aenter__(self):
        site_kw = self.preview_cls.preview_client_config(self.context)
        policy = getattr(self.preview_cls, "proxy_policy", "proxy")
        verify = site_kw.pop("verify", True)
        transport, trust_env = build_proxy_transport(policy, conf.proxies, verify=verify)
        base_kw = dict(
            transport=transport,
            follow_redirects=True,
            trust_env=trust_env,
            headers=None,
        )
        base_kw.update(site_kw)
        self.client = httpx.AsyncClient(**base_kw)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def search(self, keyword: str, page: int = 1):
        return await self.preview_cls.preview_search(
            keyword,
            self.client,
            page=page,
            context=self.context,
        )

    async def fetch_episodes(self, book):
        return await self.preview_cls.preview_fetch_episodes(
            book,
            self.client,
            context=self.context,
        )


def _build_parser():
    parser = argparse.ArgumentParser(
        description=f"CGS CLI runtime downloader. 网站序号: {SPIDERS}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-w", "--website", type=int, default=1, help="选择网站序号")
    parser.add_argument("-k", "--keyword", required=True, help="关键字（作品名）")
    parser.add_argument("-i", "--indexes", required=True, help="选书序号")
    parser.add_argument("-i2", "--indexes2", default=None, help="选话序号，非 specials 站点必填")
    parser.add_argument("-l", "--log_level", default="DEBUG", help="log level")
    parser.add_argument("-tw", "--time_wait", default=None, help="保留兼容参数，当前未使用")
    parser.add_argument("-tp", "--turn_page", action="store_true", help="保留兼容参数，当前未使用")
    parser.add_argument("-dt", "--daily_test", action="store_true", help="保留兼容参数，当前未使用")
    return parser


def _validate_args(parser, args):
    if args.website not in Spider.specials() and not args.indexes2:
        parser.error(
            "the following argument is required when website is not in Spider.specials(): -i2/--indexes2"
        )
    if args.website in Spider.specials() and args.indexes2:
        parser.error("the argument -i2/--indexes2 is not allowed when website is in Spider.specials()")


def _render_books(books_map: dict):
    for idx, book in sorted(books_map.items()):
        title = getattr(book, "name", "") or getattr(book, "title", "") or "-"
        logger.info(f"[book:{idx}] {title}")


def _render_episodes(episodes_map: dict):
    for idx, ep in sorted(episodes_map.items()):
        title = getattr(ep, "name", "") or getattr(ep, "title", "") or "-"
        logger.info(f"[ep:{idx}] {title}")


async def _search_books(site_index: int, keyword: str) -> dict:
    async with PreviewRuntime(site_index) as preview:
        books = await preview.search(keyword, page=1)
    books_map = {}
    for idx, book in enumerate(books, start=1):
        if getattr(book, "idx", None) is None:
            book.idx = idx
        books_map[int(book.idx)] = book
    return books_map


async def _fetch_episode_choices(site_index: int, books: list) -> dict:
    episode_choices = {}
    async with PreviewRuntime(site_index) as preview:
        next_idx = 1
        for book in books:
            episodes = await preview.fetch_episodes(book)
            for ep in episodes or []:
                episode_choices[next_idx] = ep
                next_idx += 1
    return episode_choices


def _build_download_payload(site_index: int, selected_books: list, selected_eps: list | None):
    if site_index in Spider.specials():
        return selected_books[0] if len(selected_books) == 1 else selected_books

    books_by_key = {}
    for ep in selected_eps or []:
        book = getattr(ep, "from_book", None)
        if book is None:
            continue
        key = id(book)
        if key not in books_by_key:
            book.episodes = []
            books_by_key[key] = book
        books_by_key[key].episodes.append(ep)
    payload = list(books_by_key.values())
    if not payload:
        raise ValueError("no episodes selected for download")
    return payload[0] if len(payload) == 1 else payload


def _submit_and_wait(site_index: int, payload) -> bool:
    runtime = SpiderRuntimeThread()
    runtime.daemon = True
    runtime.start()
    runtime.wait_ready(timeout=30)

    job = SpiderDownloadJob(
        job_id=uuid4().hex,
        spider_name=SPIDERS[site_index],
        site_index=site_index,
        payload=payload,
        options={},
    )
    logger.info(f"[submit] spider={job.spider_name} job={job.job_id}")
    runtime.submit_job(job)

    last_percent = None
    success = False
    try:
        while True:
            try:
                event = runtime.event_q.get(timeout=0.2)
            except queue.Empty:
                continue

            event_job_id = getattr(event, "job_id", None)
            if event_job_id and event_job_id != job.job_id:
                continue

            if isinstance(event, JobAcceptedEvent):
                logger.info(f"[accepted] {event.job_id}")
            elif isinstance(event, LogEvent):
                logger.info(str(event.message))
            elif isinstance(event, ProcessStateEvent):
                logger.debug(f"[stage] {event.process}")
            elif isinstance(event, BarProgressEvent):
                if event.percent != last_percent:
                    last_percent = event.percent
                    logger.info(f"[progress] {event.percent}%")
            elif isinstance(event, TasksObjEvent):
                task = event.task_obj
                if event.is_new:
                    title = getattr(task, "display_title", None) or getattr(task, "taskid", "")
                    logger.info(f"[task] {title}")
            elif isinstance(event, ErrorEvent):
                logger.error(event.error)
            elif isinstance(event, JobFinishedEvent):
                success = bool(event.success)
                logger.info(f"[finished] success={success}")
                return success
    finally:
        runtime.shutdown()
        runtime.join(timeout=5)


def main():
    parser = _build_parser()
    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper())
    _validate_args(parser, args)

    if args.turn_page:
        logger.warning("--turn_page is no longer supported in runtime CLI; ignoring")
    if args.daily_test or is_debugging:
        logger.info("runtime CLI uses the same event_q flow in daily/debug mode")

    try:
        books_map = asyncio.run(_search_books(args.website, args.keyword))
        if not books_map:
            logger.error("search returned no books")
            return 1
        _render_books(books_map)

        selected_books = select(args.indexes, books_map)
        if not selected_books:
            logger.error("selected book indexes resolved to empty set")
            return 1

        selected_eps = None
        if args.website not in Spider.specials():
            episode_choices = asyncio.run(_fetch_episode_choices(args.website, selected_books))
            if not episode_choices:
                logger.error("episode fetch returned no episodes")
                return 1
            _render_episodes(episode_choices)
            selected_eps = select(args.indexes2, episode_choices)
            if not selected_eps:
                logger.error("selected episode indexes resolved to empty set")
                return 1

        payload = _build_download_payload(args.website, selected_books, selected_eps)
        return 0 if _submit_and_wait(args.website, payload) else 1
    except Exception as exc:
        logger.exception(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
