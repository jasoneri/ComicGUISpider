"""Aria2 download-engine settings card for Script SettingInterface.

CGS005: Settings content only — do not touch ScriptWindow navigation lifecycle.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCompleter
from PySide6.QtCore import Qt
from qfluentwidgets import (
    FluentIcon as FIF,
    GroupHeaderCardWidget,
    LineEdit,
)


class Aria2GroupCard(GroupHeaderCardWidget):
    """CGS-hosted aria2 engine preferences (download proxy now; extend here later)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setting_interface = parent
        self.setObjectName("Aria2GroupCard")
        self.setTitle("Aria2 下载引擎")
        self.setBorderRadius(8)

        self.proxy_edit = LineEdit(self)
        self.proxy_edit.setObjectName("DownloadProxyEdit")
        self.proxy_edit.setPlaceholderText("127.0.0.1:10809（空=直连）")
        self.proxy_edit.setToolTip(
            "下载引擎代理（aria2 all-proxy）；与顶部 httpx「代理/Proxy」分列；空=直连"
        )
        self.proxy_edit.setClearButtonEnabled(True)
        self.proxy_edit.setMinimumWidth(320)
        completer = QCompleter(["127.0.0.1:10809", "http://127.0.0.1:10809"])
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.proxy_edit.setCompleter(completer)

        self.addGroup(
            FIF.VPN,
            "下载代理",
            "仅作用于 aria2 下载任务；HTTP(S) 代理。不支持 SOCKS5 直连",
            self.proxy_edit,
        )

    def get_proxy_text(self) -> str:
        return self.proxy_edit.text().strip()

    def set_proxy_text(self, text: object) -> None:
        self.proxy_edit.setText(str(text or ""))
