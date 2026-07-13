from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from qfluentwidgets import InfoBar, InfoBarPosition

from .preview_cache import CAPTURE_SETTLE_MS, JsoneriPreviewCache, normalize_route_url


class JsoneriServicesStatusBrowserController(QObject):
    suspect_started = Signal(str, str)
    preview_captured = Signal(str, str)

    def __init__(self, interface, api_client, *, window_factory=None, preview_cache: JsoneriPreviewCache | None = None):
        super().__init__(interface)
        self.interface = interface
        self.api_client = api_client
        self.preview_cache = preview_cache or JsoneriPreviewCache()
        self._window_factory = window_factory or self._create_browser_window
        self._window = None
        self._active_service = ""
        self._active_url = ""
        self._load_generation = 0
        self._load_url = ""
        self._generation = 0
        self._load_failures = 0
        self._suspect_reported = False
        self._capture_generation = 0
        self.api_client.route_received.connect(self._on_route_received)
        self.api_client.route_failed.connect(self._on_route_failed)
        self.api_client.suspect_reported.connect(self._on_suspect_reported)
        self.api_client.suspect_failed.connect(self._on_suspect_failed)

    def open_service(self, service_name: str, *, url: str | None = None) -> None:
        self._generation += 1
        self._active_service = str(service_name or "").strip()
        self._active_url = ""
        self._load_failures = 0
        self._suspect_reported = False
        known_url = str(url or "").strip()
        if known_url:
            self._open_known_url(self._active_service, known_url)
            return
        self.api_client.fetch_route(self._active_service)

    def close_window(self) -> None:
        if self._window is not None:
            self._window.close()

    def _create_browser_window(self):
        from GUI.browser_window import BrowserWindow

        gui = self._resolve_gui_host()
        # Must use persistent profile: OTR QWebEngineProfile (persistent_profile=False)
        # keeps localStorage/cookies in RAM only — station SPAs (theme, album history) break.
        # Named profile + setPersistentStoragePath is created by create_browser_window_profile(persistent=True).
        window = BrowserWindow(gui, skip_env_mode=True, persistent_profile=True)
        self._configure_station_browser_chrome(window)
        self._sync_browser_geometry_from_script_window(window)
        return window

    def _resolve_gui_host(self):
        parent_window = self._script_window()
        gui = getattr(parent_window, "gui", None)
        if gui is None:
            raise RuntimeError("jsoneriPalacesProbe browser requires ScriptWindow.parent_window.gui.")
        if not callable(getattr(gui, "next", None)):
            # BrowserWindowModeController binds ensure to gui.next; script stations have no crawl next.
            gui.next = lambda *args, **kwargs: None
        return gui

    def _script_window(self):
        parent_window = getattr(self.interface, "parent_window", None)
        if parent_window is None:
            raise RuntimeError("jsoneriPalacesProbe browser requires ScriptWindow as interface.parent_window.")
        return parent_window

    def _configure_station_browser_chrome(self, window) -> None:
        # Station open is not a crawl/preview handoff; hide main-GUI ensure/copy chrome.
        window.ensureBtn.hide()
        window.copyBtn.hide()

    def _sync_browser_geometry_from_script_window(self, window) -> None:
        # Match ScriptWindow position+size via the same QWidget.geometry()/setGeometry pair.
        # Ui_browser min 1040x417 / max-width 1375 would clamp setGeometry; relax for station use.
        script_window = self._script_window()
        target_geometry = script_window.geometry()
        window.setMinimumSize(0, 0)
        window.setMaximumSize(16777215, 16777215)
        window.setGeometry(target_geometry)

    def _open_known_url(self, service_name: str, url: str) -> None:
        self._active_service = service_name
        self._active_url = url
        self._load_failures = 0
        self._suspect_reported = False
        window = self._ensure_window()
        window._first_show = False
        self._configure_station_browser_chrome(window)
        self._sync_browser_geometry_from_script_window(window)
        self._load_window_url(window, self._generation, self._active_url)
        window.show()
        window.raise_()
        window.activateWindow()

    def _ensure_window(self):
        if self._window is None:
            self._window = self._window_factory()
            self._window.destroyed.connect(self._on_window_destroyed)
            self._window.pageLoadFinishedDetailed.connect(self._on_page_load_finished)
        return self._window

    def _on_route_received(self, service_name: str, url: object) -> None:
        if service_name != self._active_service:
            return
        if not url:
            InfoBar.warning(
                title="", content=f"{service_name} 暂无可用实例",
                orient=self.interface.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=3500, parent=self.interface,
            )
            return
        self._open_known_url(service_name, str(url))

    def _load_window_url(self, window, generation: int, url: str) -> None:
        self._load_generation = generation
        self._load_url = url
        window.home_url = QUrl(url)
        window.load_home()

    def _on_route_failed(self, service_name: str, message: str) -> None:
        if service_name != self._active_service:
            return
        InfoBar.error(
            title="", content=f"服务路由失败: {message}",
            orient=self.interface.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=5000, parent=self.interface,
        )

    def _on_page_load_finished(self, ok: bool, _elapsed_ms: float) -> None:
        if ok:
            self._schedule_preview_capture()
            return
        if not self._active_load_failed():
            return
        generation = self._generation
        if self._load_failures < 2:
            self._load_failures += 1
            QTimer.singleShot(2000, lambda generation=generation: self._retry_load(generation))
            return
        self.suspect_started.emit(self._active_service, self._active_url)
        self._suspect_reported = True
        self.api_client.report_suspect(self._active_service, self._active_url)

    def _schedule_preview_capture(self) -> None:
        if not self._active_service or not self._active_url:
            return
        if self._load_generation != self._generation or self._load_url != self._active_url:
            return
        self._capture_generation += 1
        capture_generation = self._capture_generation
        service_name = self._active_service
        route_url = self._active_url
        QTimer.singleShot(
            CAPTURE_SETTLE_MS,
            lambda: self._capture_preview(capture_generation, service_name, route_url),
        )

    def _capture_preview(self, capture_generation: int, service_name: str, route_url: str) -> None:
        if capture_generation != self._capture_generation:
            return
        if service_name != self._active_service or route_url != self._active_url:
            return
        if self._window is None:
            return
        view = getattr(self._window, "view", None)
        if view is None:
            return
        current_url = normalize_route_url(view.url().toString())
        expected_url = normalize_route_url(route_url)
        if not expected_url or not current_url:
            return
        if current_url != expected_url and not current_url.startswith(expected_url) and not expected_url.startswith(current_url):
            return
        pixmap = view.grab()
        if not self.preview_cache.save_pixmap(service_name, route_url, pixmap):
            return
        self.preview_captured.emit(service_name, route_url)

    def _retry_load(self, generation: int) -> None:
        if generation != self._generation or self._window is None or not self._active_url:
            return
        self._load_generation = generation
        self._load_url = self._active_url
        self._window.view.load(QUrl(self._active_url))

    def _active_load_failed(self) -> bool:
        if not self._active_service or not self._active_url or self._suspect_reported:
            return False
        if self._load_generation != self._generation or self._load_url != self._active_url:
            return False
        if self._window is None:
            return False
        return self._window.view.url().toString() == self._active_url

    def _on_suspect_reported(self, service_name: str, url: str) -> None:
        InfoBar.warning(
            title="", content=f"已上报可疑实例: {service_name}",
            orient=self.interface.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=3500, parent=self.interface,
        )

    def _on_suspect_failed(self, service_name: str, url: str, message: str) -> None:
        InfoBar.error(
            title="", content=f"可疑实例上报失败: {message}",
            orient=self.interface.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=5000, parent=self.interface,
        )

    def _on_window_destroyed(self, *_args) -> None:
        self._window = None
        self._active_url = ""
        self._load_generation = 0
        self._load_url = ""
        self._load_failures = 0
        self._suspect_reported = False
