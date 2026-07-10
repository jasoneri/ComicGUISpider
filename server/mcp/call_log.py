from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any


DEFAULT_MCP_CALL_LOG_MAXLEN = 200


class McpCallLog:
    def __init__(self, *, maxlen: int = DEFAULT_MCP_CALL_LOG_MAXLEN):
        if maxlen < 1:
            raise ValueError("maxlen must be at least 1")
        self._entries: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = Lock()

    def record(
            self,
            tool: str,
            args_summary: str,
            code: str | None,
            elapsed_ms: float,
            error: str | None,
            response_summary: str | None = None,
    ) -> None:
        entry = {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "tool": str(tool),
            "args_summary": str(args_summary),
            "code": None if code is None else str(code),
            "elapsed_ms": float(elapsed_ms),
            "error": None if error is None else str(error),
            "response_summary": None if response_summary is None else str(response_summary),
        }
        with self._lock:
            self._entries.append(entry)

    def tail(self, n: int) -> list[dict[str, Any]]:
        if n <= 0:
            return []
        with self._lock:
            entries = list(self._entries)[-n:]
        return [dict(entry) for entry in entries]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
