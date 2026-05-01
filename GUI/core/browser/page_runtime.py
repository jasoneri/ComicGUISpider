from __future__ import annotations

import json
import time

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from qfluentwidgets import InfoBar, InfoBarPosition

from .runtime import append_browser_debug_event


class PageNotReadyError(RuntimeError):
    pass


class _JsCallDispatcher(QObject):
    dispatch_requested = Signal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dispatch_requested.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    @Slot(object, object, object)
    def _dispatch(self, page, js_code, callback):
        BrowserPageRuntime._run_js_now(page, js_code, callback)


class BrowserPageRuntime:
    _READY_PROBE_INTERVAL_MS = 50
    _READY_PROBE_TIMEOUT_MS = 15000
    _READY_PROBE_JS = """(function(){
const previewRuntime = window.previewRuntime;
const previewCommandBus = window.previewCommandBus;
const readyState = document.readyState;
return JSON.stringify({
  domReady: readyState === 'interactive' || readyState === 'complete',
  readyState,
  hasPreviewRuntime: Boolean(
    previewRuntime
    && typeof previewRuntime.scanChecked === 'function'
    && typeof previewRuntime.markDownloaded === 'function'
  ),
  hasScanChecked: typeof window.scanChecked === 'function'
    || Boolean(previewRuntime && typeof previewRuntime.scanChecked === 'function'),
  hasCollectPreviewSubmitPayload: typeof window.collectPreviewSubmitPayload === 'function',
  hasPreviewCommandBus: Boolean(previewCommandBus && typeof previewCommandBus.dispatch === 'function')
});
})();"""

    def __init__(self, browser):
        self._browser = browser
        self.gui = browser.gui
        self._js_dispatcher = _JsCallDispatcher(browser)
        self._page_ready = False
        self._page_ready_announced = False
        self._page_load_started_at = None
        self._ready_generation = 0
        self._ready_probe_started_at = None
        self._ready_probe_attempts = 0
        self._js_dispatch_count = 0
        self._js_callback_count = 0
        self._js_structured_count = 0
        self._top_hint_count = 0
        self._frameless_update_count = 0
        self._last_frameless_update_started_at = None
        browser.view.loadStarted.connect(self._on_view_load_started)
        browser.view.loadFinished.connect(self._on_view_load_finished)

    @property
    def page_ready(self) -> bool:
        return self._page_ready

    @property
    def has_activity(self) -> bool:
        return bool(self._js_dispatch_count or self._js_callback_count or self._js_structured_count)

    def log_js_debug(self, message: str) -> None:
        gui = getattr(self._browser, "gui", None)
        logger = getattr(gui, "log", None)
        if logger:
            logger.debug(f"[browser.js] {message}")

    def log_web_perf(self, message: str) -> None:
        gui = getattr(self._browser, "gui", None)
        logger = getattr(gui, "log", None)
        if logger:
            logger.debug(f"[browser.perf] {message}")

    def prepare_navigation(self) -> None:
        self._page_ready = False
        self._page_ready_announced = False
        self._cancel_ready_probe()
        self._reset_metrics()

    def shutdown(self) -> None:
        self._page_ready = False
        self._cancel_ready_probe()

    def update_frameless(self, update_frameless):
        started_at = time.perf_counter()
        previous_started_at = self._last_frameless_update_started_at
        result = update_frameless()
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        self._frameless_update_count += 1
        self._last_frameless_update_started_at = started_at
        since_last_label = "n/a"
        if previous_started_at is not None:
            since_last_label = f"{(started_at - previous_started_at) * 1000:.1f}"
        self.log_web_perf(
            f"updateFrameless count={self._frameless_update_count} elapsed_ms="
            f"{elapsed_ms:.1f} since_last_ms={since_last_label} "
            f"page_ready={self._page_ready} visible={self._browser.isVisible()}"
        )
        return result

    def log_js_metrics(self, scope: str, **extra) -> None:
        details = ", ".join(f"{key}={value}" for key, value in extra.items())
        summary = (
            f"{scope}: dispatch={self._js_dispatch_count}, callbacks={self._js_callback_count}, "
            f"structured={self._js_structured_count}"
        )
        if details:
            summary = f"{summary}, {details}"
        self.log_js_debug(summary)

    def run_js(self, js_code, callback=None, *, page=None):
        self._run_page_js(page, js_code, callback)

    @staticmethod
    def js_execute_by_page(page, js_code, callback):
        BrowserPageRuntime._run_js_now(page, js_code, callback)

    def run_js_result(self, js_body, callback, *, expected_kind, description, page=None, error_callback=None):
        wrapped_js = self._wrap_structured_js(js_body)
        target_page = page or self._browser.view.page()
        if target_page is self._browser.view.page() and not self._page_ready:
            error = PageNotReadyError(f"{description} requested before page ready")
            self.log_js_debug(f"skip {description}: page not ready")
            if error_callback is not None:
                error_callback(error)
            return

        def handle_raw(raw_result):
            try:
                kind, value = self._decode_structured_result(raw_result, description)
                callback(self._validate_structured_kind(kind, value, expected_kind, description))
            except Exception as exc:
                self._handle_structured_js_error(description, exc, raw_result)
                if error_callback is not None:
                    error_callback(exc)

        self._run_page_js(page, wrapped_js, handle_raw, structured=True)

    def page_to_html(self, callback, *, page=None, description="page.toHtml()", error_callback=None):
        target_page = page or self._browser.view.page()
        current_url = target_page.url().toString()
        self._js_callback_count += 1

        def handle_raw(raw_html):
            if isinstance(raw_html, str):
                append_browser_debug_event(
                    "browser.page_to_html",
                    description=description,
                    current_url=current_url,
                    html_length=len(raw_html),
                    html_head=raw_html[:400],
                )
                callback(raw_html)
                return
            error = TypeError(f"{description} returned unexpected {type(raw_html).__name__}: {raw_html!r}")
            self._handle_structured_js_error(description, error, raw_html)
            if error_callback is not None:
                error_callback(error)

        target_page.toHtml(lambda html: QTimer.singleShot(0, lambda html=html: handle_raw(html)))

    def collect_ensure_result(self, after_callback, *, result_kind: str = "checked_ids"):
        if not self._browser.window_mode.uses_page_scan:
            self._browser.output = []
            after_callback()
            return

        def callback(ret):
            self._browser.output = ret
            after_callback()

        def on_error(exc):
            self._browser.output = []
            if isinstance(exc, PageNotReadyError):
                InfoBar.info(
                    title="",
                    content="页面仍在加载，稍后再试",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2200,
                    parent=self._browser.view,
                )
                return
            InfoBar.error(
                title="",
                content="页面脚本返回异常，请刷新预览后重试",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self._browser.view,
            )

        if result_kind == "preview_submit":
            self.run_js_result(
                "return collectPreviewSubmitPayload();",
                callback,
                expected_kind="object",
                description="collectPreviewSubmitPayload()",
                error_callback=on_error,
            )
            return

        self.run_js_result(
            "return scanChecked();",
            callback,
            expected_kind="array",
            description="scanChecked()",
            error_callback=on_error,
        )

    def _reset_metrics(self) -> None:
        self._page_load_started_at = None
        self._js_dispatch_count = 0
        self._js_callback_count = 0
        self._js_structured_count = 0
        self._top_hint_count = 0
        self._frameless_update_count = 0
        self._last_frameless_update_started_at = None

    def _mark_page_ready(self, *, reason: str) -> None:
        if self._page_ready_announced:
            return
        self._page_ready = True
        self._page_ready_announced = True
        elapsed_ms = None
        if self._page_load_started_at is not None:
            elapsed_ms = (time.perf_counter() - self._page_load_started_at) * 1000
        elapsed_label = f"{elapsed_ms:.1f}" if elapsed_ms is not None else "n/a"
        self.log_js_debug(
            f"page interactive reason={reason} elapsed_ms={elapsed_label} "
            f"dispatch={self._js_dispatch_count} callbacks={self._js_callback_count} "
            f"structured={self._js_structured_count}"
        )
        self._browser.pageInteractive.emit(reason, float(elapsed_ms if elapsed_ms is not None else -1.0))

    def _on_view_load_started(self) -> None:
        self._page_ready = False
        self._page_ready_announced = False
        self._page_load_started_at = time.perf_counter()
        current_url = self._browser.view.url().toString()
        self.log_js_debug(f"load started url={current_url!r}")
        append_browser_debug_event(
            "browser.load_started",
            url=current_url,
            home_url=self._browser.home_url.toString(),
            ensure_uses_page_scan=self._browser.window_mode.uses_page_scan,
        )
        self._cancel_ready_probe()
        self._ready_probe_started_at = self._page_load_started_at
        self._schedule_ready_probe(self._ready_generation, delay_ms=self._READY_PROBE_INTERVAL_MS)

    def _on_view_load_finished(self, ok: bool) -> None:
        self._browser.view.setFocus()
        if not ok:
            self._page_ready = False
            self._cancel_ready_probe()
            current_url = self._browser.view.url().toString()
            self.log_js_debug(f"load failed url={current_url!r}")
            append_browser_debug_event(
                "browser.load_finished",
                ok=False,
                url=current_url,
                elapsed_ms=-1.0,
                dispatch=self._js_dispatch_count,
                callbacks=self._js_callback_count,
                structured=self._js_structured_count,
            )
            self._browser.pageLoadFinishedDetailed.emit(False, -1.0)
            return
        self._probe_page_interactive(self._ready_generation)
        elapsed_ms = None
        if self._page_load_started_at is not None:
            elapsed_ms = (time.perf_counter() - self._page_load_started_at) * 1000
        if elapsed_ms is None:
            self.log_js_debug(
                f"load finished dispatch={self._js_dispatch_count} "
                f"callbacks={self._js_callback_count} structured={self._js_structured_count}"
            )
        else:
            self.log_js_debug(
                f"load finished elapsed_ms={elapsed_ms:.1f} "
                f"dispatch={self._js_dispatch_count} callbacks={self._js_callback_count} "
                f"structured={self._js_structured_count}"
            )
        elapsed_label = f"{elapsed_ms:.1f}" if elapsed_ms is not None else "n/a"
        self.log_web_perf(
            f"load finished elapsed_ms={elapsed_label} "
            f"top_hint={self._top_hint_count} frameless_updates={self._frameless_update_count}"
        )
        append_browser_debug_event(
            "browser.load_finished",
            ok=True,
            url=self._browser.view.url().toString(),
            elapsed_ms=float(elapsed_ms if elapsed_ms is not None else -1.0),
            dispatch=self._js_dispatch_count,
            callbacks=self._js_callback_count,
            structured=self._js_structured_count,
            page_ready=self._page_ready,
        )
        self._browser.pageLoadFinishedDetailed.emit(True, float(elapsed_ms if elapsed_ms is not None else -1.0))

    def _cancel_ready_probe(self) -> None:
        self._ready_generation += 1
        self._ready_probe_started_at = None
        self._ready_probe_attempts = 0

    def _schedule_ready_probe(self, generation: int, *, delay_ms: int) -> None:
        QTimer.singleShot(delay_ms, lambda generation=generation: self._probe_page_interactive(generation))

    def _probe_page_interactive(self, generation: int) -> None:
        if generation != self._ready_generation or self._page_ready:
            return
        page = self._browser.view.page()
        self._ready_probe_attempts += 1
        self._run_js_now(
            page, self._READY_PROBE_JS,
            lambda raw_result, generation=generation: self._handle_ready_probe_result(generation, raw_result),
        )

    def _handle_ready_probe_result(self, generation: int, raw_result) -> None:
        if generation != self._ready_generation or self._page_ready:
            return

        def decode_ready_probe_payload() -> dict:
            if not isinstance(raw_result, str) or not raw_result:
                return {}
            payload = json.loads(raw_result)
            if isinstance(payload, dict):
                return payload
            return {}

        def readiness_payload_is_ready(payload: dict) -> bool:
            if not isinstance(payload, dict) or not payload.get("domReady"):
                return False
            if not self._browser.window_mode.uses_page_scan:
                return True
            if not payload.get("hasPreviewRuntime") or not payload.get("hasPreviewCommandBus"):
                return False
            if self._browser.window_mode.ensure_result_kind == "preview_submit":
                return bool(payload.get("hasCollectPreviewSubmitPayload"))
            return bool(payload.get("hasScanChecked"))

        def retry_ready_probe(payload: dict) -> None:
            elapsed_ms = (time.perf_counter() - (self._ready_probe_started_at or time.perf_counter())) * 1000
            if elapsed_ms < self._READY_PROBE_TIMEOUT_MS:
                self._schedule_ready_probe(generation, delay_ms=self._READY_PROBE_INTERVAL_MS)
                return
            self.log_js_debug(f"page interactive probe timeout attempts={self._ready_probe_attempts} payload={payload!r}")

        payload = decode_ready_probe_payload()
        if readiness_payload_is_ready(payload):
            self._mark_page_ready(reason="dom-interactive")
            self._cancel_ready_probe()
            return
        retry_ready_probe(payload)

    @staticmethod
    def _run_js_now(page, js_code, callback=None):
        if callback is None:
            page.runJavaScript(js_code)
            return
        page.runJavaScript(js_code, lambda result: QTimer.singleShot(0, lambda result=result: callback(result)))

    def _run_page_js(self, page, js_code, callback=None, *, structured=False):
        target_page = page or self._browser.view.page()
        self._js_dispatch_count += 1
        if callback is not None:
            self._js_callback_count += 1
        if structured:
            self._js_structured_count += 1
        if QThread.currentThread() is target_page.thread():
            self._run_js_now(target_page, js_code, callback)
            return
        self.log_js_debug(
            f"queue runJavaScript from thread={type(QThread.currentThread()).__name__} "
            f"to page_thread={type(target_page.thread()).__name__}"
        )
        self._js_dispatcher.dispatch_requested.emit(target_page, js_code, callback)

    @staticmethod
    def _wrap_structured_js(js_body: str) -> str:
        return f"""(function(){{
let __cgsValue = null;
let __cgsKind = "undefined";
try {{
  __cgsValue = (function(){{
{js_body}
  }})();
  if (Array.isArray(__cgsValue)) {{
    __cgsKind = "array";
  }} else if (__cgsValue === null) {{
    __cgsKind = "null";
  }} else {{
    __cgsKind = typeof __cgsValue;
  }}
  return JSON.stringify({{
    ok: true,
    kind: __cgsKind,
    value: __cgsValue === undefined ? null : __cgsValue,
    error: ""
  }});
}} catch (__cgsError) {{
  const __cgsMessage = __cgsError && (__cgsError.stack || __cgsError.message)
    ? (__cgsError.stack || __cgsError.message)
    : String(__cgsError);
  return JSON.stringify({{
    ok: false,
    kind: "error",
    value: null,
    error: __cgsMessage
  }});
}}
}})();"""

    @staticmethod
    def _decode_structured_result(raw_result, description: str):
        if not isinstance(raw_result, str) or not raw_result:
            raise TypeError(f"{description} returned unexpected {type(raw_result).__name__}: {raw_result!r}")
        result = json.loads(raw_result)
        if not isinstance(result, dict):
            raise TypeError(f"{description} returned non-object envelope: {result!r}")
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or f"{description} failed without detail")
        return result.get("kind"), result.get("value")

    @staticmethod
    def _validate_structured_kind(kind: str, value, expected_kind, description: str):
        expected = (expected_kind,) if isinstance(expected_kind, str) else tuple(expected_kind)
        if kind not in expected:
            raise TypeError(f"{description} expected {expected}, got {kind!r}")
        if kind == "array" and not isinstance(value, list):
            raise TypeError(f"{description} expected list payload, got {type(value).__name__}")
        if kind == "string" and not isinstance(value, str):
            raise TypeError(f"{description} expected string payload, got {type(value).__name__}")
        if kind == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise TypeError(f"{description} expected numeric payload, got {type(value).__name__}")
        if kind == "boolean" and not isinstance(value, bool):
            raise TypeError(f"{description} expected boolean payload, got {type(value).__name__}")
        if kind == "object" and not isinstance(value, dict):
            raise TypeError(f"{description} expected object payload, got {type(value).__name__}")
        return value

    def _handle_structured_js_error(self, description: str, error: Exception, raw_result=None):
        # message = f"[browser.js] {description} failed: {error}; raw={raw_result!r}"
        self.gui.hook_exception(type(error), error, error.__traceback__)
        append_browser_debug_event(
            "browser.js_error",
            description=description,
            error=repr(error),
            raw_result=str(raw_result)[:400],
            current_url=self._browser.view.url().toString(),
        )
