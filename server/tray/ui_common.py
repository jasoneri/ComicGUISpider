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
from qfluentwidgets import CaptionLabel, TableWidget, ToolTip, ToolTipFilter, ToolTipPosition

from server.tray.style import (
    chip_stylesheet,
    harden_tray_tooltip,
    stage_dot_stylesheet,
    stage_rail_line_stylesheet,
    stage_text_stylesheet,
)


QT_FONTS_CONFIGURED = False
TRAY_UI_FONT_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "Segoe UI")
TRAY_MONO_FONT_FAMILIES = ("Hack Nerd Font", "Hack", "Cascadia Mono", "Consolas")
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
        label.setObjectName("TrayStatusChip")
        label.setText(normalized)
        label.setStyleSheet(chip_stylesheet(normalized))

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
                line.setObjectName("TrayStageRailLine")
                line.setFixedHeight(1)
                line.setStyleSheet(stage_rail_line_stylesheet())
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
        if state == "done":
            dot.setObjectName("TrayStageDotDone")
        elif state == "active":
            dot.setObjectName("TrayStageDotActive")
        else:
            dot.setObjectName("TrayStageDotPending")
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(stage_dot_stylesheet(state))
        text = CaptionLabel(label, column)
        if state == "done":
            text.setObjectName("TrayStageTextDone")
        elif state == "active":
            text.setObjectName("TrayStageTextActive")
        else:
            text.setObjectName("TrayStageTextPending")
        text.setStyleSheet(stage_text_stylesheet(state))
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


class TrayFluentToolTipFilter(ToolTipFilter):
    """ToolTipFilter that does **not** parent the bubble under ManageDialog.

    qfluent default: ``ToolTip(..., parent=widget.window())``. That puts the
    tooltip in the dialog widget tree, so dialog ``setStyleSheet`` descendants
    (even accidental ones) paint ghost borders / wrong day-night colors on
    ToolTip QLabel/QFrame. Parent ``None`` keeps FluentStyleSheet.TOOL_TIP only.
    """

    def _createToolTip(self):
        parent_widget = self.parent()
        text = parent_widget.toolTip() if parent_widget is not None else ""
        # parent=None: avoid ManageDialog stylesheet tree. Collapse shadow shell
        # before first show — same Windows translucent-margin ghost as RoundMenu.
        tip = ToolTip(text, None)
        harden_tray_tooltip(tip)
        return tip


def install_tray_fluent_tooltip(
    widget: QWidget | None,
    text: str = "",
    *,
    show_delay_ms: int = 300,
    position: ToolTipPosition = ToolTipPosition.TOP,
) -> None:
    """Theme-aware tooltip for tray surfaces (Manage dialog + cards)."""
    if widget is None:
        return
    tip = str(text or "").strip()
    widget.setToolTip(tip)
    for event_filter in list(getattr(widget, "_cgs_fluent_tooltip_filters", []) or []):
        widget.removeEventFilter(event_filter)
    widget._cgs_fluent_tooltip_filters = []
    if not tip:
        return
    tooltip_filter = TrayFluentToolTipFilter(
        widget, showDelay=int(show_delay_ms), position=position
    )
    widget.installEventFilter(tooltip_filter)
    widget._cgs_fluent_tooltip_filters = [tooltip_filter]


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
