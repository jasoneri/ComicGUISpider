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
