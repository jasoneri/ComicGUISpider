from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout
from qfluentwidgets import FluentIcon as FIF, PrimaryToolButton, StrongBodyLabel

from .models import ServiceStatus, ServiceStatusEntry


_STATUS_COLORS = {
    ServiceStatus.ONLINE: "#10b981",
    ServiceStatus.OFFLINE: "#ef4444",
    ServiceStatus.UNKNOWN: "#9ca3af",
    ServiceStatus.CHECKING: "#f59e0b",
}


class JsoneriServicesStatusCard(QFrame):
    open_requested = Signal(str)

    def __init__(self, entry: ServiceStatusEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("JsoneriServicesStatusCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._setup_ui()
        self.update_entry(entry)

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("JsoneriServicesStatusCardIcon")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(38, 38)
        root.addWidget(self.icon_label, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.title_label = StrongBodyLabel("", self)
        self.status_dot = QLabel(self)
        self.status_dot.setObjectName("JsoneriServicesStatusCardDot")
        self.status_dot.setFixedSize(10, 10)
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.status_dot, 0, Qt.AlignVCenter)
        title_row.addStretch(1)
        self.description_label = QLabel(self)
        self.description_label.setObjectName("JsoneriServicesStatusCardDescription")
        self.description_label.setWordWrap(True)
        self.meta_label = QLabel(self)
        self.meta_label.setObjectName("JsoneriServicesStatusCardMeta")
        text_layout.addLayout(title_row)
        text_layout.addWidget(self.description_label)
        text_layout.addWidget(self.meta_label)
        root.addLayout(text_layout, 1)

        self.open_button = PrimaryToolButton(FIF.RIGHT_ARROW, self)
        self.open_button.setFixedSize(38, 38)
        self.open_button.clicked.connect(lambda: self.open_requested.emit(self.entry.name))
        root.addWidget(self.open_button, 0, Qt.AlignVCenter)

    def update_entry(self, entry: ServiceStatusEntry) -> None:
        self.entry = entry
        display_label = entry.label or entry.name
        self.icon_label.setText((display_label[:1] or "?").upper())
        self.title_label.setText(display_label)
        self.description_label.setText(entry.description or "No description")
        self.meta_label.setText(f"{entry.online_count}/{entry.total_count} online")
        self.open_button.setEnabled(entry.can_open)
        color = _STATUS_COLORS[entry.status]
        self.setStyleSheet(
            f"""
            QFrame#JsoneriServicesStatusCard {{
                border: 1px solid rgba(125, 125, 125, 0.22);
                border-radius: 8px;
                background: rgba(125, 125, 125, 0.06);
            }}
            QLabel#JsoneriServicesStatusCardIcon {{
                border-radius: 19px;
                color: white;
                background: {color};
                font-weight: 700;
            }}
            QLabel#JsoneriServicesStatusCardDot {{
                border-radius: 5px;
                background: {color};
            }}
            QLabel#JsoneriServicesStatusCardDescription {{
                color: rgba(125, 125, 125, 0.92);
            }}
            QLabel#JsoneriServicesStatusCardMeta {{
                color: rgba(125, 125, 125, 0.72);
                font-size: 11px;
            }}
            """
        )
