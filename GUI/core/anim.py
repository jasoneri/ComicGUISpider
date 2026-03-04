from typing import Literal

from PyQt5.QtCore import (
    QObject,
    QAbstractAnimation,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QRect,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect


PopupDirection = Literal["right", "up", "down"]


class BreathingEffect(QObject):
    def __init__(self, widget, duration_ms=1500, min_opacity=0.6, max_opacity=1.0):
        super().__init__(widget)
        self._widget = widget
        self._duration = duration_ms
        self._min_opacity = min_opacity
        self._max_opacity = max_opacity
        self._effect = None
        self._anim = None
        self._running = False
        if widget is not None:
            widget.destroyed.connect(self._cleanup)

    def _ensure_effect_and_anim(self):
        if self._widget is None:
            return False
        if self._effect is None:
            self._effect = QGraphicsOpacityEffect(self._widget)
            self._widget.setGraphicsEffect(self._effect)
        if self._anim is None:
            self._anim = QPropertyAnimation(self._effect, b"opacity", self._widget)
            self._anim.setDuration(self._duration)
            self._anim.setStartValue(self._min_opacity)
            self._anim.setEndValue(self._max_opacity)
            self._anim.setEasingCurve(QEasingCurve.InOutSine)
            self._anim.finished.connect(self._on_finished)
        return True

    def _on_finished(self):
        if not self._running or self._anim is None:
            return
        direction = QAbstractAnimation.Backward if self._anim.direction() == QAbstractAnimation.Forward else QAbstractAnimation.Forward
        self._anim.setDirection(direction)
        self._anim.start()

    def start(self):
        if not self._ensure_effect_and_anim():
            return
        self._running = True
        self._anim.setDirection(QAbstractAnimation.Forward)
        self._anim.start()

    def stop(self, restore_opacity=True):
        self._running = False
        if self._anim and self._anim.state() == QAbstractAnimation.Running:
            self._anim.stop()
        if restore_opacity and self._effect is not None:
            self._effect.setOpacity(1.0)

    def is_running(self) -> bool:
        return self._running and self._anim is not None and self._anim.state() == QAbstractAnimation.Running

    def _cleanup(self):
        self._running = False
        if self._anim is not None:
            if self._anim.state() == QAbstractAnimation.Running:
                self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        self._effect = None
        self._widget = None


class ProxyRotationController(QObject):
    def __init__(self, proxy, duration_ms=180, easing=QEasingCurve.InOutCubic):
        super().__init__(proxy)
        self._proxy = proxy
        self._anim = QPropertyAnimation(proxy, b"rotation", proxy)
        self._anim.setDuration(duration_ms)
        self._anim.setEasingCurve(easing)
        proxy.destroyed.connect(self._cleanup)

    def rotate_to(self, angle: float):
        if self._proxy is None or self._anim is None:
            return
        self._anim.stop()
        self._anim.setStartValue(self._proxy.rotation())
        self._anim.setEndValue(angle)
        self._anim.start()

    def toggle(self, angle_a=0.0, angle_b=45.0):
        if self._proxy is None or self._anim is None:
            return
        current = self._proxy.rotation()
        self.rotate_to(angle_b if current < (angle_a + angle_b) / 2 else angle_a)

    def stop(self):
        if self._anim and self._anim.state() == QAbstractAnimation.Running:
            self._anim.stop()

    def cleanup(self):
        self._cleanup()

    def _cleanup(self):
        if self._anim is not None:
            if self._anim.state() == QAbstractAnimation.Running:
                self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        self._proxy = None


class WindowHeightAnimator(QObject):
    def __init__(self, window, duration_ms=250, easing=QEasingCurve.OutCubic):
        super().__init__(window)
        self._window = window
        self._anim = QPropertyAnimation(window, b"geometry", window)
        self._anim.setDuration(duration_ms)
        self._anim.setEasingCurve(easing)
        self._original_height = window.height()
        self._pending_callback = None
        self._anim.finished.connect(self._on_anim_finished)
        window.destroyed.connect(self._cleanup)

    @property
    def is_running(self) -> bool:
        return self._anim is not None and self._anim.state() == QAbstractAnimation.Running

    @property
    def original_height(self) -> int:
        return self._original_height

    def stop(self):
        if self._anim is not None and self._anim.state() == QAbstractAnimation.Running:
            self._anim.stop()
        self._pending_callback = None

    def _on_anim_finished(self):
        if self._pending_callback is not None:
            cb = self._pending_callback
            self._pending_callback = None
            cb()

    def animate_to(self, target_height: int, on_finished=None):
        if self._window is None or self._anim is None:
            return
        current_geo = self._window.geometry()
        target_geo = QRect(current_geo.x(), current_geo.y(), current_geo.width(), target_height)
        self._anim.stop()
        self._anim.setStartValue(current_geo)
        self._anim.setEndValue(target_geo)
        self._pending_callback = on_finished
        self._anim.start()

    def restore(self, on_finished=None):
        self.animate_to(self._original_height, on_finished)

    def cleanup(self):
        self._cleanup()

    def _cleanup(self):
        if self._anim is not None:
            if self._anim.state() == QAbstractAnimation.Running:
                self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        self._window = None
        self._pending_callback = None


class PanelHeightAnimator(QObject):
    def __init__(self, panel, duration_ms=250, easing=QEasingCurve.OutCubic):
        super().__init__(panel)
        self._panel = panel
        self._min_anim = QPropertyAnimation(panel, b"minimumHeight", panel)
        self._max_anim = QPropertyAnimation(panel, b"maximumHeight", panel)
        self._min_anim.setDuration(duration_ms)
        self._max_anim.setDuration(duration_ms)
        self._min_anim.setEasingCurve(easing)
        self._max_anim.setEasingCurve(easing)
        self._group = QParallelAnimationGroup(panel)
        self._group.addAnimation(self._min_anim)
        self._group.addAnimation(self._max_anim)
        self._pending_callback = None
        self._group.finished.connect(self._on_finished)
        panel.destroyed.connect(self._cleanup)

    @property
    def is_running(self) -> bool:
        return self._group is not None and self._group.state() == QAbstractAnimation.Running

    def stop(self):
        if self._group is not None and self._group.state() == QAbstractAnimation.Running:
            self._group.stop()
        self._pending_callback = None

    def animate(self, start_height: int, target_height: int, on_finished=None):
        if self._panel is None or self._group is None:
            return
        start = max(0, int(start_height))
        target = max(0, int(target_height))
        self._group.stop()
        self._panel.setMinimumHeight(start)
        self._panel.setMaximumHeight(start)
        self._min_anim.setStartValue(start)
        self._min_anim.setEndValue(target)
        self._max_anim.setStartValue(start)
        self._max_anim.setEndValue(target)
        self._pending_callback = on_finished
        self._group.start()

    def expand(self, target_height: int, on_finished=None):
        start = self._panel.maximumHeight() if self._panel is not None else 0
        self.animate(start, target_height, on_finished)

    def collapse(self, on_finished=None):
        start = self._panel.maximumHeight() if self._panel is not None else 0
        self.animate(start, 0, on_finished)

    def set_height(self, height: int):
        if self._panel is None:
            return
        h = max(0, int(height))
        self._panel.setMinimumHeight(h)
        self._panel.setMaximumHeight(h)

    def _on_finished(self):
        if self._pending_callback is not None:
            cb = self._pending_callback
            self._pending_callback = None
            cb()

    def _cleanup(self):
        if self._group is not None:
            if self._group.state() == QAbstractAnimation.Running:
                self._group.stop()
            self._group.deleteLater()
            self._group = None
        self._min_anim = None
        self._max_anim = None
        self._panel = None
        self._pending_callback = None


def _calc_start_rect(final_rect: QRect, direction: PopupDirection, offset_px: int) -> QRect:
    start_rect = QRect(final_rect)
    if direction == "right":
        start_rect.moveLeft(final_rect.x() - offset_px)
    elif direction == "up":
        start_rect.moveTop(final_rect.y() + offset_px)
    elif direction == "down":
        start_rect.moveTop(final_rect.y() - offset_px)
    else:
        raise ValueError(f"Unsupported direction: {direction}")
    return start_rect


def animate_popup_show(
    widget,
    final_rect: QRect,
    duration_ms: int,
    direction: PopupDirection,
    offset_px: int = 50,
    with_fade: bool = False,
):
    old_group = getattr(widget, "_popup_anim_group", None)
    if old_group:
        if old_group.state() == QAbstractAnimation.Running:
            old_group.stop()
        old_group.deleteLater()
        widget._popup_anim_group = None

    start_rect = _calc_start_rect(final_rect, direction, offset_px)
    widget.setGeometry(start_rect)

    if with_fade:
        widget.setWindowOpacity(0.0)
    widget.show()

    geo_anim = QPropertyAnimation(widget, b"geometry", widget)
    geo_anim.setDuration(duration_ms)
    geo_anim.setStartValue(start_rect)
    geo_anim.setEndValue(final_rect)
    geo_anim.setEasingCurve(QEasingCurve.Linear)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(geo_anim)

    if with_fade:
        fade_anim = QPropertyAnimation(widget, b"windowOpacity", widget)
        fade_anim.setDuration(duration_ms)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.Linear)
        group.addAnimation(fade_anim)

    widget._popup_anim_group = group

    def _on_finished():
        if getattr(widget, "_popup_anim_group", None) is group:
            widget._popup_anim_group = None
        group.deleteLater()

    group.finished.connect(_on_finished)
    group.start()
