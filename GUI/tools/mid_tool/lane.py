# -*- coding: utf-8 -*-
from dataclasses import dataclass
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame, QSizePolicy
)
from qfluentwidgets import (
    TransparentToolButton, FluentIcon as FIF, VBoxLayout
)
from GUI.core.theme.mid import LaneColorScheme
from utils.middleware import MiddlewareDefinition, TimelineStage
from .svg import SvgWidget, NodeType
from .rule import RuleToolButton


@dataclass
class NodeDisplayConfig:
    """节点显示配置"""
    node_type: NodeType
    labels: tuple[str, ...]

    @classmethod
    def create_start(cls, *labels) -> 'NodeDisplayConfig':
        return cls(NodeType.START, labels)

    @classmethod
    def create_mid(cls, *labels) -> 'NodeDisplayConfig':
        return cls(NodeType.MID, labels)

    @classmethod
    def create_end(cls, *labels) -> 'NodeDisplayConfig':
        return cls(NodeType.END, labels)


@dataclass
class LaneConfig:
    """Lane 配置数据"""
    lane_id: str
    label: str
    stage: TimelineStage
    display: NodeDisplayConfig

    @property
    def prefix(self) -> str:
        return self.lane_id[0] if self.lane_id != "POSTPROCESSING" else "E"


class LaneButtonGroup(QWidget):
    MAX_VISIBLE_RULES = 4
    RULE_HEIGHT = 44  # 32px button + 6px*2 margins

    rule_moved = pyqtSignal(str, int, int)
    rule_removed = pyqtSignal(str)
    rule_clicked = pyqtSignal(object)
    badge_toggle_requested = pyqtSignal(object, bool)  # (RuleToolButton, show)

    def __init__(
        self,
        lane_id: str,
        prefix: str,
        stage: TimelineStage,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName(f"laneButtonGroup_{lane_id}")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.lane_id = lane_id
        self.prefix = prefix
        self.stage = stage
        self.rules: list[RuleToolButton] = []
        self._is_current = False
        self._is_disabled = False
        self._color_scheme: LaneColorScheme = None
        self._play_visible = False

        self._init_ui()

    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setFixedWidth(100)
        self.layout = VBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 4, 4)
        self.layout.setSpacing(4)

        self.laneRunBtn = TransparentToolButton(FIF.PLAY_SOLID, self)
        self.laneRunBtn.setFixedSize(32, 32)
        self.laneRunBtn.setVisible(False)
        self.laneRunBtn.setEnabled(False)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.addWidget(self.laneRunBtn)
        header_layout.addStretch(1)
        self.layout.addLayout(header_layout)

        self._rules_container = QWidget(self)
        self._rules_layout = VBoxLayout(self._rules_container)
        self._rules_layout.setContentsMargins(0, 0, 0, 0)
        self._rules_layout.setSpacing(4)

        self._rules_scroll = None
        self.layout.addWidget(self._rules_container)
        self.setVisible(False)

    def _update_scroll_state(self):
        needs_scroll = len(self.rules) > self.MAX_VISIBLE_RULES
        has_scroll = self._rules_scroll is not None

        if needs_scroll and not has_scroll:
            self.layout.removeWidget(self._rules_container)
            self._rules_scroll = QScrollArea(self)
            self._rules_scroll.setWidgetResizable(True)
            self._rules_scroll.setFrameShape(QFrame.NoFrame)
            self._rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._rules_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._rules_scroll.setWidget(self._rules_container)
            self._rules_scroll.setMaximumHeight(self.MAX_VISIBLE_RULES * self.RULE_HEIGHT)
            self.layout.addWidget(self._rules_scroll)
        elif not needs_scroll and has_scroll:
            self._rules_scroll.takeWidget()
            self.layout.removeWidget(self._rules_scroll)
            self._rules_scroll.deleteLater()
            self._rules_scroll = None
            self.layout.addWidget(self._rules_container)

    def _sync_play_visibility(self):
        self.laneRunBtn.setVisible(bool(self.rules))

    def set_play_enabled(self, enabled: bool):
        self.laneRunBtn.setEnabled(enabled)

    def set_play_visible(self, visible: bool):
        self._play_visible = visible
        self._sync_play_visibility()

    def setVisible(self, visible: bool):
        super().setVisible(visible)
        self._sync_play_visibility()

    def apply_colors(self, scheme: LaneColorScheme):
        """应用颜色方案（由 WorkflowCanvas 调用）"""
        self._color_scheme = scheme
        self._update_button_colors()

    def _update_button_colors(self):
        """更新所有子按钮的颜色"""
        if not self._color_scheme:
            return
        for btn in self.rules:
            btn.apply_colors(
                bg=self._color_scheme.node_fill,
                border=self._color_scheme.button_border,
                text=self._color_scheme.node_font
            )
        self.laneRunBtn.setIcon(FIF.PLAY_SOLID.icon(color=self._color_scheme.node_fill))

    def add_rule(self, definition: MiddlewareDefinition) -> RuleToolButton:
        btn = RuleToolButton(definition.label, definition, self)
        btn.move_up.connect(lambda: self._on_move(btn, -1))
        btn.move_down.connect(lambda: self._on_move(btn, 1))
        btn.remove_clicked.connect(lambda: self._on_remove(btn))
        btn.main_button.clicked.connect(lambda: self.rule_clicked.emit(definition))
        btn.badge_toggled.connect(lambda show: self.badge_toggle_requested.emit(btn, show))

        self.rules.append(btn)
        self._rules_layout.addWidget(btn)
        self._update_scroll_state()
        self.setVisible(True)
        self._sync_play_visibility()

        if self._color_scheme:
            btn.apply_colors(
                bg=self._color_scheme.node_fill,
                border=self._color_scheme.button_border,
                text=self._color_scheme.node_font
            )
        self._update_edge_buttons()
        return btn

    def remove_rule(self, rule_id: str):
        for i, btn in enumerate(self.rules):
            if btn.definition.id == rule_id:
                self.rules.pop(i)
                self._rules_layout.removeWidget(btn)
                btn.deleteLater()
                self.rule_removed.emit(rule_id)
                break
        self._update_scroll_state()
        self._update_edge_buttons()
        self._sync_play_visibility()
        if not self.rules:
            self.setVisible(False)

    def _on_move(self, btn: RuleToolButton, direction: int):
        idx = self.rules.index(btn)
        new_idx = idx + direction
        if not (0 <= new_idx < len(self.rules)):
            return
        self.rules[idx], self.rules[new_idx] = self.rules[new_idx], self.rules[idx]
        self._rebuild_layout()
        self._update_edge_buttons()
        self.rule_moved.emit(btn.definition.id, idx, new_idx)

    def _rebuild_layout(self):
        self._rules_layout.removeAllWidget()
        for btn in self.rules:
            self._rules_layout.addWidget(btn)
            btn.update_badge_positions()

    def _update_edge_buttons(self):
        n = len(self.rules)
        for i, btn in enumerate(self.rules):
            btn.set_move_enabled(can_up=(i > 0), can_down=(i < n - 1))

    def _on_remove(self, btn: RuleToolButton):
        self.remove_rule(btn.definition.id)

    def set_current(self, is_current: bool):
        self._is_current = is_current

    def set_disabled(self, disabled: bool):
        self._is_disabled = disabled
        self.laneRunBtn.setEnabled(not disabled)

    def clear(self):
        for btn in self.rules:
            btn.deleteLater()
        self.rules.clear()
        self._update_scroll_state()
        self.setVisible(False)


class LaneNode:
    """Lane 节点封装类 - 管理单个 Lane 的所有 UI 组件"""

    def __init__(self, config: LaneConfig, parent: QWidget):
        self.config = config
        self._scheme: LaneColorScheme = None
        self._is_highlighted = False
        self._parent = parent

        display = config.display
        self.node_widget = SvgWidget(node_type=display.node_type, parent=parent)
        self.node_widget.setFixedWidth(100)
        self.node_widget.setFixedHeight(80)
        self.node_widget.set_labels(*display.labels)

        self.button_group = LaneButtonGroup(
            config.lane_id, config.prefix, config.stage, parent
        )

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addStretch(1)
        self.layout.addWidget(self.button_group)
        self.layout.addWidget(self.node_widget)

    def apply_theme(self, scheme: LaneColorScheme):
        """应用主题配色"""
        self._scheme = scheme
        self.button_group.apply_colors(scheme)
        self.node_widget.set_colors(scheme.node_fill, scheme.node_font)

    def set_highlight(self, highlighted: bool):
        """设置高亮状态"""
        if self._is_highlighted == highlighted:
            return
        self._is_highlighted = highlighted
        self.node_widget.set_highlight(highlighted)

    def set_state(self, disabled: bool, is_current: bool, play_enabled: bool):
        """设置 Lane 状态"""
        self.button_group.set_disabled(disabled)
        self.button_group.set_current(is_current)
        self.button_group.set_play_enabled(play_enabled)

    def set_hidden(self, hidden: bool):
        """隐藏/显示整个 Lane"""
        self.button_group.setVisible(not hidden)
        self.node_widget.setVisible(not hidden)
