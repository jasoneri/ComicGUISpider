from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit, PrimaryPushButton, ScrollArea, StrongBodyLabel, ToolButton

from utils.script import conf as script_conf

from .browser import JsoneriServicesStatusBrowserController
from .card import JsoneriServicesStatusCard
from .client import JsoneriServicesStatusApiClient
from .models import normalize_api_base_url


class JsoneriServicesStatusInterface(QFrame):
    info_bar_orient = Qt.Horizontal

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("JsoneriServicesStatusInterface")
        self.cards: dict[str, JsoneriServicesStatusCard] = {}
        self.client = JsoneriServicesStatusApiClient(parent=self)
        self.browser_controller = JsoneriServicesStatusBrowserController(self, self.client)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(30_000)
        self.poll_timer.timeout.connect(self.refresh_status)
        self._setup_ui()
        self._connect_client()
        self.refresh_config(fetch=False)

    def refresh_config(self, *, fetch: bool = True) -> None:
        config = script_conf.jsoneri_server_status or {}
        url = str(config.get("url") or "")
        token = str(config.get("token") or "")
        self.url_edit.setText(url)
        self.token_edit.setText(token)
        self.client.configure(base_url=url, token=token)
        if self.client.is_configured:
            self._set_header("Ready", "#9ca3af")
            if self.isVisible() and not self.poll_timer.isActive():
                self.poll_timer.start()
            if fetch:
                self.refresh_status()
            return
        self.poll_timer.stop()
        self._set_header("Not configured", "#9ca3af")
        self._set_empty_text("Configure Jsoneri Server Status URL above.")

    def save_config(self) -> None:
        try:
            url = normalize_api_base_url(self.url_edit.text())
        except ValueError as error:
            InfoBar.error(
                title="", content=str(error),
                orient=self.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=3500, parent=self,
            )
            return
        token = self.token_edit.text().strip()
        script_conf.update(jsoneri_server_status={"url": url, "token": token})
        self.refresh_config(fetch=bool(url))
        InfoBar.success(
            title="", content="Jsoneri Server Status saved",
            orient=self.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=2500, parent=self,
        )

    def refresh_status(self) -> None:
        if not self.client.is_configured:
            self.refresh_config(fetch=False)
            return
        self._set_header("Checking", "#f59e0b")
        self.client.fetch_status()

    def close_service_window(self) -> None:
        self.browser_controller.close_window()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.client.is_configured:
            self.refresh_status()
            self.poll_timer.start()

    def hideEvent(self, event) -> None:
        self.poll_timer.stop()
        super().hideEvent(event)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(12)

        header = QFrame(self)
        header.setObjectName("JsoneriServicesStatusHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)
        self.title_label = StrongBodyLabel("Jsoneri Server Status", header)
        self.connection_dot = QLabel(header)
        self.connection_dot.setFixedSize(10, 10)
        self.connection_label = QLabel("", header)
        self.refresh_button = ToolButton(FIF.SYNC, header)
        self.refresh_button.setFixedSize(34, 34)
        self.refresh_button.clicked.connect(self.refresh_status)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.connection_dot)
        header_layout.addWidget(self.connection_label)
        header_layout.addWidget(self.refresh_button)
        root.addWidget(header)

        config_panel = QFrame(self)
        config_panel.setObjectName("JsoneriServicesStatusConfig")
        config_layout = QHBoxLayout(config_panel)
        config_layout.setContentsMargins(14, 10, 14, 10)
        config_layout.setSpacing(10)
        self.url_edit = LineEdit(config_panel)
        self.url_edit.setPlaceholderText("https://status.example.com")
        self.url_edit.setClearButtonEnabled(True)
        self.token_edit = LineEdit(config_panel)
        self.token_edit.setPlaceholderText("suspect token")
        self.token_edit.setClearButtonEnabled(True)
        self.save_button = PrimaryPushButton(FIF.SAVE, "Save", config_panel)
        self.save_button.clicked.connect(self.save_config)
        config_layout.addWidget(QLabel("API URL", config_panel))
        config_layout.addWidget(self.url_edit, 1)
        config_layout.addWidget(QLabel("Token", config_panel))
        config_layout.addWidget(self.token_edit, 1)
        config_layout.addWidget(self.save_button)
        root.addWidget(config_panel)

        self.stack = QStackedWidget(self)
        self.empty_page = QWidget(self.stack)
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.addStretch(1)
        self.empty_label = StrongBodyLabel("", self.empty_page)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_label, 0, Qt.AlignCenter)
        empty_layout.addStretch(1)

        self.scroll_area = ScrollArea(self.stack)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)

        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.scroll_area)
        root.addWidget(self.stack, 1)
        self.setStyleSheet(
            """
            QFrame#JsoneriServicesStatusHeader, QFrame#JsoneriServicesStatusConfig {
                border: 1px solid rgba(125, 125, 125, 0.22);
                border-radius: 8px;
                background: rgba(125, 125, 125, 0.06);
            }
            """
        )

    def _connect_client(self) -> None:
        self.client.status_received.connect(self._on_status_received)
        self.client.status_unreachable.connect(self._on_status_unreachable)

    def _on_status_received(self, snapshot) -> None:
        self._set_header("Connected", "#10b981")
        if not snapshot.services:
            self._clear_cards()
            self._set_empty_text("No services reported.")
            return
        active_names = set()
        for entry in snapshot.services:
            active_names.add(entry.name)
            card = self.cards.get(entry.name)
            if card is None:
                card = JsoneriServicesStatusCard(entry, self.scroll_content)
                card.open_requested.connect(self.browser_controller.open_service)
                self.cards[entry.name] = card
                self.cards_layout.insertWidget(max(0, self.cards_layout.count() - 1), card)
            else:
                card.update_entry(entry)
        for stale_name in set(self.cards) - active_names:
            card = self.cards.pop(stale_name)
            card.setParent(None)
            card.deleteLater()
        self.stack.setCurrentWidget(self.scroll_area)

    def _on_status_unreachable(self, message: str) -> None:
        self._set_header("Disconnected", "#ef4444")
        if not self.cards:
            self._set_empty_text("Jsoneri Server Status API is unreachable.")
        InfoBar.warning(
            title="", content=message,
            orient=self.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=3500, parent=self,
        )

    def _set_header(self, text: str, color: str) -> None:
        self.connection_label.setText(text)
        self.connection_dot.setStyleSheet(f"border-radius: 5px; background: {color};")

    def _set_empty_text(self, text: str) -> None:
        self.empty_label.setText(text)
        self.stack.setCurrentWidget(self.empty_page)

    def _clear_cards(self) -> None:
        while self.cards:
            _name, card = self.cards.popitem()
            card.setParent(None)
            card.deleteLater()
