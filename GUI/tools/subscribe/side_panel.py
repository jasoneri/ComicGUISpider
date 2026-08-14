# -*- coding: utf-8 -*-
"""Subscribe SidePanel owner — card-config + profile binding + follows/publish chrome."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    EditableComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    StrongBodyLabel,
    TeachingTipTailPosition,
    TimePicker,
    ToolButton,
    TransparentTogglePushButton,
    TransparentToolButton,
    TransparentToggleToolButton,
)

from GUI.uic.qfluent.components.flyout_kit import CustomTeachingTip
from GUI.uic.qfluent.components.icons import CgsIcon
from GUI.uic.qfluent.components.site_toggle_grid import SiteToggleGrid
from utils.subscription import (
    DEFAULT_CUSTOMNAME,
    DEFAULT_TZ_OFFSET,
    BookEntry,
    CheckSlot,
    FollowEntry,
    VALID_TZ_OFFSETS,
    format_tz_offset_label,
    format_tz_offset_menu_text,
    list_subscription_customnames,
    normalize_site_proxy_key,
    normalize_tz_offset,
    resolve_default_weekdays,
    resolve_provider_proxy_policy,
    set_active_subscription_customname,
    site_proxy_enabled,
)
from utils.subscription.library import LocalLibraryStore
from variables import SPIDERS, SPIDERS_LABELS

from .card import SubscribeCard
from .common import WEEKDAY_IDS, subscribe_site_indexes

if TYPE_CHECKING:
    from .window import SubscribeWindow


class SubscribeSidePanel(QFrame):
    """Side rail: selected-card CheckSlot + whole-library binding editor (yml SSoT)."""

    def __init__(self, host: "SubscribeWindow", parent: QWidget | None = None):
        super().__init__(parent)
        self._host = host
        self._loading = False
        self._side_dirty = False
        self._card_check_inherits = True
        self._card_check_draft: CheckSlot | None = None
        self._site_proxy_tip = None
        self._profile_default_expanded = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("SubscribeSidePanel")
        self.setFixedWidth(300)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(10)

        # ========== CardConfFrame (TOP of SidePanel — QSS section) ==========
        self.card_conf_frame = QFrame(self)
        self.card_conf_frame.setObjectName("SubscribeCardConfFrame")
        # Maximum vertical: content-sized; never steal stretch from GlobalFrame.
        self.card_conf_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.card_conf_frame.setMaximumHeight(220)
        card_conf_layout = QVBoxLayout(self.card_conf_frame)
        card_conf_layout.setContentsMargins(10, 10, 10, 10)
        card_conf_layout.setSpacing(8)

        card_conf_layout.addWidget(StrongBodyLabel("调度周期", self.card_conf_frame))

        t_row = QHBoxLayout()
        t_row.setSpacing(6)
        self.card_conf_title = BodyLabel("—", self.card_conf_frame)
        self.card_conf_title.setObjectName("SubscribeCardConfTitle")
        # Single-line only: word-wrap + long titles inflate sizeHint and blow CardConfFrame
        # apart from GlobalFrame (side-panel section gap). Full title lives in tooltip.
        self.card_conf_title.setWordWrap(False)
        self.card_conf_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.card_conf_title.setFixedHeight(22)
        self.card_conf_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        t_row.addWidget(self.card_conf_title, 1)
        self.bookJoinBtn = TransparentToggleToolButton(CgsIcon.TOOL_RSS, self.card_conf_frame)
        self.bookJoinBtn.setObjectName("SubscribeBookJoinBtn")
        self.bookJoinBtn.setEnabled(False)
        self.bookJoinBtn.toggled.connect(self._mark_side_dirty)
        t_row.addWidget(self.bookJoinBtn, 0, Qt.AlignmentFlag.AlignTop)
        card_conf_layout.addLayout(t_row)

        self.weekday_button_group = QButtonGroup(self.card_conf_frame)
        self.weekday_button_group.setExclusive(False)
        self.weekday_buttons: dict[str, TransparentTogglePushButton] = {}
        weekday_box = QWidget(self.card_conf_frame)
        weekday_box.setObjectName("SubscribeCardWeekdayBox")
        weekday_layout = QHBoxLayout(weekday_box)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.setSpacing(4)
        for weekday_id in WEEKDAY_IDS:
            button = TransparentTogglePushButton(weekday_box)
            button.setObjectName(f"SubscribeCardWeekdayBtn{weekday_id}")
            button.setText(str(weekday_id))
            button.setCheckable(True)
            button.setMinimumSize(36, 36)
            button.setEnabled(False)
            button.toggled.connect(self._on_card_slot_field_edited)
            self.weekday_button_group.addButton(button, int(weekday_id))
            self.weekday_buttons[str(weekday_id)] = button
            weekday_layout.addWidget(button)
        card_conf_layout.addWidget(weekday_box)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(0)
        self.time_picker = TimePicker(self.card_conf_frame, showSeconds=False)
        self.time_picker.setObjectName("SubscribeCardTimePicker")
        for column_button in getattr(self.time_picker, "columns", []) or []:
            column_button.setFixedWidth(100)
        self.time_picker.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.time_picker.adjustSize()
        self.time_picker.setEnabled(False)
        self.time_picker.timeChanged.connect(self._on_card_slot_field_edited)
        time_row.addWidget(self.time_picker, 0, Qt.AlignVCenter)
        self._tz_gap = QWidget(self.card_conf_frame)
        self._tz_gap.setObjectName("SubscribeTzGap")
        self._tz_gap.setFixedWidth(10)
        self._tz_gap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        time_row.addWidget(self._tz_gap, 0)
        self.tz_offset = DEFAULT_TZ_OFFSET
        self.tz_btn = ToolButton(self.card_conf_frame)
        self.tz_btn.setObjectName("SubscribeTzOffsetBtn")
        self.tz_btn.setEnabled(False)
        self.tz_btn.clicked.connect(self._open_tz_offset_menu)
        self._sync_tz_offset_button()
        time_row.addWidget(self.tz_btn, 0, Qt.AlignVCenter)
        time_row.addStretch(1)
        card_conf_layout.addLayout(time_row)

        self.card_reset_check_btn = PushButton("恢复默认周期", self.card_conf_frame)
        self.card_reset_check_btn.setObjectName("SubscribeCardResetCheckBtn")
        self.card_reset_check_btn.setEnabled(False)
        self.card_reset_check_btn.clicked.connect(self._on_card_reset_check_clicked)
        card_reset_row = QHBoxLayout()
        card_reset_row.addWidget(self.card_reset_check_btn)
        card_conf_layout.addLayout(card_reset_row)

        panel_layout.addWidget(self.card_conf_frame, 0)

        # ========== GlobalFrame (fills rest; owns save at bottom) ==========
        self.global_frame = QFrame(self)
        self.global_frame.setObjectName("SubscribeGlobalFrame")
        self.global_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        global_layout = QVBoxLayout(self.global_frame)
        global_layout.setContentsMargins(10, 10, 10, 10)
        global_layout.setSpacing(8)

        global_layout.addWidget(StrongBodyLabel("绑定档案", self.global_frame))
        profile_header = QHBoxLayout()
        profile_header.setSpacing(6)
        self.profile_combo = EditableComboBox(self.global_frame)
        self.profile_combo.setPlaceholderText("档案名")
        self.profile_combo.currentIndexChanged.connect(self._on_profile_index_changed)
        self.profile_combo.currentTextChanged.connect(self._mark_side_dirty)
        self.profile_delete_btn = TransparentToolButton(FIF.DELETE, self.global_frame)
        self.profile_delete_btn.clicked.connect(self._on_profile_delete)
        profile_header.addWidget(self.profile_combo, 1)
        profile_header.addWidget(self.profile_delete_btn, 0)
        global_layout.addLayout(profile_header)

        self._add_side_divider(global_layout, self.global_frame)

        # Site proxy: full-width PushButton opens flyout (ConfDialog.siteChoiceBtn parity)
        self.site_proxy_btn = PushButton(FIF.VPN, "站点代理", self.global_frame)
        self.site_proxy_btn.setObjectName("SubscribeSiteProxyBtn")
        self.site_proxy_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.site_proxy_btn.clicked.connect(self._show_site_proxy_tip)
        global_layout.addWidget(self.site_proxy_btn)
        self.site_proxy_grid = None

        self._add_side_divider(global_layout, self.global_frame)

        self.profile_default_toggle_btn = TransparentToolButton(FIF.CHEVRON_DOWN_MED, self.global_frame)
        self.profile_default_toggle_btn.setObjectName("SubscribeProfileDefaultToggle")
        self.profile_default_toggle_btn.clicked.connect(self._toggle_profile_default_section)
        profile_default_header = QHBoxLayout()
        profile_default_header.setSpacing(6)
        profile_default_header.addWidget(StrongBodyLabel("默认调度周期", self.global_frame), 1)
        profile_default_header.addWidget(self.profile_default_toggle_btn, 0)
        global_layout.addLayout(profile_default_header)

        self.profile_default_body = QWidget(self.global_frame)
        self.profile_default_body.setObjectName("SubscribeProfileDefaultBody")
        profile_default_layout = QVBoxLayout(self.profile_default_body)
        profile_default_layout.setContentsMargins(0, 0, 0, 0)
        profile_default_layout.setSpacing(6)

        self.profile_weekday_button_group = QButtonGroup(self.profile_default_body)
        self.profile_weekday_button_group.setExclusive(False)
        self.profile_weekday_buttons: dict[str, TransparentTogglePushButton] = {}
        profile_weekday_box = QWidget(self.profile_default_body)
        profile_weekday_box.setObjectName("SubscribeProfileWeekdayBox")
        profile_weekday_layout = QHBoxLayout(profile_weekday_box)
        profile_weekday_layout.setContentsMargins(0, 0, 0, 0)
        profile_weekday_layout.setSpacing(4)
        for weekday_id in WEEKDAY_IDS:
            button = TransparentTogglePushButton(profile_weekday_box)
            button.setObjectName(f"SubscribeProfileWeekdayBtn{weekday_id}")
            button.setText(str(weekday_id))
            button.setCheckable(True)
            button.setMinimumSize(36, 36)
            button.toggled.connect(self._mark_side_dirty)
            self.profile_weekday_button_group.addButton(button, int(weekday_id))
            self.profile_weekday_buttons[str(weekday_id)] = button
            profile_weekday_layout.addWidget(button)
        profile_default_layout.addWidget(profile_weekday_box)

        profile_time_row = QHBoxLayout()
        profile_time_row.setContentsMargins(0, 0, 0, 0)
        profile_time_row.setSpacing(0)
        self.profile_time_picker = TimePicker(self.profile_default_body, showSeconds=False)
        self.profile_time_picker.setObjectName("SubscribeProfileTimePicker")
        for column_button in getattr(self.profile_time_picker, "columns", []) or []:
            column_button.setFixedWidth(100)
        self.profile_time_picker.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.profile_time_picker.adjustSize()
        self.profile_time_picker.timeChanged.connect(self._mark_side_dirty)
        profile_time_row.addWidget(self.profile_time_picker, 0, Qt.AlignVCenter)
        self._profile_tz_gap = QWidget(self.profile_default_body)
        self._profile_tz_gap.setObjectName("SubscribeProfileTzGap")
        self._profile_tz_gap.setFixedWidth(10)
        self._profile_tz_gap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        profile_time_row.addWidget(self._profile_tz_gap, 0)
        self.profile_tz_offset = DEFAULT_TZ_OFFSET
        self.profile_tz_btn = ToolButton(self.profile_default_body)
        self.profile_tz_btn.setObjectName("SubscribeProfileTzOffsetBtn")
        self.profile_tz_btn.clicked.connect(self._open_profile_tz_offset_menu)
        self._sync_profile_tz_offset_button()
        profile_time_row.addWidget(self.profile_tz_btn, 0, Qt.AlignVCenter)
        profile_time_row.addStretch(1)
        profile_default_layout.addLayout(profile_time_row)
        self._profile_default_expanded = False
        self.profile_default_body.setVisible(False)
        self.profile_default_toggle_btn.setIcon(FIF.CHEVRON_RIGHT_MED)
        global_layout.addWidget(self.profile_default_body)

        self._add_side_divider(global_layout, self.global_frame)

        global_layout.addWidget(StrongBodyLabel("分享链", self.global_frame))
        publish_row = QHBoxLayout()
        publish_row.setSpacing(6)
        self.share_card_label = CaptionLabel("未发布", self.global_frame)
        self.share_card_label.setObjectName("SubscribePublishStatus")
        self.share_card_label.setWordWrap(True)
        self.publish_share_card_btn = PushButton(CgsIcon.MAIN_SHARE, "发布", self.global_frame)
        self.publish_share_card_btn.clicked.connect(self._publish_share_card_from_button)
        publish_row.addWidget(self.share_card_label, 1)
        publish_row.addWidget(self.publish_share_card_btn, 0)
        global_layout.addLayout(publish_row)
        self.publish_bid_edit = None

        self._add_side_divider(global_layout, self.global_frame)

        self.follow_section_title = StrongBodyLabel("订阅源", self.global_frame)
        self.follow_section_title.setObjectName("SubscribeFollowSectionTitle")
        global_layout.addWidget(self.follow_section_title)
        self.follow_list = ListWidget(self.global_frame)
        self.follow_list.setObjectName("SubscribeFollowList")
        self.follow_list.setMinimumHeight(0)
        self.follow_list.setMaximumHeight(160)
        self.follow_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.follow_list.setFixedHeight(0)
        self.follow_list.currentRowChanged.connect(self._on_follow_row_changed)
        global_layout.addWidget(self.follow_list)

        self.follow_detail_label = BodyLabel("", self.global_frame)
        self.follow_detail_label.setObjectName("SubscribeFollowDetail")
        self.follow_detail_label.setWordWrap(True)
        self.follow_detail_label.hide()
        global_layout.addWidget(self.follow_detail_label)

        follow_out_row = QHBoxLayout()
        self.follow_remove_btn = ToolButton(FIF.DELETE, self.global_frame)
        self.follow_remove_btn.clicked.connect(self._remove_follow_soft)
        self.follow_remove_btn.hide()
        follow_out_row.addStretch(1)
        follow_out_row.addWidget(self.follow_remove_btn)
        global_layout.addLayout(follow_out_row)

        self.follow_input_host = QWidget(self.global_frame)
        self.follow_input_host.setObjectName("SubscribeFollowInputHost")
        follow_in_layout = QHBoxLayout(self.follow_input_host)
        follow_in_layout.setContentsMargins(0, 0, 0, 0)
        follow_in_layout.setSpacing(6)
        self.follow_bid_edit = LineEdit(self.follow_input_host)
        self.follow_bid_edit.setObjectName("SubscribeFollowBidEdit")
        self.follow_bid_edit.setPlaceholderText("粘贴 follow bid")
        self.follow_bid_edit.returnPressed.connect(self._add_follow_soft)
        self.follow_add_btn = ToolButton(FIF.ADD, self.follow_input_host)
        self.follow_add_btn.setObjectName("SubscribeFollowAddBtn")
        self.follow_add_btn.clicked.connect(self._add_follow_soft)
        follow_in_layout.addWidget(self.follow_bid_edit, 1)
        follow_in_layout.addWidget(self.follow_add_btn, 0)
        global_layout.addWidget(self.follow_input_host)

        # Stretch inside GlobalFrame so save stays pinned to GlobalFrame bottom.
        self.side_fill_spacer = QFrame(self.global_frame)
        self.side_fill_spacer.setObjectName("SubscribeSideFillSpacer")
        self.side_fill_spacer.setFrameShape(QFrame.Shape.NoFrame)
        self.side_fill_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.side_fill_spacer.setMinimumSize(0, 0)
        global_layout.addWidget(self.side_fill_spacer, 1)
        fill_index = global_layout.indexOf(self.side_fill_spacer)
        if fill_index >= 0:
            global_layout.setStretch(fill_index, 1)

        self._add_side_divider(global_layout, self.global_frame)

        self.side_save_btn = PrimaryPushButton(FIF.SAVE, "保存配置", self.global_frame)
        self.side_save_btn.setObjectName("SubscribeSideSaveBtn")
        self.side_save_btn.clicked.connect(self._save_side_panel_config)
        global_layout.addWidget(self.side_save_btn, 0)
        save_index = global_layout.indexOf(self.side_save_btn)
        if save_index >= 0:
            global_layout.setStretch(save_index, 0)

        panel_layout.addWidget(self.global_frame, 1)

        self._side_dirty = False
        self._reload_profile_combo()
        self._sync_card_conf_panel(None)
        self._set_follow_mode_input()


    def _add_side_divider(self, layout: QVBoxLayout, parent: QWidget) -> None:
        line = QFrame(parent)
        line.setObjectName("SubscribeSideDivider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        layout.addWidget(line)

    def _mark_side_dirty(self, *_args) -> None:
        if self._loading:
            return
        self._side_dirty = True
        if hasattr(self, "side_save_btn"):
            self.side_save_btn.setText("保存配置 *")

    def _site_key_for_index(self, site_index: int) -> str:
        return normalize_site_proxy_key(str(SPIDERS.get(int(site_index)) or ""))

    def _site_proxy_is_locked(self, site_index: int) -> bool:
        site_key = self._site_key_for_index(site_index)
        if not site_key:
            return True
        return resolve_provider_proxy_policy(site_key) == "direct"

    def _site_proxy_is_checked(self, site_index: int) -> bool:
        site_key = self._site_key_for_index(site_index)
        if not site_key:
            return False
        policy = resolve_provider_proxy_policy(site_key)
        return site_proxy_enabled(
            site_key,
            getattr(self._host.config, "site_proxy", None) or {},
            proxy_policy=policy,
        )

    def _site_proxy_set_checked(self, site_index: int, checked: bool) -> None:
        if self._loading:
            return
        site_key = self._site_key_for_index(site_index)
        if not site_key:
            return
        if self._site_proxy_is_locked(site_index):
            return
        if self._host.config.site_proxy is None:
            self._host.config.site_proxy = {}
        self._host.config.site_proxy[site_key] = bool(checked)
        self._mark_side_dirty()

    def _make_site_proxy_grid(self, parent: QWidget | None = None) -> SiteToggleGrid:
        """Build a fresh manga-site proxy toggle grid for TeachingTip content."""
        manga_indexes = sorted(int(index) for index in subscribe_site_indexes())
        grid = SiteToggleGrid(
            parent,
            site_indexes=manga_indexes,
            labels=SPIDERS_LABELS,
        )
        grid.setObjectName("SubscribeSiteProxyGrid")
        grid.setMinimumWidth(280)
        grid.bind_handlers(
            is_checked=self._site_proxy_is_checked,
            set_checked=self._site_proxy_set_checked,
            is_locked=self._site_proxy_is_locked,
        )
        return grid

    def _show_site_proxy_tip(self) -> None:
        """Open site_proxy grid in TeachingTip — same pattern as ConfDialog.siteChoiceBtn."""
        if self._site_proxy_tip is not None:
            self._site_proxy_tip.close()
        grid = self._make_site_proxy_grid(self)
        self.site_proxy_grid = grid
        select_all_button = TransparentToolButton(FIF.CHECKBOX, self)
        select_all_button.clicked.connect(
            lambda: grid.set_all_sites_selected(not grid.all_sites_selected())
        )
        tip = CustomTeachingTip.create(
            [grid],
            target=self.site_proxy_btn,
            parent=self._host,
            closeButtonBelows=(select_all_button,),
            tailPosition=TeachingTipTailPosition.TOP_RIGHT,
        )
        self._site_proxy_tip = tip

        def _on_tip_destroyed(*_args) -> None:
            self._site_proxy_tip = None
            self.site_proxy_grid = None

        tip.destroyed.connect(_on_tip_destroyed)

    def _reload_site_proxy_grid(self) -> None:
        """Refresh open flyout grid if present (config reload after save/profile switch)."""
        grid = getattr(self, "site_proxy_grid", None)
        if grid is None:
            return
        grid.reload_from_handlers()

    def _collect_check_section_into_config(self) -> None:
        """Collect profile default CheckSlot from secondary controls into cfg.check."""
        if hasattr(self, "profile_weekday_buttons"):
            weekdays = [
                weekday_id
                for weekday_id, button in self.profile_weekday_buttons.items()
                if button.isChecked()
            ]
            self._host.config.check.weekdays = weekdays
            picker_time = self.profile_time_picker.time
            time_text = picker_time.toString("HH:mm") if picker_time.isValid() else "03:00"
            if not time_text:
                time_text = "03:00"
            self._host.config.check.time = time_text
            self._host.config.check.tz_offset = normalize_tz_offset(self.profile_tz_offset)
        # Subscription = detect updates and download; always on (no UI knob).
        self._host.config.check.auto_download = True

    def _read_card_slot_from_widgets(self) -> CheckSlot:
        weekdays = [
            weekday_id
            for weekday_id, button in self.weekday_buttons.items()
            if button.isChecked()
        ]
        picker_time = self.time_picker.time
        time_text = picker_time.toString("HH:mm") if picker_time.isValid() else "03:00"
        if not time_text:
            time_text = "03:00"
        slot = CheckSlot(
            weekdays=weekdays,
            time=time_text,
            tz_offset=normalize_tz_offset(self.tz_offset),
        )
        slot.validate()
        return slot

    def _apply_slot_to_card_widgets(self, slot: CheckSlot) -> None:
        selected = set(str(item) for item in (slot.weekdays or []))
        for weekday_id, button in self.weekday_buttons.items():
            button.setChecked(weekday_id in selected)
        self.time_picker.setTime(self._check_qtime(slot.time))
        self.tz_offset = normalize_tz_offset(slot.tz_offset)
        self._sync_tz_offset_button()

    def _clone_check_slot(self, slot: CheckSlot) -> CheckSlot:
        cloned = CheckSlot(
            weekdays=list(slot.weekdays or []),
            time=str(slot.time or "03:00"),
            tz_offset=normalize_tz_offset(getattr(slot, "tz_offset", DEFAULT_TZ_OFFSET)),
        )
        cloned.validate()
        return cloned

    def _profile_check_as_slot(self) -> CheckSlot:
        return self._host.config.check.as_slot()

    def _sync_tz_offset_button(self) -> None:
        if not hasattr(self, "tz_btn"):
            return
        label = format_tz_offset_label(self.tz_offset)
        self.tz_btn.setText(label)
        self._align_tz_btn_to_time_picker()

    def _sync_profile_tz_offset_button(self) -> None:
        if not hasattr(self, "profile_tz_btn"):
            return
        label = format_tz_offset_label(self.profile_tz_offset)
        self.profile_tz_btn.setText(label)
        self._align_profile_tz_btn_to_time_picker()

    def _align_tz_btn_to_time_picker(self) -> None:
        """Match card tz ToolButton height to the painted TimePicker; width fits ±HH text."""
        self._align_tz_tool_button(self.tz_btn, self.time_picker)
        if hasattr(self, "profile_tz_btn") and hasattr(self, "profile_time_picker"):
            self._align_profile_tz_btn_to_time_picker()

    def _align_profile_tz_btn_to_time_picker(self) -> None:
        if not hasattr(self, "profile_tz_btn") or not hasattr(self, "profile_time_picker"):
            return
        self._align_tz_tool_button(self.profile_tz_btn, self.profile_time_picker)

    @staticmethod
    def _align_tz_tool_button(button: ToolButton, picker: TimePicker) -> None:
        if button is None or picker is None:
            return
        picker_height = int(picker.height())
        if picker_height < 8:
            picker_height = int(picker.sizeHint().height())
        if picker_height < 8:
            picker_height = int(picker.minimumSizeHint().height())
        if picker_height < 8:
            picker_height = 33
        label = str(button.text() or "+8")
        text_width = button.fontMetrics().horizontalAdvance(label) + 18
        button_width = max(picker_height, text_width, 36)
        button.setFixedSize(button_width, picker_height)

    def _open_tz_offset_menu(self) -> None:
        menu = RoundMenu(parent=self.tz_btn)
        current = normalize_tz_offset(self.tz_offset)
        for offset_hours in VALID_TZ_OFFSETS:
            action = Action(
                format_tz_offset_menu_text(offset_hours),
                triggered=lambda _checked=False, value=offset_hours: self._set_tz_offset(value),
            )
            action.setCheckable(True)
            action.setChecked(offset_hours == current)
            menu.addAction(action)
        menu.exec(self.tz_btn.mapToGlobal(self.tz_btn.rect().bottomLeft()))

    def _open_profile_tz_offset_menu(self) -> None:
        menu = RoundMenu(parent=self.profile_tz_btn)
        current = normalize_tz_offset(self.profile_tz_offset)
        for offset_hours in VALID_TZ_OFFSETS:
            action = Action(
                format_tz_offset_menu_text(offset_hours),
                triggered=lambda _checked=False, value=offset_hours: self._set_profile_tz_offset(value),
            )
            action.setCheckable(True)
            action.setChecked(offset_hours == current)
            menu.addAction(action)
        menu.exec(self.profile_tz_btn.mapToGlobal(self.profile_tz_btn.rect().bottomLeft()))

    def _set_tz_offset(self, offset_hours: int) -> None:
        normalized = normalize_tz_offset(offset_hours)
        if normalized == normalize_tz_offset(self.tz_offset):
            return
        self.tz_offset = normalized
        self._sync_tz_offset_button()
        self._on_card_slot_field_edited()

    def _set_profile_tz_offset(self, offset_hours: int) -> None:
        normalized = normalize_tz_offset(offset_hours)
        if normalized == normalize_tz_offset(self.profile_tz_offset):
            return
        self.profile_tz_offset = normalized
        self._sync_profile_tz_offset_button()
        self._mark_side_dirty()

    def _toggle_profile_default_section(self) -> None:
        self._profile_default_expanded = not bool(getattr(self, "_profile_default_expanded", False))
        if hasattr(self, "profile_default_body"):
            self.profile_default_body.setVisible(self._profile_default_expanded)
        if hasattr(self, "profile_default_toggle_btn"):
            icon = FIF.CHEVRON_DOWN_MED if self._profile_default_expanded else FIF.CHEVRON_RIGHT_MED
            self.profile_default_toggle_btn.setIcon(icon)
        if self._profile_default_expanded:
            self._align_profile_tz_btn_to_time_picker()

    def _save_side_panel_config(self) -> None:
        """Bottom saveBtn: profile CheckSlot + selected card enabled/check → yml SSoT."""
        try:
            name = str(self.profile_combo.currentText() or "").strip() or DEFAULT_CUSTOMNAME
            if name != self._host.store.customname:
                self._host.store = self._host.store.rebind(name)
                self._host.config = self._host.store.load()
                self._host._ensure_library_from_yaml()
            self._collect_check_section_into_config()
            # Selected card enabled + CheckSlot into yml books[] (not pkl interval dual-write).
            self._commit_selected_card_conf()
            # site_proxy already mutated live on toggle; ensure dict present for validate/save.
            if self._host.config.site_proxy is None:
                self._host.config.site_proxy = {}
            self._host.store.save(self._host.config)
            self._host.config = self._host.store.load()
            set_active_subscription_customname(self._host.store.customname)
            self._side_dirty = False
            self.side_save_btn.setText("保存配置")
            self._reload_profile_combo()
            self._load_profile_check_into_widgets()
            self._reload_site_proxy_grid()
            self._sync_card_conf_panel(self._host._selected_card_key)
            self._host._refresh_status_bar()
            InfoBar.success(
                title="",
                content=f"已保存 · {self._host.store.customname}",
                orient=Qt.Horizontal,
                position=InfoBarPosition.BOTTOM,
                duration=2000,
                parent=self._host,
            )
        except Exception as exc:
            self._host._show_error(str(exc))

    def _set_card_conf_title(self, title: str) -> None:
        """Single-line elided title so long names cannot stretch CardConfFrame."""
        if not hasattr(self, "card_conf_title"):
            return
        full = str(title or "").strip() or "—"
        self.card_conf_title.setToolTip(full if full != "—" else "")
        # Width available ≈ side panel 300 − margins − join btn − spacing.
        join_width = 0
        if hasattr(self, "bookJoinBtn") and self.bookJoinBtn is not None:
            join_width = max(self.bookJoinBtn.sizeHint().width(), self.bookJoinBtn.width(), 30)
        max_width = max(80, self.card_conf_frame.width() - 20 - join_width - 12)
        if max_width < 120:
            max_width = 200
        elided = self.card_conf_title.fontMetrics().elidedText(
            full, Qt.TextElideMode.ElideRight, max_width
        )
        self.card_conf_title.setText(elided)

    def _sync_card_conf_panel(self, card_key: str | None) -> None:
        if not hasattr(self, "card_conf_title"):
            return
        card = self._host._cards_by_key.get(str(card_key or "")) if card_key else None
        self._loading = True
        try:
            if card is None:
                self._set_card_conf_title("—")
                self.bookJoinBtn.setEnabled(False)
                self.bookJoinBtn.setChecked(False)
                self._set_card_slot_widgets_enabled(False)
                if hasattr(self, "card_reset_check_btn"):
                    self.card_reset_check_btn.setEnabled(False)
                self._card_check_inherits = True
                self._card_check_draft = None
                # Keep card widgets showing profile defaults as a neutral preview.
                self._apply_slot_to_card_widgets(self._profile_check_as_slot())
                return

            title = LocalLibraryStore.book_title(card.book) or card.card_key
            self._set_card_conf_title(title)
            self.bookJoinBtn.setEnabled(True)
            entry = self._yaml_book_entry_for_card(card)
            enabled = bool(entry.enabled) if entry is not None else bool(card.subscribe_enabled())
            self.bookJoinBtn.setChecked(enabled)
            self._set_card_slot_widgets_enabled(True)

            stored_slot = entry.check if entry is not None else None
            if stored_slot is not None:
                self._card_check_inherits = False
                self._card_check_draft = self._clone_check_slot(stored_slot)
                self._apply_slot_to_card_widgets(self._card_check_draft)
                if hasattr(self, "card_reset_check_btn"):
                    self.card_reset_check_btn.setEnabled(True)
            else:
                self._card_check_inherits = True
                self._card_check_draft = None
                self._apply_slot_to_card_widgets(self._profile_check_as_slot())
                if hasattr(self, "card_reset_check_btn"):
                    self.card_reset_check_btn.setEnabled(False)
        finally:
            self._loading = False

    def _set_card_slot_widgets_enabled(self, enabled: bool) -> None:
        for button in self.weekday_buttons.values():
            button.setEnabled(bool(enabled))
        self.time_picker.setEnabled(bool(enabled))
        self.tz_btn.setEnabled(bool(enabled))

    def _on_card_slot_field_edited(self, *_args) -> None:
        """Any card slot edit while inheriting materializes a whole-block override draft."""
        if self._loading:
            return
        if not self._host._selected_card_key:
            return
        if self._card_check_inherits:
            # Start from effective (profile) then accept the just-edited widgets as override.
            self._card_check_inherits = False
            self._card_check_draft = self._read_card_slot_from_widgets()
            if hasattr(self, "card_reset_check_btn"):
                self.card_reset_check_btn.setEnabled(True)
        else:
            self._card_check_draft = self._read_card_slot_from_widgets()
        self._mark_side_dirty()

    def _on_card_reset_check_clicked(self) -> None:
        if self._loading or not self._host._selected_card_key:
            return
        self._card_check_inherits = True
        self._card_check_draft = None
        self._loading = True
        try:
            self._apply_slot_to_card_widgets(self._profile_check_as_slot())
            if hasattr(self, "card_reset_check_btn"):
                self.card_reset_check_btn.setEnabled(False)
        finally:
            self._loading = False
        self._mark_side_dirty()

    def _yaml_book_key(self, site: str, url: str) -> str:
        return f"{str(site or '').strip()}:{str(url or '').strip()}"

    def _yaml_book_entry_for_card(self, card: SubscribeCard) -> BookEntry | None:
        book_url = LocalLibraryStore.book_unique_url(card.book)
        if not book_url:
            return None
        site_name = LocalLibraryStore.book_site(card.book, site_index=card.site_index)
        target = self._yaml_book_key(site_name, book_url)
        for entry in self._host.config.books:
            key = self._yaml_book_key(entry.site, entry.url)
            if key == target:
                return entry
        return None

    def _ensure_yaml_book_entry_for_library_book(
        self,
        site_index: int,
        book,
        *,
        apply_default_weekdays: bool = False,
        enabled: bool | None = None,
        check: CheckSlot | None = None,
        force_inherit_check: bool = False,
    ) -> bool:
        """Upsert yml books[] row for a library book. Returns True if config.books changed."""
        book_url = LocalLibraryStore.book_unique_url(book)
        if not book_url:
            return False
        site_name = LocalLibraryStore.book_site(book, site_index=site_index)
        title = LocalLibraryStore.book_title(book) or book_url
        target = self._yaml_book_key(site_name, book_url)
        entry = None
        for existing in self._host.config.books:
            if self._yaml_book_key(existing.site, existing.url) == target:
                entry = existing
                break

        changed = False
        if entry is None:
            default_enabled = (
                bool(enabled)
                if enabled is not None
                else bool(LocalLibraryStore.book_subscribe_enabled(book))
            )
            slot = check
            if apply_default_weekdays and slot is None and not force_inherit_check:
                weekdays = resolve_default_weekdays(book, added_at=datetime.now())
                if weekdays:
                    profile_slot = self._profile_check_as_slot()
                    slot = CheckSlot(
                        weekdays=list(weekdays),
                        time=str(profile_slot.time),
                        tz_offset=int(profile_slot.tz_offset),
                    )
                    slot.validate()
            entry = BookEntry(
                site=str(site_name or "").strip(),
                url=book_url,
                title=title,
                enabled=default_enabled,
                check=self._clone_check_slot(slot) if slot is not None else None,
            )
            self._host.config.books.append(entry)
            return True

        if enabled is not None and bool(entry.enabled) != bool(enabled):
            entry.enabled = bool(enabled)
            changed = True
        if title and entry.title != title:
            entry.title = title
            changed = True
        if force_inherit_check:
            if entry.check is not None:
                entry.check = None
                changed = True
        elif check is not None:
            new_slot = self._clone_check_slot(check)
            if entry.check is None or (
                list(entry.check.weekdays) != list(new_slot.weekdays)
                or str(entry.check.time) != str(new_slot.time)
                or int(entry.check.tz_offset) != int(new_slot.tz_offset)
            ):
                entry.check = new_slot
                changed = True
        elif apply_default_weekdays and entry.check is None:
            weekdays = resolve_default_weekdays(book, added_at=datetime.now())
            if weekdays:
                profile_slot = self._profile_check_as_slot()
                entry.check = CheckSlot(
                    weekdays=list(weekdays),
                    time=str(profile_slot.time),
                    tz_offset=int(profile_slot.tz_offset),
                )
                entry.check.validate()
                changed = True
        return changed

    def _commit_selected_card_conf(self) -> None:
        """Persist selected card enabled + CheckSlot into yml books[] (SSoT)."""
        key = self._host._selected_card_key
        card = self._host._cards_by_key.get(str(key or "")) if key else None
        if card is None or not self.bookJoinBtn.isEnabled():
            return
        enabled = bool(self.bookJoinBtn.isChecked())
        if self._card_check_inherits:
            self._ensure_yaml_book_entry_for_library_book(
                int(card.site_index),
                card.book,
                enabled=enabled,
                force_inherit_check=True,
            )
        else:
            slot = self._card_check_draft or self._read_card_slot_from_widgets()
            self._ensure_yaml_book_entry_for_library_book(
                int(card.site_index),
                card.book,
                enabled=enabled,
                check=slot,
            )
        # Mirror enabled onto library pkl for card visual / legacy readers only.
        # Do not dual-write cadence/interval into pkl.
        book_url = LocalLibraryStore.book_unique_url(card.book)
        if book_url:
            self._host.library.update_book_subscribe_conf(
                card.site_index,
                book_url,
                enabled=enabled,
            )
        card.apply_subscribe_conf(enabled=enabled)

    def _reload_profile_combo(self) -> None:
        if not hasattr(self, "profile_combo"):
            return
        current = self._host.store.customname
        names = list_subscription_customnames(include_default=True)
        self.profile_combo.blockSignals(True)
        try:
            self.profile_combo.clear()
            self.profile_combo.addItems(names)
            self.profile_combo.setCurrentText(current)
        finally:
            self.profile_combo.blockSignals(False)

    def _on_profile_index_changed(self, index: int) -> None:
        if self._loading or index < 0:
            return
        name = str(self.profile_combo.itemText(index) or "").strip()
        if not name or name == self._host.store.customname:
            return
        self._load_customname(name)

    def _on_profile_delete(self) -> None:
        name = str(self.profile_combo.currentText() or "").strip()
        if not name or name == DEFAULT_CUSTOMNAME:
            self._host._show_error("default 档案不可删除")
            return
        path = self._host.store.rebind(name).path
        if path.exists():
            path.unlink(missing_ok=True)
        # Fall back to default after delete.
        self._load_customname(DEFAULT_CUSTOMNAME)
        InfoBar.info(
            title="",
            content=f"已删除档案 {name}，已切回 default",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=2500,
            parent=self._host,
        )

    def _load_customname(self, customname: str) -> None:
        name = str(customname or "").strip() or DEFAULT_CUSTOMNAME
        self._host.store = self._host.store.rebind(name)
        set_active_subscription_customname(self._host.store.customname)
        # Touch-load creates file if missing (new profile).
        self._host.config = self._host.store.load()
        self._host._ensure_library_from_yaml()
        self._host._selected_card_key = None
        self._load_config_into_widgets()
        self._host._refresh_status_bar()
        self._host.refresh_library()

    def add_follow(self, bid: str, alias: str = "") -> None:
        bid = str(bid or "").strip()
        alias = str(alias or "").strip()
        if not bid:
            return
        if any(str(item.bid).strip() == bid for item in self._host.config.follows):
            InfoBar.info(
                title="",
                content="该 bid 已在列表中",
                orient=Qt.Horizontal,
                position=InfoBarPosition.BOTTOM,
                duration=1800,
                parent=self._host,
            )
            return
        self._host.config.follows.append(FollowEntry(bid=bid, alias=alias, added_at=self._utc_now()))
        self._host.store.save(self._host.config)
        self._render_follows()
        self._set_follow_mode_input()

    def _add_follow_soft(self) -> None:
        """Add from single bid input — empty = no-op, never raise to GUI.log."""
        bid = self.follow_bid_edit.text().strip()
        if not bid:
            return
        self.add_follow(bid)
        self.follow_bid_edit.clear()

    def _remove_follow_soft(self) -> None:
        """Remove selected follow — no selection = no-op, never raise."""
        row = self.follow_list.currentRow()
        if row < 0 or row >= len(self._host.config.follows):
            return
        del self._host.config.follows[row]
        self._host.store.save(self._host.config)
        self._render_follows()
        self._set_follow_mode_input()

    def remove_selected_follow(self) -> None:
        self._remove_follow_soft()

    def _render_follows(self) -> None:
        self.follow_list.blockSignals(True)
        try:
            self.follow_list.clear()
            for follow in self._host.config.follows:
                # List row is output label: prefer alias, else bid.
                label = str(follow.alias or "").strip() or str(follow.bid)
                self.follow_list.addItem(label)
        finally:
            self.follow_list.blockSignals(False)
        self._sync_follow_list_height()
        if not self._host.config.follows:
            self._set_follow_mode_input()

    def _sync_follow_list_height(self) -> None:
        """Keep follow_list content-sized so an empty list does not open a mid-panel void."""
        if not hasattr(self, "follow_list"):
            return
        count = self.follow_list.count()
        if count <= 0:
            self.follow_list.setFixedHeight(0)
            self.follow_list.hide()
            return
        self.follow_list.show()
        row_height = self.follow_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 28
        frame = int(self.follow_list.frameWidth()) * 2
        # Cap so a long follow list cannot shove the whole side panel.
        max_height = 160
        target = min(max_height, frame + row_height * count + 4)
        self.follow_list.setFixedHeight(max(row_height + frame, target))

    def _on_follow_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._host.config.follows):
            self._set_follow_mode_input()
            return
        follow = self._host.config.follows[row]
        # Output mode: label only (no dual inputs).
        name = str(follow.alias or "").strip() or "未命名"
        self.follow_detail_label.setText(f"{name}\n{follow.bid}")
        self.follow_detail_label.show()
        self.follow_remove_btn.show()
        self.follow_input_host.hide()

    def _set_follow_mode_input(self) -> None:
        """Default: show bid input, hide detail output."""
        if not hasattr(self, "follow_input_host"):
            return
        self.follow_list.clearSelection()
        self.follow_detail_label.hide()
        self.follow_detail_label.clear()
        self.follow_remove_btn.hide()
        self.follow_input_host.show()

    def _load_config_into_widgets(self) -> None:
        self._loading = True
        try:
            self._reload_profile_combo()
            self._load_profile_check_into_widgets()
            self._reload_site_proxy_grid()

            publish = self._host.config.publish
            if publish is not None:
                bid = str(publish.bid or "").strip()
                posted_at = publish.share_card.posted_at if publish.share_card else ""
                if posted_at:
                    self.share_card_label.setText(f"已发布 · {posted_at[:16]}")
                elif bid:
                    self.share_card_label.setText(f"已发布 · {bid[:12]}…")
                else:
                    self.share_card_label.setText("已发布")
                self.share_card_label.setToolTip(bid or "已发布")
                self.publish_share_card_btn.setEnabled(False)
                self.publish_share_card_btn.setText("已发布")
            else:
                self.share_card_label.setText("未发布")
                self.share_card_label.setToolTip("")
                self.publish_share_card_btn.setEnabled(True)
                self.publish_share_card_btn.setText("发布")
            self._render_follows()
            self._sync_card_conf_panel(self._host._selected_card_key)
            self._side_dirty = False
            if hasattr(self, "side_save_btn"):
                self.side_save_btn.setText("保存配置")
        finally:
            self._loading = False

    def _load_profile_check_into_widgets(self) -> None:
        """Bind profile default CheckSlot into secondary controls (not card widgets)."""
        if not hasattr(self, "profile_weekday_buttons"):
            return
        selected = set(str(item) for item in (self._host.config.check.weekdays or []))
        for weekday_id, button in self.profile_weekday_buttons.items():
            button.setChecked(weekday_id in selected)
        self.profile_time_picker.setTime(self._check_qtime(self._host.config.check.time))
        self.profile_tz_offset = normalize_tz_offset(
            getattr(self._host.config.check, "tz_offset", DEFAULT_TZ_OFFSET)
        )
        self._sync_profile_tz_offset_button()

    @staticmethod
    def _check_qtime(value: str) -> QTime:
        text = str(value or "03:00")
        parsed = QTime.fromString(text, "HH:mm")
        return parsed if parsed.isValid() else QTime(3, 0)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _publish_share_card_from_button(self) -> None:
        self._host.task_mgr.execute_simple_task(
            self._host.publish_share_card,
            success_callback=self._on_share_card_published,
            tooltip_title="订阅分享",
            tooltip_content="发布分享卡片",
            success_message="分享链已发布",
            task_id=f"subscription_share_card_{self._host.store.customname}",
            show_success_info=False,
        )

    def _on_share_card_published(self, result) -> None:
        InfoBar.success(
            title="",
            content=f"分享链已发布 {result.discord_message_id}",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=3000,
            parent=self._host,
        )

