from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFrame, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget, TableWidget, TextEdit

from server.tray.ui_common import TRAY_BORDER, TRAY_PANEL_BG_ALT

if TYPE_CHECKING:
    from server.tray.host import ServerTrayHost


SERVER_DIAGNOSTIC_LIMIT = 80


class ServerDiagnosticsPanel:
    def __init__(self, host: "ServerTrayHost") -> None:
        self.host = host
        self.debug_enabled = False
        self.diag_segment: SegmentedWidget | None = None
        self.diag_stack: QStackedWidget | None = None
        self.diag_widgets: dict[str, QWidget] = {}
        self.request_table: TableWidget | None = None
        self.event_table: TableWidget | None = None
        self.log_table: TableWidget | None = None
        self.error_table: TableWidget | None = None
        self.error_detail: TextEdit | None = None
        self.error_entries: list[dict[str, str]] = []
        self.error_rendered_entries: list[dict[str, str]] = []

    def build(self, parent) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("ServerDiagnosticsPanel")
        panel.setStyleSheet(f"#ServerDiagnosticsPanel{{background:{TRAY_PANEL_BG_ALT};border:1px solid {TRAY_BORDER};border-radius:6px;}}")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        self.diag_segment = SegmentedWidget(panel)
        self.diag_stack = QStackedWidget(panel)
        self.diag_widgets = {}
        for title, widget in (
            ("Response", self._build_response_diag(panel)),
            ("Events", self._build_events_diag(panel)),
            ("Logs", self._build_logs_diag(panel)),
            ("Errors", self._build_errors_diag(panel)),
        ):
            self.diag_segment.addItem(title, title, onClick=lambda _checked=False, item=title: self._select_diag_tab(item))
            self.diag_stack.addWidget(widget)
            self.diag_widgets[title] = widget
        layout.addWidget(self.diag_segment)
        layout.addWidget(self.diag_stack, 1)
        self._select_diag_tab("Response")
        return panel

    def refresh(self) -> None:
        host = self.host
        if self.request_table is not None:
            host.ui.set_table_rows(self.request_table, self.request_rows())
        if self.event_table is not None:
            host.ui.set_table_rows(self.event_table, self.event_rows())
        if self.log_table is not None:
            host.ui.set_table_rows(self.log_table, self.log_rows())
        if self.error_table is not None:
            self.error_rendered_entries = self.error_dialog_entries()
            host.ui.set_table_rows(self.error_table, [[entry["time"], entry["summary"]] for entry in self.error_rendered_entries])

    def set_debug_enabled(self, enabled: bool) -> None:
        self.debug_enabled = bool(enabled)

    def runtime_events_payload(self) -> dict:
        try:
            from server.runtime import runtime

            return runtime.events()
        except Exception as exc:
            return {
                "job_id": None,
                "events": [
                    {
                        "type": "error",
                        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "message": self.host.ui.redact(str(exc)),
                    }
                ],
                "logs": [],
            }

    def event_rows(self) -> list[list[str]]:
        events = self.runtime_events_payload().get("events", [])
        rows: list[list[str]] = []
        for entry in events[-SERVER_DIAGNOSTIC_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            event_type = str(entry.get("type") or "-")
            context = str(entry.get("stage") or entry.get("task_title") or entry.get("task_id") or entry.get("code") or "-")
            message = self._event_message(entry)
            if self.debug_enabled:
                message = self.host.ui.compact_json(entry)
            rows.append([self.host.ui.short_time(entry.get("timestamp")), event_type, context, message])
        return rows

    def log_rows(self) -> list[list[str]]:
        logs = self.runtime_events_payload().get("logs", [])
        rows: list[list[str]] = []
        for entry in logs[-SERVER_DIAGNOSTIC_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            message = self.host.ui.compact_json(entry) if self.debug_enabled else str(entry.get("message") or "-")
            rows.append([self.host.ui.short_time(entry.get("timestamp")), str(entry.get("level") or "-"), message])
        return rows

    def request_rows(self) -> list[list[str]]:
        try:
            from server.runtime import runtime

            diagnostics = runtime.diagnostics()
            requests = diagnostics.get("requests", [])
            server_errors = diagnostics.get("server_errors", [])
        except Exception as exc:
            return [["-", "-", "-", "-", "-", self.host.ui.redact(str(exc))]]
        rows: list[list[str]] = []
        for entry in requests[-SERVER_DIAGNOSTIC_LIMIT:]:
            if not isinstance(entry, dict):
                continue
            status = entry.get("status_code", "-")
            if entry.get("error_type"):
                status = f"{status} {entry.get('error_type')}"
            message = str(
                entry.get("message")
                or entry.get("detail")
                or entry.get("error")
                or self._request_error_summary(entry, server_errors)
                or "-"
            )
            rows.append(
                [
                    self.host.ui.short_time(entry.get("timestamp")),
                    str(entry.get("method") or "-"),
                    str(entry.get("path") or "-"),
                    str(status),
                    f"{entry.get('duration_ms', '-')} ms",
                    self.host.ui.strip_html(self.host.ui.redact(message)),
                ]
            )
        return rows

    def clear_request_diagnostics(self) -> None:
        try:
            from server.runtime import runtime

            runtime.clear_request_diagnostics()
        except Exception:
            detail = traceback.format_exc()
            self.record_error("HTTP diagnostics clear failed", detail)
            raise
        self.host.dialog.refresh(rebuild_lists=True)

    def clear_error_history(self) -> None:
        self.error_entries.clear()
        self.error_rendered_entries.clear()
        if self.error_detail is not None:
            self.error_detail.clear()
            self.error_detail.setVisible(False)

    def error_dialog_entries(self) -> list[dict[str, str]]:
        entries = list(self.error_entries)
        try:
            from server.runtime import runtime

            diagnostics = runtime.diagnostics()
            server_errors = diagnostics.get("server_errors", [])
        except Exception as exc:
            entries.append(
                {
                    "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "summary": f"Diagnostics unavailable: {self.host.ui.redact(str(exc))}",
                    "detail": self.host.ui.redact(traceback.format_exc()),
                }
            )
            return entries[-SERVER_DIAGNOSTIC_LIMIT:]
        for entry in server_errors[-SERVER_DIAGNOSTIC_LIMIT:]:
            if isinstance(entry, dict):
                entries.append(self._runtime_server_error_entry(entry))
        return entries[-SERVER_DIAGNOSTIC_LIMIT:]

    def last_error_summary(self) -> str:
        entries = self.error_dialog_entries()
        if not entries:
            return ""
        return str(entries[-1].get("summary") or "")

    def record_error(self, summary: str, detail: str) -> None:
        clean_detail = self.host.ui.strip_html(self.host.ui.redact(detail))
        clean_summary = self.host.ui.strip_html(self.host.ui.redact(summary))
        first_detail_line = next((line.strip() for line in clean_detail.splitlines() if line.strip()), "")
        if first_detail_line:
            clean_summary = f"{clean_summary}: {first_detail_line}"
        self.error_entries.append(
            {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "summary": clean_summary,
                "detail": clean_detail,
            }
        )
        del self.error_entries[:-SERVER_DIAGNOSTIC_LIMIT]

    def show_error_detail(self, row: int, _column: int) -> None:
        entries = self.error_rendered_entries or self.error_dialog_entries()
        if 0 <= row < len(entries):
            self.error_detail.setPlainText(entries[row]["detail"])
            self.error_detail.setVisible(True)

    def _build_response_diag(self, parent) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.request_table = self.host.ui.create_log_table(widget, ["Time", "Method", "Path", "Status", "Duration", "Message"])
        self.request_table.setObjectName("ServerRequestTable")
        layout.addWidget(self.request_table)
        return widget

    def _build_events_diag(self, parent) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.event_table = self.host.ui.create_log_table(widget, ["Time", "Type", "Context", "Message"])
        self.event_table.setObjectName("ServerEventTable")
        layout.addWidget(self.event_table)
        return widget

    def _build_logs_diag(self, parent) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.log_table = self.host.ui.create_log_table(widget, ["Time", "Level", "Message"])
        self.log_table.setObjectName("ServerLogTable")
        layout.addWidget(self.log_table)
        return widget

    def _build_errors_diag(self, parent) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.error_table = self.host.ui.create_log_table(widget, ["Time", "Summary"])
        self.error_table.setObjectName("ServerErrorTable")
        self.error_table.cellClicked.connect(self.show_error_detail)
        layout.addWidget(self.error_table, 1)
        self.error_detail = TextEdit(widget)
        self.error_detail.setObjectName("ServerErrorDetail")
        self.error_detail.setReadOnly(True)
        self.error_detail.setFixedHeight(96)
        self.error_detail.setVisible(False)
        layout.addWidget(self.error_detail)
        return widget

    def _select_diag_tab(self, tab_name: str) -> None:
        if self.diag_stack is None:
            return
        widget = self.diag_widgets.get(tab_name) or self.diag_widgets.get("Response")
        if widget is not None:
            self.diag_stack.setCurrentWidget(widget)
        if self.diag_segment is not None:
            self.diag_segment.setCurrentItem(tab_name if tab_name in self.diag_widgets else "Response")

    def _event_message(self, entry: dict) -> str:
        for key in ("message", "error", "latest_message", "url", "path"):
            if entry.get(key):
                return self.host.ui.strip_html(str(entry.get(key)))
        if entry.get("percent") is not None:
            return f"{entry.get('percent')}%"
        return "-"

    def _request_error_summary(self, request_entry: dict, server_errors: list) -> str:
        method = str(request_entry.get("method") or "")
        path = str(request_entry.get("path") or "")
        status = self.host.ui.coerce_int(request_entry.get("status_code"))
        if status is None or status < 400:
            return ""
        for entry in reversed(server_errors):
            if not isinstance(entry, dict):
                continue
            if method and str(entry.get("method") or "") != method:
                continue
            if path and str(entry.get("path") or "") != path:
                continue
            if status != self.host.ui.coerce_int(entry.get("status_code")):
                continue
            code = entry.get("code")
            detail = entry.get("detail")
            summary = entry.get("summary")
            return self.host.ui.strip_html(" · ".join(str(part) for part in (code, detail or summary) if part))
        return ""

    def _runtime_server_error_entry(self, entry: dict) -> dict[str, str]:
        timestamp = str(entry.get("timestamp") or entry.get("time") or "-")
        source = str(entry.get("source") or "server")
        summary = str(entry.get("summary") or "Server error")
        code = entry.get("code")
        status_code = entry.get("status_code")
        method = entry.get("method")
        path = entry.get("path")
        if status_code and method and path and str(status_code) not in summary:
            summary = f"{status_code} {method} {path}: {summary}"
        if code and str(code) not in summary:
            summary = f"{summary} [{code}]"
        detail_parts = [
            f"source: {source}",
            f"summary: {summary}",
        ]
        if status_code:
            detail_parts.append(f"status_code: {status_code}")
        if method or path:
            detail_parts.append(f"request: {method or '-'} {path or '-'}")
        if code:
            detail_parts.append(f"code: {code}")
        if entry.get("detail"):
            detail_parts.append(str(entry.get("detail")))
        if entry.get("traceback"):
            detail_parts.append(str(entry.get("traceback")))
        return {
            "time": timestamp,
            "summary": self.host.ui.strip_html(self.host.ui.redact(summary)),
            "detail": self.host.ui.strip_html(self.host.ui.redact("\n".join(detail_parts))),
        }
