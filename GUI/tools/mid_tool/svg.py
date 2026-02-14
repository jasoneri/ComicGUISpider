# -*- coding: utf-8 -*-
from enum import Enum
from itertools import zip_longest
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QStackedLayout
from PyQt5.QtGui import QColor
from qfluentwidgets import FluentIconBase, Theme, IconWidget


class MidNodeIcon(FluentIconBase, Enum):
    """Mid 工具节点图标"""
    NODE_START = "node_start"
    NODE_MID = "node_mid"
    NODE_END = "node_end"
    RULE_STACK = "rule_stack"

    def path(self, theme=Theme.AUTO):
        return f':/mid_tool/{self.value}.svg'


class NodeType(Enum):
    START = MidNodeIcon.NODE_START
    MID = MidNodeIcon.NODE_MID
    END = MidNodeIcon.NODE_END
    RULE = MidNodeIcon.RULE_STACK
    
    @property
    def icon(self) -> MidNodeIcon:
        return self.value


class SvgWidget(QWidget):
    MAX_LABEL_LINES = 2
    clicked = pyqtSignal()

    def __init__(self, node_type: NodeType = NodeType.MID, parent=None):
        super().__init__(parent)
        self._node_type = node_type
        self._icon_type = node_type.icon  # 缓存图标类型
        self._fill_color = "#808080"
        self._font_color = "#FFFFFF"
        self._labels = []

        self._init_ui()

    def _init_ui(self):
        # 使用 QStackedLayout 叠加图标和文字
        self._stack = QStackedLayout(self)
        self._stack.setStackingMode(QStackedLayout.StackAll)

        # 图标层 - 直接使用缓存的图标类型
        self._icon_widget = IconWidget(self._icon_type, self)
        self._stack.addWidget(self._icon_widget)

        # 文字层
        self._text_container = QWidget(self)
        self._text_container.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 鼠标事件穿透
        self._text_layout = QVBoxLayout(self._text_container)
        self._text_layout.setContentsMargins(2, 2, 2, 2)
        self._text_layout.setSpacing(2)
        self._text_layout.addStretch(1)
        
        # 动态创建标签行
        self._label_lines = []
        for _ in range(self.MAX_LABEL_LINES):
            label = QLabel(self._text_container)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background: transparent;")
            label.setVisible(False)
            self._label_lines.append(label)
            self._text_layout.addWidget(label)
        
        self._text_layout.addStretch(1)

        self._stack.addWidget(self._text_container)
        
        # 确保文字层在图标层之上
        self._text_container.raise_()

    def set_labels(self, *labels):
        """设置文字标签（最多 MAX_LABEL_LINES 行）"""
        self._labels = list(labels[:self.MAX_LABEL_LINES])
        
        # 使用 zip_longest 优雅地处理标签更新
        for label_widget, text in zip_longest(self._label_lines, self._labels, fillvalue=""):
            if text:
                label_widget.setText(text)
                label_widget.setVisible(True)
            else:
                label_widget.setVisible(False)

    def set_colors(self, fill_color: str, font_color: str):
        """设置颜色"""
        self._fill_color = fill_color
        self._font_color = font_color
        self._update_style()

    def _update_style(self):
        # 更新图标颜色 - 直接使用缓存的图标类型
        self._icon_widget.setIcon(self._icon_type.icon(color=self._fill_color))

        # 更新文字样式
        style = f"""
            QLabel {{
                color: {self._font_color};
                font-weight: bold; font-size: 14px; background: transparent;
            }}
        """ if self._node_type  != NodeType.RULE else """QLabel {
                font-weight: bold; font-size: 14px; background: transparent;
        }"""
        for label in self._label_lines:
            label.setStyleSheet(style)
        # 重新提升文字层,防止图标更新后遮挡文字
        self._text_container.raise_()

    def set_highlight(self, highlighted: bool):
        """设置高亮状态"""
        if highlighted:
            fill = QColor(self._fill_color).lighter(120).name()
        else:
            fill = self._fill_color

        # 直接使用缓存的图标类型
        self._icon_widget.setIcon(self._icon_type.icon(color=fill))

        # 重新提升文字层,防止图标更新后遮挡文字
        self._text_container.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
