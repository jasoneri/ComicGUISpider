# -*- coding: utf-8 -*-
from pathlib import Path
from copy import deepcopy
from PyQt5.QtCore import Qt, pyqtSignal, QEvent
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QStackedWidget, QApplication
)
from qfluentwidgets import (
    SwitchButton, PushButton, PrimaryToolButton, TransparentToolButton,
    FluentIcon as FIF,
    SubtitleLabel, EditableComboBox, InfoBar, InfoBarPosition
)

from GUI.core.theme import theme_mgr, CustTheme
from GUI.manager.mid import WorkflowState
from utils.middleware import (
    WorkflowDefinition, MiddlewareDefinition,
    TimelineStage, LaneStage
)
from utils import conf
from utils.core import sanitize_filename
from utils.middleware.providers import PresetProvider
from utils.middleware.serialization import workflow_from_json
from .lane import NodeDisplayConfig, LaneConfig, LaneNode
from .panel import RulePanel, DetailPanel
from .rule import RuleToolButton


class WorkflowCanvas(QWidget):
    rule_clicked = pyqtSignal(object)
    lane_play_clicked = pyqtSignal(str)
    active_rule_changed = pyqtSignal(object)

    # Lane 配置列表
    LANE_CONFIGS = [
        LaneConfig(
            "SITE", "选择网站", TimelineStage.WAIT_SITE,
            NodeDisplayConfig.create_start("选择", "网站")
        ),
        LaneConfig(
            "SEARCH", "输入搜索", TimelineStage.WAIT_SEARCH,
            NodeDisplayConfig.create_mid("输入", "搜索")
        ),
        LaneConfig(
            "BOOK", "选择书本", TimelineStage.WAIT_BOOK_DECISION,
            NodeDisplayConfig.create_mid("选择", "书本")
        ),
        LaneConfig(
            "EP", "选择章节", TimelineStage.WAIT_EP_DECISION,
            NodeDisplayConfig.create_mid("选择", "章节")
        ),
        LaneConfig(
            "POSTPROCESSING", "完成", TimelineStage.POSTPROCESSING,
            NodeDisplayConfig.create_end("完成")
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lane_nodes: dict[str, LaneNode] = {}
        self._current_stage = None
        self._theme_sub = None
        self._active_rule: RuleToolButton | None = None

        self._init_ui()
        self._init_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        lanes_row = QHBoxLayout()
        lanes_row.setSpacing(0)
        lanes_row.setContentsMargins(0, 0, 0, 0)

        for config in self.LANE_CONFIGS:
            lane_node = LaneNode(config, self)
            lane_node.button_group.laneRunBtn.clicked.connect(
                lambda _, lid=config.lane_id: self.lane_play_clicked.emit(lid)
            )
            lane_node.button_group.rule_clicked.connect(self.rule_clicked.emit)
            lanes_row.addLayout(lane_node.layout)
            self.lane_nodes[config.lane_id] = lane_node

        layout.addLayout(lanes_row)

    def _init_theme(self):
        """初始化主题订阅 - WorkflowCanvas 是唯一订阅者"""
        self._theme_sub = self._on_theme_changed
        theme_mgr.subscribe(self._theme_sub)
        self.destroyed.connect(self._on_destroyed)
        self._apply_theme()

    def _on_destroyed(self):
        """对象销毁时清理主题订阅"""
        if self._theme_sub:
            theme_mgr.unsubscribe(self._theme_sub)
            self._theme_sub = None

    def _on_theme_changed(self, theme: CustTheme):
        """主题切换回调"""
        self._apply_theme()

    def _apply_theme(self):
        """应用主题颜色到所有 LaneNode"""
        mid_colors = theme_mgr.theme.mid_colors
        for lane_id, lane_node in self.lane_nodes.items():
            scheme = mid_colors.get_scheme(lane_id)
            lane_node.apply_theme(scheme)

    def set_state(self, state: WorkflowState, stage: TimelineStage = None):
        """设置工作流状态"""
        self._current_stage = stage
        current_lane = LaneStage.from_timeline_stage(stage) if stage else None

        for lane_id, lane_node in self.lane_nodes.items():
            if state == WorkflowState.IDLE:
                lane_node.set_state(disabled=False, is_current=False, play_enabled=False)
            elif state == WorkflowState.RUNNING:
                lane_node.set_state(disabled=True, is_current=False, play_enabled=False)
            elif state == WorkflowState.WAITING:
                is_current = current_lane and current_lane.value == lane_id
                lane_node.set_state(
                    disabled=not is_current,
                    is_current=is_current,
                    play_enabled=is_current
                )

        self._highlight_stage(stage)

    def _highlight_stage(self, stage: TimelineStage):
        """高亮当前阶段的节点"""
        for lane_node in self.lane_nodes.values():
            lane_node.set_highlight(lane_node.config.stage == stage)

    def update_workflow(self, workflow: WorkflowDefinition):
        """更新工作流规则"""
        self.clear_active_rule()
        for lane_node in self.lane_nodes.values():
            lane_node.button_group.clear()

        for mw in sorted(workflow.middlewares, key=lambda m: m.priority):
            if not mw.allowed_lanes:
                continue
            primary_lane = mw.allowed_lanes[0]
            if primary_lane in self.lane_nodes:
                self.lane_nodes[primary_lane].button_group.add_rule(mw)

    def get_lane_rules(self, lane_id: str) -> list[MiddlewareDefinition]:
        """获取指定 Lane 的规则列表"""
        if lane_id not in self.lane_nodes:
            return []
        return [btn.definition for btn in self.lane_nodes[lane_id].button_group.rules]

    def set_active_rule(self, rule: RuleToolButton):
        """设置当前激活的规则，关闭前一个规则的 badges"""
        if self._active_rule is rule:
            if not rule._badges_visible:
                rule.show_badges()
            return
        if self._active_rule:
            self._active_rule.hide_badges()
        self._active_rule = rule
        rule.show_badges()
        self.active_rule_changed.emit(rule)

    def clear_active_rule(self):
        """关闭当前激活规则的 badges"""
        if not self._active_rule:
            return
        self._active_rule.hide_badges()
        self._active_rule = None
        self.active_rule_changed.emit(None)

    def find_rule_button(self, definition: MiddlewareDefinition) -> RuleToolButton | None:
        """根据 definition 查找对应的 RuleToolButton"""
        for lane_node in self.lane_nodes.values():
            for btn in lane_node.button_group.rules:
                if btn.definition.id == definition.id:
                    return btn
        return None



class MidToolInterface(QWidget):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.workflow = WorkflowDefinition(workflow_name="Untitled")

        self._init_ui()
        self._populate_rule_panel()
        self._try_load_active_workflow()
        self._update_workflow_dropdown()
        self._connect_manager()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.title_label = SubtitleLabel("CGSMid")

        self.workflow_combo = EditableComboBox()
        self.workflow_combo.setMaximumWidth(200)
        self.workflow_combo.setPlaceholderText("输入名称")
        self.workflow_combo.currentIndexChanged.connect(self._on_workflow_index_changed)

        self.enable_switch = SwitchButton()
        self.enable_switch.setText("自动化")
        self.enable_switch.checkedChanged.connect(self._on_enable_changed)

        self.delete_btn = TransparentToolButton(FIF.DELETE, self)
        self.delete_btn.clicked.connect(self._on_delete_workflow)

        self.save_btn = PrimaryToolButton(FIF.SAVE, self)
        self.save_btn.clicked.connect(self._on_save)

        header.addWidget(self.title_label)
        header.addWidget(self.enable_switch)
        header.addStretch()
        header.addWidget(self.workflow_combo)
        header.addWidget(self.delete_btn)
        header.addWidget(self.save_btn)
        layout.addLayout(header)

        content = QHBoxLayout()

        self.canvas = WorkflowCanvas(self)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.canvas.rule_clicked.connect(self._on_rule_clicked)
        self.canvas.lane_play_clicked.connect(self._on_lane_play)
        for lane_node in self.canvas.lane_nodes.values():
            lane_node.button_group.rule_removed.connect(self._on_rule_removed)
            lane_node.button_group.rule_moved.connect(self._on_rule_moved)
            lane_node.button_group.badge_toggle_requested.connect(self._on_badge_toggle)
        self.canvas.installEventFilter(self)

        self._panel_stack = QStackedWidget(self)
        self._panel_stack.setMaximumWidth(300)
        
        self.rule_panel = RulePanel(self)
        self.rule_panel.rule_selected.connect(self._on_rule_selected)
        self._panel_stack.addWidget(self.rule_panel)

        self.detail_panel = DetailPanel(self)
        self.detail_panel.back_requested.connect(self._show_rule_panel)
        self._panel_stack.addWidget(self.detail_panel)

        content.addWidget(self.canvas)
        content.addStretch()
        content.addWidget(self._panel_stack)
        layout.addLayout(content)

    def _populate_rule_panel(self):
        """填充规则库面板（不影响画布）"""
        provider = PresetProvider()
        available = provider.list_available()
        self.rule_panel.populate(available)

    def _try_load_active_workflow(self):
        """尝试加载上次激活的工作流，失败时保持空白"""
        if conf.active_workflow:
            self._load_workflow(conf.active_workflow)

    def _connect_manager(self):
        mgr = getattr(self.gui, "mid_mgr", None)
        if mgr:
            mgr.state_changed.connect(self._on_state_changed)
            mgr.lane_visibility_changed.connect(self._on_lane_visibility_changed)
            self.canvas.set_state(mgr.workflow_state, mgr._workflow_session.current_stage)

    def _on_state_changed(self, state: WorkflowState, stage):
        self.canvas.set_state(state, stage)

    def _on_lane_visibility_changed(self, lane_id: str, hidden: bool):
        if lane_id in self.canvas.lane_nodes:
            self.canvas.lane_nodes[lane_id].set_hidden(hidden)

    def _on_enable_changed(self, checked: bool):
        if mgr:= getattr(self.gui, "mid_mgr", None):
            mgr.set_enabled(checked)

    def on_flow_changed(self, index: int):
        flow_types = ["auto", "ep", "book"]
        self.workflow.flow_type = flow_types[index]

    def _on_rule_selected(self, definition: MiddlewareDefinition, lane_id: str):
        if definition.id in [m.id for m in self.workflow.middlewares]:
            return
        new_def = deepcopy(definition)
        self.workflow.middlewares.append(new_def)
        self.canvas.lane_nodes[lane_id].button_group.add_rule(new_def)
        self.rule_panel.hide_rule(definition.id)

    def _on_rule_removed(self, rule_id: str):
        self.workflow.middlewares = [m for m in self.workflow.middlewares if m.id != rule_id]
        self.rule_panel.show_rule(rule_id)

    def _on_rule_moved(self, rule_id: str, from_idx: int, to_idx: int):
        for lane_node in self.canvas.lane_nodes.values():
            if not lane_node.button_group.rules:
                continue
            priorities = [btn.definition.priority for btn in lane_node.button_group.rules]
            base = min(priorities)
            for i, btn in enumerate(lane_node.button_group.rules):
                btn.definition.priority = base + i

    def _on_rule_clicked(self, definition: MiddlewareDefinition):
        rule_btn = self.canvas.find_rule_button(definition)
        if rule_btn:
            self.canvas.set_active_rule(rule_btn)
        self.detail_panel.show_definition(definition)
        self._panel_stack.setCurrentWidget(self.detail_panel)

    def _show_rule_panel(self):
        self.canvas.clear_active_rule()
        self._panel_stack.setCurrentWidget(self.rule_panel)

    def _on_badge_toggle(self, rule_btn: RuleToolButton, show: bool):
        if show:
            self.canvas.set_active_rule(rule_btn)
        else:
            self.canvas.clear_active_rule()

    def eventFilter(self, obj, event):
        if obj is self.canvas and event.type() == QEvent.MouseButtonPress:
            widget_at = QApplication.widgetAt(event.globalPos())
            if widget_at is self.canvas or (widget_at and widget_at.parent() is self.canvas):
                self.canvas.clear_active_rule()
        return super().eventFilter(obj, event)

    def _on_lane_play(self, lane_id: str):
        mgr = getattr(self.gui, "mid_mgr", None)
        if mgr:
            rules = self.canvas.get_lane_rules(lane_id)
            if not rules:
                return
            lane_stage = LaneStage(lane_id)
            mgr.notify_lane_completed(lane_stage)

    @property
    def _workflows_dir(self) -> Path:
        path = conf.file.parent / "workflows"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _list_saved_workflows(self) -> list[str]:
        return sorted(f.stem for f in self._workflows_dir.glob("*.json"))

    def _save_workflow(self):
        name = sanitize_filename(self.workflow.workflow_name)
        filepath = self._workflows_dir / f"{name}.json"
        filepath.write_text(self.workflow.to_json(), encoding="utf-8")
        conf.update(active_workflow=name)

    def _load_workflow(self, name: str):
        """从 JSON 文件加载工作流"""
        safe_name = sanitize_filename(name)
        filepath = self._workflows_dir / f"{safe_name}.json"
        
        if not filepath.resolve().is_relative_to(self._workflows_dir.resolve()):
            return
        if not filepath.exists():
            return
        content = filepath.read_text(encoding="utf-8")
        self.workflow = workflow_from_json(content)
        self.canvas.update_workflow(self.workflow)
        self._sync_rule_panel()

    def _sync_rule_panel(self):
        """同步 rule_panel 的显示/隐藏状态"""
        active_ids = {m.id for m in self.workflow.middlewares}
        for rule_id in self.rule_panel.rule_rows:
            if rule_id in active_ids:
                self.rule_panel.hide_rule(rule_id)
            else:
                self.rule_panel.show_rule(rule_id)

    def _update_workflow_dropdown(self):
        saved = self._list_saved_workflows()
        self.workflow_combo.blockSignals(True)
        self.workflow_combo.clear()
        self.workflow_combo.addItems(saved)

        current = sanitize_filename(self.workflow.workflow_name)
        if current in saved:
            self.workflow_combo.setCurrentText(current)
        else:
            self.workflow_combo.setItemText(0, self.workflow.workflow_name)

        self.workflow_combo.blockSignals(False)

    def _on_workflow_index_changed(self, index: int):
        if index < 0:
            return
        name = self.workflow_combo.itemText(index)
        if name and name != sanitize_filename(self.workflow.workflow_name):
            self._load_workflow(name)
            conf.update(active_workflow=sanitize_filename(name))

    def _on_delete_workflow(self):
        index = self.workflow_combo.currentIndex()
        if index < 0:
            return
        name = self.workflow_combo.itemText(index)
        if not name:
            return
        key = sanitize_filename(name)
        filepath = self._workflows_dir / f"{key}.json"
        if not filepath.exists():
            return

        filepath.unlink(missing_ok=True)
        if saved:= self._list_saved_workflows():
            self._load_workflow(saved[0])
            conf.update(active_workflow=sanitize_filename(saved[0]))
        else:
            self.workflow = WorkflowDefinition(workflow_name="Untitled")
            self.canvas.update_workflow(self.workflow)
            self._sync_rule_panel()
            conf.update(active_workflow="")

        self._update_workflow_dropdown()

    def _on_save(self):
        name = self.workflow_combo.currentText().strip() or "Untitled"
        self.workflow.workflow_name = name
        self._save_workflow()
        self._update_workflow_dropdown()
        InfoBar.success(
            "保存成功", f"工作流已保存: {self.workflow.workflow_name}",
            parent=self, position=InfoBarPosition.TOP, duration=3000
        )
