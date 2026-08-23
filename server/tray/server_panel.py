from __future__ import annotations

import gc
import os
import traceback
from typing import TYPE_CHECKING
from urllib.parse import unquote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon as FIF,
    LineEdit,
    MessageBox,
    ProgressBar,
    StrongBodyLabel,
    SwitchButton,
    TransparentToolButton,
)

from server.runtime_state import task_progress_page_number as runtime_task_progress_page_number
from server.tray.server_diagnostics_panel import ServerDiagnosticsPanel
from GUI.uic.qfluent.components.icons import CgsIcon
from server.tray.style import cover_placeholder_stylesheet, error_label_stylesheet, progress_done_color
from server.tray.ui_common import (
    CompactKeyValueTable,
    configure_tray_qt_fonts,
    install_tray_fluent_tooltip,
    tray_mono_font,
)
from utils import conf, temp_p
from utils.server_control import server_launch_log_path
import GUI.src.material_ct

if TYPE_CHECKING:
    from server.tray.host import ServerTrayHost


class ServerTaskRow(QFrame):
    def __init__(self, parent, item: dict, panel: "ServerPanel") -> None:
        super().__init__(parent)
        self.setObjectName("ServerTaskProgressRow")
        self._panel = panel
        self._local_path = ""
        self._source_url = ""
        self._cover_path = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 4, 6, 4)
        layout.setSpacing(7)
        self._cover = QLabel("cover", self)
        self._cover.setObjectName("TrayCoverPlaceholder")
        self._cover.setFixedSize(40, 54)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setStyleSheet(cover_placeholder_stylesheet())
        layout.addWidget(self._cover)
        body = QVBoxLayout()
        body.setSpacing(2)
        title_row = QHBoxLayout()
        self._title = StrongBodyLabel("-", self)
        self._title.setMinimumWidth(0)
        self._title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_row.addWidget(self._title, 1)
        self._page_label = CaptionLabel("0P", self)
        title_row.addWidget(self._page_label)
        self._percent_label = CaptionLabel("0%", self)
        title_row.addWidget(self._percent_label)
        self._status_chip = QLabel("running", self)
        title_row.addWidget(self._status_chip)
        body.addLayout(title_row)
        self._progress = ProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        body.addWidget(self._progress)
        meta_row = QHBoxLayout()
        self._meta = CaptionLabel("-", self)
        self._meta.setMinimumWidth(0)
        meta_row.addWidget(self._meta, 1)
        self._folder = TransparentToolButton(FIF.FOLDER, self)
        self._folder.clicked.connect(lambda _checked=False: self._panel.open_path(self._local_path))
        meta_row.addWidget(self._folder)
        self._link = TransparentToolButton(FIF.LINK, self)
        self._link.clicked.connect(lambda _checked=False: self._panel.open_url(self._source_url))
        meta_row.addWidget(self._link)
        body.addLayout(meta_row)
        layout.addLayout(body, 1)
        self.apply(item)

    def apply(self, item: dict) -> None:
        host = self._panel.host
        total = host.ui.coerce_int(item.get("total_pages")) or 0
        downloaded = host.ui.coerce_int(item.get("downloaded")) or 0
        percent = host.ui.coerce_percent(item.get("percent"))
        title_text = str(item.get("task_title") or item.get("task_id") or "-")
        self._title.setText(title_text)
        install_tray_fluent_tooltip(self._title, title_text)
        self._page_label.setText(f"{downloaded}/{total}P" if total else f"{downloaded}P")
        self._percent_label.setText(f"{percent}%")
        host.ui.set_chip(self._status_chip, str(item.get("status") or "running"))
        self._progress.setValue(percent)
        if percent >= 100:
            done_color = progress_done_color()
            self._progress.setCustomBarColor(light=done_color, dark=done_color)
        stage = str(item.get("stage") or item.get("type") or "-")
        latest = str(item.get("error") or item.get("latest_message") or item.get("url") or "-")
        meta_text = f"stage: {stage}    latest: {host.ui.strip_html(latest)}"
        self._meta.setText(meta_text)
        install_tray_fluent_tooltip(self._meta, meta_text)
        self._local_path = str(item.get("local_path") or "")
        self._source_url = str(item.get("source_url") or item.get("url") or "")
        install_tray_fluent_tooltip(self._folder, self._local_path or "no local path")
        self._folder.setEnabled(bool(self._local_path))
        install_tray_fluent_tooltip(self._link, self._source_url or "no source url")
        self._link.setEnabled(bool(self._source_url))
        cover_path = self._panel.task_cover_path(item)
        if cover_path and cover_path != self._cover_path:
            self._cover_path = cover_path
            install_tray_fluent_tooltip(self._cover, cover_path)
            self._panel.apply_cover(self._cover, cover_path)


class ServerPanel:
    def __init__(self, host: "ServerTrayHost") -> None:
        self.host = host
        self.table: CompactKeyValueTable | None = None
        self.debug_switch: SwitchButton | None = None
        self.debug_enabled = False
        self.job_card: QFrame | None = None
        self.job_title_label: QLabel | None = None
        self.job_meta_label: QLabel | None = None
        self.job_stage_label: QLabel | None = None
        self.job_time_label: QLabel | None = None
        self.job_error_label: QLabel | None = None
        self.job_progress_bar: ProgressBar | None = None
        self.job_progress_label: QLabel | None = None
        self.tasks_count_label: QLabel | None = None
        self.tasks_layout: QVBoxLayout | None = None
        self.tasks_empty_label: CaptionLabel | None = None
        self.task_rows: dict[str, ServerTaskRow] = {}
        self.diagnostics = ServerDiagnosticsPanel(host)

    def build_tab(self, parent) -> QWidget:
        if app := (self.host.qt_app or QApplication.instance()):
            configure_tray_qt_fonts(app)
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_action_bar(tab))
        self.table = CompactKeyValueTable(tab)
        self.table.setObjectName("ServerStatusTable")
        self.table.setMaximumHeight(96)
        layout.addWidget(self.table)
        layout.addWidget(self._build_job_panel(tab))
        layout.addWidget(self._build_tasks_panel(tab), 2)
        layout.addWidget(self.diagnostics.build(tab), 2)
        return tab

    def refresh(self) -> None:
        if self.table is not None:
            self.table.set_rows(self.status_rows())
        if self.job_card is not None:
            self.refresh_monitor()
        self.diagnostics.refresh()

    def status_rows(self) -> list[tuple[str, object]]:
        host = self.host
        launch_log_path = server_launch_log_path()
        launch_log = str(launch_log_path)
        return [
            (
                "Connect URL",
                self._copy_value_widget(
                    host.ui.redact(host.record.connect_url), host.record.connect_url, "ServerConnectUrlLine", "ServerConnectUrlCopy"
                ),
            ),
            ("Bind", f"{host.record.bind_host}:{host.record.port}"),
            (
                "Launch log",
                self._open_folder_value_widget(
                    host.ui.redact(launch_log), str(launch_log_path.parent), "ServerLaunchLogLine", "ServerLaunchLogOpenFolder"
                ),
            ),
            ("Started", host.ui.beijing_datetime_label(host.record.created_at)),
            ("Surfaces", host.surfaces_label()),
        ]

    def set_debug_enabled(self, enabled: bool) -> None:
        self.debug_enabled = bool(enabled)
        self.diagnostics.set_debug_enabled(self.debug_enabled)
        self.host.dialog.refresh(rebuild_lists=True)

    def refresh_monitor(self) -> None:
        host = self.host
        payload = host.runtime_status_payload()
        status = str(payload.get("status") or host.projected_state())
        job = payload.get("job") if isinstance(payload.get("job"), dict) else None
        percent = self._job_percent(job, status)
        progress_items = self.progress_items(job, status)
        if not percent and progress_items:
            percent = self._progress_items_aggregate_percent(progress_items, status)
        stage = str((job or {}).get("stage") or "-")
        short_job_id = host.ui.short_job_id((job or {}).get("job_id"))
        if job:
            origin = str(job.get("origin") or "-")
            host.ui.set_label(self.job_title_label, f"Active Job · {status}")
            host.ui.set_label(self.job_meta_label, f"job: {short_job_id} · {origin}")
            host.ui.set_label(self.job_stage_label, stage)
            started = host.ui.short_time(job.get("started_at"))
            updated = host.ui.short_time(job.get("updated_at"))
            host.ui.set_label(self.job_time_label, f"{started} -> {updated}")
            error = job.get("error")
            if error:
                host.ui.set_label(self.job_error_label, f"{job.get('error_code') or 'error'}: {host.ui.strip_html(str(error))}")
                self.job_error_label.setVisible(True)
                self.job_error_label.setStyleSheet(error_label_stylesheet())
            elif self.job_error_label is not None:
                self.job_error_label.setVisible(False)
        else:
            host.ui.set_label(self.job_title_label, "No Active Job")
            host.ui.set_label(self.job_meta_label, "job: - · origin: -")
            host.ui.set_label(self.job_stage_label, f"server: {status}")
            host.ui.set_label(self.job_time_label, "started: - · updated: -")
            if self.job_error_label is not None:
                self.job_error_label.setVisible(False)
        if self.job_progress_bar is not None:
            self.job_progress_bar.setValue(percent)
            if percent >= 100:
                done_color = progress_done_color()
                self.job_progress_bar.setCustomBarColor(light=done_color, dark=done_color)
            else:
                self.job_progress_bar.setCustomBarColor(light=QColor(), dark=QColor())
        host.ui.set_label(self.job_progress_label, f"{percent}%")
        self._render_task_rows(progress_items)

    def progress_items(self, job: dict | None, status: str) -> list[dict]:
        if not isinstance(job, dict):
            return []
        rows = job.get("progress_items")
        if not isinstance(rows, list):
            return []
        return [dict(item) for item in rows if isinstance(item, dict)]

    def clear_runtime_history(self) -> None:
        payload = self.host.runtime_status_payload()
        running = str(payload.get("status") or "") in {"starting", "running"}
        content = "当前任务仍在运行，只会清理 HTTP 诊断记录；任务进度会保留。" if running else "清理已完成/失败的任务进度、事件、日志、HTTP 诊断和错误详情。"
        dialog = MessageBox("清理 CGS Server 反馈", content, self.host.manage_dialog)
        if hasattr(dialog, "yesButton"):
            dialog.yesButton.setText("清理")
        if hasattr(dialog, "cancelButton"):
            dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        try:
            from server.runtime import runtime

            runtime.clear_request_diagnostics()
            if not running:
                runtime.clear_server_errors()
                runtime.clear_work_history()
                self.diagnostics.clear_error_history()
        except Exception:
            detail = traceback.format_exc()
            self.diagnostics.record_error("Server monitor clear failed", detail)
            raise
        self.host.dialog.refresh(rebuild_lists=True)
        gc.collect()

    def open_path(self, path: str) -> None:
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    def open_url(self, url: str) -> None:
        if not url:
            return
        QDesktopServices.openUrl(QUrl(url))

    def apply_cover(self, label: QLabel, cover_url: str) -> None:
        path = self.cover_path(cover_url)
        if not path or not os.path.exists(path):
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        label.setText("")
        label.setPixmap(pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def task_cover_path(self, item: dict) -> str:
        local_cover = self.local_cover_path(str(item.get("local_path") or ""), self.host.ui.coerce_int(item.get("total_pages")) or 0)
        if local_cover:
            return local_cover
        return str(item.get("cover_url") or "")

    def local_cover_path(self, local_path: str, total_pages: int) -> str:
        if not local_path or not os.path.isdir(local_path):
            return ""
        digits = len(str(total_pages or 0))
        candidates = [
            f"{str(1).zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}",
            f"1.{getattr(conf, 'img_sv_type', 'jpg')}",
            "cover.jpg",
            "cover.png",
            "front.jpg",
            "front.png",
            "first.jpg",
            "first.png",
        ]
        for filename in candidates:
            path = os.path.join(local_path, filename)
            if os.path.isfile(path):
                return path
        for filename in os.listdir(local_path):
            if runtime_task_progress_page_number(filename) == 1:
                path = os.path.join(local_path, filename)
                if os.path.isfile(path):
                    return path
        return ""

    def cover_path(self, cover_url: str) -> str:
        text = str(cover_url or "")
        if text.startswith("/cover/"):
            filename = os.path.basename(unquote(text.removeprefix("/cover/")))
            return str(temp_p.joinpath("cover", filename))
        if text.startswith("file:///"):
            return QUrl(text).toLocalFile()
        if os.path.exists(text):
            return text
        return ""

    def _build_action_bar(self, parent) -> QWidget:
        band = QWidget(parent)
        band.setObjectName("ServerActionBar")
        layout = QHBoxLayout(band)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch(1)
        debug_label = CaptionLabel("Debug", band)
        self.debug_switch = SwitchButton(band)
        self.debug_switch.setObjectName("ServerDebugSwitch")
        self.debug_switch.setOnText("")
        self.debug_switch.setOffText("")
        self.debug_switch.checkedChanged.connect(self.set_debug_enabled)
        clear_button = TransparentToolButton(FIF.BROOM, band)
        clear_button.setObjectName("ServerRuntimeClearButton")
        clear_button.clicked.connect(lambda _checked=False: self.clear_runtime_history())
        restart_server = TransparentToolButton(CgsIcon.REBOOT, band)
        install_tray_fluent_tooltip(restart_server, "重启")
        restart_server.clicked.connect(lambda _checked=False: self.host.restart_server_surface())
        quit_server = TransparentToolButton(FIF.POWER_BUTTON, band)
        install_tray_fluent_tooltip(quit_server, "退出 CGS Server")
        quit_server.clicked.connect(lambda _checked=False: self.host.shutdown())
        layout.addWidget(debug_label)
        layout.addWidget(self.debug_switch)
        layout.addWidget(clear_button)
        layout.addWidget(restart_server)
        layout.addWidget(quit_server)
        return band

    def _build_job_panel(self, parent) -> QWidget:
        card = QFrame(parent)
        card.setObjectName("ServerActiveJobPanel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.job_title_label = StrongBodyLabel("Active Job", card)
        self.job_meta_label = CaptionLabel("job: - · origin: -", card)
        self.job_stage_label = CaptionLabel("stage: -", card)
        self.job_time_label = CaptionLabel("started: - · updated: -", card)
        for label in (self.job_meta_label, self.job_stage_label, self.job_time_label):
            label.setFont(tray_mono_font(8))
        top.addWidget(self.job_title_label)
        top.addWidget(self.job_meta_label)
        top.addWidget(self.job_stage_label)
        top.addStretch(1)
        top.addWidget(self.job_time_label)
        layout.addLayout(top)
        progress_row = QHBoxLayout()
        self.job_progress_bar = ProgressBar(card)
        self.job_progress_bar.setRange(0, 100)
        self.job_progress_bar.setValue(0)
        self.job_progress_label = CaptionLabel("0%", card)
        self.job_progress_label.setFont(tray_mono_font(8))
        self.job_progress_label.setMinimumWidth(42)
        progress_row.addWidget(self.job_progress_bar, 1)
        progress_row.addWidget(self.job_progress_label)
        layout.addLayout(progress_row)
        self.job_error_label = CaptionLabel("", card)
        self.job_error_label.setObjectName("ServerJobErrorLabel")
        self.job_error_label.setVisible(False)
        layout.addWidget(self.job_error_label)
        self.job_card = card
        return card

    def _build_tasks_panel(self, parent) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("ServerTasksPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("Active Tasks", panel))
        header.addStretch(1)
        self.tasks_count_label = CaptionLabel("0 items", panel)
        header.addWidget(self.tasks_count_label)
        layout.addLayout(header)
        scroll = QScrollArea(panel)
        scroll.setObjectName("ServerTasksScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget(scroll)
        self.tasks_layout = QVBoxLayout(container)
        self.tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_layout.setSpacing(6)
        self.tasks_empty_label = CaptionLabel("No active or retained CGS task progress.", container)
        self.tasks_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tasks_empty_label.setMinimumHeight(54)
        self.tasks_layout.addWidget(self.tasks_empty_label)
        self.tasks_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        return panel

    def _job_percent(self, job: dict | None, status: str) -> int:
        if not job:
            return 0
        if status == "completed":
            return 100
        progress = job.get("progress")
        if isinstance(progress, dict):
            for key in ("percent", "progress"):
                if key in progress:
                    return self.host.ui.coerce_percent(progress.get(key))
            downloaded = self.host.ui.coerce_int(progress.get("downloaded"))
            total = self.host.ui.coerce_int(progress.get("total") or progress.get("total_pages") or progress.get("tasks_count"))
            if downloaded is not None and total:
                return self.host.ui.coerce_percent(downloaded / total * 100)
        return 0

    def _progress_items_aggregate_percent(self, items: list[dict], status: str) -> int:
        if status == "completed":
            return 100
        total = sum(self.host.ui.coerce_int(item.get("total_pages")) or 0 for item in items)
        if not total:
            return 0
        downloaded = sum(
            min(self.host.ui.coerce_int(item.get("downloaded")) or 0, self.host.ui.coerce_int(item.get("total_pages")) or 0)
            for item in items
        )
        return self.host.ui.coerce_percent(downloaded / total * 100)

    def _render_task_rows(self, items: list[dict]) -> None:
        if self.tasks_layout is None:
            return
        seen: dict[str, ServerTaskRow] = {}
        for index, item in enumerate(items):
            tid = str(item.get("task_id"))
            row = self.task_rows.get(tid)
            if row is None:
                row = ServerTaskRow(self.host.manage_dialog, item, self)
                self.task_rows[tid] = row
            else:
                row.apply(item)
            seen[tid] = row
            self.tasks_layout.removeWidget(row)
            self.tasks_layout.insertWidget(index, row)
        for tid, row in list(self.task_rows.items()):
            if tid not in seen:
                self.tasks_layout.removeWidget(row)
                row.deleteLater()
                del self.task_rows[tid]
        if self.tasks_empty_label is not None:
            self.tasks_empty_label.setVisible(not items)
        self.host.ui.set_label(self.tasks_count_label, f"{len(items)} items")

    def _copy_value_widget(self, display_value: str, copy_value: str, line_name: str, button_name: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        line = LineEdit(widget)
        line.setObjectName(line_name)
        line.setReadOnly(True)
        line.setText(display_value)
        copy_button = TransparentToolButton(FIF.COPY, widget)
        copy_button.setObjectName(button_name)
        copy_button.clicked.connect(lambda _checked=False, value=copy_value: self.host.ui.copy_to_clipboard(value))
        layout.addWidget(line, 1)
        layout.addWidget(copy_button)
        return widget

    def _open_folder_value_widget(self, display_value: str, folder_path: str, line_name: str, button_name: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        line = LineEdit(widget)
        line.setObjectName(line_name)
        line.setReadOnly(True)
        line.setText(display_value)
        open_button = TransparentToolButton(FIF.FOLDER, widget)
        open_button.setObjectName(button_name)
        open_button.clicked.connect(lambda _checked=False, path=folder_path: self.open_path(path))
        layout.addWidget(line, 1)
        layout.addWidget(open_button)
        return widget
