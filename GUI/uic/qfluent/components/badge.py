from PySide6.QtCore import Qt, Signal, QPoint, QObject, QEvent
from PySide6.QtGui import QFont
from qfluentwidgets import (
    InfoBadgeManager, InfoBadgePosition, DotInfoBadge, IconInfoBadge, InfoBadge
)
from GUI.core.anim import BreathingEffect
from GUI.core.theme import CustTheme, theme_mgr


class ClickableIconInfoBadge(IconInfoBadge):
    clicked = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 移除透明鼠标事件属性，使 badge 可点击
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(e)

    def eventFilter(self, obj, e):
        if self._inside and obj is self._target and e.type() in (QEvent.Resize, QEvent.Move):
            self._update_position_inside()
        return super().eventFilter(obj, e)


class _BadgeAnchor(QObject):
    """Tracks target widget movement and repositions badge via mapTo."""
    def __init__(self, target, badge, parent_widget, pos, division=2):
        super().__init__(badge)
        self.target = target
        self.badge = badge
        self.parent_widget = parent_widget
        self.pos = pos
        self.division = division
        target.installEventFilter(self)
        if target.parentWidget():
            target.parentWidget().installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Resize, QEvent.Move):
            self.badge.move(self.calc_position())
        return False

    def calc_position(self):
        tr = self.target.rect().topRight()
        mapped = self.target.mapTo(self.parent_widget, tr)
        return QPoint(mapped.x() - int(self.badge.width() // self.division), mapped.y() - self.badge.height() // 2)


class CustomBadge:
    @classmethod
    def make(cls, bge_args, pos: InfoBadgePosition, target):
        _bge = ClickableIconInfoBadge(*bge_args)
        _bge.manager = InfoBadgeManager.make(pos, target, _bge)
        _bge.move(_bge.manager.position())
        return _bge

    @classmethod
    def make_ani_dot(cls, parent, size=None, target=None, level="success", pos=InfoBadgePosition.TOP_RIGHT):
        t = target or parent
        sz = size or (10, 10)
        dot = getattr(DotInfoBadge, level)(parent, target=None, position=pos)
        dot.setFixedSize(*sz)
        anchor = _BadgeAnchor(t, dot, parent, pos)
        dot.move(anchor.calc_position())
        dot._anchor = anchor
        breathing = BreathingEffect(dot, duration_ms=1500, min_opacity=0.3, max_opacity=1.0)
        breathing.start()
        dot._breath_anim = breathing
        return dot


class CountBadge:
    COLOR_BG = "#409EFF"
    COLOR_TEXT = "#F8FAFC"
    MIN_DIGITS = 2
    MIN_HEIGHT = 18
    HORIZONTAL_PADDING = 7
    VERTICAL_PADDING = 3

    def __init__(self, parent, target, pos=InfoBadgePosition.TOP_LEFT, division=3):
        self.badge = InfoBadge.custom("", self.COLOR_BG, self.COLOR_BG, parent, target=None, position=pos)
        self._anchor = _BadgeAnchor(target, self.badge, parent, pos, division=division)
        self._count = 0
        self._light_bg = self.COLOR_BG
        self._dark_bg = self.COLOR_BG
        self._min_digits = self.MIN_DIGITS
        self._min_height = self.MIN_HEIGHT
        self._horizontal_padding = self.HORIZONTAL_PADDING
        self._vertical_padding = self.VERTICAL_PADDING
        self._light_text_color = self.COLOR_TEXT
        self._dark_text_color = self.COLOR_TEXT
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setContentsMargins(0, 0, 0, 0)
        self.badge.setMargin(0)
        font = self.badge.font()
        font.setWeight(QFont.Weight.DemiBold)
        self.badge.setFont(font)
        self._apply_visual_style()
        self.badge.move(self._anchor.calc_position())
        self.badge._anchor = self._anchor

    @staticmethod
    def _is_dark_theme() -> bool:
        return theme_mgr.get_theme() == CustTheme.DARK

    def _effective_text_color(self) -> str:
        return self._dark_text_color if self._is_dark_theme() else self._light_text_color

    def _effective_background_color(self) -> str:
        return self._dark_bg if self._is_dark_theme() else self._light_bg

    def _apply_visual_style(self):
        color = self._effective_background_color()
        self.badge.setCustomBackgroundColor(color, color)
        self.badge.setStyleSheet(
            f"color: {self._effective_text_color()}; padding: 0px; margin: 0px; background: transparent;"
        )

    def apply_style(
        self,
        *,
        light_bg: str | None = None,
        dark_bg: str | None = None,
        text_color: str | None = None,
        light_text_color: str | None = None,
        dark_text_color: str | None = None,
        point_size: float | None = None,
        weight: int | None = None,
        min_digits: int | None = None,
        min_height: int | None = None,
        horizontal_padding: int | None = None,
        vertical_padding: int | None = None,
    ):
        if light_bg is not None or dark_bg is not None:
            self._light_bg = str(light_bg or dark_bg or self.COLOR_BG)
            self._dark_bg = str(dark_bg or light_bg or self.COLOR_BG)
        if text_color is not None:
            color = str(text_color)
            self._light_text_color = color
            self._dark_text_color = color
        if light_text_color is not None:
            self._light_text_color = str(light_text_color)
        if dark_text_color is not None:
            self._dark_text_color = str(dark_text_color)
        if min_digits is not None:
            self._min_digits = max(1, int(min_digits))
        if min_height is not None:
            self._min_height = max(1, int(min_height))
        if horizontal_padding is not None:
            self._horizontal_padding = max(0, int(horizontal_padding))
        if vertical_padding is not None:
            self._vertical_padding = max(0, int(vertical_padding))
        font = self.badge.font()
        if point_size is not None:
            font.setPointSizeF(max(1.0, float(point_size)))
        if weight is not None:
            font.setWeight(QFont.Weight(int(weight)))
        self.badge.setFont(font)
        self._apply_visual_style()
        self.set_count(self._count)

    def set_count(self, count: int):
        self._count = max(0, int(count))
        text = str(self._count)
        self._apply_visual_style()
        metrics = self.badge.fontMetrics()
        height = max(self._min_height, metrics.height() + self._vertical_padding * 2)
        width = max(
            height,
            metrics.horizontalAdvance("8" * self._min_digits) + self._horizontal_padding * 2,
            metrics.horizontalAdvance(text) + self._horizontal_padding * 2,
        )
        self.badge.setText(text)
        self.badge.setFixedSize(width, height)
        self.badge.move(self._anchor.calc_position())

    def show(self):
        self._apply_visual_style()
        self.badge.show()

    def hide(self):
        self.badge.hide()


class DlStatusBadge:
    COLOR_PROGRESS = "#409EFF"
    COLOR_COMPLETE = "#67C23A"
    COLOR_TEXT = "#FFFFFF"

    def __init__(self, parent, target, pos=InfoBadgePosition.TOP_LEFT):
        self.badge = InfoBadge.custom("", self.COLOR_PROGRESS, self.COLOR_PROGRESS, parent, target=None, position=pos)
        self._anchor = _BadgeAnchor(target, self.badge, parent, pos, division=3)
        self.badge.move(self._anchor.calc_position())
        self.badge._anchor = self._anchor
        self._breathing = BreathingEffect(self.badge)
        self._set_color(self.COLOR_PROGRESS)

    def update_progress(self, downloaded: int, total: int):
        text = f"{downloaded}/{total}"
        self.badge.setText(text)
        self.badge.setFixedSize(int(8.5*len(text)),15)
        self.badge.move(self._anchor.calc_position())
        if total > 0 and downloaded >= total:
            self._breathing.stop()
            self._set_color(self.COLOR_COMPLETE)
        elif downloaded >= 0:
            if not self._breathing.is_running():
                self._breathing.start()
            self._set_color(self.COLOR_PROGRESS)
        else:
            self._breathing.stop()
            self._set_color(self.COLOR_PROGRESS)

    def _set_color(self, bg_color: str):
        self.badge.setCustomBackgroundColor(bg_color, bg_color)

    def show(self):
        self.badge.show()

    def hide(self):
        self._breathing.stop()
        self.badge.hide()
