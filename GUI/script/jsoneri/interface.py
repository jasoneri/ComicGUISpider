from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, QSize, Qt, QTimer, Property, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsBlurEffect, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    FluentIcon as FIF, IndeterminateProgressBar, InfoBar, InfoBarPosition, LineEdit,
    PrimaryToolButton, TeachingTipTailPosition, ToolButton,
)

from GUI.uic.qfluent.components import CustomTeachingTip
from GUI.uic.qfluent.components.icons import CgsIcon
from utils.script import conf as script_conf
from variables import JSONERI_PALACES_PROBE_API_URL

from .browser import JsoneriServicesStatusBrowserController
from .client import JsoneriPalacesProbeApiClient
from .dashboard import CARD_COLORS, DashboardViewModel, JsoneriPalacesDashboardStore, ServiceViewModel
from .models import ServiceCardState
from .preview_cache import JsoneriPreviewCache, load_preview_pixmap
from .style import (
    build_checking_layer_stylesheet,
    build_connection_dot_stylesheet,
    build_interface_stylesheet,
    build_site_preview_shell_stylesheet,
)


CARD_MIN_WIDTH = 280
CARD_HEIGHT = 280
CHECKING_REVEAL_MS = 500
INVALID_GLITCH_MS = 2000
SUCCESS_BADGE_MS = 2000
SUCCESS_PULSE_MS = 2500
# Site screenshot fills cardContent as backdrop; gateBtn stays foreground.
SITE_PREVIEW_OPACITY = 0.75
CARD_LAYOUT_MARGINS = (14, 12, 14, 14)
CARD_LAYOUT_SPACING = 10

# Mirrors figma-design Dashboard.tsx glitch-anim keyframes (clip-path + shimmy).
# Each entry: (phase_start, phase_end, y0_frac, y1_frac, dx_px). Empty clips use y1<=y0.
_GLITCH_KEYFRAMES: tuple[tuple[float, float, float, float, int], ...] = (
    (0.00, 0.02, 0.02, 0.95, 0),
    (0.02, 0.06, 0.78, 1.00, -4),
    (0.06, 0.08, 0.78, 1.00, 4),
    (0.08, 0.09, 0.78, 1.00, 0),
    (0.09, 0.10, 0.78, 1.00, 0),
    (0.10, 0.13, 0.44, 0.54, 4),
    (0.13, 0.14, 0.44, 0.54, 0),
    (0.14, 0.21, 0.00, 0.00, 4),
    (0.21, 0.25, 0.00, 0.00, 4),
    (0.25, 0.30, 0.00, 0.00, 4),
    (0.30, 0.31, 0.00, 0.00, -4),
    (0.31, 0.35, 0.00, 0.00, 0),
    (0.35, 0.40, 0.40, 0.85, -4),
    (0.40, 0.45, 0.40, 0.85, 4),
    (0.45, 0.50, 0.40, 0.85, -4),
    (0.50, 0.55, 0.40, 0.85, 0),
    (0.55, 0.60, 0.63, 0.80, 4),
    (0.60, 0.61, 0.63, 0.80, 0),
    (0.61, 1.00, 0.00, 0.00, 0),
)


def _glitch_sample(phase: float) -> tuple[float, float, int]:
    """Return (y0_frac, y1_frac, dx_px) for a 0..1 glitch animation phase."""
    progress = phase % 1.0
    for start, end, y0, y1, dx in _GLITCH_KEYFRAMES:
        if start <= progress < end or (end >= 1.0 and progress >= start):
            return y0, y1, dx
    return 0.0, 0.0, 0

_JSONERI_SERVICE_ICONS = {
    "raw-image": CgsIcon.JSONERI_STATION_IMAGE,
    "image": CgsIcon.JSONERI_STATION_IMAGE,
    "music": CgsIcon.JSONERI_STATION_MUSIC,
    "intermediary": CgsIcon.JSONERI_STATION_ACTIVITY,
    "activity": CgsIcon.JSONERI_STATION_ACTIVITY,
    "ai-tools": CgsIcon.JSONERI_STATION_BOT,
    "bot": CgsIcon.JSONERI_STATION_BOT,
}


def jsoneri_service_icon(icon_token: str) -> CgsIcon:
    token = str(icon_token or "").strip().casefold().replace("_", "-")
    return _JSONERI_SERVICE_ICONS.get(token, CgsIcon.SCRIPT_API)


class JsoneriStatusPill(QWidget):
    def __init__(self, state: ServiceCardState, parent=None):
        super().__init__(parent)
        self.state = state
        self._glitch_phase = 0.0
        self.setObjectName("JsoneriStatusPill")
        self.setProperty("cardState", state.value)
        self.setProperty("glitchEnabled", state == ServiceCardState.INVALID)
        self.setProperty("availableBadge", state == ServiceCardState.SUCCESS)
        if state == ServiceCardState.SUCCESS:
            self.setFixedSize(28, 24)
        else:
            self.setFixedSize(24, 8)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._animation = QPropertyAnimation(self, b"glitchPhase", self)
        if state == ServiceCardState.INVALID:
            self._animation.setDuration(INVALID_GLITCH_MS)
            self._animation.setLoopCount(-1)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        elif state == ServiceCardState.SUCCESS:
            self._animation.setDuration(SUCCESS_BADGE_MS)
            self._animation.setLoopCount(-1)
            self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.state == ServiceCardState.SUCCESS:
            self._paint_available_badge(painter)
            return
        color = QColor(CARD_COLORS[self.state])
        rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 4, 4)
        if self.state != ServiceCardState.INVALID:
            return
        # CodePen / figma glitch-layer: clipped red twin + horizontal shimmy.
        y0, y1, dx = _glitch_sample(self._glitch_phase)
        if y1 <= y0:
            return
        band = QRect(rect.x(), int(rect.height() * y0), rect.width(), max(1, int(rect.height() * (y1 - y0))))
        painter.save()
        painter.setClipRect(band)
        twin = QColor("#ff6b6b")
        twin.setAlpha(220)
        painter.setBrush(twin)
        painter.drawRoundedRect(rect.translated(dx, 0), 4, 4)
        painter.restore()

    def _paint_available_badge(self, painter: QPainter) -> None:
        phase = self._glitch_phase % 1.0
        pulse = 1.0 - abs(2.0 * phase - 1.0)
        center = self.rect().center()
        green = QColor(CARD_COLORS[ServiceCardState.SUCCESS])

        outline = QColor(green)
        outline.setAlpha(int(130 * (1.0 - phase)))
        painter.setPen(QPen(outline, max(1, int(5 * (1.0 - phase)))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, int(6 + 8 * phase), int(6 + 8 * phase))

        ring = QColor(green)
        ring.setAlpha(int(255 - 95 * pulse))
        painter.setPen(QPen(ring, 2))
        painter.drawEllipse(center, int(8 + 4 * pulse), int(8 + 4 * pulse))

        dot = QColor(green)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot)
        dot_radius = max(1, int(4 * (1.0 - pulse)))
        painter.drawEllipse(center, dot_radius, dot_radius)

    def getGlitchPhase(self) -> float:
        return self._glitch_phase

    def setGlitchPhase(self, value: float) -> None:
        self._glitch_phase = value
        self.update()

    glitchPhase = Property(float, getGlitchPhase, setGlitchPhase)


class JsoneriGateButton(QAbstractButton):
    def __init__(
        self, icon: CgsIcon, color: str, *, role: str, pulse: bool = False, glitch: bool = False, icon_size: int = 56, parent=None,
    ):
        super().__init__(parent)
        self._icon = icon
        self._color = color
        self._icon_size = icon_size
        self._pulse = 0.0
        self._glitch_phase = 0.0
        self._pulse_enabled = pulse
        self._glitch_enabled = glitch
        self.setObjectName(f"JsoneriGateButton_{role}")
        self.setProperty("gateRole", role)
        self.setProperty("pulseEnabled", pulse)
        self.setProperty("glitchEnabled", glitch)
        self.setFixedSize(76, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pulse_animation = QPropertyAnimation(self, b"pulse", self)
        if pulse:
            self._pulse_animation.setDuration(SUCCESS_PULSE_MS)
            self._pulse_animation.setLoopCount(-1)
            self._pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._pulse_animation.setKeyValueAt(0.0, 0.0)
            self._pulse_animation.setKeyValueAt(0.5, 1.0)
            self._pulse_animation.setKeyValueAt(1.0, 0.0)
            self._pulse_animation.start()
        self._glitch_animation = QPropertyAnimation(self, b"glitchPhase", self)
        if glitch:
            self._glitch_animation.setDuration(INVALID_GLITCH_MS)
            self._glitch_animation.setLoopCount(-1)
            self._glitch_animation.setStartValue(0.0)
            self._glitch_animation.setEndValue(1.0)
            self._glitch_animation.start()

    def sizeHint(self) -> QSize:
        return QSize(76, 76)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() and self.isEnabled():
            hover = QColor(self._color)
            hover.setAlpha(20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover)
            painter.drawRoundedRect(self.rect().adjusted(4, 4, -4, -4), 8, 8)
        icon_rect = self._icon_rect()
        # figma healthy expandBtn: scale + opacity breath only — no radar rings.
        base_opacity = 0.8 + 0.2 * self._pulse if self._pulse_enabled else 1.0
        if self._glitch_enabled:
            self._paint_glitch_layers(painter, icon_rect)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            self._draw_icon(painter, icon_rect.translated(dx, dy), "#ffffff", opacity=0.95 * base_opacity)
        self._draw_icon(painter, icon_rect, self._color, opacity=base_opacity)

    def _paint_glitch_layers(self, painter: QPainter, icon_rect: QRect) -> None:
        # figma .glitch-layer: continuous clip-path band + red chromatic offset.
        y0, y1, dx = _glitch_sample(self._glitch_phase)
        if y1 <= y0:
            return
        clip_y = icon_rect.y() + int(icon_rect.height() * y0)
        clip_h = max(2, int(icon_rect.height() * (y1 - y0)))
        clip = QRect(icon_rect.x() - 8, clip_y, icon_rect.width() + 16, clip_h)
        painter.save()
        painter.setClipRect(clip)
        # drop-shadow(2px 0 rgba(255,50,50,0.8)) approximated as red twin + base.
        self._draw_icon(painter, icon_rect.translated(dx + 2, 0), "#ff3232", opacity=0.85)
        self._draw_icon(painter, icon_rect.translated(dx, 0), "#ff6b6b", opacity=0.95)
        painter.restore()

    def _icon_rect(self) -> QRect:
        size = self._icon_size
        if self._pulse_enabled:
            # framer-motion scale [1, 1.15, 1]
            size = int(size * (1.0 + 0.15 * self._pulse))
        rect = QRect(0, 0, size, size)
        rect.moveCenter(self.rect().center())
        return rect

    def _draw_icon(self, painter: QPainter, rect: QRect, color: str, *, opacity: float = 1.0) -> None:
        painter.save()
        painter.setOpacity(opacity)
        pixmap = self._icon.icon(color=QColor(color)).pixmap(rect.size())
        painter.drawPixmap(rect, pixmap)
        painter.restore()

    def getPulse(self) -> float:
        return self._pulse

    def setPulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    def getGlitchPhase(self) -> float:
        return self._glitch_phase

    def setGlitchPhase(self, value: float) -> None:
        self._glitch_phase = value
        self.update()

    pulse = Property(float, getPulse, setPulse)
    glitchPhase = Property(float, getGlitchPhase, setGlitchPhase)


class JsoneriCardWatermark(QWidget):
    def __init__(self, icon: CgsIcon, color: str, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.color = color
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = max(96, min(160, int(min(self.width(), self.height()) * 0.72)))
        rect = QRect(0, 0, size, size)
        rect.moveCenter(self.rect().center())
        painter.setOpacity(0.08)
        pixmap = self.icon.icon(color=QColor(self.color)).pixmap(rect.size())
        painter.drawPixmap(rect, pixmap)


class JsoneriCardSitePreview(QWidget):
    """Full cardContent backdrop: site screenshot centered-crop, opacity 75%."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._source = pixmap
        self.setObjectName("JsoneriCardSitePreview")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def paintEvent(self, _event) -> None:
        if self._source is None or self._source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(SITE_PREVIEW_OPACITY)
        scaled = self._source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Center crop — gateBtn is the foreground; screenshot is pure backdrop fill.
        draw_x = (self.width() - scaled.width()) // 2
        draw_y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(draw_x, draw_y, scaled)


class JsoneriCheckingLayer(QFrame):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("JsoneriCheckingLayer")
        self.setProperty("anchor", "cardContent")
        self._color = color
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.setDuration(CHECKING_REVEAL_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(0)
        layout.addStretch(1)
        self.progress_track = QFrame(self)
        self.progress_track.setObjectName("JsoneriCheckingProgressTrack")
        track_layout = QVBoxLayout(self.progress_track)
        track_layout.setContentsMargins(0, 3, 0, 3)
        track_layout.setSpacing(0)
        self.progress_bar = IndeterminateProgressBar(self.progress_track, start=False)
        self.progress_bar.setCustomBarColor(self._color, self._color)
        self.progress_bar.setFixedHeight(6)
        track_layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_track)
        layout.addStretch(1)
        self.setStyleSheet(build_checking_layer_stylesheet(self._color))
        self.hide()

    def show_reveal(self, full_rect: QRect, *, animated: bool) -> None:
        self.raise_()
        self.show()
        self.progress_bar.start()
        if not animated:
            self.setGeometry(full_rect)
            return
        start_rect = QRect(full_rect.x(), full_rect.y(), 0, full_rect.height())
        self.setGeometry(start_rect)
        self._animation.stop()
        self._animation.setStartValue(start_rect)
        self._animation.setEndValue(full_rect)
        self._animation.start()

    def hideEvent(self, event) -> None:
        if self.progress_bar.isStarted():
            self.progress_bar.stop()
        super().hideEvent(event)


class JsoneriServiceCard(QFrame):
    check_requested = Signal(str)
    open_requested = Signal(str)

    def __init__(
        self,
        service: ServiceViewModel,
        *,
        checking: bool = False,
        animate_checking: bool = False,
        preview_pixmap: QPixmap | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.service = service
        self._preview_pixmap = preview_pixmap
        self.setObjectName("JsoneriServiceCard")
        self.setProperty("cardState", service.card_state.value)
        self.setMinimumSize(CARD_MIN_WIDTH, CARD_HEIGHT)
        self.setFixedHeight(CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.service_icon = jsoneri_service_icon(service.icon)
        self.site_preview: JsoneriCardSitePreview | None = None
        self._setup_ui()
        if checking:
            QTimer.singleShot(0, lambda: self.show_checking(animated=animate_checking))

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("JsoneriServiceCardHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(10)
        icon = QLabel(header)
        icon.setObjectName("JsoneriServiceCardIcon")
        icon.setFixedSize(20, 20)
        icon.setPixmap(self.service_icon.icon(color=QColor("#737373")).pixmap(QSize(18, 18)))
        title = QLabel(self.service.label, header)
        title.setObjectName("JsoneriServiceCardTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        pill = JsoneriStatusPill(self.service.card_state, header)
        header_layout.addWidget(icon)
        header_layout.addWidget(title, 1)
        header_layout.addWidget(pill)
        root.addWidget(header)

        self.content = QFrame(self)
        self.content.setObjectName("JsoneriServiceCardContent")
        self.content.installEventFilter(self)
        self.background = QFrame(self.content)
        self.background.setObjectName("JsoneriCardBackground")
        background_layout = QVBoxLayout(self.background)
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.setSpacing(0)
        has_site_preview = self._preview_pixmap is not None and not self._preview_pixmap.isNull()
        if has_site_preview:
            # Absolute full-content fill; geometry synced in _sync_content_layers.
            # Transparent shell so the 75% screenshot is the actual backdrop, not washed by card gray.
            self.content.setStyleSheet(build_site_preview_shell_stylesheet())
            self.site_preview = JsoneriCardSitePreview(self._preview_pixmap, self.background)
            self.site_preview.show()
            self.site_preview.lower()
        else:
            background_layout.addWidget(JsoneriCardWatermark(self.service_icon, self.service.color, self.background))
        if self.service.card_state in {ServiceCardState.NORMAL, ServiceCardState.INVALID, ServiceCardState.PLACEHOLDER}:
            blur = QGraphicsBlurEffect(self.background)
            blur.setBlurRadius(8 if self.service.card_state != ServiceCardState.PLACEHOLDER else 12)
            self.background.setGraphicsEffect(blur)
        self.frost = QFrame(self.content)
        self.frost.setObjectName(f"JsoneriFrost_{self.service.card_state.value}")
        self.frost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.frost.setVisible(self.service.card_state in {ServiceCardState.NORMAL, ServiceCardState.INVALID, ServiceCardState.PLACEHOLDER})
        self.action_layer = QFrame(self.content)
        self.action_layer.setObjectName("JsoneriCardActionLayer")
        action_layout = QVBoxLayout(self.action_layer)
        action_layout.setContentsMargins(18, 14, 18, 14)
        action_layout.setSpacing(6)
        action_layout.addStretch(1)
        self._add_gate(action_layout)
        action_layout.addStretch(1)
        self.checking_layer = JsoneriCheckingLayer(self.service.color, self.content)
        root.addWidget(self.content, 1)

    def _add_gate(self, layout: QVBoxLayout) -> None:
        state = self.service.card_state
        if state == ServiceCardState.NORMAL:
            button = JsoneriGateButton(CgsIcon.JSONERI_CHECK, "#a3a3a3", role="checkBtn", parent=self.action_layer)
            button.setToolTip("Check")
            button.clicked.connect(lambda: self.check_requested.emit(self.service.name))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            return
        if state == ServiceCardState.INVALID:
            button = JsoneriGateButton(CgsIcon.JSONERI_RECHECK, "#ef4444", role="reCheckBtn", glitch=True, parent=self.action_layer)
            button.setToolTip("Recheck")
            button.clicked.connect(lambda: self.check_requested.emit(self.service.name))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self._add_response_text(layout)
            return
        if state == ServiceCardState.SUCCESS:
            button = JsoneriGateButton(
                CgsIcon.JSONERI_EXPAND, "#178d00", role="expandBtn", pulse=True, icon_size=62, parent=self.action_layer
            )
            button.setToolTip("Open")
            button.clicked.connect(lambda: self.open_requested.emit(self.service.name))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            return
        placeholder_gate = JsoneriGateButton(CgsIcon.JSONERI_LOCK, "#737373", role="lockPlaceholder", parent=self.action_layer)
        placeholder_gate.setProperty("placeholderOnly", True)
        placeholder_gate.setCursor(Qt.CursorShape.ArrowCursor)
        placeholder_gate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        placeholder_gate.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(placeholder_gate, 0, Qt.AlignmentFlag.AlignHCenter)
        self._add_response_text(layout)

    def _add_response_text(self, layout: QVBoxLayout) -> None:
        if self.service.response_message:
            message = QLabel(self.service.response_message, self.action_layer)
            message.setObjectName("JsoneriCardResponseMessage")
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            message.setWordWrap(True)
            layout.addWidget(message)
        if self.service.response_detail:
            detail = QLabel(self.service.response_detail, self.action_layer)
            detail.setObjectName("JsoneriCardResponseDetail")
            detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            detail.setWordWrap(True)
            layout.addWidget(detail)

    def show_checking(self, *, animated: bool) -> None:
        self._sync_content_layers()
        self.checking_layer.show_reveal(self.content.rect(), animated=animated)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.content and event.type() == QEvent.Type.Resize:
            self._sync_content_layers()
        return super().eventFilter(obj, event)

    def _sync_content_layers(self) -> None:
        rect = self.content.rect()
        self.background.setGeometry(rect)
        self.frost.setGeometry(rect)
        self.action_layer.setGeometry(rect)
        if self.site_preview is not None:
            # Full cardContent backdrop under gateBtn (not a bottom strip).
            self.site_preview.setGeometry(self.background.rect())
            self.site_preview.lower()
        if self.checking_layer.isVisible():
            self.checking_layer.setGeometry(rect)


class JsoneriPalacesProbeInterface(QFrame):
    info_bar_orient = Qt.Orientation.Horizontal

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("JsoneriPalacesProbeInterface")
        self.store = JsoneriPalacesDashboardStore()
        self.client = JsoneriPalacesProbeApiClient(parent=self)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(30_000)
        self.poll_timer.timeout.connect(self.refresh_status)
        self._token_tip = None
        self._cards: dict[str, JsoneriServiceCard] = {}
        self._checking_service_names: set[str] = set()
        self._checking_animate_once: set[str] = set()
        self._last_column_count = 0
        self._render_pending = False
        self._ui_ready = False
        self.preview_cache = JsoneriPreviewCache()
        self._setup_ui()
        self.browser_controller = JsoneriServicesStatusBrowserController(
            self, self.client, preview_cache=self.preview_cache,
        )
        self._connect_runtime()
        self.refresh_config(fetch=False)

    def refresh_config(self, *, fetch: bool = True) -> None:
        config = script_conf.jsoneriPalacesProbe or {}
        token = str(config.get("token") or "")
        self.client.configure(base_url=JSONERI_PALACES_PROBE_API_URL, token=token)
        self.store.set_configured(self.client.is_configured)
        if self.client.is_configured:
            if self.isVisible() and not self.poll_timer.isActive():
                self.poll_timer.start()
            if fetch:
                self.refresh_status()
            else:
                self._render()
            return
        self.poll_timer.stop()
        self._render()

    def save_token(self, token: str) -> None:
        token = str(token or "").strip()
        script_conf.update(jsoneriPalacesProbe={"token": token})
        self.refresh_config(fetch=True)
        InfoBar.success(
            title="", content="jsoneriPalacesProbe token saved", orient=self.info_bar_orient, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=2500, parent=self,
        )

    def refresh_status(self) -> None:
        if not self.client.is_configured:
            self.refresh_config(fetch=False)
            return
        if self.client.status_in_flight:
            self._render()
            return
        generation = self.store.begin_poll()
        self._render()
        self.client.fetch_status(generation)

    def close_service_window(self) -> None:
        self.browser_controller.close_window()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.client.is_configured:
            self.refresh_status()
            self.poll_timer.start()

    def hideEvent(self, event) -> None:
        self.poll_timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._ui_ready and self._grid_columns() != self._last_column_count and not self._render_pending:
            self._render_pending = True
            QTimer.singleShot(0, self._render)

    def _setup_ui(self) -> None:
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(*CARD_LAYOUT_MARGINS)
        self.root_layout.setSpacing(CARD_LAYOUT_SPACING)

        self.header = QFrame(self)
        self.header.setObjectName("JsoneriPalacesProbeHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)
        self.title_label = QLabel("jsoneriPalaces", self.header)
        self.title_label.setObjectName("JsoneriPalacesTitle")
        self.connection_dot = QLabel(self.header)
        self.connection_dot.setObjectName("JsoneriPalacesConnectionDot")
        self.connection_dot.setFixedSize(10, 10)
        self.connection_label = QLabel("", self.header)
        self.config_button = ToolButton(FIF.SETTING, self.header)
        self.config_button.setToolTip("Configure jsoneriPalacesProbe token")
        self.config_button.clicked.connect(self._show_token_tip)
        self.refresh_button = ToolButton(FIF.SYNC, self.header)
        self.refresh_button.setToolTip("Refresh status")
        self.refresh_button.clicked.connect(self.refresh_status)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.connection_dot)
        header_layout.addWidget(self.connection_label)
        header_layout.addWidget(self.config_button)
        header_layout.addWidget(self.refresh_button)
        self.root_layout.addWidget(self.header)

        self.card_surface = QFrame(self)
        self.card_surface.setObjectName("JsoneriPalacesCardSurface")
        card_surface_layout = QVBoxLayout(self.card_surface)
        card_surface_layout.setContentsMargins(0, 0, 0, 0)
        card_surface_layout.setSpacing(8)
        self.state_message_label = QLabel("", self.card_surface)
        self.state_message_label.setObjectName("JsoneriPalacesStateMessage")
        self.state_message_label.setWordWrap(True)
        self.state_message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_surface_layout.addWidget(self.state_message_label)
        self.card_scroll = QScrollArea(self.card_surface)
        self.card_scroll.setObjectName("JsoneriPalacesCardScroll")
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.card_grid_host = QWidget(self.card_scroll)
        self.card_grid_layout = QGridLayout(self.card_grid_host)
        self.card_grid_layout.setContentsMargins(2, 2, 10, 18)
        self.card_grid_layout.setHorizontalSpacing(16)
        self.card_grid_layout.setVerticalSpacing(16)
        self.card_scroll.setWidget(self.card_grid_host)
        card_surface_layout.addWidget(self.card_scroll, 1)
        self.root_layout.addWidget(self.card_surface, 1)
        self._ui_ready = True
        self.setStyleSheet(build_interface_stylesheet())

    def _connect_runtime(self) -> None:
        self.client.status_received.connect(self._on_status_received)
        self.client.status_unreachable.connect(self._on_status_unreachable)
        self.client.route_received.connect(self._on_route_received)
        self.client.route_failed.connect(self._on_route_failed)
        self.client.suspect_reported.connect(self._on_suspect_reported)
        self.client.suspect_failed.connect(self._on_suspect_failed)
        self.browser_controller.preview_captured.connect(self._on_preview_captured)

    def _show_token_tip(self) -> None:
        if self._token_tip is not None:
            self._token_tip.close()
        config = script_conf.jsoneriPalacesProbe or {}
        token_edit = LineEdit(self)
        token_edit.setMinimumWidth(240)
        token_edit.setPlaceholderText("suspect token")
        token_edit.setClearButtonEnabled(True)
        token_edit.setText(str(config.get("token") or ""))
        save_button = PrimaryToolButton(FIF.ACCEPT_MEDIUM, self)

        def apply_token() -> None:
            self.save_token(token_edit.text())
            tip.close()

        tip = CustomTeachingTip.create(
            [token_edit, save_button],
            target=self.config_button,
            parent=self,
            tailPosition=TeachingTipTailPosition.TOP_RIGHT,
        )
        self._token_tip = tip
        tip.destroyed.connect(lambda *_args: setattr(self, "_token_tip", None))
        token_edit.returnPressed.connect(apply_token)
        save_button.clicked.connect(apply_token)

    def _trigger_service_check(self, service_name: str) -> None:
        service = str(service_name or "").strip()
        if not service:
            raise ValueError("service_name must be a non-empty string.")
        self._checking_service_names.add(service)
        self._checking_animate_once.add(service)
        self.refresh_status()

    def _open_service(self, service_name: str) -> None:
        service = self._service_vm_by_name(service_name)
        if service.card_state != ServiceCardState.SUCCESS or not service.can_open:
            InfoBar.warning(
                title="", content=service.response_message, orient=self.info_bar_orient, isClosable=True,
                position=InfoBarPosition.BOTTOM, duration=3000, parent=self,
            )
            return
        self.store.select_service(service.name)
        self.store.begin_route(service.name)
        known_route_url = service.route_url or ""
        if known_route_url:
            self.store.route_received(service.name, known_route_url)
        # Prefer known route.url from status; otherwise BrowserController fetches /api/route.
        # Open via BrowserWindow (not in-card FramelessWebEngineView) — embedded expand crashed process.
        self.browser_controller.open_service(service.name, url=known_route_url or None)
        self._render()

    def _service_vm_by_name(self, service_name: str) -> ServiceViewModel:
        service = str(service_name or "").strip()
        for entry in self.store.view_model().services:
            if entry.name == service:
                return entry
        raise ValueError(f"Unknown Jsoneri service: {service}")

    def _on_status_received(self, generation: int, snapshot) -> None:
        self._checking_service_names.clear()
        self._checking_animate_once.clear()
        if self.store.accept_status(generation, snapshot):
            self._render()

    def _on_status_unreachable(self, generation: int, message: str) -> None:
        self._checking_service_names.clear()
        self._checking_animate_once.clear()
        if self.store.fail_status(generation, message):
            self._render()
        InfoBar.warning(
            title="", content=message, orient=self.info_bar_orient, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=3500, parent=self,
        )

    def _on_route_received(self, service_name: str, url: object) -> None:
        if self.store.route_received(service_name, url):
            self._render()

    def _on_route_failed(self, service_name: str, message: str) -> None:
        if self.store.route_failed(service_name, message):
            self._render()

    def _on_suspect_reported(self, service_name: str, url: str) -> None:
        if self.store.suspect_reported(service_name, url):
            self._render()
        InfoBar.warning(
            title="", content=f"Suspect instance reported: {service_name}", orient=self.info_bar_orient, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=3500, parent=self,
        )

    def _on_suspect_failed(self, service_name: str, url: str, message: str) -> None:
        if self.store.suspect_failed(service_name, url, message):
            self._render()
        InfoBar.error(
            title="", content=f"Suspect report failed: {message}", orient=self.info_bar_orient, isClosable=True,
            position=InfoBarPosition.BOTTOM, duration=5000, parent=self,
        )

    def _on_preview_captured(self, _service_name: str, _route_url: str) -> None:
        if self._ui_ready:
            self._render()

    def _preview_pixmap_for(self, service: ServiceViewModel) -> QPixmap | None:
        path = self.preview_cache.resolve(
            service.name,
            service.route_url,
            can_open=service.can_open,
            success=service.card_state == ServiceCardState.SUCCESS,
        )
        return load_preview_pixmap(path)

    def _render(self) -> None:
        self._render_pending = False
        view_model = self.store.view_model()
        self._render_header(view_model)
        self._render_cards(view_model)
        self.header.show()

    def _render_header(self, view_model: DashboardViewModel) -> None:
        self.connection_label.setText(view_model.connection_label)
        self.connection_dot.setStyleSheet(build_connection_dot_stylesheet(view_model.connection_color))
        self.refresh_button.setEnabled(view_model.configured)

    def _render_cards(self, view_model: DashboardViewModel) -> None:
        self._clear_cards()
        services = view_model.services
        self._checking_service_names.intersection_update({service.name for service in services})
        self.state_message_label.setVisible(bool(view_model.state_message))
        self.state_message_label.setText(view_model.state_message)
        columns = self._grid_columns()
        self._last_column_count = columns
        if not services:
            return
        for index, service in enumerate(services):
            animate = service.name in self._checking_animate_once
            checking = service.name in self._checking_service_names
            card = JsoneriServiceCard(
                service,
                checking=checking,
                animate_checking=animate,
                preview_pixmap=self._preview_pixmap_for(service),
                parent=self.card_grid_host,
            )
            card.check_requested.connect(self._trigger_service_check)
            card.open_requested.connect(self._open_service)
            row = index // columns
            column = index % columns
            self.card_grid_layout.addWidget(card, row, column)
            self.card_grid_layout.setColumnStretch(column, 1)
            self._cards[service.name] = card
        self._checking_animate_once.clear()

    def _clear_cards(self) -> None:
        self._cards.clear()
        while self.card_grid_layout.count():
            item = self.card_grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _grid_columns(self) -> int:
        if not self._ui_ready:
            width = self.width()
        else:
            width = max(self.card_scroll.viewport().width(), self.card_scroll.width(), self.card_surface.width(), self.width() - 28)
        if width < 620:
            return 1
        if width < 940:
            return 2
        return 3
