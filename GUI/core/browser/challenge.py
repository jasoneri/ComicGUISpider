from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QTimer

from .types import BrowserChallengeResult, BrowserChallengeSpec


class BrowserChallengeCoordinator(QObject):
    def __init__(
        self,
        *,
        window_factory: Callable[[], object],
        on_success: Callable[[BrowserChallengeResult, list[Callable[[], None]], list[str]], None],
        on_missing: Callable[[BrowserChallengeResult, list[str]], None],
        parent=None,
    ):
        super().__init__(parent)
        self._window_factory = window_factory
        self._on_success = on_success
        self._on_missing = on_missing
        self._window = None
        self._active_spec: BrowserChallengeSpec | None = None
        self._retry_callbacks: dict[str, Callable[[], None]] = {}
        self._tab_ids: set[str] = set()
        self._sync_inflight = False

    def current_window(self):
        return self._window

    def active_spec(self) -> BrowserChallengeSpec | None:
        return self._active_spec

    def drain_pending(self) -> tuple[list[Callable[[], None]], list[str]]:
        retry_callbacks = list(self._retry_callbacks.values())
        tab_ids = list(self._tab_ids)
        self._retry_callbacks.clear()
        self._tab_ids.clear()
        return retry_callbacks, tab_ids

    def close_window(self) -> None:
        if self._window is not None:
            self._window.close()

    def submit(
        self,
        spec: BrowserChallengeSpec,
        *,
        tab_id: str,
        retry_key: str,
        retry_callback: Callable[[], None],
    ) -> None:
        window = self._ensure_window()
        self._active_spec = spec
        self._retry_callbacks[str(retry_key)] = retry_callback
        self._tab_ids.add(tab_id)
        self._sync_inflight = False
        window.enter_challenge_mode(
            spec,
            ensure_handler=self.request_sync,
            close_handler=lambda *_args: None,
        )
        window.show()
        window.raise_()
        window.activateWindow()

    def request_sync(self, *, trigger: str = "manual", current_url: str = "") -> None:
        if self._window is None or not self._retry_callbacks or self._sync_inflight:
            return
        if self._active_spec is None:
            return
        self._sync_inflight = True
        active_url = current_url or self._window.view.url().toString()
        self._window.collect_challenge_result(
            self._active_spec,
            self._handle_result,
            current_url=active_url,
            trigger=trigger,
        )

    def _ensure_window(self):
        if self._window is None:
            window = self._window_factory()
            window.destroyed.connect(self._on_window_destroyed)
            window.pageLoadFinishedDetailed.connect(self._on_window_load_finished)
            window.pageInteractive.connect(self._on_window_page_interactive)
            self._window = window
        return self._window

    def _on_window_destroyed(self, *_args):
        self._window = None
        self._sync_inflight = False

    def _on_window_load_finished(self, ok: bool, _elapsed_ms: float):
        if not ok or self._window is None or not self._retry_callbacks:
            return
        if self._sync_inflight:
            return
        spec = self._active_spec
        if spec is None or not spec.auto_sync_on_load or spec.completion_detector is None:
            return
        current_url = self._window.view.url().toString()
        if not spec.completion_detector(current_url):
            return
        self.request_sync(trigger="auto", current_url=current_url)

    def _on_window_page_interactive(self, _reason: str, _elapsed_ms: float):
        if self._window is None or not self._retry_callbacks or self._sync_inflight:
            return
        spec = self._active_spec
        if spec is None or not spec.auto_sync_on_load or spec.completion_detector is None:
            return
        current_url = self._window.view.url().toString()
        if not spec.completion_detector(current_url):
            return
        self.request_sync(trigger="interactive", current_url=current_url)

    def _schedule_retry_sync(self, *, current_url: str = "") -> bool:
        if self._window is None or not self._retry_callbacks:
            return False
        spec = self._active_spec
        if spec is None or int(spec.poll_interval_ms or 0) <= 0:
            return False
        active_url = current_url or self._window.view.url().toString()
        QTimer.singleShot(
            int(spec.poll_interval_ms),
            lambda active_url=active_url: self.request_sync(trigger="poll", current_url=active_url),
        )
        return True

    def _handle_result(self, result: BrowserChallengeResult):
        self._sync_inflight = False
        spec = self._active_spec
        if not result.has_transfer_state:
            if self._schedule_retry_sync(current_url=result.current_url):
                return
            self._on_missing(result, list(self._tab_ids))
            return
        if spec is not None and spec.result_validator is not None and not spec.result_validator(result):
            if self._schedule_retry_sync(current_url=result.current_url):
                return
            self._on_missing(result, list(self._tab_ids))
            return
        retry_callbacks, tab_ids = self.drain_pending()
        self._on_success(result, retry_callbacks, tab_ids)
        self.close_window()
