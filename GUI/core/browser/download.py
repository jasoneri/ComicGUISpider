from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import InfoBar, InfoBarPosition


class BrowserDownloadController(QObject):
    """Qt WebEngine download owner: save dialog + accept().

    Default path MUST NOT use conf.sv_path (comic crawl root). Station/browser
    file saves belong in the OS/profile download location only.
    """

    def __init__(self, window, profile):
        super().__init__(window)
        self._window = window
        self._profile = profile
        self._active_downloads: set[QWebEngineDownloadRequest] = set()
        self._connected = True
        self._profile.downloadRequested.connect(self._on_download_requested)

    def shutdown(self) -> None:
        if self._connected:
            self._profile.downloadRequested.disconnect(self._on_download_requested)
            self._connected = False
        for download_item in list(self._active_downloads):
            self._forget_download(download_item)

    def _on_download_requested(self, download_item: QWebEngineDownloadRequest) -> None:
        suggested_name = str(download_item.suggestedFileName() or "").strip() or "download"
        default_path = self._default_directory().joinpath(suggested_name)
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._window,
            "选择保存位置",
            str(default_path),
        )
        if not selected_path:
            download_item.cancel()
            return

        save_path = Path(selected_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        download_item.setDownloadDirectory(str(save_path.parent))
        download_item.setDownloadFileName(save_path.name)
        self._track_download(download_item)
        download_item.accept()
        self._show_info(
            InfoBar.success,
            f"开始下载: {save_path.name}",
            duration=2500,
        )

    def _track_download(self, download_item: QWebEngineDownloadRequest) -> None:
        self._active_downloads.add(download_item)
        # stateChanged 会带上 DownloadState 参数；lambda 第一个形参若写成 item=
        # 会被该枚举覆盖，变成 'DownloadState' object has no attribute 'state'。
        download_item.stateChanged.connect(
            lambda _state, item=download_item: self._on_download_state_changed(item),
        )
        download_item.isFinishedChanged.connect(
            lambda item=download_item: self._on_download_finished_changed(item),
        )

    def _on_download_state_changed(self, download_item: QWebEngineDownloadRequest) -> None:
        if download_item is None:
            return
        state = download_item.state()
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self._show_info(
                InfoBar.success,
                f"下载完成: {self._resolved_path(download_item)}",
                duration=4500,
            )
            self._forget_download(download_item)
            return
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self._forget_download(download_item)
            return
        if state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            reason = str(download_item.interruptReasonString() or "").strip() or "未知原因"
            self._show_info(
                InfoBar.error,
                f"下载中断: {reason}",
                duration=6000,
            )
            self._forget_download(download_item)

    def _on_download_finished_changed(self, download_item: QWebEngineDownloadRequest) -> None:
        if download_item is None or not isinstance(download_item, QWebEngineDownloadRequest):
            return
        if not download_item.isFinished():
            return
        if download_item not in self._active_downloads:
            return
        # Some Qt builds finish without re-emitting the terminal state we care about.
        self._on_download_state_changed(download_item)

    def _forget_download(self, download_item: QWebEngineDownloadRequest) -> None:
        self._active_downloads.discard(download_item)

    def _default_directory(self) -> Path:
        # Never default under conf.sv_path — that tree is the comic crawl/library root.
        profile_download_path = str(self._profile.downloadPath() or "").strip()
        if profile_download_path:
            return Path(profile_download_path)
        return Path.home().joinpath("Downloads")

    @staticmethod
    def _resolved_path(download_item: QWebEngineDownloadRequest) -> str:
        directory = str(download_item.downloadDirectory() or "").strip()
        file_name = str(download_item.downloadFileName() or "").strip()
        if directory and file_name:
            return str(Path(directory).joinpath(file_name))
        return file_name or directory or "unknown"

    def _show_info(self, factory, content: str, *, duration: int) -> None:
        parent = getattr(self._window, "view", None) or self._window
        factory(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=parent,
        )
