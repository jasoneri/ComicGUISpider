from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from loguru import logger as lg

_danbooru_debug_event_sink_lock = threading.Lock()
_danbooru_debug_event_sink: Optional[Callable[[dict], None]] = None


def debug_shrink_text(payload: object, limit: int = 400) -> str:
    text = str(payload or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<trimmed {len(text) - limit} chars>"


def set_danbooru_debug_event_sink(sink: Optional[Callable[[dict], None]]) -> None:
    global _danbooru_debug_event_sink
    with _danbooru_debug_event_sink_lock:
        _danbooru_debug_event_sink = sink


def clear_danbooru_debug_event_sink() -> None:
    set_danbooru_debug_event_sink(None)


def append_danbooru_debug_event(stage: str, **payload) -> dict:
    event = {
        "stage": str(stage or "").strip() or "unknown",
        "time": time.time(),
        **payload,
    }
    with _danbooru_debug_event_sink_lock:
        sink = _danbooru_debug_event_sink
    if sink is None:
        return event
    try:
        sink(dict(event))
    except Exception as exc:
        lg.warning(f"[DanbooruDebug] failed to append event stage={stage}: {exc}")
    return event
