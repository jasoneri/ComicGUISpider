"""Append-only JSONL event log for tray/GUI display (temp_p/tray_events.json).

kind 约定 (append 接受任意 kind 字符串, 展示端按 kind/result 渲染):
- subscription: 订阅主流程 start/skip/ok/error
- checkin_ok / checkin_already / checkin_failed: 按站每日签到结果 (领域 6)
"""
from __future__ import annotations

import json
import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils import temp_p


class TrayEventLog:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else temp_p / "tray_events.json"
        self._lock = threading.Lock()

    def append(
        self,
        kind: str,
        *,
        book: Optional[str] = None,
        result: str,
        detail: str = "",
        exc: Optional[BaseException] = None,
    ) -> None:
        traceback_text = None
        if exc is not None:
            traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        entry = {
            "ts": self._utc_ts(),
            "kind": kind,
            "book": book,
            "result": result,
            "detail": detail,
            "traceback": traceback_text,
        }
        encoded = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            needs_separator = self._needs_line_separator()
            with open(self.path, "a", encoding="utf-8") as fp:
                if needs_separator:
                    fp.write("\n")
                fp.write(encoded)
                fp.write("\n")

    def tail(self, limit: int = 20) -> list[dict]:
        if limit <= 0 or not self.path.exists():
            return []

        entries: list[dict] = []
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as fp:
                for line in fp:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        entries.append(parsed)
        return entries[-limit:]

    def clear(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8"):
                pass

    def _needs_line_separator(self) -> bool:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return False
        with open(self.path, "rb") as fp:
            fp.seek(-1, os.SEEK_END)
            return fp.read(1) != b"\n"

    @staticmethod
    def _utc_ts() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
