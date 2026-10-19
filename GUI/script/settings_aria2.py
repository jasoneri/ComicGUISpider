"""Aria2 download-engine settings card for Script SettingInterface.

CGS005: Settings content only — do not touch ScriptWindow navigation lifecycle.
"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QCompleter, QHBoxLayout, QLineEdit, QWidget
from PySide6.QtCore import Qt
from qfluentwidgets import (
    FluentIcon as FIF,
    GroupHeaderCardWidget,
    LineEdit,
    TransparentToolButton,
)

from utils.script.aria2.lock import DEFAULT_RPC_HOST, DEFAULT_RPC_PORT, ensure_secret


class Aria2GroupCard(GroupHeaderCardWidget):
    """CGS-hosted aria2 engine preferences: download proxy + RPC endpoint display.

    Port selection is engine-internal (CGS020 IRON-1): the card shows the fixed
    rpc-uri read-only and MUST NOT expose a port editor.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setting_interface = parent
        self.setObjectName("Aria2GroupCard")
        self.setTitle("Aria2 下载引擎")
        self.setBorderRadius(8)

        self.proxy_edit = LineEdit(self)
        self.proxy_edit.setObjectName("DownloadProxyEdit")
        self.proxy_edit.setPlaceholderText("e.g. 127.0.0.1:7890")
        self.proxy_edit.setClearButtonEnabled(True)
        self.proxy_edit.setMinimumWidth(320)
        completer = QCompleter(["127.0.0.1:7890", "http://127.0.0.1:7890"])
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.proxy_edit.setCompleter(completer)

        self.rpc_edit = LineEdit(self)
        self.rpc_edit.setObjectName("RpcAddressEdit")
        self.rpc_edit.setReadOnly(True)
        self.rpc_edit.setMinimumWidth(320)
        self.rpc_copy_btn = TransparentToolButton(FIF.COPY, self)
        self.rpc_copy_btn.clicked.connect(self._copy_rpc_address)

        self.secret_edit = LineEdit(self)
        self.secret_edit.setObjectName("RpcSecretEdit")
        self.secret_edit.setReadOnly(True)
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_edit.setMinimumWidth(320)
        self.secret_view_btn = TransparentToolButton(FIF.VIEW, self)
        self.secret_view_btn.setCheckable(True)
        self.secret_view_btn.toggled.connect(self._toggle_secret_visible)
        self.secret_copy_btn = TransparentToolButton(FIF.COPY, self)
        self.secret_copy_btn.clicked.connect(self._copy_secret)

        rpc_row = self._build_row(self.rpc_edit, self.rpc_copy_btn)
        secret_row = self._build_row(self.secret_edit, self.secret_view_btn, self.secret_copy_btn)
        self.addGroup(FIF.VPN, "下载代理", "仅作用于 aria2 下载任务；HTTP(S) 代理", self.proxy_edit)
        self.addGroup(FIF.LINK, "RPC 地址", "可供外部（如 AriaNg）展示管理", rpc_row)
        self.addGroup(FIF.VIEW, "连接密钥", "外部管理连接时需要", secret_row)

        self._secret = ensure_secret()
        self.secret_edit.setText(self._secret)
        self.rpc_edit.setText(f"http://{DEFAULT_RPC_HOST}:{DEFAULT_RPC_PORT}/jsonrpc")

    def _build_row(self, *widgets: QWidget) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for widget in widgets:
            layout.addWidget(widget)
        return row

    def _toggle_secret_visible(self, visible: bool) -> None:
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def _copy_rpc_address(self) -> None:
        QGuiApplication.clipboard().setText(self.rpc_edit.text())

    def _copy_secret(self) -> None:
        QGuiApplication.clipboard().setText(self._secret)

    def get_proxy_text(self) -> str:
        return self.proxy_edit.text().strip()

    def set_proxy_text(self, text: object) -> None:
        self.proxy_edit.setText(str(text or ""))
