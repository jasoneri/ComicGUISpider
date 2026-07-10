from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, TableWidget


QT_FONTS_CONFIGURED = False
TRAY_UI_FONT_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "Segoe UI")
TRAY_MONO_FONT_FAMILIES = ("Hack Nerd Font", "Hack", "Cascadia Mono", "Consolas")
TRAY_PANEL_BG = "#303030"
TRAY_PANEL_BG_ALT = "#363636"
TRAY_ROW_BG = "#34363a"
TRAY_BORDER = "#474747"
TRAY_TEXT = "#f1f5f9"
TRAY_MUTED = "#cbd5e1"
TRAY_COVER_BG = "#2b2b2b"
MCP_BG = "#202124"
MCP_PANEL_BG = "#2b2d31"
MCP_PANEL_BG_ALT = "#303236"
MCP_BORDER = "#474a50"
MCP_TEXT = "#f1f5f9"
MCP_MUTED = "#cbd5e1"
SCHEDULE_CARD_BG = TRAY_ROW_BG
SCHEDULE_CARD_BG_SEL = "#3b3e44"
SCHEDULE_ACCENT_INFO = "#60a5fa"
SCHEDULE_ACCENT_OK = "#34d399"
SCHEDULE_DOT_PENDING = "#52525b"
BEIJING_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
HTML_TAG_RE = re.compile(r"<[^>]+>")


class TrayUiContext:
    def __init__(self, *, token_provider: Callable[[], str], app_provider: Callable[[], QApplication | None]) -> None:
        self._token_provider = token_provider
        self._app_provider = app_provider

    def set_table_rows(self, table: TableWidget, rows: list[list[str]]) -> None:
        position = table.verticalScrollBar().value()
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(self.redact(str(value))))
        table.resizeRowsToContents()
        table.verticalScrollBar().setValue(position)

    def create_log_table(self, parent, headers: list[str]) -> TableWidget:
        table = TableWidget(parent)
        table.setBorderVisible(False)
        table.setBorderRadius(6)
        table.setFont(tray_mono_font(8))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setWordWrap(False)
        table.verticalHeader().setDefaultSectionSize(28)
        if len(headers) > 1:
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def redact(self, text: str) -> str:
        token = self._token_provider()
        if token:
            return text.replace(token, "<redacted>")
        return text

    def duration_label(self, elapsed_ms: float) -> str:
        value = float(elapsed_ms)
        if value >= 1000.0:
            return f"{value / 1000.0:.2f}s"
        return f"{value:.1f}ms"

    def compact_json(self, payload: dict) -> str:
        return self.redact(json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")))

    def copy_to_clipboard(self, value: str) -> None:
        app = self._app_provider()
        app.clipboard().setText(value)

    def short_time(self, value) -> str:
        dt = self.parse_datetime(value)
        if dt is not None:
            return dt.astimezone(BEIJING_TZ).strftime("%H:%M:%S")
        if not value:
            return "-"
        text = str(value)
        if "T" in text:
            text = text.split("T", 1)[1]
        text = text.replace("Z", "").split("+", 1)[0]
        return text.split(".", 1)[0]

    def beijing_datetime_label(self, value) -> str:
        dt = self.parse_datetime(value)
        if dt is None:
            return str(value or "-")
        return f"{dt.astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')} UTC+8"

    def parse_datetime(self, value) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def short_job_id(self, value) -> str:
        text = str(value or "-")
        return text[:8] if len(text) > 8 else text

    def set_label(self, label: QLabel | None, text: str) -> None:
        if label is not None:
            label.setText(self.redact(str(text)))

    def set_chip(self, label: QLabel | None, status: str) -> None:
        if label is None:
            return
        normalized = str(status or "-")
        label.setText(normalized)
        palette = {
            "ready": ("#064e3b", "#34d399", "#065f46"),
            "running": ("#172554", "#60a5fa", "#1d4ed8"),
            "starting": ("#422006", "#fbbf24", "#92400e"),
            "completed": ("#064e3b", "#34d399", "#065f46"),
            "failed": ("#450a0a", "#f87171", "#991b1b"),
            "error": ("#450a0a", "#f87171", "#991b1b"),
            "unavailable": ("#3f3f46", "#d4d4d8", "#52525b"),
            "foreground-blocked": ("#3f3f46", "#d4d4d8", "#52525b"),
            "idle": ("#1f2937", "#cbd5e1", "#334155"),
            "queued": ("#1f2937", "#cbd5e1", "#334155"),
        }
        background, color, border = palette.get(normalized, ("#1f2937", "#cbd5e1", "#334155"))
        label.setStyleSheet(
            f"background:{background};color:{color};border:1px solid {border};"
            "border-radius:4px;padding:2px 6px;font-size:11px;"
        )

    def coerce_int(self, value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def coerce_percent(self, value) -> int:
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, number))

    def strip_html(self, text: str) -> str:
        marker = "__CGS_REDACTED__"
        clean = HTML_TAG_RE.sub("", str(text).replace("<redacted>", marker))
        return html.unescape(clean).replace(marker, "<redacted>")


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                clear_layout(child)


class ClickableFrame(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._on_click = None

    def mousePressEvent(self, event) -> None:
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


class StageRail(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(0)

    def set_stages(self, stages: list[str], current: str, *, running: bool = False) -> None:
        clear_layout(self._layout)
        if not stages:
            return
        current_idx = stages.index(current) if current in stages else -1
        for index, stage in enumerate(stages):
            if index > 0:
                line = QFrame(self)
                line.setFixedHeight(1)
                line.setStyleSheet(f"background:{TRAY_BORDER};border:none;")
                self._layout.addWidget(line, 1)
            if current_idx < 0:
                state = "pending"
            elif index < current_idx:
                state = "done"
            elif index == current_idx:
                state = "active"
            else:
                state = "pending"
            self._layout.addWidget(self._step(stage, state, running), 0)

    def _step(self, label: str, state: str, running: bool) -> QWidget:
        column = QWidget(self)
        box = QVBoxLayout(column)
        box.setContentsMargins(4, 0, 4, 0)
        box.setSpacing(2)
        dot = QLabel(column)
        dot.setFixedSize(10, 10)
        if state == "done":
            dot.setStyleSheet(f"background:{SCHEDULE_ACCENT_OK};border:2px solid {SCHEDULE_ACCENT_OK};border-radius:5px;")
        elif state == "active":
            dot.setStyleSheet(f"background:{SCHEDULE_ACCENT_INFO};border:2px solid {SCHEDULE_ACCENT_INFO};border-radius:5px;")
        else:
            dot.setStyleSheet(f"background:{TRAY_PANEL_BG};border:2px solid {SCHEDULE_DOT_PENDING};border-radius:5px;")
        text = CaptionLabel(label, column)
        text_color = SCHEDULE_ACCENT_OK if state == "done" else SCHEDULE_ACCENT_INFO if state == "active" else TRAY_MUTED
        text.setStyleSheet(f"color:{text_color};font-size:9px;")
        box.addWidget(dot, 0, Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(text, 0, Qt.AlignmentFlag.AlignHCenter)
        return column


class CompactKeyValueTable(TableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CompactKeyValueTable")
        self.setBorderVisible(False)
        self.setBorderRadius(6)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Key", "Value", "Key", "Value"])
        self.verticalHeader().hide()
        self.horizontalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(28)

    def set_rows(self, rows: list[tuple[str, object]]) -> None:
        self.clearContents()
        self.setRowCount((len(rows) + 1) // 2)
        for index, (key, value) in enumerate(rows):
            row = index // 2
            column = 0 if index % 2 == 0 else 2
            self.setItem(row, column, QTableWidgetItem(str(key)))
            if isinstance(value, QWidget):
                self.setCellWidget(row, column + 1, value)
                self.setItem(row, column + 1, QTableWidgetItem(""))
            else:
                self.setItem(row, column + 1, QTableWidgetItem(str(value)))
        for index in range(len(rows), self.rowCount() * 2):
            row = index // 2
            column = 0 if index % 2 == 0 else 2
            self.setItem(row, column, QTableWidgetItem(""))
            self.setItem(row, column + 1, QTableWidgetItem(""))
        self.resizeRowsToContents()


class ServerManageDialog(QDialog):
    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


def configure_tray_qt_fonts(app: QApplication) -> None:
    global QT_FONTS_CONFIGURED
    if QT_FONTS_CONFIGURED:
        return
    ui_family = _first_available_font_family(TRAY_UI_FONT_FAMILIES)
    if ui_family:
        font = QFont(ui_family, 9)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        app.setFont(font)
    QT_FONTS_CONFIGURED = True


def tray_mono_font(point_size: int = 9) -> QFont:
    family = _first_available_font_family(TRAY_MONO_FONT_FAMILIES) or "Consolas"
    font = QFont(family, point_size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def _first_available_font_family(candidates: tuple[str, ...]) -> str:
    families = set(QFontDatabase.families())
    lowered = {family.lower(): family for family in families}
    for candidate in candidates:
        if candidate in families:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""
