import sqlite3
from enum import StrEnum

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QTreeWidgetItem, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (
    CaptionLabel, FluentIcon as FIF, FlyoutViewBase, InfoBadge, InfoBar, InfoLevel, InfoBarPosition,
    PrimaryPushButton, ProgressBar, PushButton, SegmentedWidget, StrongBodyLabel, ToolButton, TreeWidget
)
from GUI.manager.async_task import AsyncTaskManager, TaskConfig
from GUI.uic.qfluent.components.flyout_kit import CustomFlyout
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.webdav import ProbeStage, WebdavHistoryStore, build_upload_rows, probe_webdav
from .entries import MODE_DOUJIN, MODE_MANGA, MODE_OF_SCAN, STATUS_TEXT, UploadState, UploadStatus
from .push_worker import WebdavPushThread
from .selection import WebdavLibraryTree
from .settings import WebdavSettings


class PushState(StrEnum):
    PUSHING = "pushing"
    PROBING = "probing"
    SETTINGS_DIRTY = "settings_dirty"
    NO_ENDPOINT = "no_endpoint"
    SCANNING = "scanning"
    NO_SNAPSHOT = "no_snapshot"
    READY = "ready"


PUSH_STATE_TIP = {
    PushState.PUSHING: "上传进行中",
    PushState.PROBING: "读写测试进行中",
    PushState.SETTINGS_DIRTY: "先保存当前设置",
    PushState.NO_ENDPOINT: "填写并保存 WebDAV 地址",
    PushState.SCANNING: "扫描中，暂不可上传",
    PushState.NO_SNAPSHOT: "需要有效的扫描结果",
    PushState.READY: "勾选需要上传的漫画或章节",
}

# 探测失败按阶段告知，不解析异常文案。
PROBE_STAGE_NOTICE = {
    ProbeStage.ROOT: "读取目录失败",
    ProbeStage.WRITE: "写入失败",
    ProbeStage.READ: "回读失败",
    ProbeStage.CLEANUP: "清理失败",
    ProbeStage.DONE: "读写测试未完成",
}


def _reason_line(text: str) -> str:
    """异常摘要（traceback 末行），只进 tooltip；状态列本身只显示状态文本。"""
    lines = [line for line in str(text).splitlines() if line.strip()]
    return lines[-1] if lines else ""


class WebdavHistoryFlyout(FlyoutViewBase):
    """上传历史快照 flyout：批次倒序，**最近一批常驻展开**、其余常驻折叠（点击 / 键盘展开）。"""

    MAX_BATCHES = 50
    # 单批条目行的**视图**上限：读取侧一次聚合取回，超限只少建行并明示总数（非读取侧限长）。
    MAX_ITEMS = 200

    def __init__(self, batches, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        if not batches:
            layout.addWidget(CaptionLabel("暂无上传记录", self))
            return
        self.tree = TreeWidget(self)
        self.tree.setHeaderLabels(["内容", "格式", "结果"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setUniformRowHeights(True)
        self.tree.setMaximumHeight(360)
        # 批次行文本较长（时间戳 + 三计数 + mode），给足最小宽度避免省略号吃掉计数。
        self.tree.setMinimumWidth(860)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        # 末列不跟随拉伸（qfluentwidgets 树默认拉伸末列），剩余宽度全部留给批次行文本。
        self.tree.header().setStretchLastSection(False)
        self._pending: dict[int, object] = {}
        with QSignalBlocker(self.tree):
            self.tree.setUpdatesEnabled(False)
            for index, batch in enumerate(batches):
                header = batch.header
                row = QTreeWidgetItem([
                    f"「batch.{header.id}」 {header.started_at} · 上传 {header.pushed} · "
                    f"跳过 {header.skipped} · 失败 {header.failed} · {header.mode}"])
                row.setFlags(Qt.ItemFlag.ItemIsEnabled)
                row.setData(0, Qt.ItemDataRole.UserRole, header.id)
                # 无条目无失败的批次（如中止批）不给展开箭头，避免点了什么都不出现。
                row.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                                            if batch.items or header.failed
                                            else QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
                self.tree.addTopLevelItem(row)
                self._pending[header.id] = batch
                if index == 0:
                    self._materialize(row)   # 最近一批常驻展开：打开即可见条目行
                    row.setExpanded(True)
            self.tree.setUpdatesEnabled(True)
        layout.addWidget(self.tree)
        # 其余批次常驻折叠：条目行在该批被展开时才实例化（懒建），展开回调内零 IO。
        self.tree.itemExpanded.connect(self._materialize)

    def _materialize(self, row):
        batch = self._pending.pop(row.data(0, Qt.ItemDataRole.UserRole), None)
        if batch is None:
            return
        with QSignalBlocker(self.tree):
            for record in batch.items[:self.MAX_ITEMS]:
                item = QTreeWidgetItem([
                    f"{record.book} · {record.ep}" if record.ep else record.book,
                    "CBZ" if record.kind == "cbz" else "目录",
                    STATUS_TEXT[UploadStatus.PUSHED] if record.result == "pushed" else STATUS_TEXT[UploadStatus.SKIPPED],
                ])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(0, record.relative_path)
                row.addChild(item)
            if len(batch.items) > self.MAX_ITEMS:
                row.addChild(self._note(f"共 {len(batch.items)} 项，仅显示前 {self.MAX_ITEMS}"))
            if batch.header.failed:
                row.addChild(self._note(f"失败 {batch.header.failed} 项 · 明细见日志"))

    @staticmethod
    def _note(text: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        return item


class WebdavInterface(QWidget):
    def __init__(self, gui, parent=None):
        super().__init__(parent)
        self.gui = gui
        self._thread = None
        self._snapshot = None
        self._mode = MODE_MANGA
        self._push_batch = []
        self._failed = []
        self._batch_config = {}
        self._batch_context = None
        self._batch_id = None
        self._batch_mode = None
        self._history_notified = False
        self._probe_busy = False
        self._pending_notified = False
        self._probe_config = {}
        self.probe_tasks = AsyncTaskManager(gui, self)
        # 上传历史（rV.db 两表）随界面构造打开：幂等 DDL + sweep；读写在批次开始/结束两个时点。
        self.history = WebdavHistoryStore()
        self.settings = WebdavSettings(self)
        self.library = WebdavLibraryTree(self, self.history)
        self.library.history_failed.connect(self._on_history_failed)
        self.root_label = CaptionLabel(self)
        # 状态机切换 UI：仅未选站点（context.mode=None）时可见；已选站点时模式钉死，UI 隐藏不占位。
        self.mode_widget = SegmentedWidget(self)
        self.mode_widget.setAccessibleName("上传分类")
        # 焦点落在分段项本身（容器 NoFocus），Tab 链直接连到这两项。
        self._mode_items = [
            self.mode_widget.addItem(MODE_MANGA, "漫画", onClick=lambda: self._on_mode_changed(MODE_MANGA)),
            self.mode_widget.addItem(MODE_DOUJIN, "本子", onClick=lambda: self._on_mode_changed(MODE_DOUJIN)),
        ]
        self.mode_widget.hide()
        # 计数一律用 pill 徽标：总条目常驻，勾选数 0 时隐藏（徽标宽度由 adjustSize 自适应，不手写尺寸）。
        self.total_badge = InfoBadge.info("—", self)
        self.total_badge.setAccessibleName("本地书库条目总数")
        self.selection_badge = InfoBadge.attension("", self)
        self.selection_badge.setAccessibleName("已勾选数量")
        self.selection_badge.hide()
        self.refresh_btn = ToolButton(FIF.SYNC, self)
        self.refresh_btn.setToolTip("重新扫描本地书库")
        self.refresh_btn.setAccessibleName("刷新扫描")
        self.push_btn = PrimaryPushButton(CgsIcon.UPLOAD, "上传选中", self)
        self.retry_btn = PushButton(CgsIcon.MAIN_REPAIR, "重推失败项", self)
        self.history_btn = ToolButton(FIF.HISTORY, self)
        self.history_btn.setAccessibleName("上传历史")
        self.entry_progress = ProgressBar(self)
        self.progress_row = QWidget(self)
        self._build_ui()
        self.progress_row.hide()
        self._set_tab_order()
        self.settings.changed.connect(self._update_actions)
        self.settings.test_btn.clicked.connect(self._test_connection)
        self.library.selection_changed.connect(self._update_actions)
        self.refresh_btn.clicked.connect(self._refresh)
        self.push_btn.clicked.connect(self._start_push)
        self.retry_btn.clicked.connect(self._retry_failed)
        self.history_btn.clicked.connect(self._show_history_flyout)
        manager = self.gui.rv_mgr
        manager.context_changed.connect(self._context_changed)
        manager.snapshot_changed.connect(self._snapshot_changed)
        manager.busy_changed.connect(self._scan_state_changed)
        manager.scan_failed.connect(self._scan_failed)
        self._snapshot_changed(manager.snapshot)
        self._scan_state_changed()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # 2) 连接卡：一次性配置，紧凑收纳在主工作区之上。
        conn_card = QFrame(self)
        conn_card.setObjectName("WebdavCard")
        conn_layout = QVBoxLayout(conn_card)
        conn_layout.setContentsMargins(14, 10, 14, 10)
        conn_layout.setSpacing(6)
        conn_layout.addWidget(StrongBodyLabel("连接配置", conn_card))
        conn_layout.addWidget(self.settings)
        root.addWidget(conn_card)

        # 3) 书库卡：主工作区，占据全部剩余空间。
        library_card = QFrame(self)
        library_card.setObjectName("WebdavCard")
        library_layout = QVBoxLayout(library_card)
        library_layout.setContentsMargins(14, 10, 14, 10)
        library_layout.setSpacing(6)
        head_row = QHBoxLayout()
        head_row.setSpacing(8)
        head_row.addWidget(StrongBodyLabel("本地书库", library_card))
        head_row.addWidget(self.total_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        head_row.addWidget(self.selection_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        head_row.addStretch(1)
        # 扫描范围靠右，与刷新按钮成组；计数留在左侧紧跟标题。
        head_row.addWidget(self.mode_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        head_row.addWidget(self.refresh_btn)
        library_layout.addLayout(head_row)
        library_layout.addWidget(self.library, 1)
        # 身份行：只报本地根（计数已进徽标，不再重复）。
        library_layout.addWidget(self.root_label)
        root.addWidget(library_card, 1)

        # 4) 动作栏：主行动 + 次行动 + 反馈区（进度空闲时收起）。
        self.action_bar = QFrame(self)
        self.action_bar.setObjectName("WebdavActionBar")
        action_layout = QVBoxLayout(self.action_bar)
        action_layout.setContentsMargins(14, 8, 14, 8)
        action_layout.setSpacing(6)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        # 主按钮吃满动作栏；retry_btn 隐藏时主按钮全宽。不可补尾部 addStretch，否则宽度被抢一半。
        buttons.addWidget(self.push_btn, 1)
        buttons.addWidget(self.retry_btn)
        buttons.addWidget(self.history_btn)
        action_layout.addLayout(buttons)
        progress_layout = QHBoxLayout(self.progress_row)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(10)
        # 进度只由控件表达：整批进度条 + 书库树状态列（每项），批次结果走 InfoBar。
        progress_layout.addWidget(self.entry_progress, 1)
        action_layout.addWidget(self.progress_row)
        root.addWidget(self.action_bar)
        self.entry_progress.setRange(0, 100)
        self.entry_progress.setValue(0)

    def _set_tab_order(self):
        settings, library = self.settings, self.library
        widgets = (
            settings.endpoint_edit, settings.useVpnBtn, settings.test_btn, settings.svBtn,
            settings.user_edit, settings.password_edit, settings.password_edit.viewButton,
            *self._mode_items, self.refresh_btn, library.show_uploaded_btn, library.filter_edit,
            library.select_btn, library.clear_btn, library.tree,
            self.push_btn, self.retry_btn, self.history_btn,
        )
        for previous, following in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(previous, following)

    def showEvent(self, event):
        super().showEvent(event)
        self.gui.rv_mgr.sync_context()
        self._scan_state_changed()

    def _refresh(self):
        self.gui.rv_mgr.start_scan(show_progress=False)

    def pinned(self) -> bool:
        """已选站点时模式是既成事实，状态机被钉死，切换 UI 不出现。"""
        context = self.gui.rv_mgr.context
        return context is not None and context.mode in MODE_OF_SCAN

    def resolved_mode(self) -> str:
        context = self.gui.rv_mgr.context
        if context is not None and context.mode in MODE_OF_SCAN:
            return MODE_OF_SCAN[context.mode]
        return self._mode

    def _sync_mode_ui(self):
        if self.pinned():
            self.mode_widget.hide()
            return
        self.mode_widget.show()
        self.mode_widget.setCurrentItem(self._mode)

    def _apply_mode(self):
        """只重投影缓存的扫描结果：不调用 start_scan / sync_context，不起线程。"""
        self.library.set_snapshot(self._snapshot, self.resolved_mode())

    def _on_mode_changed(self, mode: str):
        if self.pinned() or mode == self._mode:
            return
        self._mode = mode
        self._scan_state_changed()

    def _context_changed(self, _context):
        self._snapshot = None
        # 库根/模式变化 ⇒ 历史库跟随 Conf.sv_path 迁移：先释放旧库句柄，下次投影按新根重开。
        self.history.close()
        self.library.set_snapshot(None, self.resolved_mode())
        self._failed = []
        InfoBar.warning(title='', content="扫描范围已改变，旧选择已清空", position=InfoBarPosition.TOP,
                        duration=4000, parent=self.window())
        self._update_actions()

    def _snapshot_changed(self, snapshot):
        self._snapshot = snapshot
        self._scan_state_changed()

    def _scan_state_changed(self, *_args):
        manager = self.gui.rv_mgr
        self._sync_mode_ui()
        self._apply_mode()
        ready = manager.snapshot is not None
        root = str(manager.snapshot.root) if ready else ""
        self.total_badge.setText(f"{len(self.library.entries)} 项" if ready else "—")
        self.total_badge.adjustSize()
        self.root_label.setText(f"{root or '—'}")
        self.root_label.setToolTip(root)
        self.refresh_btn.setEnabled(not manager.busy)
        self.refresh_btn.setToolTip("扫描中" if manager.busy else "重新扫描本地书库")
        # 启动反馈（R-H8）：本会话首次投影（快照到达）时触发一次；切 tab / 切模式 / 重扫不重发。
        if ready and not self._history_notified:
            self._history_notified = True
            self._notify_last_batch()
        self._update_actions()

    def _notify_last_batch(self):
        """最新 done 批次有失败 ⇒ 恰好一条 warning InfoBar（带批次号/失败数，指向 flyout）。"""
        try:
            batch = self.history.latest_done_batch()
        except (sqlite3.Error, OSError) as exc:
            self.gui.log.error(f"上传历史读取失败: {exc}")
            InfoBar.error(title='', content="上传历史读取失败，请查看日志", position=InfoBarPosition.TOP,
                          duration=8000, parent=self.window())
            return
        if batch is not None and batch.failed:
            InfoBar.warning(title='',
                            content=f"上次上传 batch.{batch.id} · 失败 {batch.failed} 项 · 详情见上传历史",
                            position=InfoBarPosition.TOP, duration=8000, parent=self.window())

    def _show_history_flyout(self):
        try:
            batches = self.history.batches_with_items(WebdavHistoryFlyout.MAX_BATCHES)
        except (sqlite3.Error, OSError) as exc:
            self.gui.log.error(f"上传历史读取失败: {exc}")
            InfoBar.error(title='', content="上传历史读取失败，请查看日志", position=InfoBarPosition.TOP,
                          duration=5000, parent=self.window())
            return
        CustomFlyout.make(WebdavHistoryFlyout(batches), target=self.history_btn, parent=self.window())

    def _on_history_failed(self, message):
        """树投影读库失败：日志可见（InfoBar.error 由树当场给出），不静默降级。"""
        self.gui.log.error(f"上传历史读取失败: {message}")

    def _scan_failed(self, message):
        InfoBar.error(title='', content="扫描失败，请查看日志", position=InfoBarPosition.TOP,
                      duration=8000, parent=self.window())
        self.gui.log.error(message)
        self._scan_state_changed()

    def _update_actions(self):
        state = self._push_state()
        manager = self.gui.rv_mgr
        self._update_selection_badge()
        can_push = state == PushState.READY and bool(self.library.selected_entries())
        self.push_btn.setEnabled(can_push)
        self.push_btn.setToolTip("" if can_push else PUSH_STATE_TIP[state])
        same_batch = self.settings.saved_config == self._batch_config and manager.context == self._batch_context
        self.retry_btn.setVisible(bool(self._failed))
        self.retry_btn.setEnabled(state == PushState.READY and same_batch)
        self.retry_btn.setToolTip("" if state == PushState.READY else PUSH_STATE_TIP[state])
        self.settings.test_btn.setEnabled(not self.has_active_work())
        self.settings.set_probing(self._probe_busy)
        # 批次进行中改配置：一次性告知「下一批生效」；开关 tooltip 常驻同一信息供回看。
        pending = self._thread is not None and self.settings.is_dirty()
        self.settings.set_pending(pending)
        if self._thread is None:
            self._pending_notified = False
        elif pending and not self._pending_notified:
            self._pending_notified = True
            InfoBar.warning(title='', content="上传进行中，本批仍用原配置；改动将在下一批生效",
                            position=InfoBarPosition.TOP, duration=5000, parent=self.window())

    def _push_state(self) -> PushState:
        if self._thread is not None:
            return PushState.PUSHING
        if self._probe_busy:
            return PushState.PROBING
        if self.settings.is_dirty():
            return PushState.SETTINGS_DIRTY
        if not self.settings.saved_config["endpoint"]:
            return PushState.NO_ENDPOINT
        manager = self.gui.rv_mgr
        if manager.busy:
            return PushState.SCANNING
        if manager.error or manager.snapshot is None:
            return PushState.NO_SNAPSHOT
        return PushState.READY

    def _update_selection_badge(self):
        """勾选数徽标：0 隐藏；「筛选外已勾选」/「本地缺失」升 WARNING 并补文案。"""
        checked, hidden, missing = self.library.selection_summary()
        if not checked:
            self.selection_badge.hide()
            return
        parts = [f"已选 {checked}"]
        if hidden:
            parts.append(f"含筛选外 {hidden}")
        if missing:
            parts.append(f"含失效 {missing}")
        self.selection_badge.setText(" · ".join(parts))
        self.selection_badge.setLevel(InfoLevel.WARNING if hidden or missing else InfoLevel.ATTENTION)
        tips = []
        if hidden:
            tips.append("整书勾选包含被筛选隐藏的章节")
        if missing:
            tips.append("已勾选项含本地缺失（外部删除/改动），推送时将失败")
        self.selection_badge.setToolTip("；".join(tips) or f"已勾选 {checked} 项")
        self.selection_badge.adjustSize()
        self.selection_badge.show()

    def _test_connection(self):
        try:
            config = self.settings.validated_draft()
        except ValueError as exc:
            InfoBar.error(title='', content=str(exc), position=InfoBarPosition.TOP, duration=5000, parent=self.window())
            return
        self._probe_config = dict(config)
        self._probe_busy = True
        self._update_actions()
        started = self.probe_tasks.execute_task("webdav-probe", TaskConfig(
            task_func=probe_webdav, args=(config,), success_callback=self._probe_finished, error_callback=self._probe_errored,
            show_tooltip=False, show_success_info=False, show_error_info=False,
        ))
        if not started:
            self._probe_busy = False
            InfoBar.error(title='', content="读写测试未启动，请查看日志", position=InfoBarPosition.TOP,
                          duration=5000, parent=self.window())
            self._update_actions()

    def _probe_finished(self, result):
        self._probe_busy = False
        if self.settings.draft() != self._probe_config:
            InfoBar.success(title='', content="结果来自旧配置，当前配置未测试", position=InfoBarPosition.TOP,
                            duration=3000, parent=self.window())
            self._update_actions()
            return
        if result.ok:
            # 测试通过即自动保存：复用 svBtn 的保存流程与其"配置已保存"InfoBar
            self.settings.svBtn.click()
            InfoBar.success(title='', content="读写可用 · 测试文件已清理", position=InfoBarPosition.TOP,
                            duration=3000, parent=self.window())
            self._update_actions()
            return
        notice = PROBE_STAGE_NOTICE[result.stage]
        if result.residual_path:
            notice += f"；测试文件保留在 {result.residual_path}"
        notice += "，请查看日志"
        self.gui.log.error(str(result.error))
        InfoBar.error(title='', content=notice, position=InfoBarPosition.TOP, duration=5000, parent=self.window())
        self._update_actions()

    def _probe_errored(self, message):
        """任务层异常（探测自身没跑起来），不是探测结果。"""
        self._probe_busy = False
        self.gui.log.error(message)
        InfoBar.error(title='', content="读写测试异常终止，请查看日志", position=InfoBarPosition.TOP,
                      duration=5000, parent=self.window())
        self._update_actions()

    def _start_push(self):
        self._run_push(self.library.selected_entries(), self.settings.saved_config)

    def _retry_failed(self):
        self._run_push(self._failed, self._batch_config)

    def _run_push(self, entries, config):
        self._push_batch = [dict(entry) for entry in entries]
        self._batch_config = dict(config)
        self._batch_context = self.gui.rv_mgr.context
        self._failed = []
        # 批次开始：头表插 running 行立刻拿号；失败只丢历史，不阻断上传。
        try:
            self._batch_id = self.history.begin_batch(self.resolved_mode())
            self._batch_mode = self.resolved_mode()
        except (sqlite3.Error, OSError) as exc:
            self._batch_id, self._batch_mode = None, None
            self.gui.log.error(f"上传历史批次开启失败: {exc}")
            InfoBar.error(title='', content="上传历史记录失败，请查看日志", position=InfoBarPosition.TOP,
                          duration=5000, parent=self.window())
        self._thread = WebdavPushThread(self.gui, self._push_batch, config=self._batch_config)
        self._thread.progress.connect(self._on_progress)
        self._thread.succeeded.connect(self._on_succeeded)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._on_thread_finished)
        self.progress_row.show()
        self.entry_progress.setValue(0)
        self._update_actions()
        self._thread.start()

    def _on_progress(self, info):
        # 进度条按文件数推进；状态列只在条目开始时置「上传中」，终态由 _on_succeeded 写入。
        if info.get("event") == "plan":
            self.entry_progress.setRange(0, max(1, info["files"]))
            self.entry_progress.setValue(0)
            return
        progress = info.get("progress")
        if progress is not None:
            self.entry_progress.setValue(progress)
        if info.get("event") == "entry":
            local_path = info.get("local_path", "")
            if local_path:
                self.library.set_statuses({local_path: UploadState(UploadStatus.UPLOADING, batch=self._batch_id or 0)})

    def _settle_batch(self, result=None, *, failed_all: int = 0):
        """批次结束：单事务写落地行 + 头表终态（failed 只进计数；失败零条目行）。"""
        batch_id, mode = self._batch_id, self._batch_mode
        self._batch_id, self._batch_mode = None, None
        if batch_id is None:
            return
        pushed = len(result["pushed"]) if result else 0
        skipped = len(result["skipped"]) if result else 0
        failed = len(result["failed"]) if result else failed_all
        landed = build_upload_rows(result, mode) if result else []
        try:
            self.history.finish_batch(batch_id, pushed=pushed, skipped=skipped, failed=failed, landed=landed)
        except (sqlite3.Error, OSError) as exc:
            self.gui.log.error(f"上传历史批次落库失败: {exc}")
            InfoBar.error(title='', content="上传历史记录失败，请查看日志", position=InfoBarPosition.TOP,
                          duration=5000, parent=self.window())

    def _on_succeeded(self, result):
        failed_paths = {item["local_path"] for item in result["failed"]}
        self._failed = [entry for entry in self._push_batch if entry["local_path"] in failed_paths]
        batch = self._batch_id or 0
        statuses = {item["local_path"]: UploadState(UploadStatus.PUSHED, batch=batch) for item in result["pushed"]}
        statuses.update({item["local_path"]: UploadState(UploadStatus.SKIPPED, batch=batch) for item in result["skipped"]})
        statuses.update({item["local_path"]: UploadState(UploadStatus.FAILED, _reason_line(item["reason"]), batch=batch)
                         for item in result["failed"]})
        self.library.set_statuses(statuses)
        self._settle_batch(result)
        self.entry_progress.setValue(self.entry_progress.maximum())
        pushed, skipped, failed = len(result["pushed"]), len(result["skipped"]), len(result["failed"])
        summary = f"上传 {pushed} · 同大小跳过 {skipped} · 失败 {failed}"
        if failed:
            InfoBar.error(title='', content=summary, position=InfoBarPosition.TOP, duration=8000, parent=self.window())
            self.gui.log.error("\n\n".join(item["reason"] for item in result["failed"]))
        else:
            InfoBar.success(title='', content=summary, position=InfoBarPosition.TOP, duration=3000, parent=self.window())

    def _on_failed(self, exc):
        self._failed = list(self._push_batch)
        batch = self._batch_id or 0
        self.library.set_statuses({entry["local_path"]: UploadState(UploadStatus.FAILED, type(exc).__name__, batch=batch)
                                   for entry in self._push_batch})
        self._settle_batch(None, failed_all=len(self._push_batch))
        InfoBar.error(title='', content=f"批次中止 · {type(exc).__name__} · 待重推 {len(self._failed)} 项",
                      position=InfoBarPosition.TOP, duration=8000, parent=self.window())

    def _on_thread_finished(self):
        self._thread.deleteLater()
        self._thread = None
        self._update_actions()

    def has_active_work(self) -> bool:
        return self._thread is not None or self._probe_busy

    def server_mode_switch_blockers(self) -> list[str]:
        blockers = ["WebDAV 上传进行中"] if self._thread is not None else []
        return blockers + (["WebDAV 读写测试进行中"] if self._probe_busy else [])

    def shutdown(self) -> None:
        # 宿主关闭只隐藏单例；RV 订阅随 QObject 销毁自动释放，不能在隐藏时断开。
        self.history.close()
