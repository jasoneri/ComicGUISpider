from copy import deepcopy
import httpx
import os
import typing as t
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QEvent, QObject, QSize, QUrl
from PySide6.QtWidgets import QWidget, QLabel, QFrame
from PySide6.QtGui import QGuiApplication, QPixmap, QDesktopServices
from qfluentwidgets import (
    ProgressBar, VBoxLayout, PrimaryToolButton, TransparentToolButton,
    FluentIcon as FIF, TeachingTipTailPosition, ImageLabel
)

from GUI.core.anim import ExpandCollapseOrchestrator, ContentTarget
from GUI.core.timer import safe_single_shot
from GUI.manager.async_task import AsyncTaskManager, TaskConfig
from GUI.uic.qfluent.components import DlStatusBadge, CustomTeachingTip
from utils import conf, TaskObj, TasksObj, curr_os, get_httpx_verify
from utils.network.doh import build_http_transport
from utils.sql import SqlRecorder
from utils.website import spider_utils_map
from utils.website.core import Previewer
from utils.website.runtime_context import PreviewSiteConfig


class TaskProgress:
    """任务进度状态（不依赖 Qt）"""
    __slots__ = ("tasks_obj", "_downloaded_count", "last_percent", "completed")

    def __init__(self, tasks_obj: TasksObj):
        self.tasks_obj = tasks_obj
        self._downloaded_count = len(tasks_obj.downloaded)
        self.last_percent = (
            int(self._downloaded_count / tasks_obj.tasks_count * 100)
            if tasks_obj.tasks_count > 0 else 0
        )
        self.completed = self.last_percent >= 100

    @property
    def taskid(self) -> str:
        return self.tasks_obj.taskid

    @property
    def tasks_count(self) -> int:
        return self.tasks_obj.tasks_count

    @property
    def downloaded(self) -> int:
        return self._downloaded_count

    def apply(self, event: TaskObj) -> int:
        """接收一个下载事件，更新进度，返回百分比"""
        self._downloaded_count += 1
        self.last_percent = int(self._downloaded_count / self.tasks_obj.tasks_count * 100)
        if self.last_percent >= 100:
            self.completed = True
        return self.last_percent


class ProgressClass(QFrame):
    MAX_TITLE_LENGTH = 70
    COVER_HEIGHT = 110
    DEFAULT_COVER_WIDTH = 130
    BADGE_MARGIN = 4
    BADGE_SPACING = 3
    ACTION_BUTTON_SIZE = 18
    PAGE_BADGE_STYLE = (
        "background: rgba(0, 0, 0, 0.6);"
        "color: white;"
        "font-size: 9pt;"
        "padding: 1px 4px;"
        "border-radius: 3px;"
    )

    def __init__(self, parent: QWidget, progress: TaskProgress):
        super().__init__(parent)
        self.taskid = progress.taskid
        self.is_completed = False
        self._cover_source = None
        self.tasks_obj = progress.tasks_obj

        layout = VBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.cover_label = ImageLabel(self)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setStyleSheet("background: rgba(0, 0, 0, 0.08); border-radius: 4px;")
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setFixedSize(self.DEFAULT_COVER_WIDTH, self.COVER_HEIGHT)

        for attr, icon, callback in (
            ("folder_btn", FIF.FOLDER, self._open_task_folder),
            ("link_btn", FIF.LINK, self._open_task_link),
        ):
            btn = TransparentToolButton(icon, self.cover_label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
            btn.setIconSize(QSize(12, 12))
            btn.setStyleSheet("background: rgba(20, 20, 20, 0.4);")
            btn.clicked.connect(callback)
            setattr(self, attr, btn)
        self.page_badge = QLabel(self.cover_label)
        self.page_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.page_badge.setStyleSheet(self.PAGE_BADGE_STYLE)
        self.title_label = QLabel(self)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setWordWrap(False)
        self.progress_bar = ProgressBar(self)

        layout.addWidget(self.cover_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress_bar)

        self.setFixedWidth(self.DEFAULT_COVER_WIDTH + 8)
        self.set_tasks_obj(progress.tasks_obj)

    @classmethod
    def _clip_task_name(cls, task_name: str) -> str:
        if len(task_name) <= cls.MAX_TITLE_LENGTH:
            return task_name
        split_mark = " - "
        if split_mark not in task_name:
            return f"{task_name[:cls.MAX_TITLE_LENGTH - 3]}..."
        title, episode_name = task_name.rsplit(split_mark, 1)
        suffix = f"{split_mark}{episode_name}"
        remain = cls.MAX_TITLE_LENGTH - len(suffix) - 3
        if remain > 0:
            return f"{title[:remain]}...{suffix}"
        return f"{title[:15]}...{suffix[:cls.MAX_TITLE_LENGTH - 18]}..."

    def set_tasks_obj(self, tasks_obj: TasksObj):
        self.tasks_obj = tasks_obj
        task_name = tasks_obj.display_title or self.taskid
        self.title_label.setText(self._clip_task_name(task_name))
        self.title_label.setToolTip(task_name)
        self.folder_btn.setEnabled(bool(tasks_obj.local_path))
        self.link_btn.setEnabled(bool(tasks_obj.title_url))
        self.page_badge.setText(f"{tasks_obj.tasks_count}P")
        self.page_badge.adjustSize()
        self._relocate_badge()

    def _relocate_badge(self):
        self.page_badge.adjustSize()
        badge_y = self.cover_label.height() - self.page_badge.height() - self.BADGE_MARGIN
        curr_x = self.BADGE_MARGIN
        for widget in (self.folder_btn, self.link_btn, self.page_badge):
            widget.move(curr_x, badge_y)
            curr_x += widget.width() + self.BADGE_SPACING

    def _open_task_folder(self):
        curr_os.open_folder(self.tasks_obj.local_path)

    def _open_task_link(self):
        QDesktopServices.openUrl(QUrl(self.tasks_obj.title_url))

    def _apply_cover_pixmap(self, pixmap: QPixmap) -> bool:
        if pixmap.isNull() or pixmap.height() <= 0:
            return False
        new_w = round(self.COVER_HEIGHT * pixmap.width() / pixmap.height())
        self.cover_label.setImage(pixmap)
        self.cover_label.setFixedSize(new_w, self.COVER_HEIGHT)
        self._relocate_badge()
        margins = self.layout().contentsMargins()
        self.setFixedWidth(self.cover_label.width() + margins.left() + margins.right())
        return True

    def set_cover(self, path: str):
        if path and self._apply_cover_pixmap(QPixmap(path)):
            self._cover_source = "local"

    def set_preview_cover(self, pixmap: QPixmap):
        if self._cover_source != "local" and self._apply_cover_pixmap(pixmap):
            self._cover_source = "preview"

    def set_progress(self, percent: int):
        self.progress_bar.setValue(percent)

    def mark_completed(self):
        self.is_completed = True
        self.progress_bar.setCustomBarColor(light="#00ff00", dark="#00cc00")

    def dispose(self):
        self.deleteLater()


class TaskProgressEntry:
    """单条任务 owner：进度、视图、封面预载、上下文替换都归这里。"""

    __slots__ = ("owner", "progress", "view")

    BROWSER_IMAGE_ACCEPT = (
        "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5"
    )

    def __init__(self, owner: "TaskProgressManager", tasks_obj: TasksObj):
        self.owner = owner
        self.progress = TaskProgress(tasks_obj)
        self.view: t.Optional[ProgressClass] = None

    @property
    def taskid(self) -> str:
        return self.progress.taskid

    @property
    def tasks_obj(self) -> TasksObj:
        return self.progress.tasks_obj

    @staticmethod
    def is_page_one(page) -> bool:
        if page is None:
            return False
        page_str = str(page).strip()
        if not page_str:
            return False
        stem, _ext = os.path.splitext(page_str)
        stem = stem.lower()
        if stem.isdigit():
            return int(stem.lstrip("0") or "0") == 1
        return stem in {"cover", "front", "first"}

    @staticmethod
    def cover_pixmap(data: bytes) -> QPixmap:
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        return pixmap

    def mount(self):
        if self.view is not None:
            return
        gui = self.owner.gui
        self.view = ProgressClass(gui.scroll_content, self.progress)
        gui.flow_layout.addWidget(self.view)
        self.refresh_view()

    def dispose_view(self, reset_view_ref: bool = False):
        if self.view is None:
            return
        self.view.dispose()
        if reset_view_ref:
            self.view = None

    def replace_tasks_obj(self, tasks_obj: TasksObj):
        next_tasks_obj = deepcopy(tasks_obj)
        if next_tasks_obj.cover_bytes is None:
            next_tasks_obj.cover_bytes = self.tasks_obj.cover_bytes
        self.progress.tasks_obj = next_tasks_obj
        self.refresh_view()

    def apply_task(self, task_obj: TaskObj):
        percent = self.progress.apply(task_obj)
        if self.view is not None and self.is_page_one(task_obj.page) and task_obj.success:
            cover = self.cover_path()
            if cover:
                self.view.set_cover(cover)
        if self.view is not None:
            self.view.set_progress(percent)
            if self.progress.completed and not self.view.is_completed:
                self.view.mark_completed()

    def refresh_view(self):
        if self.view is None:
            return
        self.view.set_tasks_obj(self.tasks_obj)
        self.view.set_progress(self.progress.last_percent)
        if self.progress.completed and not self.view.is_completed:
            self.view.mark_completed()
        cover = self.cover_path()
        if cover:
            self.view.set_cover(cover)
            return
        if self.tasks_obj.cover_bytes:
            self.view.set_preview_cover(self.cover_pixmap(self.tasks_obj.cover_bytes))
            return
        self.schedule_cover_preload()

    def cover_path(self) -> t.Optional[str]:
        if not self.tasks_obj.local_path:
            return None
        filename = None
        for task_obj in self.tasks_obj.downloaded:
            page = getattr(task_obj, "page", None)
            if not self.is_page_one(page):
                continue
            page_str = str(page).strip()
            _stem, ext = os.path.splitext(page_str)
            if ext:
                filename = page_str
            else:
                digits = len(str(self.tasks_obj.tasks_count))
                filename = f"{page_str.zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}"
            break
        if filename is None:
            digits = len(str(self.tasks_obj.tasks_count))
            filename = f"{'1'.zfill(digits)}.{getattr(conf, 'img_sv_type', 'jpg')}"
        path = os.path.join(self.tasks_obj.local_path, filename)
        return path if os.path.isfile(path) else None

    def schedule_cover_preload(self):
        provider_cls = spider_utils_map.get(getattr(self.tasks_obj, "source", None))
        if (
            not self.tasks_obj.cover_url
            or self.tasks_obj.cover_bytes
            or self.cover_path()
            or not provider_cls
            or not getattr(provider_cls, "cover_preload_via_http", True)
        ):
            return
        task_id = f"task_cover_{self.taskid}"
        cover_task_mgr = self.owner.cover_task_mgr
        if cover_task_mgr.is_task_running(task_id):
            return
        cover_task_mgr.execute_task(
            task_id,
            TaskConfig(
                task_func=self.download_cover_bytes,
                success_callback=self.on_cover_preload_success,
                error_callback=self.owner.gui.log.error,
                tooltip_title="",
                show_tooltip=False,
                show_success_info=False,
                show_error_info=False,
                tooltip_parent=None,
            ),
        )

    def on_cover_preload_success(self, data: bytes):
        self.tasks_obj.cover_bytes = data
        if self.view is not None:
            self.view.set_preview_cover(self.cover_pixmap(data))

    def download_cover_bytes(self) -> bytes:
        referer_url = Previewer.build_referer_url(
            getattr(self.tasks_obj, "title_url", None),
            request_url=getattr(self.tasks_obj, "cover_url", None),
        )
        browser_headers = {}
        gui = self.owner.gui
        browser = getattr(gui, "BrowserWindow", None)
        if browser is not None:
            request_path = urlparse(str(getattr(self.tasks_obj, "cover_url", "") or "")).path
            browser_headers = dict(
                browser.latest_image_request(
                    url=str(getattr(self.tasks_obj, "cover_url", "") or ""),
                    path_suffix=request_path,
                ).get("headers") or {}
            )

        provider_cls = spider_utils_map.get(getattr(self.tasks_obj, "source", None))
        if provider_cls is None:
            raise RuntimeError(f"cover preload provider unavailable: {getattr(self.tasks_obj, 'source', None)!r}")
        snapshot = getattr(gui, "_search_context", None)
        site_config = PreviewSiteConfig.from_snapshot(
            provider_cls.name,
            snapshot,
            conf_state=conf,
        )
        site_kw = site_config.as_provider_kwargs()
        client_kw = dict(provider_cls.preview_client_config(**site_kw) or {})
        provider_headers = client_kw.pop("headers", {})
        transport_kw = dict(provider_cls.preview_transport_config() or {})
        transport_verify = transport_kw.pop("verify", get_httpx_verify())
        transport, trust_env = build_http_transport(
            getattr(provider_cls, "proxy_policy", "proxy"),
            list(site_config.transport.proxies),
            doh_url=site_config.transport.doh_url,
            is_async=False,
            verify=transport_verify,
            **transport_kw,
        )

        with httpx.Client(
            headers=getattr(provider_cls, "book_hea", None) or getattr(provider_cls, "headers", {}),
            transport=transport,
            trust_env=trust_env,
            follow_redirects=True,
            timeout=15,
            **client_kw,
        ) as cli:
            headers = httpx.Headers(cli.headers)
            headers.update(provider_headers)
            headers.update(browser_headers)
            if "accept" not in headers or "image/" not in headers.get("accept", ""):
                headers["Accept"] = self.BROWSER_IMAGE_ACCEPT
            if referer_url and "referer" not in headers:
                headers["Referer"] = referer_url
            resp = cli.get(self.tasks_obj.cover_url, headers=headers)
            resp.raise_for_status()
            return resp.content


class ExpandPanelController(QObject):
    def __init__(self, owner: "TaskProgressManager"):
        super().__init__()
        self.owner = owner
        self.expand_btn = None
        self.orchestrator = None
        self._transitioning = False
        self._sync_pending = False

    def bind(self, expand_btn):
        gui = self.owner.gui
        self.expand_btn = expand_btn
        self.orchestrator = ExpandCollapseOrchestrator(
            window_target=gui,
            content_targets=[
                ContentTarget(
                    widget=gui.scroll_area,
                    measure_height=lambda _widget: self._panel_target_height(),
                )
            ],
            window_target_height_getter=self._window_target_height,
            can_expand_window=self._can_expand_window,
            after_collapse=self._sync_scroll_visibility,
        )
        self._transitioning = False
        gui.scroll_area.viewport().installEventFilter(self)

    def cleanup(self):
        gui = self.owner.gui
        try:
            gui.scroll_area.viewport().removeEventFilter(self)
        except (RuntimeError, AttributeError):
            pass
        if self.orchestrator is not None:
            self.orchestrator.cleanup()
            self.orchestrator = None
        self._transitioning = False
        self._sync_pending = False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self.request_scroll_sync()
        return False

    def request_scroll_sync(self):
        if self._sync_pending:
            return
        self._sync_pending = True
        safe_single_shot(0, self._do_scroll_sync)

    def _do_scroll_sync(self):
        self._sync_pending = False
        gui = self.owner.gui
        sa = gui.scroll_area
        if not sa.isVisible():
            return
        viewport_w = sa.viewport().width()
        if viewport_w <= 0:
            viewport_w = sa.width() - 2
        content_h = gui.flow_layout.heightForWidth(viewport_w)
        gui.scroll_content.setMinimumHeight(content_h)
        vbar = sa.scrollDelagate.vScrollBar
        vbar.scrollTo(vbar.maximum())

    def reset_content_height(self):
        gui = self.owner.gui
        gui.scroll_content.setMinimumHeight(0)
        if self.orchestrator is not None:
            self.orchestrator.set_content_height(gui.scroll_area, 0)

    def stop_and_reset(self):
        gui = self.owner.gui
        self._transitioning = False
        if self.orchestrator is not None:
            self.orchestrator.stop()
            self.orchestrator.set_content_height(gui.scroll_area, 0)

    def on_expand_clicked(self):
        if self.expand_btn is None:
            return
        if self._transitioning or (self.orchestrator and self.orchestrator.is_transitioning):
            return
        self._transitioning = True
        self.expand_btn.expand()
        if self.orchestrator is None:
            self._transitioning = False
            return
        transition = self.orchestrator.expand if self.expand_btn.expanded else self.orchestrator.collapse
        if not transition(self._finish_transition):
            self._finish_transition()

    def _available_screen_height(self) -> int:
        gui = self.owner.gui
        window_handle = gui.windowHandle()
        screen = window_handle.screen() if window_handle is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry().height() if screen is not None else gui.maximumHeight()

    def _layout_overhead(self) -> int:
        gui = self.owner.gui
        vl4_m = gui.verticalLayout_4.contentsMargins()
        sb_h = gui.statusbar.height() if gui.statusbar.isVisible() else 0
        vl2_spacing = gui.verticalLayout_2.spacing()
        fl_spacing = gui.funcLayout.spacing()
        bv_m = gui.barVLayout.contentsMargins()
        bv_spacing = gui.barVLayout.spacing()
        return (
            vl4_m.top() + vl4_m.bottom()
            + sb_h
            + vl2_spacing
            + gui.funcGroupBox.height()
            + fl_spacing
            + bv_m.top() + bv_m.bottom()
            + bv_spacing
            + gui.barHLayout.sizeHint().height()
        )

    def _panel_target_height(self) -> int:
        gui = self.owner.gui
        width = gui.scroll_area.viewport().width()
        if width <= 0:
            width = gui.width() - 20
        content_h = gui.flow_layout.heightForWidth(width)
        max_window = min(gui.maximumHeight(), self._available_screen_height())
        available = max_window - self._layout_overhead() - gui.showArea.minimumHeight()
        return max(self.owner.PANEL_MIN_HEIGHT, min(content_h, available))

    def _can_expand_window(self, panel_h: int) -> bool:
        gui = self.owner.gui
        return panel_h > 0 and gui.height() < min(
            gui.maximumHeight(), self._available_screen_height()
        )

    def _window_target_height(self, total_expand_delta: int) -> int:
        gui = self.owner.gui
        return min(
            gui.height() + total_expand_delta + 5,
            gui.maximumHeight(),
            self._available_screen_height(),
        )

    def _sync_scroll_visibility(self):
        self.owner.gui.scroll_area.setVisible(self.expand_btn.expanded)

    def _finish_transition(self):
        self._transitioning = False


class TaskProgressManager:
    PANEL_MIN_HEIGHT = 130

    def __init__(self, gui):
        self.gui = gui
        self._entries: t.Dict[str, TaskProgressEntry] = {}
        self.record_sql = SqlRecorder()
        self.cover_task_mgr = AsyncTaskManager(gui)
        self.expandBtn = None
        self.clearBtn = None
        self._dl_status_badge = None
        self.panel_ctrl = ExpandPanelController(self)

    def _set_entry_controls_visible(self, visible: bool):
        self.expandBtn.setVisible(visible)
        self.clearBtn.setVisible(visible)

    def _dispose_views(self, reset_view_ref: bool = False):
        layout = getattr(self.gui, "flow_layout", None)
        if layout is not None:
            while layout.count():
                layout.takeAt(0)
        for entry in self._entries.values():
            entry.dispose_view(reset_view_ref=reset_view_ref)

    def _on_clear_btn_clicked(self):
        accept_btn = PrimaryToolButton(FIF.ACCEPT)
        tip = CustomTeachingTip.create(
            [accept_btn],
            target=self.gui.clearBtn,
            parent=self.gui.clearBtn,
            content="清空任务列表",
            tailPosition=TeachingTipTailPosition.RIGHT,
        )
        accept_btn.clicked.connect(self.zero_task_state)
        accept_btn.clicked.connect(tip.close)

    def init_native_panel(self):
        self._dispose_views()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self.panel_ctrl.cleanup()

        self._entries.clear()

        self.expandBtn = self.gui.expandBtn
        self.clearBtn = self.gui.clearBtn
        self.expandBtn.clicked.connect(self.panel_ctrl.on_expand_clicked)
        self.clearBtn.clicked.connect(self._on_clear_btn_clicked)

        self._dl_status_badge = DlStatusBadge(parent=self.gui, target=self.expandBtn)
        self._dl_status_badge.hide()
        self.panel_ctrl.bind(self.expandBtn)

    def capture_native_snapshot(self) -> dict:
        return {"task_ids": list(self._entries.keys())}

    def rebind_native_panel(self, snapshot: dict = None):
        task_ids = snapshot.get("task_ids") if snapshot else None
        self._dispose_views(reset_view_ref=True)
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self.panel_ctrl.cleanup()

        self.expandBtn = self.gui.expandBtn
        self.clearBtn = self.gui.clearBtn
        self.expandBtn.clicked.connect(self.panel_ctrl.on_expand_clicked)
        self.clearBtn.clicked.connect(self._on_clear_btn_clicked)

        self._dl_status_badge = DlStatusBadge(parent=self.gui, target=self.expandBtn)
        self._dl_status_badge.hide()
        self.panel_ctrl.bind(self.expandBtn)

        for task_id in task_ids if task_ids is not None else list(self._entries.keys()):
            entry = self._entries.get(task_id)
            if entry is not None:
                entry.mount()
        self._set_entry_controls_visible(bool(self._entries))
        self.gui.scroll_area.setVisible(False)
        self.panel_ctrl.reset_content_height()
        self._refresh_dl_status_badge()

    def handle(self, task: t.Union[TasksObj, TaskObj]):
        if isinstance(task, TasksObj):
            entry = self._entries.get(task.taskid)
            if entry is None:
                entry = TaskProgressEntry(self, task)
                self._entries[task.taskid] = entry
                entry.mount()
                browser = getattr(self.gui, "BrowserWindow", None)
                if browser is not None and browser.isVisible():
                    browser.show_task_added_toast(task.display_title)
                if len(self._entries) == 1:
                    self._set_entry_controls_visible(True)
                self._refresh_dl_status_badge()
                self.panel_ctrl.request_scroll_sync()
                return
            entry.replace_tasks_obj(task)
            return

        if isinstance(task, TaskObj):
            entry = self._entries.get(task.taskid)
            if entry is None:
                print(f"{task.taskid}: {task.page}")
                return
            entry.apply_task(task)
            self._refresh_dl_status_badge()

            total_downloaded = sum(item.progress.downloaded for item in self._entries.values())
            total_tasks = sum(item.progress.tasks_count for item in self._entries.values())
            aggregate = int(total_downloaded * 100 / total_tasks) if total_tasks else 0
            self.gui.processbar_load(aggregate)

            completed = sum(1 for item in self._entries.values() if item.progress.completed)
            if completed == len(self._entries) and self._entries:
                self.gui.crawl_end(str(getattr(self.gui, "sv_path", "")))

    def _refresh_dl_status_badge(self):
        if self._dl_status_badge is None:
            return
        total = len(self._entries)
        if total == 0:
            self._dl_status_badge.hide()
            return
        completed = sum(1 for entry in self._entries.values() if entry.progress.completed)
        self._dl_status_badge.update_progress(completed, total)
        self._dl_status_badge.show()

    def zero_task_state(self):
        self._dispose_views()
        self._entries.clear()
        self._set_entry_controls_visible(False)
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
        self.panel_ctrl.stop_and_reset()
        self.panel_ctrl.reset_content_height()
        self.gui.scroll_area.setVisible(False)
        if self.expandBtn.expanded:
            self.expandBtn.expanded = False
            self.expandBtn._anim_ctrl.rotate_to(0.0)

    @property
    def unfinished_tasks(self):
        task_ids = list(self._entries.keys())
        downloaded_taskids = self.record_sql.batch_check_dupe(task_ids)
        un_taskids = set(task_ids) - set(downloaded_taskids)
        return [self._entries[taskid].tasks_obj for taskid in un_taskids]

    def close(self):
        self.cover_task_mgr.cleanup()
        self.panel_ctrl.cleanup()
        self._dispose_views(reset_view_ref=True)
        self._entries.clear()
        if self._dl_status_badge is not None:
            self._dl_status_badge.hide()
            self._dl_status_badge.badge.deleteLater()
            self._dl_status_badge = None
        self.record_sql.close()
