# -*- coding: utf-8 -*-
"""Thin CLI downloader entry using the shared CGS Server runtime owner."""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

from loguru import logger

from server.runtime import PreviewRuntime
from server.runtime_download import serialize_protocol_event, submit_and_wait
from utils import install_qfluentwidgets_notice_filter, select
from variables import SPIDERS, Spider

if "--structured-events" in sys.argv[1:]:
    install_qfluentwidgets_notice_filter()

is_debugging = os.getenv("CGS_DEBUG") == "1"


class CliArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, event_writer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_writer = event_writer

    def error(self, message):
        if self.event_writer:
            self.event_writer.error("argument_error", message)
            self.event_writer.finished(False, message)
        super().error(message)


class CliEventWriter:
    def __init__(self, job_id: str, stream=None):
        self.job_id = job_id
        self.stream = stream or sys.stdout

    def emit(self, event_type: str, **fields):
        payload = {
            "type": event_type,
            "job_id": fields.pop("job_id", None) or self.job_id,
            "timestamp": fields.pop("timestamp", None) or datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        self.stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        self.stream.flush()

    def error(self, stage: str, error):
        self.emit("error", stage=stage, error=str(error))

    def finished(self, success: bool, error=None):
        fields = {"success": bool(success)}
        if error:
            fields["error"] = str(error)
        self.emit("finished", **fields)

    def protocol_event(self, event):
        payload = serialize_protocol_event(event, default_job_id=self.job_id)
        self.emit(payload.pop("type"), **payload)


def _build_parser(event_writer=None):
    parser = CliArgumentParser(
        description=f"CGS CLI runtime downloader. 网站序号: {SPIDERS}",
        formatter_class=argparse.RawDescriptionHelpFormatter, event_writer=event_writer,
    )
    parser.add_argument("-w", "--website", type=int, default=1, help="选择网站序号")
    parser.add_argument("-k", "--keyword", required=True, help="关键字（作品名）")
    parser.add_argument("-i", "--indexes", required=True, help="选书序号")
    parser.add_argument("-i2", "--indexes2", default=None, help="选话序号，非 specials 站点必填")
    parser.add_argument("-l", "--log_level", default="DEBUG", help="log level")
    parser.add_argument("-tw", "--time_wait", default=None, help="保留兼容参数，当前未使用")
    parser.add_argument("-tp", "--turn_page", action="store_true", help="保留兼容参数，当前未使用")
    parser.add_argument("-dt", "--daily_test", action="store_true", help="保留兼容参数，当前未使用")
    parser.add_argument("--structured-events", action="store_true", help="输出 JSON Lines 结构化事件到 stdout")
    return parser


def _validate_args(parser, args):
    if args.website not in SPIDERS:
        parser.error(f"unknown website: {args.website}")
    if args.website not in Spider.specials() and not args.indexes2:
        parser.error("the following argument is required when website is not in Spider.specials(): -i2/--indexes2")
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


async def _fetch_selected_pages(site_index: int, items: list):
    async with PreviewRuntime(site_index) as preview:
        for item in items:
            if page_urls := getattr(item, "page_urls", None):
                if getattr(item, "pages", None) is None:
                    item.pages = len(page_urls)
                continue
            if getattr(item, "pages", None) is not None:
                continue
            page_urls = await preview.fetch_pages(item)
            if not isinstance(page_urls, list):
                raise TypeError(f"preview_fetch_pages must return list, got {type(page_urls).__name__}")
            item.pages = len(page_urls)
            item.page_urls = list(page_urls)


def _build_download_payload(site_index: int, selected_books: list, selected_eps: list | None):
    if site_index in Spider.specials():
        return selected_books[0] if len(selected_books) == 1 else selected_books
    payload = list(selected_eps or [])
    if not payload:
        raise ValueError("no episodes selected for download")
    return payload[0] if len(payload) == 1 else payload


def main():
    job_id = uuid4().hex
    event_writer = CliEventWriter(job_id) if "--structured-events" in sys.argv[1:] else None
    parser = _build_parser(event_writer=event_writer)
    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level=args.log_level.upper())
    _validate_args(parser, args)

    if args.turn_page:
        logger.warning("--turn_page is no longer supported in runtime CLI; ignoring")
    if args.daily_test or is_debugging:
        logger.info("runtime CLI uses the same CGS Server runtime owner in daily/debug mode")

    try:
        books_map = asyncio.run(_search_books(args.website, args.keyword))
        if not books_map:
            error = "search returned no books"
            if event_writer:
                event_writer.error("search", error)
                event_writer.finished(False, error)
            logger.error(error)
            return 1
        _render_books(books_map)

        selected_books = select(args.indexes, books_map)
        if not selected_books:
            error = "selected book indexes resolved to empty set"
            if event_writer:
                event_writer.error("select_books", error)
                event_writer.finished(False, error)
            logger.error(error)
            return 1

        selected_eps = None
        if args.website not in Spider.specials():
            episode_choices = asyncio.run(_fetch_episode_choices(args.website, selected_books))
            if not episode_choices:
                error = "episode fetch returned no episodes"
                if event_writer:
                    event_writer.error("fetch_episodes", error)
                    event_writer.finished(False, error)
                logger.error(error)
                return 1
            _render_episodes(episode_choices)
            selected_eps = select(args.indexes2, episode_choices)
            if not selected_eps:
                error = "selected episode indexes resolved to empty set"
                if event_writer:
                    event_writer.error("select_episodes", error)
                    event_writer.finished(False, error)
                logger.error(error)
                return 1
            asyncio.run(_fetch_selected_pages(args.website, selected_eps))
        else:
            asyncio.run(_fetch_selected_pages(args.website, selected_books))

        payload = _build_download_payload(args.website, selected_books, selected_eps)
        sink = event_writer if event_writer else None
        return 0 if submit_and_wait(args.website, payload, job_id=job_id, event_sink=sink) else 1
    except Exception as exc:
        if event_writer:
            event_writer.error("cli", exc)
            event_writer.finished(False, exc)
        logger.exception(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
