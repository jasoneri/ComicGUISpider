from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout
from qfluentwidgets import CheckBox

from utils.script.image.danbooru.models import DanbooruPost

from .style import DanbooruCardMetrics, DanbooruUiPalette, DEFAULT_CARD_METRICS, build_card_stylesheet

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
        self._preview_pixmap = QPixmap()
        self.preview_height = self._derive_preview_height()
        self.setObjectName(f"DanbooruCard_{post.post_id}")
        self._setup_ui()
        self.apply_theme()

    def _setup_ui(self):
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(self.metrics.width)
        self.setProperty("downloaded", self.already_downloaded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self.preview_frame = QFrame(self)
        self.preview_frame.setFixedHeight(self.preview_height)
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.preview_button = QPushButton(self.preview_frame)
        self.preview_button.setObjectName("DanbooruCardPreview")
        self.preview_button.setProperty("unsupported", DanbooruPost.is_unsupported_file_ext(self.post.file_ext))
        self.preview_button.setCursor(Qt.PointingHandCursor)
        self.preview_button.clicked.connect(lambda: self.open_detail_requested.emit(self.post))
        self.preview_button.setFixedHeight(self.preview_height)
        self.preview_button.setText("Loading..." if self.post.preview_file_url else "No Preview")
        preview_layout.addWidget(self.preview_button)

        self.checkbox = CheckBox(self.preview_frame)
        self.checkbox.raise_()
        self.checkbox.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self.preview_frame)

        if DanbooruPost.is_unsupported_file_ext(self.post.file_ext):
            self.checkbox.setDisabled(True)
            self.checkbox.setChecked(False)
            self.preview_button.setText(f"Unsupported: {self.post.file_ext}")

        self._apply_checkbox_availability()
        self._position_overlay_widgets()
        self._sync_selection_state(self.checkbox.isChecked())

    def apply_theme(self):
        self.setStyleSheet(build_card_stylesheet(DanbooruUiPalette.current(), self.already_downloaded))

    def _derive_preview_height(self) -> int:
        preview_width = self.post.preview_width or self.post.image_width
        preview_height = self.post.preview_height or self.post.image_height
        if preview_width > 0 and preview_height > 0:
            raw_height = int(round(self.metrics.preview_content_width * preview_height / preview_width))
            return max(self.metrics.preview_min_height, min(self.metrics.preview_max_height, raw_height))
        return self.metrics.preview_base_height

    def preview_fetch_width(self) -> int:
        return self.metrics.preview_content_width

    def _position_overlay_widgets(self):
        tokens = get_danbooru_qss_tokens()
        self.checkbox.move(
            max(0, int(round(float(tokens["CARD_CHECKBOX_OFFSET_X"])))),
            max(0, int(round(float(tokens["CARD_CHECKBOX_OFFSET_Y"])))),
        )

    def _apply_checkbox_availability(self):
        unsupported = DanbooruPost.is_unsupported_file_ext(self.post.file_ext)
        self.checkbox.setVisible(not self.already_downloaded)
        self.checkbox.setDisabled(unsupported or self.already_downloaded)

    def _sync_selection_state(self, selected: bool):
        self.setProperty("selected", selected)
        self.setProperty("downloaded", self.already_downloaded)
        self.style().unpolish(self)
        self.style().polish(self)
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
            self.checkbox.setDisabled(True)
        self.apply_theme()
        self._sync_selection_state(self.checkbox.isChecked())

    def set_preview_pixmap(self, pixmap: QPixmap):
        self._preview_pixmap = QPixmap(pixmap)
        target_size = QtCore.QSize(self.metrics.preview_content_width, self.preview_height)
        scaled = self._preview_pixmap.scaled(target_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if self.already_downloaded:
            scaled = self._apply_partial_grayscale(scaled, self._downloaded_preview_grayscale())
        self.preview_button.setIcon(QtGui.QIcon(scaled))
        self.preview_button.setIconSize(target_size)
        self.preview_button.setText("")

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
    def _downloaded_preview_grayscale() -> float:
        return max(0.0, min(1.0, float(get_danbooru_qss_tokens()["CARD_PREVIEW_DOWNLOADED_GRAYSCALE"])))

    def apply_metrics(self, metrics: DanbooruCardMetrics):
        self.metrics = metrics
        self.preview_height = self._derive_preview_height()
        self.setFixedWidth(self.metrics.width)
        self.preview_frame.setFixedHeight(self.preview_height)
        self.preview_button.setFixedHeight(self.preview_height)
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()
        self._position_overlay_widgets()
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay_widgets()
