from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QObject, QEvent
from qfluentwidgets import (
    InfoBadgeManager, InfoBadgePosition, DotInfoBadge, IconInfoBadge, InfoBadge
)
from GUI.core.anim import BreathingEffect


class ClickableIconInfoBadge(IconInfoBadge):
    clicked = pyqtSignal()

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

    def __init__(self, parent, target, pos=InfoBadgePosition.TOP_LEFT, division=3):
        self.badge = InfoBadge.custom("", self.COLOR_BG, self.COLOR_BG, parent, target=None, position=pos)
        self._anchor = _BadgeAnchor(target, self.badge, parent, pos, division=division)
        self.badge.move(self._anchor.calc_position())
        self.badge._anchor = self._anchor

    def set_count(self, count: int):
        text = str(max(0, count))
        metrics = self.badge.fontMetrics()
        width = max(18, metrics.horizontalAdvance(text) + 6)
        height = max(16, metrics.height() + 4)
        self.badge.setText(text)
        self.badge.setFixedSize(width, height)
        self.badge.move(self._anchor.calc_position())

    def show(self):
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
