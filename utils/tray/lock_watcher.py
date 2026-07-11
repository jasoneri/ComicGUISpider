from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from utils.subscription.lock import TrayLock


class LockWatcher:
    def __init__(self, release_callback: Callable[[], None], *, interval_s: float, lock_path: Path | str) -> None:
        self._release_callback = release_callback
        self._interval_s = float(interval_s)
        self._lock_path = Path(lock_path)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="CGSTrayLockWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_s * 4))
            self._thread = None

    def _run(self) -> None:
        request_path = TrayLock.release_request_path(self._lock_path)
        while not self._stop_event.wait(self._interval_s):
            if not request_path.exists():
                continue
            self._release_callback()
            request_path.unlink(missing_ok=True)
            return
