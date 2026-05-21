from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from qfluentwidgets import InfoBar, InfoBarPosition


class JsoneriServicesStatusBrowserController(QObject):
    suspect_started = Signal(str, str)

    def __init__(self, interface, api_client, *, window_factory=None):
        super().__init__(interface)
        self.interface = interface
        self.api_client = api_client
        self._window_factory = window_factory or self._create_browser_window
        self._window = None
        self._active_service = ""
        self._active_url = ""
        self._load_generation = 0
        self._load_url = ""
        self._generation = 0
        self._load_failures = 0
        self._suspect_reported = False
        self.api_client.route_received.connect(self._on_route_received)
        self.api_client.route_failed.connect(self._on_route_failed)
        self.api_client.suspect_reported.connect(self._on_suspect_reported)
        self.api_client.suspect_failed.connect(self._on_suspect_failed)

    def open_service(self, service_name: str) -> None:
        self._generation += 1
        self._active_service = str(service_name or "").strip()
        self._active_url = ""
        self._load_failures = 0
        self._suspect_reported = False
        self.api_client.fetch_route(self._active_service)

    def close_window(self) -> None:
        if self._window is not None:
            self._window.close()

    def _create_browser_window(self):
        from GUI.browser_window import BrowserWindow

        return BrowserWindow(self.interface.parent_window.gui, skip_env_mode=True, persistent_profile=False)

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
        self._active_url = str(url)
        self._load_failures = 0
        self._suspect_reported = False
        window = self._ensure_window()
        window._first_show = False
        self._load_window_url(window, self._generation, self._active_url)
        window.show()
        window.raise_()
        window.activateWindow()

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
        if ok or not self._active_load_failed():
            return
        generation = self._generation
        if self._load_failures < 2:
            self._load_failures += 1
            QTimer.singleShot(2000, lambda generation=generation: self._retry_load(generation))
            return
        self.suspect_started.emit(self._active_service, self._active_url)
        self._suspect_reported = True
        self.api_client.report_suspect(self._active_service, self._active_url)

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
