from __future__ import annotations

import os
import time
from pathlib import Path


class TrayLock:
    def __init__(self, lock_path: Path | str) -> None:
        self.lock_path = Path(lock_path)
        self._owned = False

    @classmethod
    def release_request_path(cls, lock_path: Path | str) -> Path:
        path = Path(lock_path)
        return path.with_name(f"{path.name}.release")

    @classmethod
    def is_held(cls, lock_path: Path | str) -> bool:
        return Path(lock_path).exists()

    @classmethod
    def acquire_for_cgs_startup(
        cls,
        lock_path: Path | str,
        *,
        timeout_s: float = 2.0,
        retry_interval_s: float = 0.05,
    ) -> "TrayLock":
        path = Path(lock_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cls.release_request_path(path).write_text(str(os.getpid()), encoding="ascii")
        deadline = time.monotonic() + float(timeout_s)
        lock = cls(path)
        while True:
            try:
                lock.acquire()
                cls.release_request_path(path).unlink(missing_ok=True)
                return lock
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for tray lock release: {path}")
                time.sleep(float(retry_interval_s))

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="ascii") as fp:
            fp.write(str(os.getpid()))
        self._owned = True

    def release(self) -> None:
        if not self._owned and not self.lock_path.exists():
            return
        self.lock_path.unlink(missing_ok=True)
        self._owned = False

    def __enter__(self) -> "TrayLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
