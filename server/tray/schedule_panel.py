from __future__ import annotations

import gc
import json
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon as FIF,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    SegmentedWidget,
    StrongBodyLabel,
    SwitchButton,
    TableWidget,
    TextEdit,
    TransparentToolButton,
)

from server.tray.ui_common import (
    ClickableFrame,
    SCHEDULE_ACCENT_INFO,
    SCHEDULE_ACCENT_OK,
    SCHEDULE_CARD_BG,
    SCHEDULE_CARD_BG_SEL,
    StageRail,
    TRAY_BORDER,
    TRAY_COVER_BG,
    TRAY_MUTED,
    TRAY_PANEL_BG,
    TRAY_PANEL_BG_ALT,
    TRAY_TEXT,
    clear_layout,
    tray_mono_font,
)
from utils.subscription import MODE_SUBSCRIBER
from utils.tray.schedule_presentation import SchedulePresentation

if TYPE_CHECKING:
    from server.tray.host import ServerTrayHost


@dataclass
class _ScheduleRunState:
    active: bool = False
    run_id: str = ""
    trigger: str = ""
    started_monotonic: float = 0.0
    stage: str = ""
    scanned_books: int = 0
    pending_episodes: int = 0
    submitted_jobs: int = 0
    latest_message: str = ""
    error: str = ""

    def elapsed_sec(self) -> int:
        if not self.started_monotonic:
            return 0
        return max(0, int(time.monotonic() - self.started_monotonic))


class SchedulePanel:
    def __init__(self, host: "ServerTrayHost") -> None:
        self.host = host
        self.events_table: TableWidget | None = None
        self.mode_chip: QLabel | None = None
        self.state_chip: QLabel | None = None
        self.next_label: QLabel | None = None
        self.run_button: PrimaryPushButton | None = None
        self.debug_switch: SwitchButton | None = None
        self.debug_enabled = False
        self.plan_layout: QGridLayout | None = None
        self.cache_chip: QLabel | None = None
        self.sources_segment: SegmentedWidget | None = None
        self.sources_stack: QStackedWidget | None = None
        self.sources_layout: QVBoxLayout | None = None
        self.sources_count_label: QLabel | None = None
        self.history_count_label: QLabel | None = None
        self.run_id_chip: QLabel | None = None
        self.run_trigger_label: QLabel | None = None
        self.run_elapsed_label: QLabel | None = None
        self.run_scanned_label: QLabel | None = None
        self.run_pending_label: QLabel | None = None
        self.run_jobs_label: QLabel | None = None
        self.run_meta_label: QLabel | None = None
        self.stage_rail: StageRail | None = None
        self.latest_banner: QLabel | None = None
        self.pending_layout: QVBoxLayout | None = None
        self.pending_count_label: QLabel | None = None
        self.detail_title: QLabel | None = None
        self.detail_source: QLabel | None = None
        self.detail_stage_chip: QLabel | None = None
        self.detail_status_chip: QLabel | None = None
        self.detail_pkl_label: QLabel | None = None
        self.detail_message: QLabel | None = None
        self.detail_open_source_btn: PushButton | None = None
        self.detail_open_folder_btn: PushButton | None = None
        self.debug_drawer: QFrame | None = None
        self.debug_text: TextEdit | None = None
        self.detail_entries: list[dict[str, str]] = []
        self.selected_index = -1
        self.latest_presentation: SchedulePresentation | None = None
        self.run_state: _ScheduleRunState | None = None
        self.debug_last_text = ""

    def build_tab(self, parent) -> QWidget:
        tab = QWidget(parent)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_header_panel(tab))
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)
        columns.addWidget(self._build_left_panel(tab), 1)
        columns.addWidget(self._build_run_panel(tab), 2)
        columns.addWidget(self._build_detail_panel(tab), 1)
        layout.addLayout(columns, 1)
        layout.addWidget(self._build_debug_panel(tab))
        return tab

    def status_rows(self) -> list[tuple[str, object]]:
        host = self.host
        rows: list[tuple[str, object]] = [
            ("下次检查", "-"),
            ("模式", "-"),
            ("摘要", "-"),
            ("最近结果", host.ui.redact(host.schedule.last_result)),
        ]
        try:
            presentation = host.schedule.presentation(blocker=host.schedule_run_blocker())
        except Exception as exc:
            return [("错误", host.ui.redact(str(exc)))] + rows
        return [
            ("下次检查", presentation.plan.next_run_at),
            ("模式", presentation.plan.mode_label),
            ("状态", presentation.plan.automation_label),
            ("缓存", f"{presentation.cache.status} ({presentation.cache.book_count})"),
            ("对象", len(presentation.sources)),
            ("待处理", len(presentation.pending_items)),
            ("运行", presentation.run.status),
            ("阶段", presentation.run.stage or "-"),
            ("最近结果", host.ui.redact(host.schedule.last_result)),
            ("配置来源", presentation.plan.config_owner),
        ]

    def start_run_state(self, detail: str) -> None:
        self.run_state = _ScheduleRunState(active=True, trigger=detail, started_monotonic=time.monotonic(), latest_message=detail)

    def finish_run_state(self) -> None:
        if self.run_state is not None:
            self.run_state.active = False

    def fail_run_state(self, exc: BaseException) -> None:
        if self.run_state is not None:
            self.run_state.active = False
            self.run_state.error = str(exc)

    def update_run_state(self, snap: dict) -> None:
        state = self.run_state
        if state is None or not state.active:
            return
        state.run_id = str(snap.get("run_id") or state.run_id)
        state.stage = str(snap.get("stage") or state.stage)
        state.scanned_books = int(snap.get("scanned_books") or 0)
        state.pending_episodes = int(snap.get("pending_episodes") or 0)
        state.submitted_jobs = int(snap.get("submitted_jobs") or 0)
        message = str(snap.get("latest_message") or "")
        if message:
            state.latest_message = message

    def refresh(self, *, full: bool = True) -> None:
        host = self.host
        if not full:
            self.refresh_live()
            return
        try:
            presentation = host.schedule.presentation(blocker=host.schedule_run_blocker())
        except Exception as exc:
            host.ui.set_chip(self.mode_chip, "error")
            host.ui.set_chip(self.state_chip, "error")
            host.ui.set_label(self.next_label, f"Error {exc}")
            host.ui.set_label(self.detail_message, host.ui.redact(str(exc)))
            return
        self.latest_presentation = presentation
        host.ui.set_chip(self.mode_chip, presentation.plan.mode_label)
        run_is_alive = host.schedule.run_thread is not None and host.schedule.run_thread.is_alive()
        host.ui.set_chip(self.state_chip, "running" if run_is_alive else presentation.plan.automation_state)
        host.ui.set_label(self.next_label, f"下次检查 {presentation.plan.next_run_at}")
        if self.run_button is not None:
            self.run_button.setEnabled(not run_is_alive and not bool(presentation.plan.blocker))
            self.run_button.setText("Running" if run_is_alive else "立刻执行")
        self._render_plan(presentation)
        self._render_sources(presentation)
        run = presentation.run
        self._apply_run_header(
            run_id=run.run_id, trigger=run.trigger, elapsed_sec=run.elapsed_sec, scanned=run.scanned_books,
            pending=run.pending_episodes, jobs=run.submitted_jobs, meta=run.published_metadata, stage=run.stage,
            latest=run.latest_message or host.schedule.last_result, running=run_is_alive, stages=presentation.stages,
        )
        self._render_pending(presentation)
        if self.events_table is not None:
            events = host.schedule.events(20)
            host.ui.set_table_rows(self.events_table, [self._event_row(entry) for entry in events])
            host.ui.set_label(self.history_count_label, f"{len(events)} events")
        self._update_debug_text(presentation)

    def refresh_live(self) -> None:
        state = self.run_state
        if state is None or not state.active:
            return
        stages = self.latest_presentation.stages if self.latest_presentation is not None else []
        self._apply_run_header(
            run_id=state.run_id, trigger=state.trigger, elapsed_sec=float(state.elapsed_sec()), scanned=state.scanned_books,
            pending=state.pending_episodes, jobs=state.submitted_jobs, meta=False, stage=state.stage,
            latest=state.latest_message, running=True, stages=stages,
        )

    def _build_header_panel(self, parent) -> QWidget:
        band = QFrame(parent)
        band.setObjectName("ScheduleHeaderPanel")
        band.setStyleSheet(f"QFrame#ScheduleHeaderPanel{{background:{TRAY_PANEL_BG};border:1px solid {TRAY_BORDER};border-radius:6px;}}")
        layout = QHBoxLayout(band)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        title = StrongBodyLabel("订阅运行", band)
        self.mode_chip = QLabel(band)
        self.state_chip = QLabel(band)
        self.next_label = CaptionLabel("Next -", band)
        self.next_label.setStyleSheet(f"color:{TRAY_MUTED};")
        self.run_button = PrimaryPushButton(FIF.PLAY, "立刻执行", band)
        self.run_button.clicked.connect(lambda _checked=False: self.host.run_schedule_now())
        subscribe_button = PushButton(FIF.LINK, "打开追更配置", band)
        subscribe_button.setToolTip("订阅配置由 SpiderGUI 主窗口管理")
        subscribe_button.clicked.connect(lambda _checked=False: self.open_subscribe_guidance())
        refresh_button = TransparentToolButton(FIF.SYNC, band)
        refresh_button.setToolTip("刷新订阅运行状态")
        refresh_button.clicked.connect(lambda _checked=False: self.host.refresh_status(schedule_full=True))
        clear_button = TransparentToolButton(FIF.BROOM, band)
        clear_button.setToolTip("清空订阅运行历史（确认后执行）")
        clear_button.clicked.connect(lambda _checked=False: self.clear_history())
        self.debug_switch = SwitchButton(band)
        self.debug_switch.setText("Debug")
        self.debug_switch.checkedChanged.connect(self.set_debug_enabled)
        layout.addWidget(title)
        layout.addWidget(self.mode_chip)
        layout.addWidget(self.state_chip)
        layout.addWidget(self.next_label)
        layout.addStretch(1)
        layout.addWidget(self.run_button)
        layout.addWidget(subscribe_button)
        layout.addWidget(refresh_button)
        layout.addWidget(clear_button)
        layout.addWidget(self.debug_switch)
        return band

    def _panel(self, parent, object_name: str, *, alt: bool = False):
        frame = QFrame(parent)
        frame.setObjectName(object_name)
        bg = TRAY_PANEL_BG_ALT if alt else TRAY_PANEL_BG
        frame.setStyleSheet(f"#{object_name}{{background:{bg};border:1px solid {TRAY_BORDER};border-radius:6px;}}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        return frame, layout

    def _site_badge(self, site: str, parent) -> QLabel:
        chip = QLabel((site or "?").upper(), parent)
        chip.setStyleSheet(
            f"background:{TRAY_PANEL_BG};color:{TRAY_MUTED};border:1px solid {TRAY_BORDER};"
            "border-radius:3px;padding:1px 4px;font-size:9px;font-weight:600;"
        )
        return chip

    def _scroll_host(self, parent):
        scroll = QScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        scroll.setWidget(body)
        return scroll, layout

    def _build_left_panel(self, parent) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        plan_frame, plan_layout = self._panel(panel, "SchedulePlanPanel")
        plan_header = QHBoxLayout()
        plan_header.setContentsMargins(0, 0, 0, 0)
        plan_title = CaptionLabel("PLAN", plan_frame)
        plan_title.setStyleSheet(f"color:{TRAY_MUTED};font-weight:600;")
        self.cache_chip = QLabel(plan_frame)
        plan_header.addWidget(plan_title)
        plan_header.addStretch(1)
        plan_header.addWidget(self.cache_chip)
        plan_layout.addLayout(plan_header)
        grid_host = QWidget(plan_frame)
        self.plan_layout = QGridLayout(grid_host)
        self.plan_layout.setContentsMargins(0, 2, 0, 0)
        self.plan_layout.setHorizontalSpacing(10)
        self.plan_layout.setVerticalSpacing(4)
        plan_layout.addWidget(grid_host)
        layout.addWidget(plan_frame)

        sources_frame, sources_layout = self._panel(panel, "ScheduleSourcesPanel")
        self.sources_segment = SegmentedWidget(sources_frame)
        self.sources_stack = QStackedWidget(sources_frame)

        sources_page = QWidget()
        sp_layout = QVBoxLayout(sources_page)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(4)
        self.sources_count_label = CaptionLabel("0 个对象", sources_page)
        self.sources_count_label.setStyleSheet(f"color:{TRAY_MUTED};")
        sources_scroll, self.sources_layout = self._scroll_host(sources_page)
        sp_layout.addWidget(self.sources_count_label)
        sp_layout.addWidget(sources_scroll, 1)

        history_page = QWidget()
        hp_layout = QVBoxLayout(history_page)
        hp_layout.setContentsMargins(0, 0, 0, 0)
        hp_layout.setSpacing(4)
        self.history_count_label = CaptionLabel("0 条事件", history_page)
        self.history_count_label.setStyleSheet(f"color:{TRAY_MUTED};")
        self.events_table = self.host.ui.create_log_table(history_page, ["时间", "类型", "结果", "详情"])
        self.events_table.setObjectName("ScheduleEventsTable")
        hp_layout.addWidget(self.history_count_label)
        hp_layout.addWidget(self.events_table, 1)

        self.sources_stack.addWidget(sources_page)
        self.sources_stack.addWidget(history_page)
        self.sources_segment.addItem("sources", "对象", onClick=lambda _checked=False: self.sources_stack.setCurrentIndex(0))
        self.sources_segment.addItem("history", "历史", onClick=lambda _checked=False: self.sources_stack.setCurrentIndex(1))
        self.sources_segment.setCurrentItem("sources")
        sources_layout.addWidget(self.sources_segment)
        sources_layout.addWidget(self.sources_stack, 1)
        layout.addWidget(sources_frame, 1)
        return panel

    def _build_run_panel(self, parent) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        run_frame, run_layout = self._panel(panel, "ScheduleRunPanel")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.run_id_chip = QLabel("-", run_frame)
        self.run_id_chip.setFont(tray_mono_font(8))
        self.run_id_chip.setStyleSheet(
            f"background:{TRAY_PANEL_BG};color:{TRAY_MUTED};border:1px solid {TRAY_BORDER};border-radius:3px;padding:1px 6px;"
        )
        self.run_trigger_label = CaptionLabel("触发: -", run_frame)
        self.run_trigger_label.setStyleSheet(f"color:{TRAY_MUTED};")
        self.run_elapsed_label = CaptionLabel("0s", run_frame)
        self.run_elapsed_label.setFont(tray_mono_font(8))
        self.run_elapsed_label.setStyleSheet(f"color:{TRAY_MUTED};")
        head.addWidget(self.run_id_chip)
        head.addWidget(self.run_trigger_label)
        head.addWidget(self.run_elapsed_label)
        head.addStretch(1)
        self.run_scanned_label = CaptionLabel("扫描 0", run_frame)
        self.run_scanned_label.setStyleSheet(f"color:{TRAY_MUTED};")
        self.run_pending_label = CaptionLabel("待处理 0", run_frame)
        self.run_pending_label.setStyleSheet(f"color:{SCHEDULE_ACCENT_INFO};")
        self.run_jobs_label = CaptionLabel("任务 0", run_frame)
        self.run_jobs_label.setStyleSheet(f"color:{SCHEDULE_ACCENT_OK};")
        self.run_meta_label = CaptionLabel("元数据 -", run_frame)
        self.run_meta_label.setStyleSheet(f"color:{TRAY_MUTED};")
        for widget in (self.run_scanned_label, self.run_pending_label, self.run_jobs_label, self.run_meta_label):
            widget.setFont(tray_mono_font(8))
            head.addWidget(widget)
        run_layout.addLayout(head)
        self.stage_rail = StageRail(run_frame)
        run_layout.addWidget(self.stage_rail)
        self.latest_banner = BodyLabel("-", run_frame)
        self.latest_banner.setWordWrap(True)
        self.latest_banner.setStyleSheet(
            f"background:#172554;color:{SCHEDULE_ACCENT_INFO};border:1px solid #1d4ed8;border-radius:4px;padding:3px 6px;"
        )
        run_layout.addWidget(self.latest_banner)
        layout.addWidget(run_frame)

        pending_frame, pending_layout = self._panel(panel, "SchedulePendingPanel", alt=True)
        pending_header = QHBoxLayout()
        pending_header.setContentsMargins(0, 0, 0, 0)
        pending_header.addWidget(StrongBodyLabel("待处理条目", pending_frame))
        pending_header.addStretch(1)
        self.pending_count_label = CaptionLabel("0 个", pending_frame)
        self.pending_count_label.setStyleSheet(f"color:{TRAY_MUTED};")
        pending_header.addWidget(self.pending_count_label)
        pending_layout.addLayout(pending_header)
        pending_scroll, self.pending_layout = self._scroll_host(pending_frame)
        pending_layout.addWidget(pending_scroll, 1)
        layout.addWidget(pending_frame, 1)
        return panel

    def _build_detail_panel(self, parent) -> QWidget:
        frame, layout = self._panel(parent, "ScheduleDetailPanel")
        layout.addWidget(StrongBodyLabel("条目详情", frame))
        self.detail_title = BodyLabel("-", frame)
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(f"color:{TRAY_TEXT};font-weight:600;")
        self.detail_source = CaptionLabel("-", frame)
        self.detail_source.setWordWrap(True)
        self.detail_source.setFont(tray_mono_font(8))
        self.detail_source.setStyleSheet(f"color:{TRAY_MUTED};")
        chips = QHBoxLayout()
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(4)
        self.detail_stage_chip = QLabel(frame)
        self.detail_status_chip = QLabel(frame)
        chips.addWidget(self.detail_stage_chip)
        chips.addWidget(self.detail_status_chip)
        chips.addStretch(1)
        pkl_title = CaptionLabel("PKL BOOKINFO", frame)
        pkl_title.setStyleSheet(f"color:{TRAY_MUTED};font-weight:600;")
        self.detail_pkl_label = CaptionLabel("-", frame)
        self.detail_pkl_label.setWordWrap(True)
        self.detail_pkl_label.setFont(tray_mono_font(8))
        self.detail_pkl_label.setStyleSheet(
            f"background:{TRAY_PANEL_BG};color:{TRAY_MUTED};border:1px solid {TRAY_BORDER};border-radius:4px;padding:4px;"
        )
        self.detail_open_source_btn = PushButton(FIF.LINK, "打开来源", frame)
        self.detail_open_source_btn.setEnabled(False)
        self.detail_open_source_btn.clicked.connect(lambda _checked=False: self.open_detail_source())
        self.detail_open_folder_btn = PushButton(FIF.FOLDER, "打开本地目录", frame)
        self.detail_open_folder_btn.setEnabled(False)
        self.detail_open_folder_btn.setToolTip("下载完成后可打开目录")
        self.detail_message = CaptionLabel("选择一个待处理条目查看 BookInfo 派生字段。", frame)
        self.detail_message.setWordWrap(True)
        self.detail_message.setStyleSheet(f"color:{TRAY_MUTED};")
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_source)
        layout.addLayout(chips)
        layout.addWidget(pkl_title)
        layout.addWidget(self.detail_pkl_label)
        layout.addWidget(self.detail_open_source_btn)
        layout.addWidget(self.detail_open_folder_btn)
        layout.addWidget(self.detail_message)
        layout.addStretch(1)
        return frame

    def _build_debug_panel(self, parent) -> QWidget:
        drawer, layout = self._panel(parent, "ScheduleDebugDrawer", alt=True)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(StrongBodyLabel("原始 Schedule Payload", drawer))
        header.addStretch(1)
        copy_button = TransparentToolButton(FIF.COPY, drawer)
        copy_button.setToolTip("复制已脱敏 Schedule debug 内容")
        copy_button.clicked.connect(
            lambda _checked=False: self.host.ui.copy_to_clipboard(self.debug_text.toPlainText() if self.debug_text is not None else "")
        )
        header.addWidget(copy_button)
        layout.addLayout(header)
        self.debug_text = TextEdit(drawer)
        self.debug_text.setObjectName("ScheduleDebugText")
        self.debug_text.setReadOnly(True)
        self.debug_text.setFont(tray_mono_font(8))
        self.debug_text.setMinimumHeight(90)
        layout.addWidget(self.debug_text)
        self.debug_drawer = drawer
        drawer.setVisible(self.debug_enabled)
        return drawer

    def set_debug_enabled(self, enabled: bool) -> None:
        self.debug_enabled = bool(enabled)
        if self.debug_drawer is not None:
            self.debug_drawer.setVisible(self.debug_enabled)
        self.host.dialog.refresh(rebuild_lists=True)

    def _apply_run_header(self, *, run_id, trigger, elapsed_sec, scanned, pending, jobs, meta, stage, latest, running, stages=None) -> None:
        host = self.host
        if self.run_id_chip is not None:
            self.run_id_chip.setText(host.ui.short_job_id(run_id) if run_id else "-")
        host.ui.set_label(self.run_trigger_label, f"触发: {trigger or '-'}")
        host.ui.set_label(self.run_elapsed_label, host.ui.duration_label(float(elapsed_sec) * 1000))
        host.ui.set_label(self.run_scanned_label, f"扫描 {scanned}")
        host.ui.set_label(self.run_pending_label, f"待处理 {pending}")
        host.ui.set_label(self.run_jobs_label, f"任务 {jobs}")
        host.ui.set_label(self.run_meta_label, "元数据 ✓" if meta else "元数据 -")
        if self.stage_rail is not None:
            if stages is not None:
                rail_stages = stages
            else:
                rail_stages = self.latest_presentation.stages if self.latest_presentation is not None else []
            self.stage_rail.set_stages(list(rail_stages), stage or "", running=running)
        host.ui.set_label(self.latest_banner, latest or "-")

    def _render_plan(self, presentation: SchedulePresentation) -> None:
        if self.plan_layout is None:
            return
        clear_layout(self.plan_layout)
        plan = presentation.plan
        if plan.mode == MODE_SUBSCRIBER:
            pairs = [
                ("模式", plan.mode_label),
                ("状态", plan.automation_label),
                ("拉取间隔", f"{plan.pull_interval_hours}h"),
                ("下次拉取", plan.next_run_at),
                ("订阅源", str(plan.follows)),
                ("自动下载", "开" if plan.auto_download else "关"),
            ]
        else:
            pairs = [
                ("模式", plan.mode_label),
                ("状态", plan.automation_label),
                ("检查时间", plan.timing),
                ("Publish BID", plan.publish_bid),
                ("作品", str(plan.enabled_books)),
                ("作者/标签", str(plan.enabled_features)),
            ]
        pairs.append(("缓存", f"{presentation.cache.status} ({presentation.cache.book_count})"))
        if plan.blocker:
            pairs.append(("阻塞原因", plan.blocker))
        if plan.blocker_action:
            pairs.append(("下一步", plan.blocker_action))
        for index, (key, value) in enumerate(pairs):
            row, column = divmod(index, 2)
            cell = QWidget()
            box = QVBoxLayout(cell)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(0)
            key_label = CaptionLabel(key, cell)
            key_label.setStyleSheet(f"color:{TRAY_MUTED};")
            value_label = CaptionLabel(str(value), cell)
            value_label.setStyleSheet(f"color:{TRAY_TEXT};")
            value_label.setWordWrap(True)
            box.addWidget(key_label)
            box.addWidget(value_label)
            self.plan_layout.addWidget(cell, row, column)
        if self.cache_chip is not None:
            self.host.ui.set_chip(self.cache_chip, self._cache_chip_status(presentation.cache.status))

    def _cache_chip_status(self, status: str) -> str:
        normalized = str(status or "").lower()
        if normalized == "ready":
            return "ready"
        if normalized == "error":
            return "failed"
        if normalized in {"degraded", "summary missing"}:
            return "starting"
        return "idle"

    def _render_sources(self, presentation: SchedulePresentation) -> None:
        if self.sources_layout is None:
            return
        clear_layout(self.sources_layout)
        sources = presentation.sources
        self.host.ui.set_label(self.sources_count_label, f"{len(sources)} 个对象")
        if not sources:
            empty = CaptionLabel(self._sources_empty_text(presentation))
            empty.setStyleSheet(f"color:{TRAY_MUTED};")
            empty.setWordWrap(True)
            self.sources_layout.addWidget(empty)
            self.sources_layout.addStretch(1)
            return
        for source in sources:
            self.sources_layout.addWidget(self._source_card(source))
        self.sources_layout.addStretch(1)

    def _sources_empty_text(self, presentation: SchedulePresentation) -> str:
        if presentation.plan.mode == MODE_SUBSCRIBER:
            return "还没有订阅源。请从主窗口进入工具箱 > 追更 / 订阅源，添加 follow bid。"
        return "还没有启用的追更对象。请从预览页勾选作品加入追更，或在主窗口追更配置里启用已有对象。"

    def _source_card(self, source) -> QWidget:
        card = QFrame()
        card.setObjectName("ScheduleSourceCard")
        card.setStyleSheet(
            f"#ScheduleSourceCard{{background:{SCHEDULE_CARD_BG};border:1px solid {TRAY_BORDER};border-radius:6px;}}"
            f"#ScheduleSourceCard:hover{{background:{SCHEDULE_CARD_BG_SEL};}}"
        )
        box = QVBoxLayout(card)
        box.setContentsMargins(8, 6, 8, 6)
        box.setSpacing(3)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self._site_badge(source.site, card))
        title = BodyLabel(source.title or source.locator or "-", card)
        title.setStyleSheet(f"color:{TRAY_TEXT};")
        top.addWidget(title, 1)
        enabled = CaptionLabel(self._source_status_label(source.status), card)
        enabled.setStyleSheet(f"color:{SCHEDULE_ACCENT_OK if source.enabled else TRAY_MUTED};")
        top.addWidget(enabled)
        box.addLayout(top)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(6)
        locator = CaptionLabel(source.locator or "-", card)
        locator.setStyleSheet(f"color:{TRAY_MUTED};")
        locator.setFont(tray_mono_font(8))
        bottom.addWidget(locator, 1)
        if source.pending_count:
            pending = CaptionLabel(f"{source.pending_count} 个待处理", card)
            pending.setStyleSheet(f"color:{SCHEDULE_ACCENT_INFO};")
        else:
            pending = CaptionLabel(source.latest or "最近记录", card)
            pending.setStyleSheet(f"color:{TRAY_MUTED};")
        bottom.addWidget(pending)
        box.addLayout(bottom)
        return card

    def _source_status_label(self, status: str) -> str:
        labels = {
            "enabled": "启用",
            "disabled": "停用",
            "following": "关注中",
            "unsupported": "不支持",
        }
        return labels.get(str(status or ""), str(status or "-"))

    def _render_pending(self, presentation: SchedulePresentation) -> None:
        if self.pending_layout is None:
            return
        clear_layout(self.pending_layout)
        items = presentation.pending_items
        self.detail_entries = [self._detail_entry(item) for item in items]
        self.host.ui.set_label(self.pending_count_label, f"{len(items)} 个")
        if not items:
            self.selected_index = -1
            empty = CaptionLabel("暂无待处理条目。可以手动执行一次检查，或等待下一次自动检查。")
            empty.setStyleSheet(f"color:{TRAY_MUTED};")
            empty.setWordWrap(True)
            self.pending_layout.addWidget(empty)
            self.pending_layout.addStretch(1)
            self._render_detail(None)
            return
        for index, item in enumerate(items):
            self.pending_layout.addWidget(self._pending_card(item, index))
        self.pending_layout.addStretch(1)
        if not 0 <= self.selected_index < len(items):
            self.selected_index = 0
        self._render_detail(self.detail_entries[self.selected_index])

    def _detail_entry(self, item) -> dict[str, str]:
        return {
            "title": item.title or "-",
            "episode": item.episode or "-",
            "site": item.site or "-",
            "status": item.status or "pending",
            "stage": item.stage or "-",
            "message": item.message or "-",
            "source_id": item.source_id or "-",
            "source_url": item.source_url or "",
            "cover_url": item.cover_url or "",
        }

    def _pending_card(self, item, index: int) -> QWidget:
        selected = index == self.selected_index
        card = ClickableFrame()
        card.setObjectName("SchedulePendingCard")
        bg = SCHEDULE_CARD_BG_SEL if selected else SCHEDULE_CARD_BG
        card.setStyleSheet(
            f"#SchedulePendingCard{{background:{bg};border:1px solid {TRAY_BORDER};border-radius:6px;}}"
            f"#SchedulePendingCard:hover{{background:{SCHEDULE_CARD_BG_SEL};}}"
        )
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card._on_click = lambda i=index: self.select_pending(i)
        row = QHBoxLayout(card)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(8)
        cover = QLabel("封面", card)
        cover.setFixedSize(36, 50)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet(
            f"background:{TRAY_COVER_BG};border:1px solid {TRAY_BORDER};border-radius:4px;color:{TRAY_MUTED};font-size:9px;"
        )
        if item.cover_url:
            self.host.server_panel.apply_cover(cover, item.cover_url)
        row.addWidget(cover)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title = BodyLabel(item.title or "-", card)
        title.setStyleSheet(f"color:{TRAY_TEXT};")
        episode = CaptionLabel(item.episode or "-", card)
        episode.setStyleSheet(f"color:{SCHEDULE_ACCENT_INFO};")
        title_box.addWidget(title)
        title_box.addWidget(episode)
        head.addLayout(title_box, 1)
        head.addWidget(self._site_badge(item.site, card))
        body.addLayout(head)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(6)
        message = CaptionLabel(item.message or item.stage or "-", card)
        message.setStyleSheet(f"color:{TRAY_MUTED};")
        bottom.addWidget(message, 1)
        open_button = TransparentToolButton(FIF.LINK, card)
        open_button.setFixedSize(22, 22)
        open_button.setToolTip("打开来源")
        open_button.setEnabled(bool(item.source_url))
        open_button.clicked.connect(lambda _checked=False, url=item.source_url: self.host.server_panel.open_url(url))
        details_button = TransparentToolButton(FIF.VIEW, card)
        details_button.setFixedSize(22, 22)
        details_button.setToolTip("查看详情")
        details_button.clicked.connect(lambda _checked=False, i=index: self.select_pending(i))
        bottom.addWidget(open_button)
        bottom.addWidget(details_button)
        body.addLayout(bottom)
        row.addLayout(body, 1)
        return card

    def select_pending(self, index: int) -> None:
        if not 0 <= index < len(self.detail_entries):
            return
        self.selected_index = index
        self._restyle_pending_cards(index)
        self._render_detail(self.detail_entries[index])

    def _restyle_pending_cards(self, selected_index: int) -> None:
        if self.pending_layout is None:
            return
        card_index = 0
        for i in range(self.pending_layout.count()):
            item = self.pending_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is None or widget.objectName() != "SchedulePendingCard":
                continue
            bg = SCHEDULE_CARD_BG_SEL if card_index == selected_index else SCHEDULE_CARD_BG
            widget.setStyleSheet(
                f"#SchedulePendingCard{{background:{bg};border:1px solid {TRAY_BORDER};border-radius:6px;}}"
                f"#SchedulePendingCard:hover{{background:{SCHEDULE_CARD_BG_SEL};}}"
            )
            card_index += 1

    def _render_detail(self, entry) -> None:
        host = self.host
        if self.detail_title is None:
            return
        if not entry:
            host.ui.set_label(self.detail_title, "-")
            host.ui.set_label(self.detail_source, "-")
            self.detail_stage_chip.setText("")
            self.detail_stage_chip.setStyleSheet("")
            self.detail_status_chip.setText("")
            self.detail_status_chip.setStyleSheet("")
            host.ui.set_label(self.detail_pkl_label, "-")
            self.detail_open_source_btn.setEnabled(False)
            host.ui.set_label(self.detail_message, "选择一个待处理条目查看 BookInfo 派生字段。")
            return
        host.ui.set_label(self.detail_title, entry.get("title") or "-")
        host.ui.set_label(self.detail_source, entry.get("source_id") or "-")
        host.ui.set_chip(self.detail_stage_chip, entry.get("stage") or "-")
        host.ui.set_chip(self.detail_status_chip, entry.get("status") or "pending")
        host.ui.set_label(
            self.detail_pkl_label,
            "\n".join(
                [
                    f"episode: {entry.get('episode') or '-'}",
                    f"site: {entry.get('site') or '-'}",
                    f"cover_ref: {entry.get('cover_url') or '-'}",
                    f"source: {entry.get('source_url') or '-'}",
                ]
            ),
        )
        self.detail_open_source_btn.setEnabled(bool(entry.get("source_url")))
        host.ui.set_label(self.detail_message, entry.get("message") or "-")

    def open_detail_source(self) -> None:
        if 0 <= self.selected_index < len(self.detail_entries):
            self.host.server_panel.open_url(self.detail_entries[self.selected_index].get("source_url") or "")

    def open_subscribe_guidance(self) -> None:
        box = MessageBox(
            "打开追更配置",
            "订阅配置由 SpiderGUI 主窗口管理。请打开主窗口，进入 工具箱 > 追更 / 订阅源；后台 Schedule 面板负责运行、状态和诊断，不直接编辑订阅配置。",
            self.host.manage_dialog,
        )
        box.exec()

    def clear_history(self) -> None:
        box = MessageBox("清空订阅运行历史", "确认清空全部订阅运行历史事件？不会取消正在运行的任务。", self.host.manage_dialog)
        if not box.exec():
            return
        self.host.schedule.event_log.clear()
        self.host.refresh_status(schedule_full=True)
        gc.collect()

    def _update_debug_text(self, presentation: SchedulePresentation) -> None:
        if self.debug_text is None:
            return
        if not (self.debug_enabled and self.debug_drawer is not None and self.debug_drawer.isVisible()):
            return
        payload = self._debug_text_payload(presentation)
        if payload == self.debug_last_text:
            return
        self.debug_last_text = payload
        bar = self.debug_text.verticalScrollBar()
        prev = bar.value() if bar is not None else 0
        at_bottom = bar is not None and prev >= bar.maximum()
        self.debug_text.setPlainText(payload)
        if bar is not None:
            bar.setValue(bar.maximum() if at_bottom else min(prev, bar.maximum()))

    def _debug_text_payload(self, presentation: SchedulePresentation) -> str:
        if not self.debug_enabled:
            return "Debug 已关闭。"
        return self.host.ui.redact(json.dumps(asdict(presentation), ensure_ascii=False, indent=2, default=str))

    def _event_row(self, entry: dict) -> list[str]:
        return [
            str(entry.get("ts", "")),
            str(entry.get("kind", "")),
            str(entry.get("result", "")),
            str(entry.get("detail", "")),
        ]
