from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QPushButton, QSizePolicy, QStyle, QStyleOptionButton, QStylePainter, QToolButton, QVBoxLayout

from utils.script.image.danbooru.models import DanbooruPost

from .style import (
    DanbooruCardMetrics,
    DanbooruCardTheme,
    DanbooruUiPalette,
    DEFAULT_CARD_METRICS,
    build_card_stylesheet,
    get_danbooru_card_theme,
    get_danbooru_qss_tokens,
    qcolor_from_css,
)

_CARD_SELECTOR_SIZE = 26
_CARD_SELECTOR_IDLE_INNER_RATIO = 0.7
_CARD_SELECTOR_HOVER_INNER_RATIO = 0.55
_CARD_CONTENT_MARGIN = 4
_CARD_PREVIEW_BORDER_INSET = 1
_CARD_PREVIEW_RADIUS = 16.0


class _DanbooruCardSelectorButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._shadow_color = QtGui.QColor("#ffbeb8")
        self._inner_color = QtGui.QColor("#ffffff")
        self._gradient_start = QtGui.QColor("#acb1cb")
        self._gradient_mid = QtGui.QColor("#d1aacf")
        self._gradient_end = QtGui.QColor("#a99f8d")
        self._idle_opacity = 0.25
        self._disabled_opacity = 0.25
        self.setObjectName("DanbooruCardSelector")
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")
        self.setFixedSize(_CARD_SELECTOR_SIZE, _CARD_SELECTOR_SIZE)
        self.apply_theme()

    def apply_theme(self):
        tokens = get_danbooru_qss_tokens()
        self._gradient_start = qcolor_from_css(tokens["CARD_CHECKBOX_GRADIENT_START"])
        self._gradient_mid = qcolor_from_css(tokens["CARD_CHECKBOX_GRADIENT_MID"])
        self._gradient_end = qcolor_from_css(tokens["CARD_CHECKBOX_GRADIENT_END"])
        self._shadow_color = qcolor_from_css(tokens["CARD_CHECKBOX_SHADOW"])
        self._inner_color = qcolor_from_css(tokens["CARD_CHECKBOX_INNER"])
        self._idle_opacity = max(0.0, min(1.0, float(tokens["CARD_CHECKBOX_OPACITY"])))
        self._disabled_opacity = max(0.0, min(1.0, float(tokens["CARD_CHECKBOX_DISABLED_OPACITY"])))
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        _ = event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        opacity = self._disabled_opacity if not self.isEnabled() else (1.0 if self._hovered or self.hasFocus() else self._idle_opacity)
        painter.setOpacity(opacity)

        shadow_rect = QtCore.QRectF(1.0, 4.0, self.width() - 2.0, self.height() - 2.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._shadow_color)
        painter.drawEllipse(shadow_rect)

        circle_rect = QtCore.QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        gradient = QtGui.QLinearGradient(circle_rect.topLeft(), circle_rect.bottomRight())
        gradient.setColorAt(0.0, self._gradient_start)
        gradient.setColorAt(0.46, self._gradient_mid)
        gradient.setColorAt(1.0, self._gradient_end)
        painter.setBrush(QtGui.QBrush(gradient))
        painter.drawEllipse(circle_rect)

        inner_ratio = _CARD_SELECTOR_HOVER_INNER_RATIO if self._hovered and self.isEnabled() else _CARD_SELECTOR_IDLE_INNER_RATIO
        inner_size = self.width() * inner_ratio
        inner_offset = (self.width() - inner_size) / 2.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._inner_color)
        painter.drawEllipse(QtCore.QRectF(inner_offset, inner_offset, inner_size, inner_size))

        if self.hasFocus():
            painter.setOpacity(1.0)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 72), 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(circle_rect.adjusted(-2.0, -2.0, 2.0, 2.0))


class _DanbooruCardPreviewButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_pixmap = QPixmap()

    def set_preview_pixmap(self, pixmap: QPixmap):
        self._preview_pixmap = QPixmap(pixmap)
        self.update()

    def clear_preview_pixmap(self):
        self._preview_pixmap = QPixmap()
        self.update()

    def preview_pixmap(self) -> QPixmap:
        return QPixmap(self._preview_pixmap)

    def paintEvent(self, event):
        if self._preview_pixmap.isNull():
            super().paintEvent(event)
            return

        _ = event
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.icon = QtGui.QIcon()
        option.text = ""

        painter = QStylePainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.drawControl(QStyle.CE_PushButtonBevel, option)

        target_rect = self.rect().adjusted(
            _CARD_PREVIEW_BORDER_INSET,
            _CARD_PREVIEW_BORDER_INSET,
            -_CARD_PREVIEW_BORDER_INSET,
            -_CARD_PREVIEW_BORDER_INSET,
        )
        if target_rect.width() <= 0 or target_rect.height() <= 0:
            return

        scaled = self._preview_pixmap.scaled(target_rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        source_x = max(0, (scaled.width() - target_rect.width()) // 2)
        source_y = max(0, (scaled.height() - target_rect.height()) // 2)
        source_rect = QtCore.QRect(source_x, source_y, target_rect.width(), target_rect.height())

        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(target_rect), _CARD_PREVIEW_RADIUS, _CARD_PREVIEW_RADIUS)
        painter.save()
        painter.setClipPath(path)
        painter.drawPixmap(target_rect, scaled, source_rect)
        painter.restore()


class DanbooruCardWidget(QFrame):
    open_detail_requested = Signal(object)
    selection_changed = Signal(object, bool)

    def __init__(
        self,
        post: DanbooruPost,
        already_downloaded: bool = False,
        parent=None,
        metrics: DanbooruCardMetrics = DEFAULT_CARD_METRICS,
    ):
        super().__init__(parent)
        self.post = post
        self.already_downloaded = already_downloaded
        self.metrics = metrics
        self._card_theme = get_danbooru_card_theme(self.already_downloaded)
        self._preview_pixmap = QPixmap()
        self._preview_size = self._derive_preview_size()
        self.preview_height = self._preview_size.height()
        self.setObjectName(f"DanbooruCard_{post.post_id}")
        self._setup_ui()
        self.apply_theme()

    def _setup_ui(self):
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setProperty("downloaded", self.already_downloaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_CARD_CONTENT_MARGIN, _CARD_CONTENT_MARGIN, _CARD_CONTENT_MARGIN, _CARD_CONTENT_MARGIN)
        layout.setSpacing(0)

        self.preview_frame = QFrame(self)
        self.preview_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.preview_button = _DanbooruCardPreviewButton(self.preview_frame)
        self.preview_button.setObjectName("DanbooruCardPreview")
        self.preview_button.setProperty("unsupported", DanbooruPost.is_unsupported_file_ext(self.post.file_ext))
        self.preview_button.setCursor(Qt.PointingHandCursor)
        self.preview_button.clicked.connect(lambda: self.open_detail_requested.emit(self.post))
        self.preview_button.setText("Loading..." if self.post.preview_file_url else "No Preview")
        preview_layout.addWidget(self.preview_button)

        self._preview_glow = QGraphicsDropShadowEffect(self.preview_frame)
        self._preview_glow.setOffset(0.0, 0.0)
        self._preview_glow.setBlurRadius(0.0)
        self._preview_glow.setEnabled(False)
        self.preview_frame.setGraphicsEffect(self._preview_glow)

        self.checkbox = _DanbooruCardSelectorButton(self.preview_frame)
        self.checkbox.raise_()
        self.checkbox.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self.preview_frame, 0, Qt.AlignLeft | Qt.AlignTop)

        if DanbooruPost.is_unsupported_file_ext(self.post.file_ext):
            self.checkbox.setDisabled(True)
            self.checkbox.setChecked(False)
            self.preview_button.setText(f"Unsupported: {self.post.file_ext}")

        self._sync_geometry()
        self._apply_checkbox_availability()
        self._position_overlay_widgets()
        self._sync_selection_state(self.checkbox.isChecked())

    def apply_theme(self):
        self._card_theme = get_danbooru_card_theme(self.already_downloaded)
        self.setStyleSheet(build_card_stylesheet(DanbooruUiPalette.current(), self.already_downloaded))
        self.checkbox.apply_theme()
        self._sync_preview_glow()
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()

    def _source_preview_size(self) -> QtCore.QSize:
        if not self._preview_pixmap.isNull():
            return self._preview_pixmap.size()
        preview_width = self.post.preview_width or self.post.image_width or 0
        preview_height = self.post.preview_height or self.post.image_height or 0
        if preview_width > 0 and preview_height > 0:
            return QtCore.QSize(preview_width, preview_height)
        return QtCore.QSize(max(1, self.metrics.preview_content_width), max(1, self.metrics.preview_base_height))

    def _derive_preview_size(self) -> QtCore.QSize:
        source_size = self._source_preview_size()
        bounds = QtCore.QSize(
            max(1, self.metrics.preview_content_width),
            max(1, self.metrics.preview_max_height),
        )
        if source_size.width() <= 0 or source_size.height() <= 0:
            return QtCore.QSize(bounds.width(), max(1, self.metrics.preview_base_height))
        fitted = source_size.scaled(bounds, Qt.KeepAspectRatio)
        return QtCore.QSize(max(1, fitted.width()), max(1, fitted.height()))

    @property
    def preview_width(self) -> int:
        return max(1, self._preview_size.width())

    def preview_fetch_width(self) -> int:
        return self.preview_width

    def _position_overlay_widgets(self):
        tokens = get_danbooru_qss_tokens()
        max_x = max(0, self.preview_width - self.checkbox.width())
        max_y = max(0, self.preview_height - self.checkbox.height())
        self.checkbox.move(
            max(0, min(max_x, int(round(float(tokens["CARD_CHECKBOX_OFFSET_X"]))))),
            max(0, min(max_y, int(round(float(tokens["CARD_CHECKBOX_OFFSET_Y"]))))),
        )

    def _apply_checkbox_availability(self):
        unsupported = DanbooruPost.is_unsupported_file_ext(self.post.file_ext)
        self.checkbox.setVisible(not self.already_downloaded)
        self.checkbox.setDisabled(unsupported or self.already_downloaded)

    def _is_selected(self) -> bool:
        return bool(self.property("selected"))

    def _sync_preview_glow(self):
        self._preview_glow.setColor(qcolor_from_css(self._card_theme.glow_color))
        self._preview_glow.setBlurRadius(26.0)
        self._preview_glow.setEnabled(self._is_selected())

    def _sync_selection_state(self, selected: bool):
        self.setProperty("selected", selected)
        self.setProperty("downloaded", self.already_downloaded)
        self.style().unpolish(self)
        self.style().polish(self)
        self._sync_preview_glow()
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()
        self.update()

    def _on_checkbox_toggled(self, checked: bool):
        self._sync_selection_state(checked)
        self.selection_changed.emit(self, checked)

    def set_selected(self, selected: bool):
        if self.checkbox.isEnabled():
            self.checkbox.blockSignals(True)
            self.checkbox.setChecked(selected)
            self.checkbox.blockSignals(False)
        self._sync_selection_state(self.checkbox.isChecked())

    def set_already_downloaded(self, downloaded: bool):
        self.already_downloaded = downloaded
        if downloaded:
            self.checkbox.blockSignals(True)
            self.checkbox.setChecked(False)
            self.checkbox.blockSignals(False)
        self._apply_checkbox_availability()
        self.apply_theme()
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()
        self._sync_selection_state(self.checkbox.isChecked())

    def set_preview_pixmap(self, pixmap: QPixmap):
        self._preview_pixmap = QPixmap(pixmap)
        self._sync_geometry()
        self._apply_preview_icon()

    def _preview_target_size(self) -> QtCore.QSize:
        return QtCore.QSize(self.preview_width, max(1, self.preview_height))

    def _default_preview_text(self) -> str:
        if DanbooruPost.is_unsupported_file_ext(self.post.file_ext):
            return f"Unsupported: {self.post.file_ext}"
        return "Loading..." if self.post.preview_file_url else "No Preview"

    def _build_preview_icon(self) -> QPixmap:
        target_size = self._preview_target_size()
        if self._preview_pixmap.isNull():
            return QPixmap()
        preview = self._preview_pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self.already_downloaded:
            preview = self._apply_downloaded_preview_effect(preview, self._card_theme)
        if self._is_selected():
            preview = self._apply_selection_overlay(preview, self._card_theme)
        return preview

    def _apply_preview_icon(self):
        preview = self._build_preview_icon()
        self.preview_button.set_preview_pixmap(preview)
        self.preview_button.setText("" if not preview.isNull() else self._default_preview_text())

    @staticmethod
    def _apply_partial_grayscale(pixmap: QPixmap, amount: float) -> QPixmap:
        clamped = max(0.0, min(1.0, amount))
        if clamped <= 0:
            return QPixmap(pixmap)
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                gray = int(round(color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114))
                color.setRed(int(round(color.red() * (1.0 - clamped) + gray * clamped)))
                color.setGreen(int(round(color.green() * (1.0 - clamped) + gray * clamped)))
                color.setBlue(int(round(color.blue() * (1.0 - clamped) + gray * clamped)))
                image.setPixelColor(x, y, color)
        return QPixmap.fromImage(image)

    @staticmethod
    def _apply_downloaded_preview_effect(pixmap: QPixmap, card_theme: DanbooruCardTheme) -> QPixmap:
        def _apply_opacity(pixmap: QPixmap) -> QPixmap:
            clamped = max(0.0, min(1.0, card_theme.preview_downloaded_opacity))
            if clamped >= 1.0 or pixmap.isNull():
                return QPixmap(pixmap)
            faded = QPixmap(pixmap.size())
            faded.fill(Qt.transparent)
            painter = QtGui.QPainter(faded)
            painter.setOpacity(clamped)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            return faded
        return _apply_opacity(DanbooruCardWidget._apply_partial_grayscale(pixmap, card_theme.preview_downloaded_grayscale))

    @staticmethod
    def _apply_selection_overlay(pixmap: QPixmap, card_theme: DanbooruCardTheme) -> QPixmap:
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        gradient = QtGui.QLinearGradient(0.0, 0.0, float(image.width()), float(image.height()))
        gradient.setColorAt(0.0, qcolor_from_css(card_theme.preview_selected_overlay_start))
        gradient.setColorAt(1.0, qcolor_from_css(card_theme.preview_selected_overlay_end))
        painter.fillRect(image.rect(), gradient)
        painter.end()
        return QPixmap.fromImage(image)

    def _sync_geometry(self):
        self._preview_size = self._derive_preview_size()
        self.preview_height = self._preview_size.height()
        self.preview_frame.setFixedSize(self._preview_size)
        self.preview_button.setFixedSize(self._preview_size)
        self.setFixedSize(self.sizeHint())

    def apply_metrics(self, metrics: DanbooruCardMetrics):
        self.metrics = metrics
        self._sync_geometry()
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()
        self._position_overlay_widgets()
        self.adjustSize()
        self.updateGeometry()

    def sizeHint(self) -> QtCore.QSize:
        layout = self.layout()
        margins = layout.contentsMargins() if layout is not None else QtCore.QMargins()
        return QtCore.QSize(
            margins.left() + self.preview_width + margins.right(),
            margins.top() + self.preview_height + margins.bottom(),
        )

    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._preview_pixmap.isNull() and self.preview_button.iconSize() != self._preview_target_size():
            self._apply_preview_icon()
        self._position_overlay_widgets()
