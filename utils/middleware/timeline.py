# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
import typing as t


class TimelineStage(IntEnum):
    SESSION_INIT = 50

    WAIT_KEYWORD = 100
    KEYWORD_SENT = 110
    SPIDER_INIT = 120
    SEARCHING = 130

    BOOKS_READY = 200
    WAIT_BOOK_DECISION = 210
    BOOK_SENT = 220

    EPS_READY = 300
    WAIT_EP_DECISION = 310
    EP_SENT = 320

    DOWNLOADING = 400
    ITEM_SAVED = 500
    POSTPROCESSING = 600
    FINISHED = 700

    PAGE_TURN_REQUESTED = 800
    RETRY_REQUESTED = 810

    SESSION_END = 950
    SESSION_CANCEL = 960
    SESSION_ERROR = 970


class EventSource(str, Enum):
    PROCESS_QUEUE = "ProcessQueue"
    TEXTBROWSER_QUEUE = "TextBrowserQueue"
    UI = "UI"


@dataclass(frozen=True)
class Event:
    source: EventSource
    stage: TimelineStage
    payload: dict


_PROCESS_TO_STAGE: dict[str, TimelineStage] = {
    "init": TimelineStage.WAIT_KEYWORD,
    "spider_init": TimelineStage.SPIDER_INIT,
    "start_requests": TimelineStage.KEYWORD_SENT,
    "search": TimelineStage.SEARCHING,
    "parse": TimelineStage.SEARCHING,
    "defer_parse": TimelineStage.SEARCHING,
    "parse section": TimelineStage.DOWNLOADING,
    "fin": TimelineStage.FINISHED,
}


def stage_from_process_name(process_name: str) -> t.Optional[TimelineStage]:
    if not process_name:
        return None
    return _PROCESS_TO_STAGE.get(process_name)


def stage_from_textbrowser_payload(payload) -> t.Optional[TimelineStage]:
    if isinstance(payload, dict):
        values = list(payload.values())
        if not values:
            return None
        first = values[0]
        if first.__class__.__name__ == "BookInfo":
            return TimelineStage.BOOKS_READY
        if first.__class__.__name__ == "Episode":
            return TimelineStage.EPS_READY
    return None


def stage_from_ui_action(action_name: str) -> t.Optional[TimelineStage]:
    if action_name == "page_turn":
        return TimelineStage.PAGE_TURN_REQUESTED
    if action_name == "retry":
        return TimelineStage.RETRY_REQUESTED
    if action_name == "book_sent":
        return TimelineStage.BOOK_SENT
    if action_name == "ep_sent":
        return TimelineStage.EP_SENT
    return None
