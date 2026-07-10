from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QHBoxLayout, QWidget
from qfluentwidgets import Flyout, FlyoutAnimationType, IconWidget, TeachingTip, TeachingTipView

from GUI.core.anim import ProxyRotationController


class CustomFlyout:
    @classmethod
    def make(cls, view, target, parent, calc_bottom=False, aniType=FlyoutAnimationType.PULL_UP):
        _fly = Flyout.make(
            view=view, parent=parent, aniType=aniType,
            target=cls.calculate_target_position(target) if calc_bottom else target
        )
        if hasattr(view, "closed"):
            view.closed.connect(_fly.close)
        return _fly

    @staticmethod
    def calculate_target_position(widget):
        rect = widget.rect()
        bottom_center = widget.mapToGlobal(rect.bottomLeft())
        bottom_center.setX(bottom_center.x() + rect.width() // 2 - widget.width() // 2)
        bottom_center.setY(bottom_center.y() - 15)
        return bottom_center


class CustomTeachingTip:
    @classmethod
    def create(cls, widgets, target, parent, content=None, topLayout=None, isClosable=True, duration=-1, **kw):
        view = TeachingTipView(
            title="", content="", isClosable=isClosable
        )
        offset = 0
        cindex = 1 if isClosable else 0
        if topLayout:
            view.viewLayout.insertLayout(view.viewLayout.count() - cindex, topLayout)
        for w in widgets:
            view.viewLayout.insertWidget(view.viewLayout.count() - cindex, w)
            offset += (w.sizeHint().width() + 5)
        view.adjustSize()
        tip = TeachingTip(view, target, duration, parent=parent, **kw)
        tip.show()
        view.closeButton.clicked.connect(tip.close)
        return tip


_ICON_SIZE = 18
_VIEW_SIZE = 24
_PAD = (_VIEW_SIZE - _ICON_SIZE) // 2


class ExpandButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        from .icons import CgsIcon

        super().__init__(parent)
        self.expanded = False

        self._label = IconWidget(CgsIcon.EXPAND)
        self._label.setFixedSize(_ICON_SIZE, _ICON_SIZE)

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene, self)
        self._proxy = self._scene.addWidget(self._label)
        self._proxy.setPos(_PAD, _PAD)
        self._proxy.setTransformOriginPoint(_ICON_SIZE / 2, _ICON_SIZE / 2)
        self._scene.setSceneRect(0, 0, _VIEW_SIZE, _VIEW_SIZE)

        self._view.setFixedSize(_VIEW_SIZE, _VIEW_SIZE)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setFrameShape(QGraphicsView.NoFrame)
        self._view.setStyleSheet("background: transparent;")
        self._view.setBackgroundBrush(QBrush(Qt.transparent))
        self._view.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._anim_ctrl = ProxyRotationController(self._proxy)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self.setFixedSize(_VIEW_SIZE, _VIEW_SIZE)
        self.setCursor(Qt.PointingHandCursor)

    def set_expanded(self, expanded: bool, *, animate: bool = True):
        self.expanded = bool(expanded)
        angle = -45.0 if self.expanded else 0.0
        if animate:
            self._anim_ctrl.rotate_to(angle)
            return
        self._anim_ctrl.stop()
        self._proxy.setRotation(angle)

    def expand(self):
        self.set_expanded(not self.expanded)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def click(self):
        self.clicked.emit()
