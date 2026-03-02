from typing import Literal

from PyQt5.QtCore import (
    QAbstractAnimation,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QRect,
)


PopupDirection = Literal["right", "up", "down"]


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
