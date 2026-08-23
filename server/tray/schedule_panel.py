from __future__ import annotations

import gc
import json
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
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

from server.tray.style import (
    accent_info_label_stylesheet,
    accent_ok_label_stylesheet,
    body_text_stylesheet,
    cover_placeholder_stylesheet,
    detail_title_stylesheet,
    install_tray_combo_menu_hardening,
    latest_banner_stylesheet,
    muted_label_stylesheet,
    pending_card_stylesheet,
    pkl_detail_stylesheet,
    run_id_chip_stylesheet,
    section_heading_stylesheet,
    site_badge_stylesheet,
    source_card_stylesheet,
)
from server.tray.ui_common import (
    ClickableFrame,
    StageRail,
    clear_layout,
    install_tray_fluent_tooltip,
    tray_mono_font,
)
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
        self.state_chip: QLabel | None = None
        self.next_label: QLabel | None = None
        self.run_button: PrimaryPushButton | None = None
        self.debug_switch: SwitchButton | None = None
        self.debug_enabled = False
        self.plan_layout: QGridLayout | None = None
        self.cache_chip: QLabel | None = None
        self.binding_combo: ComboBox | None = None
        self.catchup_combo: ComboBox | None = None
        self._binding_combo_guard = False
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
        self.work_segment: SegmentedWidget | None = None
        self.work_stack: QStackedWidget | None = None
        self.queue_layout: QVBoxLayout | None = None
        self.finish_layout: QVBoxLayout | None = None
        self.queue_count_label: QLabel | None = None
        self.finish_count_label: QLabel | None = None
        self.pending_layout: QVBoxLayout | None = None  # active list (queue or finish)
        self.pending_count_label: QLabel | None = None
        self.work_bucket: str = "queue"
        self.detail_title: QLabel | None = None
        self.detail_episode: QLabel | None = None
        self.detail_open_source_btn: PushButton | None = None
        self.detail_open_folder_btn: PushButton | None = None
        # Kept as None aliases so older refresh paths / tests never AttributeError.
        self.detail_status_chip: QLabel | None = None
        self.detail_source: QLabel | None = None
        self.detail_stage_chip: QLabel | None = None
        self.detail_pkl_label: QLabel | None = None
        self.detail_message: QLabel | None = None
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
        # presentation errors must reach tray/sys.excepthook — no local swallow.
        presentation = host.schedule.presentation(blocker=host.schedule_run_blocker())
        return [
            ("下次检查", presentation.plan.next_run_at),
            ("检查间隔", presentation.plan.timing),
            ("状态", presentation.plan.automation_label),
            ("缓存", f"{presentation.cache.status} ({presentation.cache.book_count})"),
            ("对象", len(presentation.sources)),
            (
                "章节",
                f"待下载 {sum(1 for item in presentation.pending_items if self._item_bucket(item) == 'queue')} / "
                f"已下载 {sum(1 for item in presentation.pending_items if self._item_bucket(item) == 'finish')}",
            ),
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
        # presentation / store / scheduler failures propagate to tray excepthook.
        presentation = host.schedule.presentation(blocker=host.schedule_run_blocker())
        self.latest_presentation = presentation
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
        layout = QHBoxLayout(band)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        title = StrongBodyLabel("订阅运行", band)
        self.state_chip = QLabel(band)
        self.next_label = CaptionLabel("Next -", band)
        self.next_label.setObjectName("TrayMutedLabel")
        self.next_label.setStyleSheet(muted_label_stylesheet())
        self.run_button = PrimaryPushButton(FIF.PLAY, "立刻执行", band)
        self.run_button.clicked.connect(lambda _checked=False: self.host.run_schedule_now())
        subscribe_button = PushButton(FIF.LINK, "打开追更配置", band)
        self._set_fluent_tooltip(subscribe_button, "订阅配置由 SpiderGUI 主窗口管理")
        subscribe_button.clicked.connect(lambda _checked=False: self.open_subscribe_guidance())
        refresh_button = TransparentToolButton(FIF.SYNC, band)
        self._set_fluent_tooltip(refresh_button, "刷新订阅运行状态")
        refresh_button.clicked.connect(lambda _checked=False: self.host.refresh_status(schedule_full=True))
        clear_button = TransparentToolButton(FIF.BROOM, band)
        self._set_fluent_tooltip(clear_button, "清空订阅运行历史（确认后执行）")
        clear_button.clicked.connect(lambda _checked=False: self.clear_history())
        self.debug_switch = SwitchButton(band)
        self.debug_switch.setText("Debug")
        self.debug_switch.checkedChanged.connect(self.set_debug_enabled)
        layout.addWidget(title)
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
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        return frame, layout

    def _site_badge(self, site: str, parent) -> QLabel:
        chip = QLabel((site or "?").upper(), parent)
        chip.setObjectName("TraySiteBadge")
        chip.setStyleSheet(site_badge_stylesheet())
        return chip

    def _scroll_host(self, parent):
        scroll = QScrollArea(parent)
        scroll.setObjectName("TrayTransparentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("TrayTransparentBody")
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
        plan_title.setObjectName("TrayMutedLabel")
        plan_title.setStyleSheet(section_heading_stylesheet())
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

        # Binding profile = which subscription_*.yml tray executes.
        binding_row = QHBoxLayout()
        binding_row.setContentsMargins(0, 4, 0, 0)
        binding_row.setSpacing(8)
        binding_label = CaptionLabel("绑定", plan_frame)
        binding_label.setObjectName("TrayMutedLabel")
        binding_label.setStyleSheet(muted_label_stylesheet())
        self.binding_combo = ComboBox(plan_frame)
        self.binding_combo.setMinimumWidth(140)
        self.binding_combo.setObjectName("ScheduleBindingCombo")
        install_tray_combo_menu_hardening(self.binding_combo)
        self._set_fluent_tooltip(self.binding_combo, "切换要执行的 subscription_*.yml")
        self.binding_combo.currentIndexChanged.connect(self._on_binding_changed)
        binding_row.addWidget(binding_label)
        binding_row.addWidget(self.binding_combo, 1)
        plan_layout.addLayout(binding_row)

        # 后巡查 = tray-global catch-up (not SidePanel, not per-book).
        catchup_row = QHBoxLayout()
        catchup_row.setContentsMargins(0, 4, 0, 0)
        catchup_row.setSpacing(8)
        catchup_label = CaptionLabel("后巡查", plan_frame)
        catchup_label.setObjectName("TrayMutedLabel")
        catchup_label.setStyleSheet(muted_label_stylesheet())
        self.catchup_combo = ComboBox(plan_frame)
        self.catchup_combo.setMinimumWidth(120)
        self.catchup_combo.setObjectName("ScheduleCatchupCombo")
        install_tray_combo_menu_hardening(self.catchup_combo)
        self._set_fluent_tooltip(self.catchup_combo, "后巡查间隔（托盘全局，非单本）")
        from utils.subscription.schema import CATCHUP_PRESET_ITEMS
        from utils.subscription.store import get_subscription_catchup_preset

        for preset_key, preset_label in CATCHUP_PRESET_ITEMS:
            self.catchup_combo.addItem(preset_label, userData=preset_key)
        current_catchup = get_subscription_catchup_preset()
        for index in range(self.catchup_combo.count()):
            if self.catchup_combo.itemData(index) == current_catchup:
                self.catchup_combo.setCurrentIndex(index)
                break
        self.catchup_combo.currentIndexChanged.connect(self._on_catchup_changed)
        catchup_row.addWidget(catchup_label)
        catchup_row.addWidget(self.catchup_combo, 1)
        plan_layout.addLayout(catchup_row)

        layout.addWidget(plan_frame)

        sources_frame, sources_layout = self._panel(panel, "ScheduleSourcesPanel")
        self.sources_segment = SegmentedWidget(sources_frame)
        self.sources_stack = QStackedWidget(sources_frame)

        sources_page = QWidget()
        sp_layout = QVBoxLayout(sources_page)
        sp_layout.setContentsMargins(0, 0, 0, 0)
        sp_layout.setSpacing(4)
        self.sources_count_label = CaptionLabel("0 个对象", sources_page)
        self.sources_count_label.setObjectName("TrayMutedLabel")
        self.sources_count_label.setStyleSheet(muted_label_stylesheet())
        sources_scroll, self.sources_layout = self._scroll_host(sources_page)
        sp_layout.addWidget(self.sources_count_label)
        sp_layout.addWidget(sources_scroll, 1)

        history_page = QWidget()
        hp_layout = QVBoxLayout(history_page)
        hp_layout.setContentsMargins(0, 0, 0, 0)
        hp_layout.setSpacing(4)
        self.history_count_label = CaptionLabel("0 条事件", history_page)
        self.history_count_label.setObjectName("TrayMutedLabel")
        self.history_count_label.setStyleSheet(muted_label_stylesheet())
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
        self.run_id_chip.setObjectName("TrayRunIdChip")
        self.run_id_chip.setFont(tray_mono_font(8))
        self.run_id_chip.setStyleSheet(run_id_chip_stylesheet())
        self.run_trigger_label = CaptionLabel("触发: -", run_frame)
        self.run_trigger_label.setObjectName("TrayMutedLabel")
        self.run_trigger_label.setStyleSheet(muted_label_stylesheet())
        self.run_elapsed_label = CaptionLabel("0s", run_frame)
        self.run_elapsed_label.setObjectName("TrayMutedLabel")
        self.run_elapsed_label.setFont(tray_mono_font(8))
        self.run_elapsed_label.setStyleSheet(muted_label_stylesheet())
        head.addWidget(self.run_id_chip)
        head.addWidget(self.run_trigger_label)
        head.addWidget(self.run_elapsed_label)
        head.addStretch(1)
        self.run_scanned_label = CaptionLabel("扫描 0", run_frame)
        self.run_scanned_label.setObjectName("TrayMutedLabel")
        self.run_scanned_label.setStyleSheet(muted_label_stylesheet())
        self.run_pending_label = CaptionLabel("待处理 0", run_frame)
        self.run_pending_label.setObjectName("TrayAccentInfoLabel")
        self.run_pending_label.setStyleSheet(accent_info_label_stylesheet())
        self.run_jobs_label = CaptionLabel("任务 0", run_frame)
        self.run_jobs_label.setObjectName("TrayAccentOkLabel")
        self.run_jobs_label.setStyleSheet(accent_ok_label_stylesheet())
        self.run_meta_label = CaptionLabel("元数据 -", run_frame)
        self.run_meta_label.setObjectName("TrayMutedLabel")
        self.run_meta_label.setStyleSheet(muted_label_stylesheet())
        for widget in (self.run_scanned_label, self.run_pending_label, self.run_jobs_label, self.run_meta_label):
            widget.setFont(tray_mono_font(8))
            head.addWidget(widget)
        run_layout.addLayout(head)
        self.stage_rail = StageRail(run_frame)
        run_layout.addWidget(self.stage_rail)
        self.latest_banner = BodyLabel("-", run_frame)
        self.latest_banner.setObjectName("TrayLatestBanner")
        self.latest_banner.setWordWrap(True)
        self.latest_banner.setStyleSheet(latest_banner_stylesheet())
        run_layout.addWidget(self.latest_banner)
        layout.addWidget(run_frame)

        work_frame, work_layout = self._panel(panel, "SchedulePendingPanel", alt=True)
        self.work_segment = SegmentedWidget(work_frame)
        self.work_stack = QStackedWidget(work_frame)

        queue_page = QWidget()
        queue_box = QVBoxLayout(queue_page)
        queue_box.setContentsMargins(0, 0, 0, 0)
        queue_box.setSpacing(4)
        # Count only — bucket name is already the Segmented label (no "N 个已落地" echo).
        self.queue_count_label = CaptionLabel("0", queue_page)
        self.queue_count_label.setObjectName("TrayMutedLabel")
        self.queue_count_label.setStyleSheet(muted_label_stylesheet())
        queue_scroll, self.queue_layout = self._scroll_host(queue_page)
        queue_box.addWidget(self.queue_count_label)
        queue_box.addWidget(queue_scroll, 1)

        finish_page = QWidget()
        finish_box = QVBoxLayout(finish_page)
        finish_box.setContentsMargins(0, 0, 0, 0)
        finish_box.setSpacing(4)
        self.finish_count_label = CaptionLabel("0", finish_page)
        self.finish_count_label.setObjectName("TrayMutedLabel")
        self.finish_count_label.setStyleSheet(muted_label_stylesheet())
        finish_scroll, self.finish_layout = self._scroll_host(finish_page)
        finish_box.addWidget(self.finish_count_label)
        finish_box.addWidget(finish_scroll, 1)

        self.work_stack.addWidget(queue_page)
        self.work_stack.addWidget(finish_page)
        self.work_segment.addItem(
            "queue",
            "待下载",
            onClick=lambda _checked=False: self._select_work_bucket("queue"),
        )
        self.work_segment.addItem(
            "finish",
            "已下载",
            onClick=lambda _checked=False: self._select_work_bucket("finish"),
        )
        self.work_segment.setCurrentItem("queue")
        self.pending_layout = self.queue_layout
        self.pending_count_label = self.queue_count_label
        work_layout.addWidget(self.work_segment)
        work_layout.addWidget(self.work_stack, 1)
        layout.addWidget(work_frame, 1)
        return panel

    def _build_detail_panel(self, parent) -> QWidget:
        """Right rail: identity + actions. Bucket (待下载/已下载) already owns status."""
        frame, layout = self._panel(parent, "ScheduleDetailPanel")
        layout.addWidget(StrongBodyLabel("详情", frame))
        self.detail_title = BodyLabel("-", frame)
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(detail_title_stylesheet())
        self.detail_episode = CaptionLabel("", frame)
        self.detail_episode.setObjectName("TrayMutedLabel")
        self.detail_episode.setStyleSheet(muted_label_stylesheet())
        self.detail_episode.setVisible(False)
        self.detail_status_chip = None
        self.detail_open_source_btn = PushButton(FIF.LINK, "打开来源", frame)
        self.detail_open_source_btn.setEnabled(False)
        self.detail_open_source_btn.clicked.connect(lambda _checked=False: self.open_detail_source())
        self.detail_open_folder_btn = PushButton(FIF.FOLDER, "打开本地目录", frame)
        self.detail_open_folder_btn.setEnabled(False)
        self.detail_open_folder_btn.clicked.connect(lambda _checked=False: self.open_detail_folder())
        self._set_fluent_tooltip(self.detail_open_source_btn, "在浏览器打开来源页")
        self._set_fluent_tooltip(self.detail_open_folder_btn, "打开本地章节目录")
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_episode)
        layout.addWidget(self.detail_open_source_btn)
        layout.addWidget(self.detail_open_folder_btn)
        layout.addStretch(1)
        return frame

    def _build_debug_panel(self, parent) -> QWidget:
        drawer, layout = self._panel(parent, "ScheduleDebugDrawer", alt=True)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(StrongBodyLabel("原始 Schedule Payload", drawer))
        header.addStretch(1)
        copy_button = TransparentToolButton(FIF.COPY, drawer)
        self._set_fluent_tooltip(copy_button, "复制已脱敏 Schedule debug 内容")
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
        host.ui.set_label(self.run_pending_label, f"章节 {pending}")
        host.ui.set_label(self.run_jobs_label, f"任务 {jobs}")
        host.ui.set_label(self.run_meta_label, "元数据 ✓" if meta else "元数据 -")
        if self.stage_rail is not None:
            if stages is not None:
                rail_stages = stages
            else:
                rail_stages = self.latest_presentation.stages if self.latest_presentation is not None else []
            self.stage_rail.set_stages(list(rail_stages), stage or "", running=running)
        host.ui.set_label(self.latest_banner, latest or "-")

    def _on_catchup_changed(self, *_args) -> None:
        if self.catchup_combo is None:
            return
        preset = self.catchup_combo.currentData()
        if preset is None:
            return
        from utils.subscription.store import set_subscription_catchup_preset

        # Invalid preset / qconfig write failures must propagate to tray excepthook.
        set_subscription_catchup_preset(str(preset))
        self.host.refresh_status(schedule_full=True)

    def _on_binding_changed(self, *_args) -> None:
        if self._binding_combo_guard or self.binding_combo is None:
            return
        name = self.binding_combo.currentData()
        if name is None:
            return
        from utils.subscription import (
            get_active_subscription_customname,
            set_active_subscription_customname,
        )

        wanted = str(name).strip()
        if not wanted or wanted == get_active_subscription_customname():
            return
        set_active_subscription_customname(wanted)
        self.host.schedule.rebind_active_store()
        self.host.refresh_status(schedule_full=True)

    def _sync_binding_combo(self, presentation: SchedulePresentation) -> None:
        if self.binding_combo is None:
            return
        from utils.subscription import (
            get_active_subscription_customname,
            list_subscription_customnames,
        )

        names = list(list_subscription_customnames(include_default=True))
        active = get_active_subscription_customname()
        # Prefer active name even if list is momentarily empty (cold dir).
        if active and active not in names:
            names.insert(0, active)
        current_data = [
            str(self.binding_combo.itemData(index) or "")
            for index in range(self.binding_combo.count())
        ]
        self._binding_combo_guard = True
        try:
            if current_data != names:
                self.binding_combo.clear()
                for name in names:
                    # Display short profile id; full yml name is obvious from convention.
                    self.binding_combo.addItem(name, userData=name)
            target_index = 0
            for index in range(self.binding_combo.count()):
                if str(self.binding_combo.itemData(index) or "") == active:
                    target_index = index
                    break
            if self.binding_combo.currentIndex() != target_index:
                self.binding_combo.setCurrentIndex(target_index)
        finally:
            self._binding_combo_guard = False

    def _render_plan(self, presentation: SchedulePresentation) -> None:
        self._sync_binding_combo(presentation)
        if self.plan_layout is None:
            return
        clear_layout(self.plan_layout)
        plan = presentation.plan
        pairs = [
            ("状态", plan.automation_label),
            ("检查日/后巡查", plan.timing),
            ("下次检查", plan.next_run_at),
            ("配置来源", plan.config_owner),
            ("作品", str(plan.enabled_books)),
            ("作者/标签", str(plan.enabled_features)),
            ("订阅源", str(plan.follows)),
            ("Publish BID", plan.publish_bid),
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
            key_label.setObjectName("TrayMutedLabel")
            key_label.setStyleSheet(muted_label_stylesheet())
            value_label = CaptionLabel(str(value), cell)
            value_label.setStyleSheet(body_text_stylesheet())
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
            empty.setObjectName("TrayMutedLabel")
            empty.setStyleSheet(muted_label_stylesheet())
            empty.setWordWrap(True)
            self.sources_layout.addWidget(empty)
            self.sources_layout.addStretch(1)
            return
        for source in sources:
            self.sources_layout.addWidget(self._source_card(source))
        self.sources_layout.addStretch(1)

    def _sources_empty_text(self, presentation: SchedulePresentation) -> str:
        profile = ""
        owner = str(presentation.plan.config_owner or "")
        if "«" in owner and "»" in owner:
            profile = owner.split("«", 1)[1].split("»", 1)[0]
        if profile:
            return (
                f"绑定 «{profile}» 的 subscription_*.yml 没有启用书目。"
                "请在追更工作台选中卡片，用 SidePanel 启用并保存周期（写入 yml）；"
                "tray 只执行 yml，不会扫描整库收藏。"
            )
        return (
            "当前 binding 的 yml 没有启用书。"
            "请打开追更工作台 SidePanel 配置并保存到 subscription_*.yml。"
        )

    def _source_card(self, source) -> QWidget:
        # Left column is narrow (~1/4 dialog). Elide budgets stay tight and fixed.
        _SOURCE_TITLE_ELIDE = 112
        _SOURCE_LOCATOR_ELIDE = 96
        _SOURCE_SLOT_ELIDE = 72

        card = QFrame()
        card.setObjectName("ScheduleSourceCard")
        card.setStyleSheet(source_card_stylesheet())
        box = QVBoxLayout(card)
        box.setContentsMargins(8, 6, 8, 6)
        box.setSpacing(3)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self._site_badge(source.site, card))
        title = BodyLabel("-", card)
        title.setStyleSheet(body_text_stylesheet())
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._set_elided_label(
            title,
            source.title or source.locator or "-",
            max_width=_SOURCE_TITLE_ELIDE,
        )
        top.addWidget(title, 1)
        enabled = CaptionLabel(self._source_status_label(source.status), card)
        enabled.setStyleSheet(accent_ok_label_stylesheet() if source.enabled else muted_label_stylesheet())
        top.addWidget(enabled)
        box.addLayout(top)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(6)
        locator = CaptionLabel("-", card)
        locator.setObjectName("TrayMutedLabel")
        locator.setStyleSheet(muted_label_stylesheet())
        locator.setFont(tray_mono_font(8))
        locator.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._set_elided_label(
            locator,
            source.locator or "-",
            max_width=_SOURCE_LOCATOR_ELIDE,
        )
        bottom.addWidget(locator, 1)
        # Right meta is the CheckSlot fingerprint (刊期), never a pending-count rewrite.
        slot_text = str(source.latest or "").strip() or "—"
        slot_label = CaptionLabel(slot_text, card)
        slot_label.setObjectName("TrayMutedLabel")
        slot_label.setFont(tray_mono_font(8))
        slot_label.setStyleSheet(muted_label_stylesheet())
        slot_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._set_fluent_tooltip(slot_label, slot_text)
        # Fixed-ish budget so long fingerprints elide without eating the title column.
        metrics = QFontMetrics(slot_label.font())
        slot_label.setText(
            metrics.elidedText(slot_text, Qt.TextElideMode.ElideRight, _SOURCE_SLOT_ELIDE)
        )
        bottom.addWidget(slot_label)
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

    def _select_work_bucket(self, bucket: str) -> None:
        name = "finish" if str(bucket or "") == "finish" else "queue"
        self.work_bucket = name
        if self.work_stack is not None:
            self.work_stack.setCurrentIndex(1 if name == "finish" else 0)
        if self.work_segment is not None:
            self.work_segment.setCurrentItem(name)
        self.pending_layout = self.finish_layout if name == "finish" else self.queue_layout
        self.pending_count_label = (
            self.finish_count_label if name == "finish" else self.queue_count_label
        )
        if self.latest_presentation is not None:
            self._render_pending(self.latest_presentation)

    def _render_pending(self, presentation: SchedulePresentation) -> None:
        if self.queue_layout is None or self.finish_layout is None:
            return
        all_items = list(presentation.pending_items or [])
        queue_items = [item for item in all_items if self._item_bucket(item) == "queue"]
        finish_items = [item for item in all_items if self._item_bucket(item) == "finish"]
        self.host.ui.set_label(self.queue_count_label, str(len(queue_items)))
        self.host.ui.set_label(self.finish_count_label, str(len(finish_items)))

        active_items = finish_items if self.work_bucket == "finish" else queue_items
        self.detail_entries = [self._detail_entry(item) for item in active_items]
        self.pending_layout = self.finish_layout if self.work_bucket == "finish" else self.queue_layout
        self.pending_count_label = (
            self.finish_count_label if self.work_bucket == "finish" else self.queue_count_label
        )

        for layout in (self.queue_layout, self.finish_layout):
            clear_layout(layout)

        self._fill_work_list(
            self.queue_layout,
            queue_items,
            empty_text="空",
            bucket="queue",
        )
        self._fill_work_list(
            self.finish_layout,
            finish_items,
            empty_text="空",
            bucket="finish",
        )

        if not active_items:
            self.selected_index = -1
            self._render_detail(None)
            return
        if not 0 <= self.selected_index < len(active_items):
            self.selected_index = 0
        self._render_detail(self.detail_entries[self.selected_index])

    def _item_bucket(self, item) -> str:
        status = str(getattr(item, "status", "") or "").strip().casefold()
        local_path = str(getattr(item, "local_path", "") or "").strip()
        if status in {"finished", "done", "complete", "completed", "ok", "submitted"} or local_path:
            return "finish"
        return "queue"

    def _fill_work_list(self, layout, items, *, empty_text: str, bucket: str) -> None:
        if layout is None:
            return
        if not items:
            empty = CaptionLabel(empty_text)
            empty.setObjectName("TrayMutedLabel")
            empty.setStyleSheet(muted_label_stylesheet())
            empty.setWordWrap(True)
            layout.addWidget(empty)
            layout.addStretch(1)
            return
        for index, item in enumerate(items):
            # Cards only selectable when their bucket is active.
            card_index = index if bucket == self.work_bucket else -1
            layout.addWidget(self._pending_card(item, card_index))
        layout.addStretch(1)

    def _detail_entry(self, item) -> dict[str, str]:
        local_path = str(getattr(item, "local_path", "") or "").strip()
        cover = str(
            getattr(item, "local_cover_path", "")
            or getattr(item, "cover_url", "")
            or ""
        ).strip()
        status = str(item.status or "queued")
        if local_path:
            status = "finished"
        return {
            "title": item.title or "-",
            "episode": item.episode or "-",
            "site": item.site or "-",
            "status": status,
            "stage": item.stage or "-",
            "message": item.message or "-",
            "source_id": item.source_id or "-",
            "source_url": item.source_url or "",
            "cover_url": cover,
            "local_path": local_path,
        }

    def _pending_card(self, item, index: int) -> QWidget:
        # Center column is wider than left objects list — use a looser elide budget.
        _WORK_TITLE_ELIDE = 220
        _WORK_EPISODE_ELIDE = 180

        selected = index >= 0 and index == self.selected_index
        card = ClickableFrame()
        card.setObjectName("SchedulePendingCard")
        card.setStyleSheet(pending_card_stylesheet(selected=selected))
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        if index >= 0:
            card._on_click = lambda i=index: self.select_pending(i)
        row = QHBoxLayout(card)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(8)
        cover = QLabel("封面", card)
        cover.setObjectName("TrayCoverPlaceholderSmall")
        cover.setFixedSize(36, 50)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet(cover_placeholder_stylesheet(small=True))
        cover_ref = str(
            getattr(item, "local_cover_path", "") or getattr(item, "cover_url", "") or ""
        ).strip()
        if cover_ref:
            self.host.server_panel.apply_cover(cover, cover_ref)
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
        book_title = str(item.title or "").strip()
        episode_name = str(item.episode or "").strip()
        primary_text = book_title or episode_name or "-"
        secondary_text = (
            episode_name if book_title and episode_name and episode_name != book_title else ""
        )
        title = BodyLabel("-", card)
        title.setStyleSheet(body_text_stylesheet())
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._set_elided_label(title, primary_text, max_width=_WORK_TITLE_ELIDE)
        title_box.addWidget(title)
        if secondary_text:
            episode = CaptionLabel("-", card)
            episode.setObjectName("TrayAccentInfoLabel")
            episode.setStyleSheet(accent_info_label_stylesheet())
            episode.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._set_elided_label(episode, secondary_text, max_width=_WORK_EPISODE_ELIDE)
            title_box.addWidget(episode)
        head.addLayout(title_box, 1)
        head.addWidget(self._site_badge(item.site, card))
        body.addLayout(head)
        row.addLayout(body, 1)
        return card

    def select_pending(self, index: int) -> None:
        if not 0 <= index < len(self.detail_entries):
            return
        self.selected_index = index
        self._restyle_pending_cards(index)
        self._render_detail(self.detail_entries[index])

    def _restyle_pending_cards(self, selected_index: int) -> None:
        layout = self.pending_layout
        if layout is None:
            return
        card_index = 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is None or widget.objectName() != "SchedulePendingCard":
                continue
            widget.setStyleSheet(pending_card_stylesheet(selected=card_index == selected_index))
            card_index += 1

    def _set_fluent_tooltip(self, widget, text: str) -> None:
        """Theme-aware Fluent tooltip; bubble is not parented under ManageDialog."""
        install_tray_fluent_tooltip(widget, text)

    def _set_elided_label(self, label: QLabel, full_text: str, *, max_width: int | None = None) -> None:
        """Elide with an explicit pixel budget.

        Callers must pass different ``max_width`` for left objects vs center work
        lists — the two columns are not the same width.
        """
        text = str(full_text or "").strip() or "-"
        self._set_fluent_tooltip(label, text)
        width = int(max_width or 0)
        if width <= 0:
            raise ValueError("_set_elided_label requires max_width (column-specific budget)")
        metrics = QFontMetrics(label.font())
        label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, width))

    def _render_detail(self, entry) -> None:
        """Identity + actions only. Status is the Segmented bucket, not a badge."""
        host = self.host
        if self.detail_title is None:
            return
        if not entry:
            host.ui.set_label(self.detail_title, "未选择")
            if self.detail_episode is not None:
                self.detail_episode.setVisible(False)
                host.ui.set_label(self.detail_episode, "")
            if self.detail_open_source_btn is not None:
                self.detail_open_source_btn.setEnabled(False)
                self._set_fluent_tooltip(self.detail_open_source_btn, "")
            if self.detail_open_folder_btn is not None:
                self.detail_open_folder_btn.setEnabled(False)
                self._set_fluent_tooltip(self.detail_open_folder_btn, "")
            return

        book_title = str(entry.get("title") or "").strip() or "-"
        episode_text = str(entry.get("episode") or "").strip()
        host.ui.set_label(self.detail_title, book_title)
        if self.detail_episode is not None:
            if episode_text and episode_text != book_title:
                host.ui.set_label(self.detail_episode, episode_text)
                self.detail_episode.setVisible(True)
            else:
                host.ui.set_label(self.detail_episode, "")
                self.detail_episode.setVisible(False)

        local_path = str(entry.get("local_path") or "").strip()
        source_url = str(entry.get("source_url") or "").strip()

        if self.detail_open_source_btn is not None:
            self.detail_open_source_btn.setEnabled(bool(source_url))
            self._set_fluent_tooltip(self.detail_open_source_btn, source_url)
        if self.detail_open_folder_btn is not None:
            self.detail_open_folder_btn.setEnabled(bool(local_path))
            self._set_fluent_tooltip(self.detail_open_folder_btn, local_path)

    def open_detail_source(self) -> None:
        if 0 <= self.selected_index < len(self.detail_entries):
            self.host.server_panel.open_url(self.detail_entries[self.selected_index].get("source_url") or "")

    def open_detail_folder(self) -> None:
        if not 0 <= self.selected_index < len(self.detail_entries):
            return
        local_path = str(self.detail_entries[self.selected_index].get("local_path") or "").strip()
        if local_path:
            self.host.server_panel.open_path(local_path)

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
