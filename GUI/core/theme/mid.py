# -*- coding: utf-8 -*-
"""Mid 工具流程节点配色方案"""

from dataclasses import dataclass
from PySide6.QtGui import QColor


@dataclass
class LaneColorScheme:
    """单个 Lane 的完整配色方案"""
    lane_id: str

    # 节点颜色 (SVG 使用)
    node_fill: str
    node_font: str

    # Lane 区域颜色 (LaneButtonGroup 使用)
    lane_bg: str
    lane_bg_current: str
    lane_bg_disabled: str

    # 按钮颜色 (RuleToolButton 使用)
    button_bg: str
    button_border: str
    button_text: str

    @staticmethod
    def from_base_color(lane_id: str, base_fill: str, base_font: str, is_dark: bool):
        """
        从基础颜色生成完整配色方案

        Args:
            lane_id: Lane ID (如 "SITE", "SEARCH" 等)
            base_fill: 基础填充色 (节点背景色)
            base_font: 基础文字色
            is_dark: 是否为暗色模式

        Returns:
            LaneColorScheme: 完整的配色方案
        """
        base_color = QColor(base_fill)
        if not base_color.isValid():
            base_color = QColor("#808080")
            base_fill = "#808080"  # 同步更新 base_fill

        font_color = QColor(base_font)
        if not font_color.isValid():
            base_font = "#FFFFFF"

        if is_dark:
            lane_bg = base_color.darker(150).name()
            lane_bg_current = base_color.darker(130).name()
            button_bg = base_color.darker(160).name()
            button_border = base_color.darker(110).name()
            lane_bg_disabled = "#555555"
        else:
            lane_bg = base_color.lighter(150).name()
            lane_bg_current = base_color.lighter(130).name()
            button_bg = base_color.lighter(160).name()
            button_border = base_color.darker(110).name()
            lane_bg_disabled = "#CCCCCC"

        return LaneColorScheme(
            lane_id=lane_id,
            node_fill=base_fill,
            node_font=base_font,
            lane_bg=lane_bg,
            lane_bg_current=lane_bg_current,
            lane_bg_disabled=lane_bg_disabled,
            button_bg=button_bg,
            button_border=button_border,
            button_text=base_font
        )


class MidNodeColors:
    """Mid 工具节点配色管理器"""

    def __init__(self, base_colors: dict[str, tuple[str, str]], is_dark: bool):
        """
        Args:
            base_colors: {lane_id: (fill_color, font_color)}
            is_dark: 是否为暗色模式
        """
        self.is_dark = is_dark
        self._schemes: dict[str, LaneColorScheme] = {}

        for lane_id, (fill, font) in base_colors.items():
            self._schemes[lane_id] = LaneColorScheme.from_base_color(
                lane_id, fill, font, is_dark
            )

    def get_scheme(self, lane_id: str) -> LaneColorScheme:
        """获取指定 Lane 的完整配色方案"""
        if lane_id in self._schemes:
            return self._schemes[lane_id]
        return self._get_default_scheme(lane_id)

    def _get_default_scheme(self, lane_id: str) -> LaneColorScheme:
        """获取默认配色（灰色）"""
        return LaneColorScheme.from_base_color(
            lane_id, "#808080", "#FFFFFF", self.is_dark
        )


# 白天模式基础配色 (柔和色调)
LIGHT_BASE_COLORS = {
    "SITE": ("#5DADE2", "#FFFFFF"),
    "SEARCH": ("#58D68D", "#FFFFFF"),
    "BOOK": ("#F8B739", "#333333"),  # 亮色背景用深色文字
    "EP": ("#AF7AC5", "#FFFFFF"),
    "POSTPROCESSING": ("#EC7063", "#FFFFFF"),
}

# 夜间模式基础配色 (明亮色调)
DARK_BASE_COLORS = {
    "SITE": ("#3498DB", "#FFFFFF"),
    "SEARCH": ("#2ECC71", "#FFFFFF"),
    "BOOK": ("#F39C12", "#FFFFFF"),
    "EP": ("#9B59B6", "#FFFFFF"),
    "POSTPROCESSING": ("#E74C3C", "#FFFFFF"),
}


def create_light_mid_colors() -> MidNodeColors:
    """创建白天模式的 Mid 配色"""
    return MidNodeColors(LIGHT_BASE_COLORS, is_dark=False)


def create_dark_mid_colors() -> MidNodeColors:
    """创建夜间模式的 Mid 配色"""
    return MidNodeColors(DARK_BASE_COLORS, is_dark=True)
