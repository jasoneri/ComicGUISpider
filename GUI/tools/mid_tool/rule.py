# -*- coding: utf-8 -*-
import re
from dataclasses import dataclass
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSizePolicy
)
from qfluentwidgets import (
    FluentIcon as FIF, InfoBadgePosition, InfoLevel
)

from GUI.tools.mid_tool.svg import SvgWidget, NodeType
from GUI.uic.qfluent.components import CustomBadge
from utils.middleware import (
    MiddlewareDefinition,
)


class RuleToolButton(QWidget):
    LANE_WIDTH = 100
    WIDTH_OFFSET = 30
    BUTTON_HEIGHT = 24

    move_up = Signal()
    move_down = Signal()
    remove_clicked = Signal()
    badge_toggled = Signal(bool)

    def __init__(self, label: str, definition: MiddlewareDefinition, parent=None):
        super().__init__(parent)
        self.label = label
        self.definition = definition
        self._colors = None
        self._can_up = True
        self._can_down = True
        self._badges_visible = False

        self._init_ui()
    
    def _init_ui(self):
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10,9,7,7)  # remark 严格影响badge的可视
        
        self.main_button = SvgWidget(NodeType.RULE, self)
        self.main_button.setFixedSize(self.LANE_WIDTH - self.WIDTH_OFFSET, self.BUTTON_HEIGHT)
        self.main_button.set_labels(self.label)
        self.main_button.setToolTip(self.definition.name)
        layout.addWidget(self.main_button)
        
        self.up_bge = CustomBadge.make(
            (FIF.CARE_UP_SOLID, self, InfoLevel.SUCCESS),
            target=self.main_button,
            pos=InfoBadgePosition.TOP_LEFT,
        )
        
        self.down_bge = CustomBadge.make(
            (FIF.CARE_DOWN_SOLID, self, InfoLevel.SUCCESS),
            target=self.main_button,
            pos=InfoBadgePosition.BOTTOM_LEFT,
        )
        
        self.remove_bge = CustomBadge.make(
            (FIF.CLOSE, self, InfoLevel.ERROR),
            target=self.main_button,
            pos=InfoBadgePosition.TOP_RIGHT,
        )
        
        self.up_bge.clicked.connect(self._on_up)
        self.down_bge.clicked.connect(self._on_down)
        self.remove_bge.clicked.connect(self._on_remove)

        self._apply_badges_visibility()
        self.main_button.clicked.connect(self._request_toggle_badges)

    def show_badges(self):
        if self._badges_visible:
            return
        self._badges_visible = True
        self._apply_badges_visibility()

    def hide_badges(self):
        if not self._badges_visible:
            return
        self._badges_visible = False
        self._apply_badges_visibility()

    def _apply_badges_visibility(self):
        up_visible = self._badges_visible and self._can_up
        down_visible = self._badges_visible and self._can_down
        remove_visible = self._badges_visible

        self.up_bge.setVisible(up_visible)
        self.down_bge.setVisible(down_visible)
        self.remove_bge.setVisible(remove_visible)

        self.up_bge.setAttribute(Qt.WA_TransparentForMouseEvents, not up_visible)
        self.down_bge.setAttribute(Qt.WA_TransparentForMouseEvents, not down_visible)
        self.remove_bge.setAttribute(Qt.WA_TransparentForMouseEvents, not remove_visible)

    def _request_toggle_badges(self):
        self.badge_toggled.emit(not self._badges_visible)
    
    def showEvent(self, event):
        super().showEvent(event)
        self.update_badge_positions()

    def update_badge_positions(self):
        for bge in (self.up_bge, self.down_bge, self.remove_bge):
            if hasattr(bge, 'manager') and bge.manager:
                bge.move(bge.manager.position())

    def _on_up(self):
        self.hide_badges()
        self.move_up.emit()

    def _on_down(self):
        self.hide_badges()
        self.move_down.emit()

    def _on_remove(self):
        self.hide_badges()
        self.remove_clicked.emit()
    
    def apply_colors(self, bg: str, border: str, text: str):
        self._colors = (bg, border, text)
        self.main_button.set_colors(fill_color=bg, font_color=text)

    def set_move_enabled(self, can_up: bool, can_down: bool):
        self._can_up = can_up
        self._can_down = can_down
        if self._badges_visible:
            self._apply_badges_visibility()
