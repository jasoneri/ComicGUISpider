from __future__ import annotations

import gc
import json
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon as FIF,
    LineEdit,
    MessageBox,
    PasswordLineEdit,
    StrongBodyLabel,
    SwitchButton,
    TableWidget,
    TextEdit,
    TransparentToolButton,
)

from server.tray.style import chip_stylesheet, mcp_heading_stylesheet, mcp_muted_label_stylesheet
from server.tray.ui_common import install_tray_fluent_tooltip, tray_mono_font
from utils.server_control import DEFAULT_SERVER_MCP_PATH, server_launch_log_path
from GUI.uic.qfluent.components.icons import CgsIcon

if TYPE_CHECKING:
    from server.tray.host import ServerTrayHost


MCP_TOOL_NAMES = (
    "cgs_health",
    "cgs_list_sites",
    "cgs_search_books",
    "cgs_list_book_episodes",
    "cgs_submit_books",
    "cgs_get_status",
    "cgs_get_events",
    "cgs_reset_work_state",
)
MCP_RESOURCE_NAMES = ("cgs://health", "cgs://sites", "cgs://status", "cgs://events")
MCP_TOOL_TAGS = {
    "cgs_health": "read",
    "cgs_list_sites": "read",
    "cgs_search_books": "session",
    "cgs_list_book_episodes": "session",
    "cgs_submit_books": "starts job",
    "cgs_get_status": "read",
    "cgs_get_events": "read",
    "cgs_reset_work_state": "clear",
}
MCP_LOG_LIMIT = 80


class McpPanel:
    def __init__(self, host: "ServerTrayHost") -> None:
        self.host = host
        self.debug_switch: SwitchButton | None = None
        self.debug_enabled = False
        self.debug_drawer: QFrame | None = None
        self.debug_text: TextEdit | None = None
        self.state_chip: QLabel | None = None
        self.state_status_label: QLabel | None = None
        self.state_reason_label: QLabel | None = None
        self.transport_http_label: QLabel | None = None
        self.transport_stdio_label: QLabel | None = None
        self.recent_fail_label: QLabel | None = None
        self.recent_slowest_label: QLabel | None = None
        self.recent_median_label: QLabel | None = None
        self.tools_table: TableWidget | None = None
        self.capability_name_line: LineEdit | None = None
        self.capability_copy_button: TransparentToolButton | None = None
        self.auth_line: PasswordLineEdit | None = None
        self.auth_copy_button: TransparentToolButton | None = None
        self.log_table: TableWidget | None = None
        self.log_detail: TextEdit | None = None
        self.rendered_log_keys: list[tuple[object, ...]] = []
        self.rendered_log_entries: list[dict] = []
        self.call_log = None

    def set_call_log(self, call_log) -> None:
        self.call_log = call_log

    def build_tab(self, parent) -> QWidget:
        tab = QWidget(parent)
        tab.setObjectName("McpMonitorTab")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_action_bar(tab))
        layout.addLayout(self._build_status_band(tab))

        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(8)
        split.addWidget(self._build_capability_panel(tab), 1)
        split.addWidget(self._build_call_stream_panel(tab), 3)
        split.addWidget(self._build_detail_panel(tab), 2)
        layout.addLayout(split, 1)

        layout.addWidget(self._build_debug_drawer(tab))
        return tab

    def refresh(self, *, rebuild_lists: bool = False) -> None:
        self.refresh_capability_table()
        self.refresh_monitor()
        self.sync_log_table(rebuild=rebuild_lists)

    def on_surface_restarted(self) -> None:
        self.call_log = None
        self.rendered_log_keys.clear()
        self.rendered_log_entries.clear()
        if self.log_table is not None:
            self.log_table.setRowCount(0)
        if self.log_detail is not None:
            self.log_detail.setPlainText("MCP surface restarted; waiting for new calls.")
        if self.debug_text is not None:
            self.debug_text.clear()
        if self.auth_line is not None:
            self.auth_line.setText(self.host.record.token)

    def status_label(self) -> str:
        projected_state = self.host.projected_state()
        if projected_state == "starting":
            return "MCP: starting"
        if projected_state == "foreground-blocked":
            return f"MCP: blocked ({self.unavailable_reason()})"
        if projected_state == "error":
            return f"MCP: unavailable ({self.unavailable_reason()})"
        return "MCP: ready"

    def unavailable_reason(self) -> str:
        host = self.host
        projected_state = host.projected_state()
        if projected_state == "starting":
            return "Server starting"
        if projected_state == "foreground-blocked":
            status = host.runtime_status_payload()
            return host.ui.strip_html(str(status.get("reason") or "CGS GUI foreground owns runtime"))
        if projected_state == "error":
            last_error = host.server_panel.diagnostics.last_error_summary()
            if last_error:
                return host.ui.strip_html(last_error)
            if host.error_detail:
                return host.last_error_line()
            return "Server error"
        return "Ready"

    def sync_log_table(self, *, rebuild: bool = False) -> None:
        entries = self._call_entries()
        keys = [self._log_key(entry) for entry in entries]
        table = self.log_table
        if table is None:
            return
        scrollbar = table.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
        if rebuild or len(self.rendered_log_keys) > len(keys):
            table.setRowCount(0)
            self.rendered_log_keys = []
            self.rendered_log_entries = []
        overlap = self._log_overlap(keys)
        stale_count = len(self.rendered_log_keys) - overlap
        for _ in range(stale_count):
            table.removeRow(0)
        self.rendered_log_entries = self.rendered_log_entries[-overlap:] if overlap else []
        for entry in entries[overlap:]:
            self._append_log_row(entry)
            self.rendered_log_entries.append(dict(entry))
        self.rendered_log_keys = keys
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def refresh_capability_table(self) -> None:
        if self.tools_table is None:
            return
        rows = self._capability_rows()
        self.host.ui.set_table_rows(self.tools_table, rows)
        for row, values in enumerate(rows):
            name = values[0]
            for column in range(self.tools_table.columnCount()):
                item = self.tools_table.item(row, column)
                if item is not None:
                    # QTableWidgetItem tooltip is native Qt; full name is also on the line edit.
                    item.setToolTip(name)
        if rows and self.capability_name_line is not None and not self.capability_name_line.text():
            self._set_capability_name(rows[0][0])
            self.tools_table.selectRow(0)

    def refresh_monitor(self) -> None:
        host = self.host
        entries = self._call_entries()
        projected_state = host.projected_state()
        panel_state = self._projected_panel_state(projected_state)
        self._set_state_chip(panel_state)
        host.ui.set_label(self.state_status_label, f"Status: {projected_state}")
        host.ui.set_label(self.state_reason_label, f"Reason: {self.unavailable_reason()}")
        host.ui.set_label(self.transport_http_label, f"HTTP: {host.record.connect_url}{DEFAULT_SERVER_MCP_PATH}")
        host.ui.set_label(self.transport_stdio_label, "stdio: cgs-mcp")
        stats = self._recent_stats(entries)
        host.ui.set_label(self.recent_fail_label, f"Fails: {stats['failures']}")
        host.ui.set_label(self.recent_slowest_label, f"Slowest: {stats['slowest']}")
        host.ui.set_label(self.recent_median_label, f"Median: {stats['median']}")
        if self.debug_drawer is not None:
            self.debug_drawer.setVisible(self.debug_enabled)
        if self.debug_text is not None:
            self.debug_text.setPlainText("\n".join(self._debug_lines(entries)))

    def _build_action_bar(self, parent) -> QWidget:
        band = QWidget(parent)
        band.setObjectName("McpActionBar")
        layout = QHBoxLayout(band)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch(1)
        debug_label = CaptionLabel("Debug", band)
        self.debug_switch = SwitchButton(band)
        self.debug_switch.setObjectName("McpDebugSwitch")
        self.debug_switch.setOnText("")
        self.debug_switch.setOffText("")
        self.debug_switch.checkedChanged.connect(self._set_debug_enabled)
        clear_button = TransparentToolButton(FIF.BROOM, band)
        clear_button.setObjectName("McpCallLogClearButton")
        clear_button.clicked.connect(lambda _checked=False: self._clear_call_log())
        restart_button = TransparentToolButton(CgsIcon.REBOOT, band)
        install_tray_fluent_tooltip(restart_button, "重启")
        restart_button.clicked.connect(lambda _checked=False: self.host.restart_server_surface())
        layout.addWidget(debug_label)
        layout.addWidget(self.debug_switch)
        layout.addWidget(clear_button)
        layout.addWidget(restart_button)
        return band

    def _build_status_band(self, parent) -> QHBoxLayout:
        band = QHBoxLayout()
        band.setContentsMargins(0, 0, 0, 0)
        band.setSpacing(8)
        state_card = self._status_card(parent, "MCP State")
        state_layout = state_card.layout()
        self.state_chip = CaptionLabel("Starting", state_card)
        self._set_state_chip("starting")
        state_layout.addWidget(self.state_chip)
        self.state_status_label = CaptionLabel("Status: starting", state_card)
        self.state_reason_label = CaptionLabel("Reason: starting", state_card)
        for label in (self.state_status_label, self.state_reason_label):
            label.setObjectName("McpMutedLabel")
            label.setFont(tray_mono_font(8))
            label.setStyleSheet(mcp_muted_label_stylesheet())
            state_layout.addWidget(label)

        transport_card = self._status_card(parent, "Transport")
        transport_layout = transport_card.layout()
        http_url = f"{self.host.record.connect_url}{DEFAULT_SERVER_MCP_PATH}"
        http_row, self.transport_http_label = self._transport_row(transport_card, "HTTP", http_url, http_url)
        stdio_row, self.transport_stdio_label = self._transport_row(transport_card, "stdio", "cgs-mcp", "cgs-mcp")
        transport_layout.addWidget(http_row)
        transport_layout.addWidget(stdio_row)

        auth_card = self._status_card(parent, "Auth")
        auth_card.layout().addWidget(self._auth_widget())

        recent_card = self._status_card(parent, "Recent Calls")
        recent_layout = recent_card.layout()
        self.recent_fail_label = CaptionLabel("Fails: 0", recent_card)
        self.recent_slowest_label = CaptionLabel("Slowest: -", recent_card)
        self.recent_median_label = CaptionLabel("Median: -", recent_card)
        for label in (self.recent_fail_label, self.recent_slowest_label, self.recent_median_label):
            label.setObjectName("McpMutedLabel")
            label.setFont(tray_mono_font(8))
            label.setStyleSheet(mcp_muted_label_stylesheet())
            recent_layout.addWidget(label)

        for card in (state_card, transport_card, auth_card, recent_card):
            band.addWidget(card, 1)
        return band

    def _status_card(self, parent, title: str) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("McpStatusCard")
        card.setMinimumHeight(94)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 7)
        layout.setSpacing(4)
        heading = CaptionLabel(title, card)
        heading.setObjectName("McpHeadingLabel")
        heading.setStyleSheet(mcp_heading_stylesheet())
        layout.addWidget(heading)
        return card

    def _transport_row(self, parent, label: str, value: str, copy_value: str) -> tuple[QWidget, QLabel]:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        text = CaptionLabel(f"{label}: {value}", row)
        text.setObjectName("McpMutedLabel")
        text.setFont(tray_mono_font(8))
        text.setStyleSheet(mcp_muted_label_stylesheet())
        button = TransparentToolButton(FIF.COPY, row)
        button.setFixedSize(24, 24)
        install_tray_fluent_tooltip(button, f"复制 {label}")
        button.clicked.connect(lambda _checked=False, value=copy_value: self.host.ui.copy_to_clipboard(value))
        layout.addWidget(text, 1)
        layout.addWidget(button)
        return row, text

    def _build_capability_panel(self, parent) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("McpCapabilityPanel")
        panel.setMinimumWidth(220)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("Capabilities", panel))
        header.addStretch(1)
        count = CaptionLabel(f"{len(MCP_TOOL_NAMES)} tools / {len(MCP_RESOURCE_NAMES)} resources", panel)
        count.setObjectName("McpMutedLabel")
        count.setStyleSheet(mcp_muted_label_stylesheet())
        header.addWidget(count)
        layout.addLayout(header)
        self.tools_table = self.host.ui.create_log_table(panel, ["Name", "Kind"])
        self.tools_table.setObjectName("McpCapabilityTable")
        self.tools_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tools_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tools_table.cellClicked.connect(self._show_capability_name)
        self.tools_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tools_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tools_table, 1)
        selected = QWidget(panel)
        selected_layout = QHBoxLayout(selected)
        selected_layout.setContentsMargins(0, 0, 0, 0)
        selected_layout.setSpacing(4)
        self.capability_name_line = LineEdit(selected)
        self.capability_name_line.setObjectName("McpCapabilityNameLine")
        self.capability_name_line.setReadOnly(True)
        self.capability_name_line.setPlaceholderText("Select a capability to view the full name")
        self.capability_copy_button = TransparentToolButton(FIF.COPY, selected)
        self.capability_copy_button.setObjectName("McpCapabilityNameCopyButton")
        install_tray_fluent_tooltip(self.capability_copy_button, "复制完整 Name")
        self.capability_copy_button.clicked.connect(lambda _checked=False: self._copy_capability_name())
        selected_layout.addWidget(self.capability_name_line, 1)
        selected_layout.addWidget(self.capability_copy_button)
        layout.addWidget(selected)
        return panel

    def _build_call_stream_panel(self, parent) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("McpCallStreamPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("Call Stream", panel))
        header.addStretch(1)
        limit = CaptionLabel(f"Last {MCP_LOG_LIMIT}", panel)
        limit.setObjectName("McpMutedLabel")
        limit.setStyleSheet(mcp_muted_label_stylesheet())
        header.addWidget(limit)
        layout.addLayout(header)
        self.log_table = self.host.ui.create_log_table(panel, ["Time", "Tool", "Result", "Elapsed", "Summary"])
        self.log_table.setObjectName("McpCallLogTable")
        self.log_table.cellClicked.connect(self._show_log_detail)
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.log_table, 1)
        return panel

    def _build_detail_panel(self, parent) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("McpCallDetailPanel")
        panel.setMinimumWidth(270)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(StrongBodyLabel("Selected Call", panel))
        self.log_detail = TextEdit(panel)
        self.log_detail.setObjectName("McpCallLogDetail")
        self.log_detail.setReadOnly(True)
        self.log_detail.setFont(tray_mono_font(8))
        self.log_detail.setPlainText("Select a call row to inspect request, response, error, and Server correlation.")
        layout.addWidget(self.log_detail, 1)
        return panel

    def _build_debug_drawer(self, parent) -> QWidget:
        drawer = QFrame(parent)
        drawer.setObjectName("McpDebugDrawer")
        drawer.setFixedHeight(126)
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("Debug Drawer", drawer))
        header.addStretch(1)
        copy_button = TransparentToolButton(FIF.COPY, drawer)
        copy_button.setObjectName("McpDebugCopyButton")
        install_tray_fluent_tooltip(copy_button, "复制已脱敏 MCP debug 内容")
        copy_button.clicked.connect(lambda _checked=False: self._copy_debug_text())
        header.addWidget(copy_button)
        layout.addLayout(header)
        self.debug_text = TextEdit(drawer)
        self.debug_text.setObjectName("McpDebugText")
        self.debug_text.setReadOnly(True)
        self.debug_text.setFont(tray_mono_font(8))
        layout.addWidget(self.debug_text, 1)
        self.debug_drawer = drawer
        drawer.setVisible(False)
        return drawer

    def _auth_widget(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.auth_line = PasswordLineEdit(widget)
        self.auth_line.setObjectName("McpAuthTokenLine")
        self.auth_line.setReadOnly(True)
        self.auth_line.setText(self.host.record.token)
        self.auth_line.setViewPasswordButtonVisible(True)
        self.auth_copy_button = TransparentToolButton(FIF.COPY, widget)
        self.auth_copy_button.setObjectName("McpAuthCopyButton")
        install_tray_fluent_tooltip(self.auth_copy_button, "复制 Auth token")
        self.auth_copy_button.clicked.connect(lambda _checked=False: self.host.ui.copy_to_clipboard(self.host.record.token))
        layout.addWidget(self.auth_line, 1)
        layout.addWidget(self.auth_copy_button)
        return widget

    def _log_overlap(self, keys: list[tuple[object, ...]]) -> int:
        max_overlap = min(len(self.rendered_log_keys), len(keys))
        for size in range(max_overlap, 0, -1):
            if self.rendered_log_keys[-size:] == keys[:size]:
                return size
        return 0

    def _append_log_row(self, entry: dict) -> None:
        table = self.log_table
        if table is None:
            return
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(self._log_row(entry)):
            table.setItem(row, column, QTableWidgetItem(self.host.ui.redact(str(value))))
        table.resizeRowsToContents()

    def _capability_rows(self) -> list[list[str]]:
        rows = [[name, MCP_TOOL_TAGS.get(name, "tool")] for name in MCP_TOOL_NAMES]
        rows.extend([[resource, "resource"] for resource in MCP_RESOURCE_NAMES])
        return rows

    def _show_capability_name(self, row: int, _column: int) -> None:
        if self.tools_table is None:
            return
        item = self.tools_table.item(row, 0)
        if item is not None:
            self._set_capability_name(item.text())

    def _set_capability_name(self, name: str) -> None:
        if self.capability_name_line is not None:
            self.capability_name_line.setText(name)
            install_tray_fluent_tooltip(self.capability_name_line, name)

    def _copy_capability_name(self) -> None:
        if self.capability_name_line is not None:
            self.host.ui.copy_to_clipboard(self.capability_name_line.text())

    def _set_debug_enabled(self, enabled: bool) -> None:
        self.debug_enabled = bool(enabled)
        if self.debug_drawer is not None:
            self.debug_drawer.setVisible(self.debug_enabled)
        self.host.dialog.refresh(rebuild_lists=True)

    def _projected_panel_state(self, projected_state: str) -> str:
        if projected_state == "starting":
            return "starting"
        if projected_state == "foreground-blocked":
            return "blocked"
        if projected_state == "error":
            return "unavailable"
        return "ready"

    def _set_state_chip(self, state: str) -> None:
        if self.state_chip is None:
            return
        normalized = str(state or "unavailable")
        text = {
            "ready": "Ready",
            "starting": "Starting",
            "blocked": "Blocked",
            "unavailable": "Unavailable",
        }.get(normalized, normalized)
        chip_status = {
            "ready": "ready",
            "starting": "starting",
            "blocked": "foreground-blocked",
            "unavailable": "unavailable",
        }.get(normalized, "unavailable")
        self.state_chip.setObjectName("TrayStatusChip")
        self.state_chip.setText(text)
        self.state_chip.setStyleSheet(chip_stylesheet(chip_status) + "font-weight:600;")

    def _call_entries(self) -> list[dict]:
        return self.call_log.tail(MCP_LOG_LIMIT) if self.call_log is not None else []

    def _recent_stats(self, entries: list[dict]) -> dict[str, str | int]:
        failures = sum(1 for entry in entries if entry.get("error"))
        elapsed_values = sorted(float(entry.get("elapsed_ms") or 0.0) for entry in entries if entry.get("elapsed_ms") is not None)
        if not elapsed_values:
            return {"failures": failures, "slowest": "-", "median": "-"}
        midpoint = len(elapsed_values) // 2
        if len(elapsed_values) % 2:
            median = elapsed_values[midpoint]
        else:
            median = (elapsed_values[midpoint - 1] + elapsed_values[midpoint]) / 2
        return {
            "failures": failures,
            "slowest": self.host.ui.duration_label(elapsed_values[-1]),
            "median": self.host.ui.duration_label(median),
        }

    def _clear_call_log(self) -> None:
        dialog = MessageBox("清理 CGS MCP 调用记录", "清理 MCP 调用流、选中详情和 Debug 抽屉内容。", self.host.manage_dialog)
        if hasattr(dialog, "yesButton"):
            dialog.yesButton.setText("清理")
        if hasattr(dialog, "cancelButton"):
            dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        if self.call_log is not None:
            self.call_log.clear()
        self.rendered_log_keys.clear()
        self.rendered_log_entries.clear()
        if self.log_table is not None:
            self.log_table.setRowCount(0)
        if self.log_detail is not None:
            self.log_detail.setPlainText("MCP call log cleared.")
        if self.debug_text is not None:
            self.debug_text.clear()
        self.host.dialog.refresh(rebuild_lists=True)
        gc.collect()

    def _copy_debug_text(self) -> None:
        if self.debug_text is None:
            return
        self.host.ui.copy_to_clipboard(self.debug_text.toPlainText())

    def _show_log_detail(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.rendered_log_entries):
            entry = self.rendered_log_entries[row]
            if self.log_detail is not None:
                self.log_detail.setPlainText(self._log_detail_text(entry))

    def _log_key(self, entry: dict) -> tuple[object, ...]:
        return (
            entry.get("created_at"),
            entry.get("tool"),
            entry.get("code"),
            entry.get("elapsed_ms"),
            entry.get("args_summary"),
            entry.get("response_summary"),
            entry.get("error"),
        )

    def _log_row(self, entry: dict) -> list[str]:
        host = self.host
        return [
            host.ui.short_time(entry.get("created_at")),
            str(entry.get("tool", "")),
            self._result_label(entry),
            host.ui.duration_label(float(entry.get("elapsed_ms") or 0.0)),
            self._log_summary(entry),
        ]

    def _result_label(self, entry: dict) -> str:
        if entry.get("error"):
            return str(entry.get("code") or "error")
        return str(entry.get("code") or "ok")

    def _log_summary(self, entry: dict) -> str:
        if entry.get("error"):
            return self.host.ui.strip_html(str(entry.get("error") or "-"))
        response = str(entry.get("response_summary") or "-")
        if len(response) > 180:
            return f"{response[:180]}..."
        return response

    def _log_detail_text(self, entry: dict) -> str:
        host = self.host
        parts = [
            f"Tool: {entry.get('tool') or '-'}",
            f"Time: {host.ui.short_time(entry.get('created_at'))}",
            f"Result: {self._result_label(entry)}",
            f"Elapsed: {host.ui.duration_label(float(entry.get('elapsed_ms') or 0.0))}",
            "",
            "Request",
            self._format_payload(entry.get("args_summary") or "{}"),
            "",
            "Response",
            self._format_payload(entry.get("response_summary") or "-"),
            "",
            "Error",
            host.ui.strip_html(str(entry.get("error") or "-")),
            "",
            "Correlation",
            self._correlation_text(entry),
        ]
        return host.ui.redact("\n".join(parts))

    def _format_payload(self, value: object) -> str:
        text = str(value)
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return self.host.ui.strip_html(text)
        return json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True, default=str)

    def _correlation_text(self, entry: dict) -> str:
        tool = str(entry.get("tool") or "")
        if tool == "cgs_submit_books":
            return "Server tab: active job/progress is the runtime owner for submitted work."
        if entry.get("error"):
            return "Server tab: Errors panel may contain the matching source=mcp record."
        if tool in {"cgs_get_status", "cgs_get_events"}:
            return "Server tab: status/events are the same runtime projection."
        return "No runtime mutation; inspect Server tab only if this call failed."

    def _debug_lines(self, entries: list[dict]) -> list[str]:
        host = self.host
        lines = [
            f"state={self._projected_panel_state(host.projected_state())}",
            f"reason={self.unavailable_reason()}",
            f"http={host.record.connect_url}{DEFAULT_SERVER_MCP_PATH}",
            "stdio=cgs-mcp",
            f"launch_log={server_launch_log_path()}",
        ]
        last_error = host.server_panel.diagnostics.last_error_summary()
        if last_error:
            lines.append(f"last_server_error={last_error}")
        if not entries:
            lines.append("No MCP calls recorded.")
            return [host.ui.redact(host.ui.strip_html(line)) for line in lines]
        lines.append("recent_calls:")
        for entry in entries[-20:]:
            line = (
                f"[{host.ui.short_time(entry.get('created_at'))}] "
                f"{entry.get('tool') or '-'} result={self._result_label(entry)} "
                f"elapsed={host.ui.duration_label(float(entry.get('elapsed_ms') or 0.0))} "
                f"args={entry.get('args_summary') or '{}'} "
                f"response={entry.get('response_summary') or '-'} "
                f"error={entry.get('error') or '-'}"
            )
            lines.append(host.ui.redact(host.ui.strip_html(line)))
        return lines
