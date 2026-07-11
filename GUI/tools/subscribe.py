from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QListWidgetItem,
    QStackedWidget,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    CompactSpinBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    IconWidget,
    LineEdit,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    SegmentedWidget,
    StrongBodyLabel,
    TimePicker,
    ToolButton,
    TransparentTogglePushButton,
    VBoxLayout,
    isDarkTheme,
    themeColor,
)

from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components import AcceptEdit
from utils import conf
from utils.share import DiscordShareAPI, WorkerIndexClient
from utils.subscription import (
    BookEntry,
    DEFAULT_CUSTOMNAME,
    FEATURE_KIND_ARTIST,
    FEATURE_KIND_TAG,
    FeatureEntry,
    FollowEntry,
    MODE_BROADCASTER,
    MODE_SUBSCRIBER,
    ShareCard,
    load_subscription,
    save_subscription,
)
from variables import CGS_DISCORD_SHARE_API, CGS_METADATA_CHANNEL_ID


MODE_LABELS = {
    MODE_BROADCASTER: "追更",
    MODE_SUBSCRIBER: "订阅源",
}
MODE_HINTS = {
    MODE_BROADCASTER: "从预览页加入作品，按日期自动检查新章节并提交下载。分享链发布后可同步元数据。",
    MODE_SUBSCRIBER: "关注他人发布的订阅源，按间隔拉取更新并自动下载。",
}


class WizardStepIndicator(QWidget):
    """Lightweight self-drawn step indicator (qfluent has no native stepper).

    Each step renders a 26px circle dot + CaptionLabel title, joined by a thin
    HLine. Three states drive color via themeColor()/isDarkTheme():
      - done   : theme-color fill + ACCEPT icon (color + icon, not color alone)
      - active : theme-color fill + step number + outline ring
      - wait   : grey outline + step number
    PRD UI/UX 表面1: 2-step wizard keeps the indicator minimal (no connector animation).
    """

    DOT_SIZE = 26

    def __init__(self, titles: list[str], parent=None):
        super().__init__(parent)
        self._titles = list(titles)
        self._current = 0
        self._dots: list[IconWidget] = []
        self._numbers: list[CaptionLabel] = []
        self._labels: list[CaptionLabel] = []

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for index, title in enumerate(self._titles):
            dot = IconWidget(FIF.ACCEPT, self)
            dot.setFixedSize(self.DOT_SIZE, self.DOT_SIZE)
            number = CaptionLabel(str(index + 1), dot)
            number.setAlignment(Qt.AlignCenter)
            number.setGeometry(0, 0, self.DOT_SIZE, self.DOT_SIZE)
            label = CaptionLabel(title, self)
            self._dots.append(dot)
            self._numbers.append(number)
            self._labels.append(label)
            row.addWidget(dot)
            row.addWidget(label)
            if index != len(self._titles) - 1:
                line = QFrame(self)
                line.setFrameShape(QFrame.HLine)
                line.setFixedWidth(28)
                row.addWidget(line)
        row.addStretch(1)
        self.set_current(0)

    def set_current(self, index: int) -> None:
        if index < 0 or index >= len(self._titles):
            raise ValueError(f"wizard step index out of range: {index}")
        self._current = index
        self._restyle()

    @property
    def current(self) -> int:
        return self._current

    def _restyle(self) -> None:
        accent = themeColor()
        wait_color = QColor(150, 150, 150) if isDarkTheme() else QColor(180, 180, 180)
        for index, dot in enumerate(self._dots):
            number = self._numbers[index]
            if index < self._current:
                # done: theme fill + ACCEPT icon (color + icon, never color alone)
                dot.setStyleSheet(f"background:{accent.name()}; border-radius:{self.DOT_SIZE // 2}px;")
                number.hide()
                dot.show()
            elif index == self._current:
                # active: theme fill + number + outline ring
                dot.setStyleSheet(
                    f"background:{accent.name()};"
                    f"border:2px solid {accent.name()}; border-radius:{self.DOT_SIZE // 2}px;"
                )
                number.setStyleSheet("color:#FFFFFF; background:transparent;")
                number.show()
            else:
                # wait: grey outline + number
                dot.setStyleSheet(
                    f"background:transparent; border:1px solid {wait_color.name()};"
                    f"border-radius:{self.DOT_SIZE // 2}px;"
                )
                number.setStyleSheet(f"color:{wait_color.name()}; background:transparent;")
                number.show()


class SubscribeInterface(QWidget):
    """Configuration surface for subscription mode and one-shot share publication."""

    WEEKDAY_IDS = tuple(range(1, 8))

    def __init__(
        self,
        parent,
        *,
        customname: str = DEFAULT_CUSTOMNAME,
        base_dir=None,
        share_api_factory=None,
        worker_client_factory=None,
    ):
        super().__init__(parent)
        self.gui = parent.gui
        self.customname = customname
        self.base_dir = base_dir
        self.task_mgr = AsyncTaskManager(self.gui, self)
        self._share_api_factory = share_api_factory or self._default_share_api_factory
        self._worker_client_factory = worker_client_factory or self._default_worker_client_factory
        self._loading = False
        self.pushed_books = []
        self.config = load_subscription(customname, base_dir=base_dir)
        self._build_ui()
        self._load_config_into_widgets()

    def save_current(self) -> None:
        self._sync_current_view_to_config(require_token=False)
        save_subscription(self.config, base_dir=self.base_dir)
        self.config = load_subscription(self.customname, base_dir=self.base_dir)
        self._load_config_into_widgets()

    def switch_mode(self, mode: str) -> None:
        if mode not in (MODE_BROADCASTER, MODE_SUBSCRIBER):
            raise ValueError(f"unsupported subscription mode: {mode!r}")
        self._sync_current_view_to_config(require_token=False)
        self.config.mode = mode
        save_subscription(self.config, base_dir=self.base_dir)
        self.config = load_subscription(self.customname, base_dir=self.base_dir)
        self._load_config_into_widgets()

    def _switch_mode_from_ui(self, mode: str) -> None:
        if self._loading:
            return
        self._run_ui_action(lambda: self.switch_mode(mode))

    async def publish_share_card(self):
        self._sync_current_view_to_config(require_token=True)
        broadcaster = self.config.broadcaster
        if broadcaster.share_card and broadcaster.share_card.posted_at:
            raise ValueError("share_card already published")

        enabled_books = [book for book in broadcaster.books if book.enabled]
        if not enabled_books:
            raise ValueError("at least one enabled broadcaster book is required before publishing share_card")

        token = self._require_discord_token()
        worker = self._worker_client_factory(token)
        summary_book = enabled_books[0]
        registration = await self._register_publish_bid(worker, summary_book)
        share_api = self._share_api_factory(token)
        result = await self._publish_share_card(
            share_api=share_api,
            book_names=[book.title for book in enabled_books],
        )

        broadcaster.publish_bid = registration.bid
        broadcaster.share_card = ShareCard(
            posted_at=result.posted_at,
            discord_channel=result.discord_channel,
            discord_message_id=result.discord_message_id,
        )
        save_subscription(self.config, base_dir=self.base_dir)
        self.config = load_subscription(self.customname, base_dir=self.base_dir)
        self._load_config_into_widgets()
        return result

    def import_preview_books(self) -> None:
        preview_manager = self.gui.preview_mgr
        if not preview_manager.books_cache:
            raise ValueError("open a preview with books before importing")
        browser = self.gui.BrowserWindow
        if not browser.page_runtime.page_ready:
            raise ValueError("open the current preview before importing")

        is_manga_like = bool(preview_manager.is_manga or preview_manager.is_fix)
        browser.subscription.configure_entry(is_manga_like=is_manga_like)
        if is_manga_like:
            browser.subscription.enter_selection()
        browser.show()
        browser.raise_()
        browser.activateWindow()

    def receive_pushed_books(self, books: list) -> None:
        """Handover entry for books pushed from the preview subscribe-mode gesture (G3).

        G5: enter the broadcaster add-subscription wizard seeded with these books
        (switch to broadcaster mode/view, open Step ① with the indicator active).
        """
        self.pushed_books = list(books or [])
        if not self.pushed_books:
            raise ValueError("no books were pushed from preview")
        # The wizard only serves broadcaster add-subscription; ensure that view is shown.
        if self.config.mode != MODE_BROADCASTER:
            self.config.mode = MODE_BROADCASTER
            self.mode_segment.setCurrentItem(MODE_BROADCASTER)
            self.stack.setCurrentWidget(self.broadcaster_view)
        self._open_wizard()
        InfoBar.info(
            title="",
            content=f"已接收 {len(self.pushed_books)} 本预览书",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=2500,
            parent=self,
        )

    def _run_ui_action(self, action) -> None:
        try:
            action()
        except Exception as exc:
            self._show_error(str(exc))
            raise

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title="",
            content=message,
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=5000,
            parent=self,
        )

    def _build_ui(self) -> None:
        self.main_layout = VBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 10)
        self.main_layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("追更 / 订阅源", self))
        header.addWidget(CaptionLabel("default profile", self))
        header.addStretch(1)

        self.customname_edit = AcceptEdit(self)
        self.customname_edit.setPlaceholderText(DEFAULT_CUSTOMNAME)
        self.customname_edit.setText(self.customname)
        self.customname_edit.custSignal.connect(self._load_customname)
        header.addWidget(self.customname_edit, 2)
        self.main_layout.addLayout(header)

        mode_row = QHBoxLayout()
        self.mode_segment = SegmentedWidget(self)
        self.mode_segment.addItem(MODE_BROADCASTER, MODE_LABELS[MODE_BROADCASTER], onClick=lambda: self._switch_mode_from_ui(MODE_BROADCASTER))
        self.mode_segment.addItem(MODE_SUBSCRIBER, MODE_LABELS[MODE_SUBSCRIBER], onClick=lambda: self._switch_mode_from_ui(MODE_SUBSCRIBER))
        mode_row.addWidget(self.mode_segment)
        mode_row.addStretch(1)
        self.save_btn = PrimaryPushButton(FIF.SAVE, "保存配置", self)
        self.save_btn.clicked.connect(self._save_from_button)
        mode_row.addWidget(self.save_btn)
        self.main_layout.addLayout(mode_row)
        self.mode_hint_label = CaptionLabel("", self)
        self.mode_hint_label.setWordWrap(True)
        self.main_layout.addWidget(self.mode_hint_label)

        self.stack = QStackedWidget(self)
        self.broadcaster_view = self._build_broadcaster_view()
        self.subscriber_view = self._build_subscriber_view()
        self.stack.addWidget(self.broadcaster_view)
        self.stack.addWidget(self.subscriber_view)
        self.main_layout.addWidget(self.stack)

    def _build_broadcaster_view(self) -> QWidget:
        view = QWidget(self)
        layout = VBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)

        # Broadcaster view hosts two panels: the normal config panel and the
        # add-subscription wizard. receive_pushed_books() flips to the wizard;
        # finishing/cancelling flips back. One stack, one panel visible at a time.
        self.broadcaster_stack = QStackedWidget(view)
        self.broadcaster_normal_panel = self._build_broadcaster_normal_panel()
        self.wizard_panel = self._build_wizard_panel()
        self.broadcaster_stack.addWidget(self.broadcaster_normal_panel)
        self.broadcaster_stack.addWidget(self.wizard_panel)
        layout.addWidget(self.broadcaster_stack)
        return view

    def _build_broadcaster_normal_panel(self) -> QWidget:
        view = QWidget(self)
        layout = VBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        self.publish_bid_edit = LineEdit(view)
        self.publish_bid_edit.setReadOnly(True)
        self.publish_bid_edit.setPlaceholderText("未发布")
        self.share_card_label = BodyLabel("未发布", view)
        self.publish_share_card_btn = PrimaryPushButton(FIF.SHARE, "发布分享链", view)
        self.publish_share_card_btn.clicked.connect(self._publish_share_card_from_button)
        top_row.addWidget(self.publish_bid_edit, 2)
        top_row.addWidget(self.share_card_label, 2)
        top_row.addWidget(self.publish_share_card_btn)
        layout.addLayout(top_row)
        publish_hint = CaptionLabel("发布分享链会生成 publish_bid；后台元数据发布依赖它。只配置追更对象时，请先保存对象和调度，再按提示补齐发布信息。", view)
        publish_hint.setWordWrap(True)
        layout.addWidget(publish_hint)

        schedule_row = QHBoxLayout()
        self.weekday_button_group = QButtonGroup(view)
        self.weekday_button_group.setExclusive(False)
        self.weekday_buttons = {}
        self.weekday_box = QWidget(view)
        weekday_layout = QHBoxLayout(self.weekday_box)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.setSpacing(4)
        for weekday_id in self.WEEKDAY_IDS:
            button = TransparentTogglePushButton(self.weekday_box)
            button.setText(str(weekday_id))
            button.setCheckable(True)
            button.setMinimumSize(44, 44)
            self.weekday_button_group.addButton(button, weekday_id)
            self.weekday_buttons[weekday_id] = button
            weekday_layout.addWidget(button)
        self.time_picker = TimePicker(view, showSeconds=False)
        self.time_picker.setMinimumHeight(44)
        schedule_row.addWidget(BodyLabel("检查日", view))
        schedule_row.addWidget(self.weekday_box)
        schedule_row.addWidget(BodyLabel("时间", view))
        schedule_row.addWidget(self.time_picker)
        schedule_row.addStretch(1)
        layout.addLayout(schedule_row)

        book_toolbar = QHBoxLayout()
        self.import_preview_btn = ToolButton(FIF.DOWNLOAD, view)
        self.import_preview_btn.setToolTip("从当前预览导入")
        self.import_preview_btn.clicked.connect(self._import_preview_books_from_button)
        # TODO: Accept BookInfo exported from progress/preview instead of expanding manual url/title entry.
        self.remove_book_btn = ToolButton(FIF.REMOVE, view)
        self.remove_book_btn.setToolTip("移除选中")
        self.remove_book_btn.clicked.connect(lambda _checked=False: self._run_ui_action(self.remove_selected_book))
        self.book_enabled_check = CheckBox("启用", view)
        self.book_enabled_check.stateChanged.connect(self._toggle_selected_book_enabled)
        book_toolbar.addWidget(self.import_preview_btn)
        book_toolbar.addWidget(self.remove_book_btn)
        book_toolbar.addWidget(self.book_enabled_check)
        book_toolbar.addStretch(1)
        layout.addLayout(book_toolbar)

        self.book_list = ListWidget(view)
        self.book_list.currentRowChanged.connect(self._load_selected_book)
        layout.addWidget(self.book_list)
        return view

    def _build_subscriber_view(self) -> QWidget:
        view = QWidget(self)
        layout = VBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)

        pull_row = QHBoxLayout()
        self.pull_interval_spin = CompactSpinBox(view)
        self.pull_interval_spin.setRange(1, 168)
        self.lookback_spin = CompactSpinBox(view)
        self.lookback_spin.setRange(0, 365)
        self.auto_download_check = CheckBox("有更新自动下载", view)
        pull_row.addWidget(BodyLabel("拉取间隔(小时)", view))
        pull_row.addWidget(self.pull_interval_spin)
        pull_row.addWidget(BodyLabel("初始回看(天)", view))
        pull_row.addWidget(self.lookback_spin)
        pull_row.addWidget(self.auto_download_check)
        pull_row.addStretch(1)
        layout.addLayout(pull_row)

        follow_row = QHBoxLayout()
        self.follow_bid_edit = LineEdit(view)
        self.follow_bid_edit.setPlaceholderText("follow bid")
        self.follow_alias_edit = LineEdit(view)
        self.follow_alias_edit.setPlaceholderText("显示名称")
        self.add_follow_btn = ToolButton(FIF.ADD, view)
        self.add_follow_btn.setToolTip("添加订阅")
        self.add_follow_btn.clicked.connect(self._add_follow_from_inputs)
        self.update_follow_btn = ToolButton(FIF.SAVE, view)
        self.update_follow_btn.setToolTip("更新选中")
        self.update_follow_btn.clicked.connect(self._update_follow_from_inputs)
        self.remove_follow_btn = ToolButton(FIF.REMOVE, view)
        self.remove_follow_btn.setToolTip("移除选中")
        self.remove_follow_btn.clicked.connect(lambda _checked=False: self._run_ui_action(self.remove_selected_follow))
        follow_row.addWidget(self.follow_bid_edit, 2)
        follow_row.addWidget(self.follow_alias_edit, 2)
        follow_row.addWidget(self.add_follow_btn)
        follow_row.addWidget(self.update_follow_btn)
        follow_row.addWidget(self.remove_follow_btn)
        layout.addLayout(follow_row)

        self.follow_list = ListWidget(view)
        self.follow_list.currentRowChanged.connect(self._load_selected_follow)
        layout.addWidget(self.follow_list)
        return view

    # ----- broadcaster add-subscription wizard (G5) -----

    def _build_wizard_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = VBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.wizard_indicator = WizardStepIndicator(["对象", "自动检查"], panel)
        layout.addWidget(self.wizard_indicator)

        self.wizard_step_stack = QStackedWidget(panel)
        self.wizard_step_input = self._build_wizard_step_input()
        self.wizard_step_config = self._build_wizard_step_config()
        self.wizard_step_stack.addWidget(self.wizard_step_input)
        self.wizard_step_stack.addWidget(self.wizard_step_config)
        layout.addWidget(self.wizard_step_stack, 1)

        nav_row = QHBoxLayout()
        self.wizard_cancel_btn = PushButton(FIF.CLOSE, "取消", panel)
        self.wizard_cancel_btn.clicked.connect(self._cancel_wizard)
        self.wizard_prev_btn = PushButton(FIF.LEFT_ARROW, "上一步", panel)
        self.wizard_prev_btn.clicked.connect(self._wizard_prev)
        self.wizard_next_btn = PrimaryPushButton(FIF.RIGHT_ARROW, "下一步", panel)
        self.wizard_next_btn.clicked.connect(lambda _checked=False: self._run_ui_action(self._wizard_next))
        nav_row.addWidget(self.wizard_cancel_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.wizard_prev_btn)
        nav_row.addWidget(self.wizard_next_btn)
        layout.addLayout(nav_row)
        return panel

    def _build_wizard_step_input(self) -> QWidget:
        view = QWidget(self)
        layout = VBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(StrongBodyLabel("确认追更对象", view))
        self.wizard_flow_hint = CaptionLabel("", view)
        self.wizard_flow_hint.setWordWrap(True)
        layout.addWidget(self.wizard_flow_hint)
        self.wizard_books_list = ListWidget(view)
        layout.addWidget(self.wizard_books_list, 1)

        # doujinshi/Ero seeds expose artist/tags -> feature-tracking: a checkable
        # list de-duplicates artist/tag across the pushed books (the select-list).
        self.wizard_features_label = StrongBodyLabel("选择要追踪的作者 / 标签", view)
        layout.addWidget(self.wizard_features_label)
        self.wizard_features_list = ListWidget(view)
        layout.addWidget(self.wizard_features_list, 1)
        return view

    def _build_wizard_step_config(self) -> QWidget:
        view = QWidget(self)
        layout = VBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(StrongBodyLabel("设置自动检查", view))
        schedule_row = QHBoxLayout()
        self.wizard_weekday_group = QButtonGroup(view)
        self.wizard_weekday_group.setExclusive(False)
        self.wizard_weekday_buttons = {}
        weekday_box = QWidget(view)
        weekday_layout = QHBoxLayout(weekday_box)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.setSpacing(4)
        for weekday_id in self.WEEKDAY_IDS:
            button = TransparentTogglePushButton(weekday_box)
            button.setText(str(weekday_id))
            button.setCheckable(True)
            button.setMinimumSize(44, 44)
            self.wizard_weekday_group.addButton(button, weekday_id)
            self.wizard_weekday_buttons[weekday_id] = button
            weekday_layout.addWidget(button)
        self.wizard_time_picker = TimePicker(view, showSeconds=False)
        self.wizard_time_picker.setMinimumHeight(44)
        schedule_row.addWidget(BodyLabel("检查日", view))
        schedule_row.addWidget(weekday_box)
        schedule_row.addWidget(BodyLabel("时间", view))
        schedule_row.addWidget(self.wizard_time_picker)
        schedule_row.addStretch(1)
        layout.addLayout(schedule_row)

        layout.addStretch(1)
        hint = CaptionLabel("配置完成后由后台 Schedule 按此调度自动执行，无需保持主窗口打开。", view)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return view

    def _open_wizard(self) -> None:
        """Enter the wizard seeded with pushed_books, indicator at Step ①."""
        self._populate_wizard_input()
        self._seed_wizard_config()
        self.wizard_step_stack.setCurrentIndex(0)
        self.wizard_indicator.set_current(0)
        self._sync_wizard_nav()
        self.broadcaster_stack.setCurrentWidget(self.wizard_panel)

    def _seed_wizard_config(self) -> None:
        """Seed Step ② controls from the broadcaster's current schedule defaults."""
        schedule = self.config.broadcaster.schedule
        selected = {int(value) for value in schedule.weekdays}
        for weekday_id, button in self.wizard_weekday_buttons.items():
            button.setChecked(weekday_id in selected)
        self.wizard_time_picker.setTime(self._schedule_qtime(schedule.time))


    def _populate_wizard_input(self) -> None:
        self.wizard_books_list.clear()
        for book in self.pushed_books:
            site = str(getattr(book, "source", "") or "").strip()
            title = str(getattr(book, "name", "") or "").strip()
            self.wizard_books_list.addItem(f"{site} | {title}")

        self.wizard_features_list.clear()
        feature_seeds = self._collect_feature_seeds()
        is_feature_flow = bool(feature_seeds)
        self.wizard_flow_hint.setText(
            "按作者/标签追踪新作品；完成后会保存去重后的特征条目。"
            if is_feature_flow
            else "追踪这些作品的新章节；完成后会保存去重后的作品 URL。"
        )
        self.wizard_features_label.setVisible(is_feature_flow)
        self.wizard_features_list.setVisible(is_feature_flow)
        for site, kind, value in feature_seeds:
            item = QListWidgetItem(f"{kind}: {value}  ({site})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, (site, kind, value))
            self.wizard_features_list.addItem(item)

    def _is_feature_flow(self) -> bool:
        """Ero/doujinshi seeds carry id_and_md5() -> feature-tracking; manga lacks it."""
        return any(hasattr(book, "id_and_md5") for book in self.pushed_books)

    def _collect_feature_seeds(self) -> list[tuple[str, str, str]]:
        """De-duplicate artist/tag across feature-flow (Ero) pushed books, preserving order."""
        if not self._is_feature_flow():
            return []
        seeds: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for book in self.pushed_books:
            if not hasattr(book, "id_and_md5"):
                continue
            site = str(getattr(book, "source", "") or "").strip()
            artist = str(getattr(book, "artist", "") or "").strip()
            if artist:
                seed = (site, FEATURE_KIND_ARTIST, artist)
                if seed not in seen:
                    seen.add(seed)
                    seeds.append(seed)
            for tag in getattr(book, "tags", None) or []:
                tag_value = str(tag or "").strip()
                if not tag_value:
                    continue
                seed = (site, FEATURE_KIND_TAG, tag_value)
                if seed not in seen:
                    seen.add(seed)
                    seeds.append(seed)
        return seeds

    def _sync_wizard_nav(self) -> None:
        index = self.wizard_step_stack.currentIndex()
        self.wizard_prev_btn.setEnabled(index > 0)
        is_last = index == self.wizard_step_stack.count() - 1
        self.wizard_next_btn.setText("完成" if is_last else "下一步")
        self.wizard_next_btn.setIcon(FIF.ACCEPT if is_last else FIF.RIGHT_ARROW)

    def _wizard_prev(self) -> None:
        index = self.wizard_step_stack.currentIndex()
        if index <= 0:
            return
        self.wizard_step_stack.setCurrentIndex(index - 1)
        self.wizard_indicator.set_current(index - 1)
        self._sync_wizard_nav()

    def _wizard_next(self) -> None:
        index = self.wizard_step_stack.currentIndex()
        if index == 0:
            self._validate_wizard_input()
            self.wizard_step_stack.setCurrentIndex(1)
            self.wizard_indicator.set_current(1)
            self._sync_wizard_nav()
            return
        self._finish_wizard()

    def _validate_wizard_input(self) -> None:
        if not self.pushed_books:
            raise ValueError("no books to subscribe in wizard")
        if self._is_feature_flow() and not self._checked_feature_seeds():
            raise ValueError("select at least one artist/tag feature to subscribe")

    def _checked_feature_seeds(self) -> list[tuple[str, str, str]]:
        seeds = []
        for row in range(self.wizard_features_list.count()):
            item = self.wizard_features_list.item(row)
            if item.checkState() == Qt.Checked:
                seeds.append(item.data(Qt.UserRole))
        return seeds

    def _finish_wizard(self) -> None:
        broadcaster = self.config.broadcaster
        added = 0
        skipped = 0
        if self._is_feature_flow():
            existing = {(f.site, f.kind, f.value) for f in broadcaster.features}
            for site, kind, value in self._checked_feature_seeds():
                if (site, kind, value) in existing:
                    skipped += 1
                    continue
                entry = FeatureEntry(site=site, kind=kind, value=value, enabled=True)
                entry.validate()
                broadcaster.features.append(entry)
                existing.add((site, kind, value))
                added += 1
        else:
            existing_urls = {entry.url for entry in broadcaster.books}
            for book in self.pushed_books:
                entry = self._book_entry_from_preview_book(book)
                if not entry.url or entry.url in existing_urls:
                    skipped += 1
                    continue
                broadcaster.books.append(entry)
                existing_urls.add(entry.url)
                added += 1

        broadcaster.schedule.weekdays = [
            str(weekday_id)
            for weekday_id in self.WEEKDAY_IDS
            if self.wizard_weekday_buttons[weekday_id].isChecked()
        ]
        broadcaster.schedule.time = self.wizard_time_picker.time.toString("HH:mm")

        self.config.validate()
        save_subscription(self.config, base_dir=self.base_dir)
        self.config = load_subscription(self.customname, base_dir=self.base_dir)
        self._load_config_into_widgets()
        self._close_wizard()
        InfoBar.success(
            title="",
            content=f"已添加 {added} 项追更，跳过 {skipped} 个重复项",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=2500,
            parent=self,
        )

    def _cancel_wizard(self) -> None:
        self._close_wizard()

    def _close_wizard(self) -> None:
        self.pushed_books = []
        self.broadcaster_stack.setCurrentWidget(self.broadcaster_normal_panel)


    def _load_config_into_widgets(self) -> None:
        self._loading = True
        try:
            self.customname = self.config.customname
            self.customname_edit.setText(self.customname)
            self.mode_segment.setCurrentItem(self.config.mode)
            self.mode_hint_label.setText(MODE_HINTS.get(self.config.mode, ""))
            self.stack.setCurrentWidget(self.broadcaster_view if self.config.mode == MODE_BROADCASTER else self.subscriber_view)

            broadcaster = self.config.broadcaster
            publish_bid = str(broadcaster.publish_bid or "").strip()
            self.publish_bid_edit.setText(publish_bid or "未发布")
            self._set_weekday_buttons(broadcaster.schedule.weekdays)
            self.time_picker.setTime(self._schedule_qtime(broadcaster.schedule.time))
            if broadcaster.share_card and broadcaster.share_card.posted_at:
                self.share_card_label.setText(f"已发布于 {broadcaster.share_card.posted_at}")
                self.publish_share_card_btn.setEnabled(False)
                self.publish_share_card_btn.setText(f"已发布于 {broadcaster.share_card.posted_at[:10]}")
            else:
                self.share_card_label.setText("未发布")
                self.publish_share_card_btn.setEnabled(True)
                self.publish_share_card_btn.setText("发布分享链")
            self._render_books()

            subscriber = self.config.subscriber
            self.pull_interval_spin.setValue(int(subscriber.pull_interval_hours))
            self.lookback_spin.setValue(int(subscriber.initial_lookback_days))
            self.auto_download_check.setChecked(bool(subscriber.auto_download))
            self._render_follows()
        finally:
            self._loading = False

    def _sync_current_view_to_config(self, *, require_token: bool) -> None:
        if require_token:
            self._require_discord_token()
        if self.config.mode == MODE_BROADCASTER:
            self._sync_broadcaster_widgets_to_config()
        else:
            self._sync_subscriber_widgets_to_config()
        self.config.validate()

    def _sync_broadcaster_widgets_to_config(self) -> None:
        broadcaster = self.config.broadcaster
        broadcaster.schedule.weekdays = [str(weekday_id) for weekday_id in self.WEEKDAY_IDS if self.weekday_buttons[weekday_id].isChecked()]
        broadcaster.schedule.time = self.time_picker.time.toString("HH:mm")

    def _set_weekday_buttons(self, weekdays: list[str]) -> None:
        selected = {int(value) for value in weekdays}
        for weekday_id, button in self.weekday_buttons.items():
            button.setChecked(weekday_id in selected)

    def _schedule_qtime(self, value: str) -> QTime:
        time_value = QTime.fromString(value, "HH:mm")
        if not time_value.isValid():
            raise ValueError(f"schedule.time must be HH:MM, got {value!r}")
        return time_value

    def _sync_subscriber_widgets_to_config(self) -> None:
        subscriber = self.config.subscriber
        subscriber.pull_interval_hours = int(self.pull_interval_spin.value())
        subscriber.initial_lookback_days = int(self.lookback_spin.value())
        subscriber.auto_download = bool(self.auto_download_check.isChecked())

    def _render_books(self) -> None:
        self.book_list.clear()
        for book in self.config.broadcaster.books:
            suffix = "" if book.enabled else " disabled"
            self.book_list.addItem(f"{book.site} | {book.title} | {book.url}{suffix}")

    def _render_follows(self) -> None:
        self.follow_list.clear()
        for follow in self.config.subscriber.follows:
            alias = f" ({follow.alias})" if follow.alias else ""
            self.follow_list.addItem(f"{follow.bid}{alias}")

    def _load_customname(self, customname: str) -> None:
        customname = customname.strip() or DEFAULT_CUSTOMNAME
        self.customname = customname
        self.config = load_subscription(customname, base_dir=self.base_dir)
        self._load_config_into_widgets()

    def _save_from_button(self) -> None:
        def action() -> None:
            self.save_current()
            InfoBar.success(title="", content="订阅配置已保存", orient=Qt.Horizontal, position=InfoBarPosition.BOTTOM, duration=2000, parent=self)

        self._run_ui_action(action)

    def _publish_share_card_from_button(self) -> None:
        started = self.task_mgr.execute_simple_task(
            self.publish_share_card,
            success_callback=self._on_share_card_published,
            tooltip_title="订阅分享",
            tooltip_content="发布分享卡片",
            success_message="分享链已发布",
            task_id=f"subscription_share_card_{self.customname}",
            show_success_info=False,
        )
        if not started:
            return

    def _on_share_card_published(self, result) -> None:
        InfoBar.success(
            title="",
            content=f"分享链已发布 {result.discord_message_id}",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=3000,
            parent=self,
        )

    def _import_preview_books_from_button(self) -> None:
        def action() -> None:
            self.import_preview_books()
            InfoBar.info(
                title="",
                content="已切回预览，勾选后点击「加入订阅」",
                orient=Qt.Horizontal,
                position=InfoBarPosition.BOTTOM,
                duration=2500,
                parent=self,
            )

        self._run_ui_action(action)

    def _add_follow_from_inputs(self) -> None:
        def action() -> None:
            self.add_follow(self.follow_bid_edit.text(), self.follow_alias_edit.text())
            self.follow_bid_edit.clear()
            self.follow_alias_edit.clear()

        self._run_ui_action(action)

    def _update_follow_from_inputs(self) -> None:
        def action() -> None:
            row = self.follow_list.currentRow()
            if row < 0:
                raise ValueError("select a subscriber follow before updating")
            bid = self.follow_bid_edit.text().strip()
            alias = self.follow_alias_edit.text().strip()
            if not bid:
                raise ValueError("follow requires bid")
            self.config.subscriber.follows[row] = FollowEntry(bid=bid, alias=alias, added_at=self._utc_now())
            self._render_follows()
            self.follow_list.setCurrentRow(row)

        self._run_ui_action(action)

    def _load_selected_book(self, row: int) -> None:
        if row < 0 or row >= len(self.config.broadcaster.books):
            self._loading = True
            try:
                self.book_enabled_check.setChecked(False)
            finally:
                self._loading = False
            return
        self._loading = True
        try:
            book = self.config.broadcaster.books[row]
            self.book_enabled_check.setChecked(book.enabled)
        finally:
            self._loading = False

    def _load_selected_follow(self, row: int) -> None:
        if row < 0 or row >= len(self.config.subscriber.follows):
            return
        follow = self.config.subscriber.follows[row]
        self.follow_bid_edit.setText(follow.bid)
        self.follow_alias_edit.setText(follow.alias)

    def _toggle_selected_book_enabled(self, state: int) -> None:
        if self._loading:
            return
        row = self.book_list.currentRow()
        if row < 0 or row >= len(self.config.broadcaster.books):
            return
        self.config.broadcaster.books[row].enabled = bool(state)
        self._render_books()
        self.book_list.setCurrentRow(row)

    def remove_selected_book(self) -> None:
        row = self.book_list.currentRow()
        if row < 0:
            raise ValueError("select a broadcaster book before removing")
        del self.config.broadcaster.books[row]
        self._render_books()

    def add_follow(self, bid: str, alias: str) -> None:
        bid = bid.strip()
        alias = alias.strip()
        if not bid:
            raise ValueError("follow requires bid")
        self.config.subscriber.follows.append(FollowEntry(bid=bid, alias=alias, added_at=self._utc_now()))
        self._render_follows()

    def remove_selected_follow(self) -> None:
        row = self.follow_list.currentRow()
        if row < 0:
            raise ValueError("select a subscriber follow before removing")
        del self.config.subscriber.follows[row]
        self._render_follows()

    def _book_entry_from_preview_book(self, book) -> BookEntry:
        site = str(getattr(book, "source", "") or "").strip()
        url = str(getattr(book, "url", "") or getattr(book, "preview_url", "") or "").strip()
        title = str(getattr(book, "name", "") or "").strip()
        if not site or not url or not title:
            raise ValueError("preview book missing site/url/title")
        return BookEntry(site=site, url=url, title=title, enabled=True)

    def _conf_discord_user_token(self) -> str:
        return str(conf.discord_share_user_token or "").strip()

    def _require_discord_token(self) -> str:
        token = self._conf_discord_user_token()
        if token:
            return token
        self.gui.conf_dia.show_self()
        raise ValueError("conf.discord_share_user_token is required")

    async def _register_publish_bid(self, worker: WorkerIndexClient, book):
        summary = {
            "site": str(book.site or "").strip(),
            "title": str(book.title or "").strip(),
            "book_url": str(book.url or "").strip(),
        }
        return await worker.register_publish_bid(summary=summary)

    async def _publish_share_card(self, *, share_api: DiscordShareAPI, book_names: list[str]):
        channel_id = str(CGS_METADATA_CHANNEL_ID or "").strip()
        if not channel_id:
            raise ValueError("CGS_METADATA_CHANNEL_ID is required before publishing share_card")
        return await share_api.publish_share_card(channel_id=channel_id, book_names=book_names)

    @staticmethod
    def _default_share_api_factory(user_token: str) -> DiscordShareAPI:
        return DiscordShareAPI(str(CGS_DISCORD_SHARE_API or "").strip(), user_token)

    @staticmethod
    def _default_worker_client_factory(user_token: str) -> WorkerIndexClient:
        return WorkerIndexClient(auth_token=user_token)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
