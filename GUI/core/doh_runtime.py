from __future__ import annotations

from loguru import logger
from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from utils.config.qc import cgs_cfg
from utils.network.extra import ensure_doh_dns_stub_started
from utils.network.doh import normalize_doh_url


class ScriptDoHStubRuntime:
    def __init__(self, window):
        self._window = window
        self._doh_url = ""
        self._pending_warning = False

    def ensure_from_config(self) -> bool:
        return self.ensure(cgs_cfg.get_doh_url())

    def ensure(self, doh_url: object) -> bool:
        raw_value = str(doh_url or "").strip()
        self._doh_url = normalize_doh_url(raw_value) if raw_value else ""
        if not self._doh_url:
            return False
        try:
            ensure_doh_dns_stub_started(self._doh_url)
        except Exception:
            self._log_failure()
            self._show_or_queue_warning()
            return False
        self._pending_warning = False
        return True

    def flush_warning(self) -> None:
        if not self._pending_warning:
            return
        self._pending_warning = False
        self._show_warning()

    def _show_or_queue_warning(self) -> None:
        if self._window.isVisible():
            self._show_warning()
            return
        self._pending_warning = True

    def _show_warning(self) -> None:
        InfoBar.warning(
            title="",
            content="已配置 DoH，但本地 DNS stub 启动失败，本次脚本窗口的相关 DoH 功能可能不可用。",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM,
            duration=8000,
            parent=self._window,
        )

    def _log_failure(self) -> None:
        gui_logger = getattr(getattr(self._window, "gui", None), "log", None)
        if gui_logger is not None:
            gui_logger.exception("[ScriptWindow] DoH DNS stub startup failed")
            return
        logger.exception("[ScriptWindow] DoH DNS stub startup failed")
