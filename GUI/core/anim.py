from dataclasses import dataclass
from typing import Callable, Literal, Optional, Sequence

from PyQt5.QtCore import (
    QObject, QAbstractAnimation, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup, QSequentialAnimationGroup, QRect, QPoint,
    pyqtProperty,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect

from GUI.core.timer import safe_single_shot


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
            widget.destroyed.connect(self.cleanup)

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

    def cleanup(self):
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
        proxy.destroyed.connect(self.cleanup)

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
        if self._anim is not None:
            if self._anim.state() == QAbstractAnimation.Running:
                self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        self._proxy = None


class WindowHeightAnimator(QObject):
    def __init__(self, window, duration_ms: int = 250, easing=QEasingCurve.OutCubic):
        super().__init__(window)
        self._window = window
        self._duration_ms = duration_ms
        self._easing = easing
        window.destroyed.connect(self.cleanup)

    @pyqtProperty(int)
    def animatedHeight(self):
        return 0 if self._window is None else int(self._window.height())

    @animatedHeight.setter
    def animatedHeight(self, value):
        if self._window is None:
            return
        h = max(0, int(value))
        if h != self._window.height():
            self._window.resize(self._window.width(), h)

    def build_anim(self, start_h: int, target_h: int) -> QPropertyAnimation:
        anim = QPropertyAnimation(self, b"animatedHeight")
        anim.setDuration(self._duration_ms)
        anim.setEasingCurve(self._easing)
        anim.setStartValue(max(0, int(start_h)))
        anim.setEndValue(max(0, int(target_h)))
        return anim

    def cleanup(self):
        self._window = None


class PanelHeightAnimator(QObject):
    def __init__(self, panel, duration_ms: int = 250, easing=QEasingCurve.OutCubic):
        super().__init__(panel)
        self._panel = panel
        self._duration_ms = duration_ms
        self._easing = easing
        panel.destroyed.connect(self.cleanup)

    def create_group(self, start: int, target: int) -> Optional[QParallelAnimationGroup]:
        if self._panel is None:
            return None
        s, t = max(0, int(start)), max(0, int(target))
        self._panel.setMinimumHeight(s)
        self._panel.setMaximumHeight(s)
        group = QParallelAnimationGroup()
        for prop in (b"minimumHeight", b"maximumHeight"):
            anim = QPropertyAnimation(self._panel, prop)
            anim.setDuration(self._duration_ms)
            anim.setEasingCurve(self._easing)
            anim.setStartValue(s)
            anim.setEndValue(t)
            group.addAnimation(anim)
        return group

    def set_height(self, height: int):
        if self._panel is None:
            return
        h = max(0, int(height))
        self._panel.setMinimumHeight(h)
        self._panel.setMaximumHeight(h)

    def cleanup(self):
        self._panel = None


@dataclass(frozen=True)
class ContentTarget:
    widget: object
    measure_height: Optional[Callable[[object], int]] = None
    duration_weight: float = 1.0


class ContentAnimationController:
    def __init__(self, content_targets: Optional[Sequence[object]], duration_ms: int, easing):
        self._targets = [self._normalize_target(target) for target in (content_targets or []) if target is not None]
        total_weight = sum(max(0.0, target.duration_weight) for target in self._targets) or 1.0
        self._panel_animators = {
            target.widget: PanelHeightAnimator(
                target.widget,
                duration_ms=self._duration_for_target(target, duration_ms, total_weight),
                easing=easing,
            )
            for target in self._targets
        }

    @staticmethod
    def _normalize_target(target) -> ContentTarget:
        if isinstance(target, ContentTarget):
            return target
        return ContentTarget(widget=target)

    def _duration_for_target(self, target: ContentTarget, total_duration_ms: int, total_weight: float) -> int:
        if len(self._targets) <= 1:
            return total_duration_ms
        weight = max(0.0, target.duration_weight)
        return max(16, int(total_duration_ms * weight / total_weight))

    @staticmethod
    def _widget_height(widget) -> int:
        if widget is None:
            return 0
        max_h = int(widget.maximumHeight()) if hasattr(widget, "maximumHeight") else 0
        if max_h and max_h < 16777215:
            return max(0, max_h)
        if hasattr(widget, "height"):
            return max(0, int(widget.height()))
        return 0

    def _expand_height(self, target: ContentTarget) -> int:
        if target.measure_height is not None:
            return max(0, int(target.measure_height(target.widget)))
        if hasattr(target.widget, "sizeHint"):
            return max(0, int(target.widget.sizeHint().height()))
        return self._widget_height(target.widget)

    def total_expand_delta(self) -> int:
        return sum(
            max(0, self._expand_height(target) - self._widget_height(target.widget))
            for target in self._targets
        )

    def build_sequence(self, collapse: bool) -> Optional[QSequentialAnimationGroup]:
        targets = list(reversed(self._targets)) if collapse else list(self._targets)
        if not collapse:
            for target in targets:
                target.widget.setVisible(True)

        sequence = QSequentialAnimationGroup()
        for target in targets:
            animator = self._panel_animators.get(target.widget)
            if animator is None:
                continue

            start_height = self._widget_height(target.widget)
            target_height = 0 if collapse else self._expand_height(target)
            if start_height == target_height:
                animator.set_height(target_height)
                if collapse:
                    target.widget.setVisible(False)
                continue

            group = animator.create_group(start_height, target_height)
            if group is None:
                continue
            if collapse:
                widget = target.widget
                group.finished.connect(lambda widget_=widget: widget_.setVisible(False))
            sequence.addAnimation(group)

        return sequence if sequence.animationCount() > 0 else None

    def set_height(self, target_widget, height: int):
        animator = self._panel_animators.get(target_widget)
        if animator is not None:
            animator.set_height(height)

    def cleanup(self):
        for animator in self._panel_animators.values():
            animator.cleanup()
        self._panel_animators.clear()
        self._targets = []


class ExpandCollapseOrchestrator(QObject):
    def __init__(
        self,
        *,
        window_target=None,
        content_targets: Optional[Sequence[object]] = None,
        duration_ms: int = 250,
        easing=QEasingCurve.OutCubic,
        window_target_height_getter: Optional[Callable[[int], int]] = None,
        can_expand_window: Optional[Callable[[int], bool]] = None,
        before_expand: Optional[Callable[[], None]] = None,
        after_expand: Optional[Callable[[], None]] = None,
        before_collapse: Optional[Callable[[], None]] = None,
        after_collapse: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        owner = parent or window_target
        super().__init__(owner)
        self._window_target = window_target
        self._window_target_height_getter = window_target_height_getter
        self._can_expand_window = can_expand_window
        self._before_expand = before_expand
        self._after_expand = after_expand
        self._before_collapse = before_collapse
        self._after_collapse = after_collapse
        self._window_anim = WindowHeightAnimator(window_target, duration_ms, easing) if window_target is not None else None
        self._window_restore_height: Optional[int] = None
        self._content_controller = ContentAnimationController(content_targets, duration_ms, easing)
        self._anim_group: Optional[QParallelAnimationGroup] = None
        if owner is not None:
            owner.destroyed.connect(self.cleanup)

    @property
    def is_transitioning(self) -> bool:
        return self._anim_group is not None and self._anim_group.state() == QAbstractAnimation.Running

    def _resolve_window_target(self, total_expand_delta: int) -> int:
        if self._window_target_height_getter is not None:
            return max(0, int(self._window_target_height_getter(total_expand_delta)))
        if self._window_target is None:
            return 0
        return max(0, int(self._window_target.height() + total_expand_delta))

    def _can_window_expand(self, total_expand_delta: int) -> bool:
        if total_expand_delta <= 0:
            return False
        if self._can_expand_window is None:
            return True
        return bool(self._can_expand_window(total_expand_delta))

    def expand(self, on_finished=None) -> bool:
        if self.is_transitioning:
            return False
        if self._before_expand is not None:
            self._before_expand()
        top = QParallelAnimationGroup(self)
        seq = self._content_controller.build_sequence(collapse=False)
        if seq is not None:
            top.addAnimation(seq)
        total_delta = self._content_controller.total_expand_delta()
        if self._window_anim is not None and self._can_window_expand(total_delta):
            current_h = self._window_target.height()
            if self._window_restore_height is None:
                self._window_restore_height = current_h
            target_h = self._resolve_window_target(total_delta)
            if target_h > current_h:
                top.addAnimation(self._window_anim.build_anim(current_h, target_h))

        def _done():
            grp = self._anim_group
            self._anim_group = None
            if self._after_expand is not None:
                self._after_expand()
            if on_finished is not None:
                on_finished()
            if grp is not None:
                grp.deleteLater()

        top.finished.connect(_done)
        self._anim_group = top
        top.start()
        return True

    def collapse(self, on_finished=None) -> bool:
        if self.is_transitioning:
            return False
        if self._before_collapse is not None:
            self._before_collapse()
        top = QParallelAnimationGroup(self)
        seq = self._content_controller.build_sequence(collapse=True)
        if seq is not None:
            top.addAnimation(seq)
        if self._window_anim is not None and self._window_restore_height is not None:
            current_h = self._window_target.height()
            restore_h = self._window_restore_height
            if current_h > restore_h:
                top.addAnimation(self._window_anim.build_anim(current_h, restore_h))
            else:
                self._window_restore_height = None

        def _done():
            grp = self._anim_group
            self._anim_group = None
            self._window_restore_height = None
            if self._after_collapse is not None:
                self._after_collapse()
            if on_finished is not None:
                on_finished()
            if grp is not None:
                grp.deleteLater()

        top.finished.connect(_done)
        self._anim_group = top
        top.start()
        return True

    def set_content_height(self, target_widget, height: int):
        self._content_controller.set_height(target_widget, height)

    def stop(self):
        if self._anim_group is not None:
            self._anim_group.stop()
            self._anim_group.deleteLater()
            self._anim_group = None
        self._window_restore_height = None

    def cleanup(self):
        self.stop()
        if self._window_anim is not None:
            self._window_anim.cleanup()
            self._window_anim = None
        self._content_controller.cleanup()
        self._window_restore_height = None
        self._before_expand = None
        self._after_expand = None
        self._before_collapse = None
        self._after_collapse = None


class PopupAnimator:
    @staticmethod
    def _calc_start_pos(final_rect: QRect, direction: PopupDirection, offset_px: int) -> QPoint:
        x, y = final_rect.x(), final_rect.y()
        if direction == "right":
            x -= offset_px
        elif direction == "up":
            y += offset_px
        elif direction == "down":
            y -= offset_px
        else:
            raise ValueError(f"Unsupported direction: {direction}")
        return QPoint(x, y)

    @staticmethod
    def show(
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

        start_pos = PopupAnimator._calc_start_pos(final_rect, direction, offset_px)
        widget.resize(final_rect.size())
        widget.move(start_pos)
        widget.setWindowOpacity(0.0)
        widget.show()

        pos_anim = QPropertyAnimation(widget, b"pos", widget)
        pos_anim.setDuration(duration_ms)
        pos_anim.setStartValue(start_pos)
        pos_anim.setEndValue(final_rect.topLeft())
        pos_anim.setEasingCurve(QEasingCurve.Linear)

        group = QParallelAnimationGroup(widget)
        group.addAnimation(pos_anim)

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

        def _start_anim():
            if getattr(widget, "_popup_anim_group", None) is not group:
                return
            if not with_fade:
                widget.setWindowOpacity(1.0)
            group.start()

        safe_single_shot(0, _start_anim)
