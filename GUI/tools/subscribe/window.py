# -*- coding: utf-8 -*-
"""Frameless subscribe library window shell."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    StrongBodyLabel,
    TransparentToolButton,
    VBoxLayout,
)
from qframelesswindow import FramelessWindow
from qframelesswindow.utils import startSystemMove

from GUI.core.theme import CustTheme, theme_mgr
from GUI.core.theme.qss_template import render_templated_qss_section
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components.icons import CgsIcon
from utils import conf, ori_path
from utils.config.qc import cgs_cfg
from utils.share import DiscordShareAPI, WorkerIndexClient
from utils.subscription import (
    PublishSection,
    ShareCard,
    SubscriptionStore,
    get_active_subscription_customname,
    remove_yaml_book,
    set_active_subscription_customname,
)
from utils.subscription.library import LocalLibraryStore
from utils.tray.schedule_presentation import ScheduleCache
from utils.tray.subscription_scheduler import SubscriptionScheduler, default_scheduler_state_path
from variables import (
    CGS_DISCORD_SHARE_API,
    CGS_METADATA_CHANNEL_ID,
    SPIDERS,
    SPIDERS_LABELS,
)

from .common import (
    resolve_subscribe_site_index,
    subscribe_site_indexes,
)
from .cover_session import CoverSession
from .library_board import LibraryBoard
from .side_panel import SubscribeSidePanel

SUBSCRIBE_QSS_PATH = ori_path.joinpath("GUI/core/theme/subscribe.qss")


class SubscribeWindow(FramelessWindow):
    """订阅管理：ComfyJobsDialog shell + ProgressClass cards + FlowLayout."""

    def __init__(
        self,
        parent=None,
        *,
        store: SubscriptionStore | None = None,
        share_api_factory=None,
        worker_client_factory=None,
    ):
        super().__init__()
        self.gui = parent
        # Whole-library binding currently active for tray (not a per-card schedule).
        if store is not None:
            self.store = store
        else:
            self.store = SubscriptionStore(get_active_subscription_customname())
        self.library = LocalLibraryStore()
        self.schedule_cache = ScheduleCache()
        self.task_mgr = AsyncTaskManager(self.gui, self)
        self._share_api_factory = share_api_factory or self._default_share_api_factory
        self._worker_client_factory = worker_client_factory or self._default_worker_client_factory

        # --- session flags (window lifecycle; not a multi-state FSM) ---
        self._closing = False
        self._content_hydrated = False
        self._side_panel_expanded = True

        # --- library + cover owners (assembled below after chrome exists) ---
        self._selected_card_key: str | None = None
        self.cover_session: CoverSession | None = None
        self.library_board: LibraryBoard | None = None
        self._theme_callback = self._apply_subscribe_qss

        self.setObjectName("SubscribeWindow")
        self.setWindowTitle("订阅管理")
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()

        self.setMinimumSize(900, 560)
        self._restore_window_geometry()

        self.config = self.store.load()
        self._ensure_library_from_yaml()
        self._build_ui()
        theme_mgr.subscribe(self._theme_callback)
        self.destroyed.connect(self._unsubscribe_theme)
        self._apply_subscribe_qss(theme_mgr.get_theme())
        # Heavy library paint happens once in showEvent / explicit refresh callers.
        self._load_config_into_widgets()
        self._sync_site_filter_from_gui()
        self._refresh_status_bar()
        set_active_subscription_customname(self.store.customname)

    # SidePanel owns these symbols; shell proxies them for probes / legacy call sites.
    # Live getattr — not one-shot setattr snapshots (mutable state must write through).
    _SIDE_PANEL_PROXY_NAMES = frozenset({
        "card_conf_frame",
        "card_conf_title",
        "bookJoinBtn",
        "weekday_button_group",
        "weekday_buttons",
        "time_picker",
        "tz_btn",
        "tz_offset",
        "card_reset_check_btn",
        "global_frame",
        "profile_combo",
        "profile_delete_btn",
        "site_proxy_btn",
        "site_proxy_grid",
        "profile_default_toggle_btn",
        "profile_default_body",
        "profile_weekday_button_group",
        "profile_weekday_buttons",
        "profile_time_picker",
        "profile_tz_btn",
        "profile_tz_offset",
        "share_card_label",
        "publish_share_card_btn",
        "follow_section_title",
        "follow_list",
        "follow_detail_label",
        "follow_remove_btn",
        "follow_input_host",
        "follow_bid_edit",
        "follow_add_btn",
        "side_save_btn",
        "side_fill_spacer",
        "_loading",
        "_side_dirty",
        "_card_check_inherits",
        "_card_check_draft",
        "_site_proxy_tip",
        "_profile_default_expanded",
        "_mark_side_dirty",
        "_sync_tz_offset_button",
        "_align_tz_btn_to_time_picker",
        "_on_card_slot_field_edited",
        "_load_config_into_widgets",
        "_sync_card_conf_panel",
        "_ensure_yaml_book_entry_for_library_book",
        "_save_side_panel_config",
        "add_follow",
        "remove_selected_follow",
    })
    _SIDE_PANEL_STATE_NAMES = frozenset({
        "_loading",
        "_side_dirty",
        "_card_check_inherits",
        "_card_check_draft",
        "_site_proxy_tip",
        "_profile_default_expanded",
        "tz_offset",
        "profile_tz_offset",
        "site_proxy_grid",
    })

    @property
    def scroll(self):
        """Board ScrollArea. Explicit property shadows QWidget.scroll(dx, dy)."""
        board = self.__dict__.get("library_board")
        if board is None:
            raise AttributeError("library_board not assembled")
        return board.scroll

    @property
    def cards_host(self):
        board = self.__dict__.get("library_board")
        if board is None:
            raise AttributeError("library_board not assembled")
        return board.cards_host

    @property
    def cards_layout(self):
        board = self.__dict__.get("library_board")
        if board is None:
            raise AttributeError("library_board not assembled")
        return board.cards_layout

    @property
    def empty_label(self):
        board = self.__dict__.get("library_board")
        if board is None:
            raise AttributeError("library_board not assembled")
        return board.empty_label

    @property
    def _cards(self):
        board = self.__dict__.get("library_board")
        if board is None:
            return []
        return board.cards

    @property
    def _cards_by_key(self):
        board = self.__dict__.get("library_board")
        if board is None:
            return {}
        return board.cards_by_key

    @property
    def _cover_generation(self) -> int:
        cover = self.__dict__.get("cover_session")
        if cover is None:
            return 0
        return int(cover.cover_generation)

    def _ensure_cover_worker(self):
        """Probe/legacy name — CoverSession owns the worker lifecycle."""
        cover = self.cover_session
        if cover is None:
            return None
        return cover.ensure_cover_worker()

    def _stop_cover_worker(self, *, wait: bool = False) -> None:
        cover = self.cover_session
        if cover is None:
            return
        cover.stop_cover_worker(wait=wait)

    def __getattr__(self, name: str):
        # SidePanel is the config-editor owner. Probe/legacy paths still address the
        # shell; live-proxy every panel attribute rather than a frozen name list.
        panel = self.__dict__.get("side_panel")
        if panel is not None:
            try:
                return getattr(panel, name)
            except AttributeError:
                pass
        board = self.__dict__.get("library_board")
        if board is not None and name == "_filter_site_index":
            return board.filter_site_index
        cover = self.__dict__.get("cover_session")
        if cover is not None:
            if name == "_cover_cache":
                return cover.cover_cache
            if name == "_cover_inflight":
                return cover.cover_inflight
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __setattr__(self, name: str, value) -> None:
        # Mutable SidePanel state must write through (probes assign window._loading etc.).
        panel = self.__dict__.get("side_panel")
        if panel is not None and name in SubscribeWindow._SIDE_PANEL_STATE_NAMES:
            setattr(panel, name, value)
            return
        if panel is not None and name not in {
            "side_panel",
            "library_board",
            "cover_session",
            "gui",
            "store",
            "library",
            "config",
            "schedule_cache",
            "task_mgr",
            "_closing",
            "_content_hydrated",
            "_side_panel_expanded",
            "_selected_card_key",
            "_theme_callback",
            "_share_api_factory",
            "_worker_client_factory",
        }:
            # Only write-through names the panel already owns (avoid inventing attrs).
            if hasattr(type(panel), name) or name in getattr(panel, "__dict__", {}):
                setattr(panel, name, value)
                return
        board = self.__dict__.get("library_board")
        if board is not None and name == "_filter_site_index":
            board.filter_site_index = value
            return
        super().__setattr__(name, value)

    def _unsubscribe_theme(self, *_args) -> None:
        theme_mgr.unsubscribe(self._theme_callback)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Re-measure after layout so tz_btn height tracks the painted TimePicker.
        self._align_tz_btn_to_time_picker()
        # First show only: avoid open_subscribe_window + showEvent double full refresh.
        if self._content_hydrated:
            return
        self._content_hydrated = True
        # Load/status/library failures must reach SpiderGUI.hook_exception — no swallow.
        self.config = self.store.load()
        self._ensure_library_from_yaml()
        self._load_config_into_widgets()
        self._sync_site_filter_from_gui()
        self._refresh_status_bar()
        self.refresh_library()
        self._align_tz_btn_to_time_picker()

    def receive_pushed_books(self, books: list) -> None:
        pushed = list(books or [])
        if not pushed:
            raise ValueError("no books were pushed from preview")
        allowed = subscribe_site_indexes()
        fallback_site_index = None
        preview_manager = getattr(self.gui, "preview_mgr", None) if self.gui is not None else None
        if preview_manager is not None:
            try:
                fallback_site_index = int(preview_manager.site_index)
            except (TypeError, ValueError):
                fallback_site_index = None
        added = 0
        skipped = 0
        yaml_books_changed = False
        for book in pushed:
            site_index = resolve_subscribe_site_index(book, fallback_site_index=fallback_site_index)
            if site_index is None or int(site_index) not in allowed:
                skipped += 1
                continue
            spider_name = str(SPIDERS.get(int(site_index)) or "")
            if spider_name and str(getattr(book, "source", "") or "") != spider_name:
                setattr(book, "source", spider_name)
            if self.library.add_book(int(site_index), book):
                added += 1
                if self._ensure_yaml_book_entry_for_library_book(
                    int(site_index),
                    book,
                    apply_default_weekdays=True,
                ):
                    yaml_books_changed = True
            else:
                skipped += 1
        if yaml_books_changed:
            self.store.save(self.config)
            self.config = self.store.load()
        self.refresh_library()
        InfoBar.success(
            title="",
            content=f"已添加 {added} 项本地收藏，跳过 {skipped} 个重复/不支持项",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=2500,
            parent=self,
        )

    def refresh_library(self) -> None:
        board = self.library_board
        cover = self.cover_session
        if board is None or cover is None:
            return
        kept = board.refresh(
            library=self.library,
            selected_card_key=self._selected_card_key,
            count_label=self.library_count_label,
        )
        if kept:
            self._on_card_selected(kept)
        else:
            self._selected_card_key = None
            self._sync_card_conf_panel(None)
        cover.start_dl_scan()

    def server_mode_switch_blockers(self) -> list[str]:
        if self.task_mgr.get_running_tasks():
            return ["subscribe task"]
        return []

    def import_preview_books(self) -> None:
        if self.gui is None:
            raise ValueError("subscribe window requires gui")
        preview_manager = self.gui.preview_mgr
        if not preview_manager.books_cache:
            raise ValueError("open a preview with books before importing")
        browser = self.gui.BrowserWindow
        if not browser or not browser.page_runtime.page_ready:
            raise ValueError("open the current preview before importing")
        # Subscribe push is mangaCard-only — never JM/ero specials.
        is_manga_like = bool(preview_manager.is_manga)
        browser.subscription.configure_entry(is_manga_like=is_manga_like)
        if is_manga_like:
            browser.subscription.enter_selection()
        browser.show()
        browser.raise_()
        browser.activateWindow()

    async def publish_share_card(self):
        if self.config.publish is not None:
            raise ValueError("share_card already published")
        enabled_books = [
            entry
            for entry in self.library.book_entries(yaml_books=self.config.books)
            if bool(entry.enabled)
            and (site_index := LocalLibraryStore.site_index_for_name(entry.site)) is not None
            and int(site_index) in subscribe_site_indexes()
        ]
        if not enabled_books:
            raise ValueError("at least one library book is required before publishing share_card")

        token = self._require_discord_token()
        worker = self._worker_client_factory(token)
        registration = await self._register_publish_bid(worker, enabled_books[0])
        share_api = self._share_api_factory(token)
        result = await self._publish_share_card(
            share_api=share_api,
            book_names=[book.title for book in enabled_books],
        )
        self.config.publish = PublishSection(
            bid=registration.bid,
            share_card=ShareCard(
                posted_at=result.posted_at,
                discord_channel=result.discord_channel,
                discord_message_id=result.discord_message_id,
            ),
        )
        self.store.save(self.config)
        self.config = self.store.load()
        self._load_config_into_widgets()
        return result

    def closeEvent(self, event) -> None:
        self._closing = True
        self._persist_window_geometry()
        if self.cover_session is not None:
            self.cover_session.shutdown(wait=True)
        if self.library_board is not None:
            self.library_board.cards_by_key.clear()
            self.library_board.clear_cards()
        super().closeEvent(event)

    @staticmethod
    def _normalized_window_rect(x: int, y: int, width: int, height: int) -> QRect:
        """Keep restored geometry usable when a prior monitor was disconnected."""
        min_width, min_height = 900, 560
        width = max(min_width, int(width))
        height = max(min_height, int(height))
        proposed = QRect(int(x), int(y), width, height)
        screens = QApplication.screens()
        if not screens:
            return proposed

        def _visible_enough(rect: QRect) -> bool:
            for screen in screens:
                intersection = screen.availableGeometry().intersected(rect)
                if intersection.width() >= min(120, rect.width()) and intersection.height() >= 48:
                    return True
            return False

        if _visible_enough(proposed):
            return proposed

        primary = QApplication.primaryScreen() or screens[0]
        available = primary.availableGeometry()
        fitted_width = min(width, available.width())
        fitted_height = min(height, available.height())
        return QRect(
            available.x() + max(0, (available.width() - fitted_width) // 2),
            available.y() + max(0, (available.height() - fitted_height) // 2),
            fitted_width,
            fitted_height,
        )

    def _restore_window_geometry(self) -> None:
        saved_rect = cgs_cfg.subscribeWinRect.value
        if saved_rect and len(saved_rect) >= 4:
            x, y, width, height = (int(value) for value in saved_rect[:4])
            self.setGeometry(self._normalized_window_rect(x, y, width, height))
            return
        screen = QGuiApplication.primaryScreen()
        screen_geo = screen.availableGeometry() if screen is not None else None
        if screen_geo is not None:
            window_width = max(980, int(screen_geo.width() * 0.82))
            window_height = max(640, int(screen_geo.height() * 0.82))
            self.resize(window_width, window_height)
            self.move(
                int(screen_geo.x() + (screen_geo.width() - self.width()) / 2),
                int(screen_geo.y() + (screen_geo.height() - self.height()) / 2),
            )
        else:
            self.resize(1100, 720)

    def _persist_window_geometry(self) -> None:
        geometry = self._normalized_window_rect(self.x(), self.y(), self.width(), self.height())
        cgs_cfg.subscribeWinRect.value = [
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
        ]
        cgs_cfg.save()

    def _build_ui(self) -> None:
        """ComfyJobsDialog shell: header + ScrollArea/FlowLayout hero + status bar + side rail."""
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 14)
        root.setSpacing(8)

        self.header_shell = QFrame(self)
        self.header_shell.setObjectName("SubscribeHeaderShell")
        self.header_shell.installEventFilter(self)
        header = QHBoxLayout(self.header_shell)
        header.setContentsMargins(14, 6, 8, 6)
        header.setSpacing(8)

        title_block = QWidget(self.header_shell)
        title_layout = VBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        self.header_title = StrongBodyLabel("订阅管理", title_block)
        self.header_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.library_count_label = CaptionLabel("0 部", title_block)
        self.library_count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title_layout.addWidget(self.header_title)
        title_layout.addWidget(self.library_count_label)
        header.addWidget(title_block)

        self.site_filter_combo = ComboBox(self.header_shell)
        self.site_filter_combo.setMinimumWidth(160)
        self.site_filter_combo.addItem("全部", userData=None)
        for site_index in sorted(subscribe_site_indexes()):
            label = SPIDERS_LABELS.get(site_index) or SPIDERS.get(site_index) or str(site_index)
            self.site_filter_combo.addItem(label, userData=int(site_index))
        self.site_filter_combo.currentIndexChanged.connect(self._on_site_filter_changed)
        header.addWidget(self.site_filter_combo)
        header.addStretch(1)

        self.import_preview_btn = TransparentToolButton(FIF.DOWNLOAD, self.header_shell)
        self.import_preview_btn.clicked.connect(self._import_preview_books_from_button)
        header.addWidget(self.import_preview_btn)

        self.refresh_btn = TransparentToolButton(FIF.SYNC, self.header_shell)
        self.refresh_btn.clicked.connect(lambda _checked=False: self.refresh_library())
        header.addWidget(self.refresh_btn)

        self.side_panel_btn = TransparentToolButton(FIF.MENU, self.header_shell)
        self.side_panel_btn.clicked.connect(self._toggle_side_panel)
        header.addWidget(self.side_panel_btn)

        self.close_button = TransparentToolButton(self.header_shell)
        self.close_button.setIcon(QIcon(":/close.svg"))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        root.addWidget(self.header_shell)

        body = QWidget(self)
        body.setObjectName("SubscribeBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        self.cover_session = CoverSession(
            self,
            cards_by_key=lambda: self.library_board.cards_by_key if self.library_board else {},
            cards=lambda: self.library_board.cards if self.library_board else [],
            is_closing=lambda: self._closing,
        )
        self.library_board = LibraryBoard(
            self,
            cover_session=self.cover_session,
            on_card_selected=self._on_card_selected,
            on_card_delete_requested=self._on_card_delete_requested,
            parent=body,
        )
        self.status_bar = QFrame(self.library_board)
        self.status_bar.setObjectName("SubscribeStatusBar")
        self.status_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(10, 6, 10, 6)
        status_layout.setSpacing(16)
        self.last_run_label = CaptionLabel("上次执行：-", self.status_bar)
        self.last_run_label.setObjectName("SubscribeStatusLastRun")
        self.next_run_label = CaptionLabel("下次执行：-", self.status_bar)
        self.next_run_label.setObjectName("SubscribeStatusNextRun")
        status_layout.addWidget(self.last_run_label, 0)
        status_layout.addWidget(self.next_run_label, 0)
        status_layout.addStretch(1)
        self.library_board.attach_status_bar(self.status_bar)
        body_layout.addWidget(self.library_board, 1)

        self.side_panel = SubscribeSidePanel(self, body)
        body_layout.addWidget(self.side_panel, 0)
        root.addWidget(body, 1)

    def _toggle_side_panel(self) -> None:
        self._side_panel_expanded = not self._side_panel_expanded
        self.side_panel.setVisible(self._side_panel_expanded)

    def _on_site_filter_changed(self, *_args) -> None:
        if self._loading:
            return
        value = self.site_filter_combo.currentData()
        if value is not None:
            value = int(value)
        if self.library_board is not None:
            self.library_board.filter_site_index = value
        self.refresh_library()

    def _sync_site_filter_from_gui(self) -> None:
        """Default filter follows SpiderGUI.chooseBox when it is a manga site."""
        if not hasattr(self, "site_filter_combo"):
            return
        target = None
        choose_box = getattr(self.gui, "chooseBox", None) if self.gui is not None else None
        if choose_box is not None:
            try:
                current = int(choose_box.currentIndex())
            except (TypeError, ValueError):
                current = 0
            if current in subscribe_site_indexes():
                target = current
        self._loading = True
        try:
            matched = False
            for index in range(self.site_filter_combo.count()):
                data = self.site_filter_combo.itemData(index)
                if target is None and data is None:
                    self.site_filter_combo.setCurrentIndex(index)
                    matched = True
                    break
                if target is not None and data is not None and int(data) == int(target):
                    self.site_filter_combo.setCurrentIndex(index)
                    matched = True
                    break
            if not matched:
                self.site_filter_combo.setCurrentIndex(0)
            value = self.site_filter_combo.currentData()
            if value is not None:
                value = int(value)
            if self.library_board is not None:
                self.library_board.filter_site_index = value
        finally:
            self._loading = False

    def _header_press_hits_button(self, position) -> bool:
        hit_widget = self.header_shell.childAt(position)
        while hit_widget is not None and hit_widget is not self.header_shell:
            if isinstance(hit_widget, QAbstractButton):
                return True
            hit_widget = hit_widget.parentWidget()
        return False

    def eventFilter(self, obj, event):
        if obj is self.header_shell and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                press_pos = event.position().toPoint()
                if not self._header_press_hits_button(press_pos):
                    startSystemMove(self, event.globalPosition().toPoint())
                    return True
        return super().eventFilter(obj, event)

    def _apply_subscribe_qss(self, theme=None) -> None:
        current = theme if theme is not None else theme_mgr.get_theme()
        if isinstance(current, CustTheme):
            theme_name = current.value
        else:
            theme_name = "dark" if theme_mgr.get_theme() == CustTheme.DARK else "light"
        try:
            qss = render_templated_qss_section(SUBSCRIBE_QSS_PATH, theme_name, "window")
        except Exception:
            qss = ""
        self.setStyleSheet(qss)

    def _ensure_library_from_yaml(self) -> None:
        if not self.config.books:
            return
        self.library.ensure_books_from_yaml(self.config.books)

    def _refresh_status_bar(self) -> None:
        """Schedule chrome from cache + scheduler. Domain errors propagate to hook_exception."""
        if not hasattr(self, "last_run_label") or not hasattr(self, "next_run_label"):
            return
        last_text = "上次执行：-"
        summary = self.schedule_cache.read_summary()
        if summary is not None:
            run = summary.get("run") or {}
            finished_at = str(run.get("finished_at") or "")
            if finished_at:
                elapsed = float(run.get("elapsed_sec") or 0.0)
                last_text = f"上次执行：{self._relative_time(finished_at)}（{elapsed:.0f}s）"
        self.last_run_label.setText(last_text)

        next_text = "下次执行：-"
        scheduler = SubscriptionScheduler(
            self.store.load,
            state_path=default_scheduler_state_path(),
        )
        next_run_at = scheduler.status().next_run_at
        if next_run_at is not None:
            next_text = f"下次执行：{next_run_at.strftime('%m-%d %H:%M')}"
        self.next_run_label.setText(next_text)

    @staticmethod
    def _relative_time(iso_z: str) -> str:
        moment = datetime.fromisoformat(iso_z.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - moment
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 60:
            return "刚刚"
        if seconds < 3600:
            return f"{seconds // 60}分钟前"
        if seconds < 86400:
            return f"{seconds // 3600}小时前"
        return f"{seconds // 86400}天前"

    def _on_card_selected(self, card_key: str) -> None:
        key = str(card_key or "")
        if not key:
            return
        self._selected_card_key = key
        if self.library_board is not None:
            self.library_board.set_selection_visual(key)
        if not self._side_panel_expanded:
            self._side_panel_expanded = True
            self.side_panel.setVisible(True)
        self._sync_card_conf_panel(key)

    def _on_card_delete_requested(self, card_key: str) -> None:
        """Delete the yml schedule row and library join, then drop the card."""
        key = str(card_key or "")
        board = self.library_board
        if board is None:
            return
        card = board.cards_by_key.get(key)
        if card is None:
            return
        site_index = int(card.site_index)
        book_url = LocalLibraryStore.book_unique_url(card.book)
        site_name = LocalLibraryStore.book_site(card.book, site_index=site_index)
        title = LocalLibraryStore.book_title(card.book) or key
        if not book_url:
            self._show_error(f"无法删除订阅：缺少书目 URL · {title}")
            return

        try:
            yaml_removed = remove_yaml_book(self.config, site_name, book_url)
            if yaml_removed:
                self.store.save(self.config)
            library_removed = self.library.remove_url(site_index, book_url)
        except Exception as error:
            self._show_error(f"删除订阅失败 · {error}")
            return
        if not yaml_removed and not library_removed:
            # Stale card only: no persistence row claimed this delete.
            if self._selected_card_key == key:
                self._selected_card_key = None
                self._sync_card_conf_panel(None)
            board.remove_card(key)
            board.show_empty_after_delete(self.library_count_label)
            return

        if self._selected_card_key == key:
            self._selected_card_key = None
            self._sync_card_conf_panel(None)
        board.remove_card(key)
        board.show_empty_after_delete(self.library_count_label)
        InfoBar.success(
            title="",
            content=f"已删除订阅 · {title}",
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=2200,
            parent=self,
        )

    def _run_ui_action(self, action) -> None:
        """Slot-safe: show InfoBar only — never re-raise into sys.excepthook white box."""
        try:
            action()
        except Exception as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            title="",
            content=message,
            orient=Qt.Horizontal,
            position=InfoBarPosition.BOTTOM,
            duration=5000,
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

    def _require_discord_token(self) -> str:
        token = str(getattr(conf, "discord_share_user_token", "") or "").strip()
        if not token:
            raise ValueError("discord_share_user_token is required")
        return token

    def _default_share_api_factory(self, token: str):
        return DiscordShareAPI(token=token, api_base=CGS_DISCORD_SHARE_API)

    def _default_worker_client_factory(self, token: str):
        return WorkerIndexClient(token=token)

    async def _register_publish_bid(self, worker, book_entry: object):
        return await worker.register_bid(
            site=str(getattr(book_entry, "site", "") or ""),
            title=str(getattr(book_entry, "title", "") or ""),
            url=str(getattr(book_entry, "url", "") or ""),
        )

    async def _publish_share_card(self, *, share_api, book_names: list[str]):
        return await share_api.publish_share_card(
            channel_id=CGS_METADATA_CHANNEL_ID,
            book_names=book_names,
            customname=self.store.customname,
        )
