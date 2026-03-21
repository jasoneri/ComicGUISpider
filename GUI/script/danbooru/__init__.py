import sys
import typing as t
from pathlib import Path

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QApplication, QCompleter, QFrame, QHBoxLayout, QLabel, QPushButton, QRubberBand, QStackedWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    Action, BodyLabel, StrongBodyLabel, CheckBox, ComboBox, FluentIcon as FIF, 
    FlowLayout, InfoBar, InfoBarPosition, SearchLineEdit,
    PushButton, RoundMenu, ScrollArea, SubtitleLabel, TabBar, ToolButton, 
    TabCloseButtonDisplayMode, TransparentToolButton, PrimaryToolButton, TransparentToggleToolButton
)
from qframelesswindow.utils import startSystemMove

from deploy import curr_os
from GUI.core.timer import safe_single_shot
from GUI.core.theme import theme_mgr
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent import MonkeyPatch as FluentMonkeyPatch
from GUI.uic.qfluent.components import CountBadge, FlexImageLabel
from utils.config.qc import danbooru_cfg
from utils.script.image.danbooru import *
from .core import (
    DanbooruDownloadController,
    DanbooruSearchController,
    DanbooruTabState,
    DanbooruViewerFitCalculator,
    DanbooruViewerFitResult,
    delete_flow_item as _delete_flow_item,
    fetch_pixmap as _fetch_pixmap,
    run_async as _run_async,
)
from .style import (
    CARD_ZOOM_METRICS, DEFAULT_CARD_METRICS, DEFAULT_CARD_ZOOM_INDEX, DEFAULT_TAB_STATUS_CLASS, DEFAULT_TAB_STATUS_TEXT,
    DanbooruCardMetrics, DanbooruUiPalette,
    build_card_stylesheet, build_interface_stylesheet, build_tab_stylesheet, build_tip_line_stylesheet, build_title_label_stylesheet, build_viewer_stylesheet,
    format_tip_rich_text as _format_tip_rich_text,
    qcolor_from_css,
)


def _iter_tag_groups(post: DanbooruPost) -> list[tuple[str, list[str]]]:
    groups = [
        ("Character", list(filter(None, post.tag_string_character.split(" ")))),
        ("Artist", list(filter(None, post.tag_string_artist.split(" ")))),
        ("Copyright", list(filter(None, post.tag_string_copyright.split(" ")))),
        ("General", list(filter(None, post.tag_string_general.split(" ")))),
    ]
    return [(label, tags) for label, tags in groups if tags]

class DanbooruCardWidget(QFrame):
    open_detail_requested = pyqtSignal(object)
    selection_changed = pyqtSignal(str, bool)

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
        self.preview_button.setCursor(Qt.PointingHandCursor)
        self.preview_button.clicked.connect(lambda: self.open_detail_requested.emit(self.post))
        self.preview_button.setFixedHeight(self.preview_height)
        self.preview_button.setText("Loading..." if self.post.preview_file_url else "No Preview")
        preview_layout.addWidget(self.preview_button)

        self.checkbox = CheckBox(self.preview_frame)
        self.checkbox.raise_()
        self.checkbox.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self.preview_frame)

        if is_unsupported_media_type(self.post.file_ext):
            self.checkbox.setDisabled(True)
            self.checkbox.setChecked(False)
            self.preview_button.setText(f"Unsupported: {self.post.file_ext}")
        elif self.already_downloaded:
            self.checkbox.setDisabled(True)

        self._position_overlay_widgets()
        self._sync_selection_state(self.checkbox.isChecked())

    def apply_theme(self):
        palette = DanbooruUiPalette.current()
        text_color = "#b65239" if is_unsupported_media_type(self.post.file_ext) else palette.text
        self.setStyleSheet(build_card_stylesheet(palette, self.already_downloaded))
        self.preview_button.setStyleSheet(f"color: {text_color};")

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
        self.checkbox.move(12, 12)

    def _sync_selection_state(self, selected: bool):
        self.setProperty("selected", selected)
        self.setProperty("downloaded", self.already_downloaded)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _on_checkbox_toggled(self, checked: bool):
        self._sync_selection_state(checked)
        self.selection_changed.emit(self.post.md5, checked)

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
        scaled = pixmap.scaled(target_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.preview_button.setIcon(QtGui.QIcon(scaled))
        self.preview_button.setIconSize(target_size)
        self.preview_button.setText("")

    def apply_metrics(self, metrics: DanbooruCardMetrics):
        self.metrics = metrics
        self.preview_height = self._derive_preview_height()
        self.setFixedWidth(self.metrics.width)
        self.preview_frame.setFixedHeight(self.preview_height)
        self.preview_button.setFixedHeight(self.preview_height)
        if not self._preview_pixmap.isNull():
            self.set_preview_pixmap(self._preview_pixmap)
        self._position_overlay_widgets()
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay_widgets()


class DanbooruImageViewer(QWidget):
    tag_clicked = pyqtSignal(str)
    download_requested = pyqtSignal(object)
    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None)
        self._anchor_widget = parent
        self.post: t.Optional[DanbooruPost] = None
        self._already_downloaded = False
        self._drag_offset: t.Optional[QtCore.QPoint] = None
        self._default_image_size = QtCore.QSize(520, 340)
        self._keep_on_top = True
        self._display_source_size: t.Optional[QtCore.QSize] = None
        self._loaded_pixmap_size: t.Optional[QtCore.QSize] = None
        self._last_fit_result: t.Optional[DanbooruViewerFitResult] = None
        self._applying_layout = False
        self._pending_loaded_settle_post_id: t.Optional[int] = None
        self._loaded_settle_revision = 0
        self._loaded_settle_scheduled = False
        self._setup_ui()
        self.apply_theme()

    def _setup_ui(self):
        self.setObjectName("DanbooruImageViewer")
        self.setWindowFlags(self._window_flags(self._keep_on_top))
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(12, 12, 12, 12)

        self.frame = QFrame(self)
        self.frame.setObjectName("DanbooruImageViewerFrame")
        self.outer_layout.addWidget(self.frame)

        self.main_layout = QHBoxLayout(self.frame)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(14)

        self.tags_scroll = ScrollArea(self.frame)
        self.tags_scroll.setWidgetResizable(True)
        self.tags_scroll.setFixedWidth(196)
        self.tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tags_scroll.setStyleSheet("background: transparent; border: none;")
        self.tags_container = QWidget(self.tags_scroll)
        self.tags_container.setObjectName("DanbooruTagsContainer")
        self.tags_layout = QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(8)
        self.tags_scroll.setWidget(self.tags_container)
        self.main_layout.addWidget(self.tags_scroll)

        self.right_panel_widget = QWidget(self.frame)
        self.right_panel_widget.setObjectName("DanbooruViewerRightPanel")
        self.right_panel_layout = QVBoxLayout(self.right_panel_widget)
        self.right_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.right_panel_layout.setSpacing(12)

        self.top_bar = QWidget(self.frame)
        self.top_bar.setObjectName("DanbooruViewerTopBar")
        self.top_bar.installEventFilter(self)
        top_bar = QHBoxLayout(self.top_bar)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)
        self.previous_btn = TransparentToolButton(FIF.LEFT_ARROW, self.frame)
        self.previous_btn.setFixedSize(34, 34)
        self.previous_btn.setToolTip("上一张")
        self.previous_btn.clicked.connect(self.previous_requested.emit)
        self.next_btn = TransparentToolButton(FIF.RIGHT_ARROW, self.frame)
        self.next_btn.setFixedSize(34, 34)
        self.next_btn.setToolTip("下一张")
        self.next_btn.clicked.connect(self.next_requested.emit)
        self.download_btn = PrimaryToolButton(FIF.DOWNLOAD, self.frame)
        self.download_btn.setFixedHeight(34)
        self.download_btn.clicked.connect(self._emit_download)
        self.close_btn = TransparentToolButton(FIF.CLOSE, self.frame)
        self.close_btn.setFixedSize(34, 34)
        self.close_btn.clicked.connect(self.hide)
        self.topHintBox = TransparentToggleToolButton(self.top_bar)
        self.topHintBox.setIcon(FIF.PIN)
        self.topHintBox.setChecked(self._keep_on_top)
        self.topHintBox.setToolTip("窗口置顶")
        self.topHintBox.clicked.connect(self.keep_top_hint)
        top_bar.addWidget(self.topHintBox)
        top_bar.addStretch(1)
        top_bar.addWidget(self.previous_btn)
        top_bar.addWidget(self.next_btn)
        top_bar.addWidget(self.download_btn)
        top_bar.addWidget(self.close_btn)
        self.top_bar.setFixedHeight(34)
        self.right_panel_layout.addWidget(self.top_bar, 0, Qt.AlignTop)

        self.image_label = FlexImageLabel(self.frame)
        self.image_label.setObjectName("DanbooruImageLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setWordWrap(True)
        self.image_label.setBorderRadius(16, 16, 16, 16)
        self.image_label.setFixedSize(self._default_image_size)
        self.image_hint_label = QLabel("No Preview", self.image_label)
        self.image_hint_label.setObjectName("DanbooruImageHint")
        self.image_hint_label.setAlignment(Qt.AlignCenter)
        self.image_hint_label.setWordWrap(True)
        self._sync_image_hint_geometry()
        self.image_label.mousePressEvent = self._image_mouse_press_event
        self.image_label.mouseMoveEvent = self._image_mouse_move_event
        self.image_label.mouseReleaseEvent = self._image_mouse_release_event
        self.right_panel_layout.addWidget(self.image_label, 0, Qt.AlignHCenter | Qt.AlignTop)
        self.right_panel_layout.addStretch(1)

        self.right_panel_widget.setFixedWidth(self._default_image_size.width())
        self.main_layout.addWidget(self.right_panel_widget, 0, Qt.AlignTop)
        self._update_download_button()
        self._clear_tags()
        self.set_navigation_enabled(False, False)

    def apply_theme(self):
        palette = DanbooruUiPalette.current()
        self.setStyleSheet(build_viewer_stylesheet(palette))

    def eventFilter(self, obj, event):
        if obj is self.top_bar and event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton and obj.childAt(event.pos()) is None:
                startSystemMove(self, event.globalPos())
                return True
        return super().eventFilter(obj, event)

    def _emit_download(self):
        if self.post is not None:
            self.download_requested.emit(self.post)

    def _window_flags(self, keep_on_top: bool):
        flags = Qt.Window | Qt.FramelessWindowHint
        if keep_on_top:
            flags |= Qt.WindowStaysOnTopHint
        return flags

    def _sync_native_topmost(self, keep_on_top: bool):
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            import win32con
            import win32gui
        except ImportError:
            return
        hwnd = int(self.winId())
        insert_after = win32con.HWND_TOPMOST if keep_on_top else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(
            hwnd,
            insert_after, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )

    def _apply_window_mode(self):
        geometry = self.geometry()
        was_visible = self.isVisible()
        self.setWindowFlags(self._window_flags(self._keep_on_top))
        if was_visible:
            self.show()
            if geometry.isValid():
                self.setGeometry(geometry)
            self._sync_native_topmost(self._keep_on_top)

    def keep_top_hint(self, _flag: bool = None):
        flag = _flag if _flag is not None else self.topHintBox.isChecked()
        self._keep_on_top = flag
        self.topHintBox.setChecked(flag)
        self._apply_window_mode()

    def _screen_geometry(self):
        center = None
        parent_window = self._anchor_widget if isinstance(self._anchor_widget, QWidget) else None
        if parent_window is not None and parent_window.isVisible():
            center = parent_window.mapToGlobal(parent_window.rect().center())
        elif self.isVisible():
            center = self.mapToGlobal(self.rect().center())
        screen = QApplication.screenAt(center) if center is not None else None
        if screen is not None:
            return screen.availableGeometry()
        screen = QApplication.primaryScreen()
        if screen is None:
            return QtCore.QRect(0, 0, 1280, 720)
        return screen.availableGeometry()

    def _reposition_viewer(self):
        geometry = self._screen_geometry()
        self.adjustSize()
        x = geometry.x() + max(0, (geometry.width() - self.width()) // 2)
        y = geometry.y() + max(0, (geometry.height() - self.height()) // 2)
        self.move(x, y)

    @staticmethod
    def _is_valid_size(size: t.Optional[QtCore.QSize]) -> bool:
        return bool(size is not None and size.width() > 0 and size.height() > 0)

    @staticmethod
    def _size_area(size: QtCore.QSize) -> int:
        return max(0, size.width()) * max(0, size.height())

    def _clone_size(self, size: QtCore.QSize) -> QtCore.QSize:
        return QtCore.QSize(size.width(), size.height())

    def _update_display_source_size(self, source_size: t.Optional[QtCore.QSize], *, replace: bool = False) -> bool:
        if not self._is_valid_size(source_size):
            return False
        normalized = self._clone_size(source_size)
        if replace or not self._is_valid_size(self._display_source_size):
            self._display_source_size = normalized
            return True
        assert self._display_source_size is not None
        if self._size_area(normalized) > self._size_area(self._display_source_size):
            self._display_source_size = normalized
            return True
        return False

    def _effective_display_source_size(self) -> t.Optional[QtCore.QSize]:
        if self._is_valid_size(self._display_source_size):
            assert self._display_source_size is not None
            return self._clone_size(self._display_source_size)
        post_hint = self._post_size_hint(self.post) if self.post is not None else None
        if self._is_valid_size(post_hint):
            assert post_hint is not None
            return self._clone_size(post_hint)
        if self._is_valid_size(self._loaded_pixmap_size):
            assert self._loaded_pixmap_size is not None
            return self._clone_size(self._loaded_pixmap_size)
        return None

    def _panel_chrome_width(self) -> int:
        outer_margins = self.outer_layout.contentsMargins()
        main_margins = self.main_layout.contentsMargins()
        right_panel_margins = self.right_panel_layout.contentsMargins()
        return (
            outer_margins.left()
            + outer_margins.right()
            + main_margins.left()
            + main_margins.right()
            + self.tags_scroll.width()
            + self.main_layout.spacing()
            + right_panel_margins.left()
            + right_panel_margins.right()
        )

    def _panel_chrome_height(self) -> int:
        outer_margins = self.outer_layout.contentsMargins()
        main_margins = self.main_layout.contentsMargins()
        right_panel_margins = self.right_panel_layout.contentsMargins()
        return (
            outer_margins.top()
            + outer_margins.bottom()
            + main_margins.top()
            + main_margins.bottom()
            + right_panel_margins.top()
            + right_panel_margins.bottom()
            + self.top_bar.height()
            + self.right_panel_layout.spacing()
        )

    def _max_right_panel_width(self) -> int:
        geometry = self._screen_geometry()
        return max(1, geometry.width() - self._panel_chrome_width())

    def _top_bar_min_width(self) -> int:
        return max(self.top_bar.sizeHint().width(), self.top_bar.minimumSizeHint().width(), self.top_bar.minimumWidth())

    def _image_display_bounds(self) -> QtCore.QSize:
        geometry = self._screen_geometry()
        return QtCore.QSize(
            self._max_right_panel_width(),
            max(1, geometry.height() - self._panel_chrome_height()),
        )

    def _calculate_fit_result(self, source_size: t.Optional[QtCore.QSize]) -> DanbooruViewerFitResult:
        return DanbooruViewerFitCalculator.calculate(self._image_display_bounds(), source_size)

    def _fit_image_size(self, source_size: t.Optional[QtCore.QSize]) -> QtCore.QSize:
        return self._calculate_fit_result(source_size).display_size

    def _apply_image_display_size(self, display_size: QtCore.QSize):
        panel_width = min(self._max_right_panel_width(), max(display_size.width(), self._top_bar_min_width()))
        self.image_label.setFixedSize(display_size)
        self.right_panel_widget.setFixedWidth(panel_width)
        self._sync_image_hint_geometry()

    def _settle_viewer_layout(self, source_size: t.Optional[QtCore.QSize] = None):
        self._update_display_source_size(source_size)
        self._last_fit_result = self._calculate_fit_result(self._effective_display_source_size())
        self._applying_layout = True
        try:
            self._apply_image_display_size(self._last_fit_result.display_size)
            self._reposition_viewer()
        finally:
            self._applying_layout = False

    def _schedule_loaded_settlement(self):
        post_id = self._pending_loaded_settle_post_id
        if post_id is None or self._loaded_settle_scheduled:
            return
        revision = self._loaded_settle_revision
        self._loaded_settle_scheduled = True

        def _apply_loaded_settle():
            self._loaded_settle_scheduled = False
            if (
                self.post is None
                or self.post.post_id != post_id
                or self._pending_loaded_settle_post_id != post_id
                or revision != self._loaded_settle_revision
            ):
                return
            self._pending_loaded_settle_post_id = None
            self._settle_viewer_layout()

        safe_single_shot(0, _apply_loaded_settle)

    def _arm_loaded_settlement(self, post_id: int):
        self._pending_loaded_settle_post_id = post_id
        self._loaded_settle_revision += 1
        self._schedule_loaded_settlement()

    @staticmethod
    def _post_size_hint(post: DanbooruPost) -> t.Optional[QtCore.QSize]:
        width = post.image_width or post.preview_width
        height = post.image_height or post.preview_height
        if width > 0 and height > 0:
            return QtCore.QSize(width, height)
        return None

    def _clear_tags(self):
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            _delete_flow_item(item)
        self.tags_layout.addStretch(1)

    def _sync_image_hint_geometry(self):
        self.image_hint_label.setGeometry(0, 0, self.image_label.width(), self.image_label.height())

    def set_placeholder(self, text: str):
        self.image_label.setPixmap(QPixmap())
        self.image_hint_label.setText(text)
        self.image_hint_label.show()
        self._sync_image_hint_geometry()

    def set_placeholder_for_post(self, post: DanbooruPost, text: str):
        self._update_display_source_size(self._post_size_hint(post), replace=True)
        self._last_fit_result = self._calculate_fit_result(self._effective_display_source_size())
        self._apply_image_display_size(self._last_fit_result.display_size)
        self.set_placeholder(text)

    def set_placeholder_size(self, post_id: int, source_size: QtCore.QSize):
        if self.post is None or self.post.post_id != post_id or source_size.width() <= 0 or source_size.height() <= 0:
            return
        self._settle_viewer_layout(source_size)

    def _populate_tags(self, post: DanbooruPost):
        self._clear_tags()
        tail = self.tags_layout.takeAt(self.tags_layout.count() - 1)
        _delete_flow_item(tail)
        for section_label, tags in _iter_tag_groups(post):
            title = BodyLabel(section_label, self.tags_container)
            title.setObjectName("DanbooruTagSectionTitle")
            self.tags_layout.addWidget(title)
            for tag in tags:
                button = PushButton(tag, self.tags_container)
                button.setObjectName("DanbooruTagButton")
                button.clicked.connect(lambda _=False, current_tag=tag: self.tag_clicked.emit(current_tag))
                self.tags_layout.addWidget(button)
        self.tags_layout.addStretch(1)

    def _update_download_button(self):
        downloadable = self.post is not None and is_supported_media_type(self.post.file_ext) and not self._already_downloaded
        self.download_btn.setDisabled(not downloadable)

    def set_download_state(self, downloaded: bool):
        self._already_downloaded = downloaded
        self._update_download_button()

    def set_navigation_enabled(self, has_previous: bool, has_next: bool):
        self.previous_btn.setEnabled(has_previous)
        self.next_btn.setEnabled(has_next)

    def show_post(self, post: DanbooruPost, already_downloaded: bool):
        self.post = post
        self._already_downloaded = already_downloaded
        self._display_source_size = None
        self._loaded_pixmap_size = None
        self._last_fit_result = None
        self._pending_loaded_settle_post_id = None
        self._loaded_settle_revision += 1
        self._loaded_settle_scheduled = False
        self._update_display_source_size(self._post_size_hint(post), replace=True)
        self._populate_tags(post)
        self._update_download_button()
        self.set_placeholder_for_post(post, "Loading..." if (post.large_file_url or post.file_url or post.preview_file_url) else "No Preview")
        self.show()
        self._settle_viewer_layout()
        self.raise_()
        self.activateWindow()

    def set_image(self, post_id: int, pixmap: QPixmap):
        if self.post is None or self.post.post_id != post_id:
            return
        if pixmap.width() == 0 or pixmap.height() == 0:
            return
        pixmap_size = QtCore.QSize(pixmap.width(), pixmap.height())
        self._loaded_pixmap_size = self._clone_size(pixmap_size)
        self._update_display_source_size(pixmap_size)
        self.image_label.setPixmap(pixmap)
        self.image_hint_label.hide()
        self._settle_viewer_layout()
        self._arm_loaded_settlement(post_id)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_image_hint_geometry()
        if self._applying_layout:
            return
        self._schedule_loaded_settlement()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event):
        self._drag_offset = None
        self.closed.emit()
        super().hideEvent(event)

    def _image_mouse_press_event(self, event):
        QLabel.mousePressEvent(self.image_label, event)

    def _image_mouse_move_event(self, event):
        QLabel.mouseMoveEvent(self.image_label, event)

    def _image_mouse_release_event(self, event):
        self._drag_offset = None
        QLabel.mouseReleaseEvent(self.image_label, event)


class DanbooruTabWidget(QFrame):
    selection_count_changed = pyqtSignal(int)
    request_search = pyqtSignal(str, bool)
    request_conversion = pyqtSignal()
    request_single_download = pyqtSignal(object)
    request_tag_jump = pyqtSignal(str)
    request_next_page = pyqtSignal()
    detail_opened = pyqtSignal(object)

    SORT_OPTIONS = list(DANBOORU_SORT_OPTIONS)

    def __init__(self, state: DanbooruTabState, parent=None):
        super().__init__(parent)
        self.state = state
        self.card_metrics = DEFAULT_CARD_METRICS
        self.card_widgets: dict[str, DanbooruCardWidget] = {}
        self._selection_band: t.Optional[QRubberBand] = None
        self._drag_select_origin: t.Optional[QtCore.QPoint] = None
        self._drag_select_active = False
        self._drag_select_source: t.Optional[QWidget] = None
        self._setup_ui()
        self.apply_theme()

    def _create_group_frame(self, object_name: str) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName(object_name)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        return frame, layout

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(12)

        query_frame, query_group = self._create_group_frame("DanbooruSearchQueryGroup")
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("输入标签，例如 blue_archive")
        self.search_edit.setMinimumHeight(38)
        self.search_edit.returnPressed.connect(self._submit_search_from_keyboard)
        self.search_edit.searchSignal.connect(lambda text: self.request_search.emit(text, False))
        self.search_edit.searchButton.clicked.connect(self._submit_empty_search_if_needed)
        FluentMonkeyPatch.rbutton_menu_lineEdit(
            self.search_edit,
            extra_actions=[
                self._create_search_value_action("打开历史", FIF.HISTORY, danbooru_cfg.get_history, "暂无历史记录"),
                self._create_search_value_action("打开收藏列表", FIF.HEART, lambda: sorted(danbooru_cfg.get_favorites()), "暂无收藏记录"),
            ],
        )
        self.favorite_btn = TransparentToolButton(FIF.HEART, self)
        self.favorite_btn.setFixedSize(38, 38)
        self.convert_btn = PushButton("转换", self)
        self.convert_btn.setMinimumHeight(38)
        self.convert_btn.clicked.connect(self.request_conversion.emit)
        self.sort_box = ComboBox(self)
        self.sort_box.setMinimumHeight(38)
        for label, _ in self.SORT_OPTIONS:
            self.sort_box.addItem(label)
        self.sort_box.currentIndexChanged.connect(self._on_sort_changed)
        query_group.addWidget(self.search_edit, 1)
        query_group.addWidget(self.favorite_btn)
        query_group.addWidget(self.convert_btn)
        query_group.addWidget(self.sort_box)
        query_frame.setMinimumHeight(58)
        query_frame.setMinimumWidth(420)
        search_row.addWidget(query_frame, 1)

        self.main_layout.addLayout(search_row)

        self.scroll_area = ScrollArea(self)
        self.scroll_area.setObjectName("DanbooruGridScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("DanbooruGridContent")
        self.flow_layout = FlowLayout(self.scroll_content)
        self.flow_layout.setContentsMargins(2, 2, 2, 2)
        self.flow_layout.setHorizontalSpacing(12)
        self.flow_layout.setVerticalSpacing(12)
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self._selection_band = QRubberBand(QRubberBand.Rectangle, self.scroll_area.viewport())
        self._selection_band.hide()
        self._install_drag_select_source(self.scroll_area.viewport())
        self._install_drag_select_source(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area, 1)
        self.refresh_from_state()

    def _set_search_edit_value(self, value: str):
        self.search_edit.setText(value)
        self.search_edit.setFocus()
        self.search_edit.setCursorPosition(len(value))

    def _submit_search_from_keyboard(self):
        if self.search_edit.text().strip():
            self.search_edit.search()
            return
        self.request_search.emit("", False)

    def _submit_empty_search_if_needed(self):
        if not self.search_edit.text().strip():
            self.request_search.emit("", False)

    def _create_search_value_action(self, text: str, icon, values_getter, empty_text: str) -> Action:
        def open_menu():
            menu = RoundMenu(parent=self.search_edit)
            values = [current for value in values_getter() or [] if (current := str(value).strip())]
            if not values:
                empty_action = Action(text=empty_text)
                empty_action.setEnabled(False)
                menu.addAction(empty_action)
            else:
                for value in values:
                    menu.addAction(Action(text=value, triggered=lambda _=False, current=value: self._set_search_edit_value(current)))
            menu.exec_(self.search_edit.mapToGlobal(self.search_edit.rect().bottomLeft()))

        return Action(icon, text=text, triggered=open_menu)

    def show_conversion_candidates(
        self, candidates: list[DanbooruAutocompleteCandidate],
        on_selected: t.Callable[[DanbooruAutocompleteCandidate], None],
    ):
        menu = RoundMenu(parent=self.search_edit)
        if not candidates:
            empty_action = Action(text="暂无候选")
            empty_action.setEnabled(False)
            menu.addAction(empty_action)
        else:
            for candidate in candidates:
                menu.addAction(
                    Action(text=candidate.menu_text,
                        triggered=lambda _=False, current=candidate: on_selected(current),))
        menu.exec_(self.search_edit.mapToGlobal(self.search_edit.rect().bottomLeft()))

    def apply_theme(self):
        palette = DanbooruUiPalette.current()
        self.setStyleSheet(build_tab_stylesheet(palette))
        if self._selection_band is not None:
            self._selection_band.setStyleSheet(
                f"border: 2px dashed {palette.selection_border}; background: {palette.preview_hover};"
            )
        for card in self.card_widgets.values():
            card.apply_theme()

    def refresh_from_state(self):
        self.search_edit.setText(self.state.query)
        for idx, (_, value) in enumerate(self.SORT_OPTIONS):
            if value == self.state.sort_mode:
                self.sort_box.blockSignals(True)
                self.sort_box.setCurrentIndex(idx)
                self.sort_box.blockSignals(False)
                break

    def _on_sort_changed(self):
        _, value = self.SORT_OPTIONS[self.sort_box.currentIndex()]
        self.state.sort_mode = value
        self.request_search.emit(self.search_edit.text(), True)

    def _on_scroll_changed(self, value: int):
        bar = self.scroll_area.verticalScrollBar()
        if bar.maximum() - value < 200 and not self.state.loading and self.state.has_more_results:
            self.request_next_page.emit()

    def update_completer(self, terms: list[str]):
        completer = QCompleter(terms, self)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.search_edit.setCompleter(completer)

    def set_loading(self, loading: bool):
        self.state.loading = loading
        self.search_edit.searchButton.setDisabled(loading)
        self.convert_btn.setDisabled(loading)
        self.sort_box.setDisabled(loading)

    def clear_results(self):
        self._reset_drag_select_state()
        self.state.result_list.clear()
        self.state.selected_md5_set.clear()
        self.state.page_cursor = 1
        self.state.has_more_results = True
        self.state.has_loaded_once = False
        self.selection_count_changed.emit(0)
        while self.flow_layout.count():
            _delete_flow_item(self.flow_layout.takeAt(0))
        self.card_widgets.clear()

    def append_results(self, posts: list[DanbooruPost], downloaded_md5s: set[str]) -> list[DanbooruCardWidget]:
        appended_cards: list[DanbooruCardWidget] = []
        for post in posts:
            card = DanbooruCardWidget(
                post,
                already_downloaded=post.md5 in downloaded_md5s,
                parent=self.scroll_content,
                metrics=self.card_metrics,
            )
            card.selection_changed.connect(self._on_selection_changed)
            card.open_detail_requested.connect(self.detail_opened.emit)
            card.set_selected(post.md5 in self.state.selected_md5_set)
            self._install_drag_select_source(card)
            self._install_drag_select_source(card.preview_frame)
            self._install_drag_select_source(card.preview_button)
            self.flow_layout.addWidget(card)
            self.card_widgets[post.md5] = card
            appended_cards.append(card)
        self.state.result_list.extend(posts)
        self.selection_count_changed.emit(len(self.state.selected_md5_set))
        self.apply_theme()
        return appended_cards

    def set_card_metrics(self, metrics: DanbooruCardMetrics):
        self.card_metrics = metrics
        for card in self.card_widgets.values():
            card.apply_metrics(metrics)
        self.flow_layout.invalidate()
        self.scroll_content.adjustSize()
        self.scroll_content.updateGeometry()

    def _on_selection_changed(self, md5_value: str, selected: bool):
        if selected:
            self.state.selected_md5_set.add(md5_value)
        else:
            self.state.selected_md5_set.discard(md5_value)
        self.selection_count_changed.emit(len(self.state.selected_md5_set))

    def apply_downloaded_state(self, md5_value: str):
        card = self.card_widgets.get(md5_value)
        if card is not None:
            card.set_already_downloaded(True)
        self.state.selected_md5_set.discard(md5_value)
        self.selection_count_changed.emit(len(self.state.selected_md5_set))

    def _install_drag_select_source(self, widget: QWidget):
        widget.setProperty("danbooruDragSelectSource", True)
        widget.installEventFilter(self)

    def _viewport_point_from_global(self, global_pos: QtCore.QPoint) -> QtCore.QPoint:
        viewport = self.scroll_area.viewport()
        rect = viewport.rect()
        point = viewport.mapFromGlobal(global_pos)
        return QtCore.QPoint(
            min(max(point.x(), rect.left()), rect.right()),
            min(max(point.y(), rect.top()), rect.bottom()),
        )

    def _reset_drag_select_state(self):
        was_active = self._drag_select_active
        self._drag_select_origin = None
        self._drag_select_active = False
        self._drag_select_source = None
        if self._selection_band is not None:
            self._selection_band.hide()
        if was_active:
            QApplication.restoreOverrideCursor()

    def _begin_drag_select(self):
        if self._drag_select_active or self._drag_select_origin is None or self._selection_band is None:
            return
        self._drag_select_active = True
        self._selection_band.setGeometry(QtCore.QRect(self._drag_select_origin, QtCore.QSize()))
        self._selection_band.show()
        if isinstance(self._drag_select_source, QPushButton):
            self._drag_select_source.setDown(False)
        QApplication.setOverrideCursor(Qt.CrossCursor)

    def _update_drag_select_band(self, global_pos: QtCore.QPoint):
        if self._selection_band is None or self._drag_select_origin is None:
            return
        self._selection_band.setGeometry(
            QtCore.QRect(self._drag_select_origin, self._viewport_point_from_global(global_pos)).normalized()
        )

    def _apply_drag_selection(self, selection_rect: QtCore.QRect):
        if selection_rect.width() < 5 and selection_rect.height() < 5:
            return
        viewport = self.scroll_area.viewport()
        for card in self.card_widgets.values():
            if not card.checkbox.isEnabled():
                continue
            card_rect = QtCore.QRect(card.mapTo(viewport, QtCore.QPoint(0, 0)), card.size())
            if selection_rect.intersects(card_rect):
                card.set_selected(True)

    def eventFilter(self, obj, event):
        if not bool(getattr(obj, "property", lambda *_args: False)("danbooruDragSelectSource")):
            return super().eventFilter(obj, event)
        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            if event.button() != Qt.LeftButton:
                return super().eventFilter(obj, event)
            self._drag_select_origin = self._viewport_point_from_global(event.globalPos())
            self._drag_select_active = False
            self._drag_select_source = obj
            return False
        if event_type == QtCore.QEvent.MouseMove:
            if self._drag_select_origin is None:
                return super().eventFilter(obj, event)
            current_point = self._viewport_point_from_global(event.globalPos())
            if not self._drag_select_active:
                if (current_point - self._drag_select_origin).manhattanLength() < QApplication.startDragDistance():
                    return False
                self._begin_drag_select()
            self._update_drag_select_band(event.globalPos())
            return True
        if event_type == QtCore.QEvent.MouseButtonRelease:
            if self._drag_select_origin is None:
                return super().eventFilter(obj, event)
            selection_rect = self._selection_band.geometry() if self._selection_band is not None else QtCore.QRect()
            drag_was_active = self._drag_select_active
            self._reset_drag_select_state()
            if drag_was_active:
                self._apply_drag_selection(selection_rect)
                return True
            return False
        return super().eventFilter(obj, event)


class DanbooruInterface(QFrame):
    download_result_signal = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("DanbooruInterface")
        self.task_mgr = AsyncTaskManager(self)
        self.tab_counter = 0
        self.tabs: dict[str, DanbooruTabWidget] = {}
        self.tab_states: dict[str, DanbooruTabState] = {}
        self._tab_tips: dict[str, tuple[str, str]] = {}
        self.sql_recorder = create_danbooru_sql_recorder()
        self.image_viewer = DanbooruImageViewer(parent)
        self.search_controller = DanbooruSearchController(self)
        self.download_controller = DanbooruDownloadController(self)
        self._viewer_tab_id: t.Optional[str] = None
        self._card_zoom_index = DEFAULT_CARD_ZOOM_INDEX
        self._viewer_pixmap_cache: dict[int, QPixmap] = {}
        self._viewer_size_cache: dict[int, QtCore.QSize] = {}
        self._viewer_prefetching_post_ids: set[int] = set()
        self.download_result_signal.connect(self.download_controller.on_download_result)
        self.image_viewer.tag_clicked.connect(self._open_tag_jump_tab)
        self.image_viewer.download_requested.connect(self.download_controller.submit_single)
        self.image_viewer.previous_requested.connect(lambda: self._open_adjacent_viewer_post(-1))
        self.image_viewer.next_requested.connect(lambda: self._open_adjacent_viewer_post(1))
        self.image_viewer.closed.connect(self._clear_viewer_context)
        theme_mgr.subscribe(self._apply_theme)
        self.setupUi()
        self._apply_theme()
        self.create_tab()

    def setupUi(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 14)
        self.main_layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 20, 0)
        title_row.setSpacing(4)
        self.title_block = QWidget(self)
        self.title_block.setObjectName("DanbooruTitleBlock")
        title_block_layout = QHBoxLayout(self.title_block)
        title_block_layout.setContentsMargins(16, 12, 16, 12)
        title_block_layout.setSpacing(16)
        self.title_label = SubtitleLabel("Danbooru", self)
        self.tip_line = StrongBodyLabel("", self)
        self.tip_line.setTextFormat(Qt.RichText)
        self.tip_line.setObjectName("DanbooruTipLine")
        title_block_layout.addWidget(self.title_label)
        title_block_layout.addWidget(self.tip_line, 1)
        zoomBtnGroup = QVBoxLayout()
        zoomBtnGroup.setContentsMargins(2,0,2,0)
        zoomBtnGroup.setSpacing(0)
        self.zoomIn = ToolButton(QIcon(':/script/zoomin.svg'))
        self.zoomIn.setToolTip("放大卡片")
        self.zoomIn.setMaximumHeight(22)
        self.zoomOut = ToolButton(QIcon(':/script/zoomout.svg'))
        self.zoomOut.setToolTip("缩小卡片")
        self.zoomOut.setMaximumHeight(22)
        self.zoomIn.clicked.connect(self._zoom_in_cards)
        self.zoomOut.clicked.connect(self._zoom_out_cards)
        zoomBtnGroup.addWidget(self.zoomIn)
        zoomBtnGroup.addWidget(self.zoomOut)
        self.openBtn = ToolButton(FIF.FOLDER)
        self.openBtn.setToolTip("打开下载目录")
        self.openBtn.setMinimumHeight(50)
        self.openBtn.clicked.connect(self._open_save_path)
        self.batch_download_btn = PrimaryToolButton(FIF.DOWNLOAD, self)
        self.batch_download_btn.setMinimumHeight(50)
        self.batch_download_btn.setMinimumWidth(80)
        self.batch_download_btn.setDisabled(True)
        self.batch_download_btn.clicked.connect(self.download_controller.submit_selected)
        self.batch_download_badge = CountBadge(parent=self, target=self.batch_download_btn)
        self.batch_download_badge.hide()
        title_row.addWidget(self.title_block, 1)
        title_row.addLayout(zoomBtnGroup)
        title_row.addWidget(self.openBtn)
        title_row.addWidget(self.batch_download_btn)
        self.main_layout.addLayout(title_row)

        self.pivot_shell = QFrame(self)
        self.pivot_shell.setObjectName("DanbooruPivotShell")
        self.pivot_shell.setMinimumHeight(34)
        pivot_shell_layout = QHBoxLayout(self.pivot_shell)
        pivot_shell_layout.setContentsMargins(14, 2, 14, 2)
        pivot_shell_layout.setSpacing(8)
        self.pivot_back_btn = TransparentToolButton(FIF.LEFT_ARROW, self.pivot_shell)
        self.pivot_back_btn.setObjectName("DanbooruPivotScrollButton")
        self.pivot_back_btn.setFixedSize(18, 18)
        self.pivot_back_btn.setIconSize(QtCore.QSize(14, 14))
        self.pivot_back_btn.setToolTip("向左滚动标签")
        self.pivot_back_btn.clicked.connect(lambda: self._scroll_pivot_tabs(-1))
        pivot_shell_layout.addWidget(self.pivot_back_btn, 0, Qt.AlignVCenter)
        self.tab_bar = TabBar(self.pivot_shell)
        self.tab_bar.setObjectName("DanbooruPivotScrollArea")
        self.tab_bar.view.setObjectName("DanbooruPivotTabBarView")
        self.tab_bar.setAddButtonVisible(False)
        self.tab_bar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.ON_HOVER)
        self.tab_bar.setTabShadowEnabled(False)
        self.tab_bar.setTabMaximumWidth(148)
        self.tab_bar.setTabMinimumWidth(96)
        self.tab_bar.enableTransparentBackground()
        self.tab_bar.itemLayout.setContentsMargins(0, 5, 0, 5)
        self.tab_bar.itemLayout.setSpacing(6)
        self.pivot_scroll = self.tab_bar
        self.tab_bar.currentChanged.connect(self._on_tabbar_index_changed)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        pivot_shell_layout.addWidget(self.tab_bar, 1)
        self.pivot_forward_btn = TransparentToolButton(FIF.RIGHT_ARROW, self.pivot_shell)
        self.pivot_forward_btn.setObjectName("DanbooruPivotScrollButton")
        self.pivot_forward_btn.setFixedSize(18, 18)
        self.pivot_forward_btn.setIconSize(QtCore.QSize(14, 14))
        self.pivot_forward_btn.setToolTip("向右滚动标签")
        self.pivot_forward_btn.clicked.connect(lambda: self._scroll_pivot_tabs(1))
        pivot_shell_layout.addWidget(self.pivot_forward_btn, 0, Qt.AlignVCenter)
        pivot_scroll_bar = self.pivot_scroll.horizontalScrollBar()
        pivot_scroll_bar.rangeChanged.connect(lambda *_args: self._sync_pivot_scroll_controls())
        pivot_scroll_bar.valueChanged.connect(lambda *_args: self._sync_pivot_scroll_controls())
        self.main_layout.addWidget(self.pivot_shell)

        self.content_shell = QFrame(self)
        self.content_shell.setObjectName("DanbooruContentShell")
        content_shell_layout = QVBoxLayout(self.content_shell)
        content_shell_layout.setContentsMargins(12, 12, 12, 12)
        content_shell_layout.setSpacing(0)
        self.stacked_widget = QStackedWidget(self.content_shell)
        self.stacked_widget.currentChanged.connect(self._on_current_tab_changed)
        content_shell_layout.addWidget(self.stacked_widget)
        self.main_layout.addWidget(self.content_shell, 1)

    def _apply_theme(self, *_args):
        palette = DanbooruUiPalette.current()
        self.setStyleSheet(build_interface_stylesheet(palette))
        self.title_label.setStyleSheet(build_title_label_stylesheet(palette))
        self.tip_line.setStyleSheet(build_tip_line_stylesheet(palette))
        self.tab_bar.setTabShadowEnabled(False)
        selected_color = qcolor_from_css(palette.pivot_selected)
        self.tab_bar.setTabSelectedBackgroundColor(selected_color, selected_color)
        self.image_viewer.apply_theme()
        for tab in self.tabs.values():
            tab.apply_theme()
        self._update_tab_chrome()
        self._sync_tip_line()
        self._update_zoom_buttons()
        self._sync_tab_bar_width()

    def create_tab(self, initial_query: str = "", auto_search: bool = False):
        self.tab_counter += 1
        tab_id = f"danbooru-tab-{self.tab_counter}"
        state = DanbooruTabState(
            tab_id=tab_id,
            title=self._display_title_for_query(initial_query, self.tab_counter),
            query=canonicalize_search_term(initial_query),
        )
        tab = DanbooruTabWidget(state, self)
        tab.setObjectName(tab_id)
        tab.set_card_metrics(self._current_card_metrics())
        tab.request_search.connect(lambda query, _reset, tid=tab_id: self.search_controller.start_search(tid, query))
        tab.request_conversion.connect(lambda tid=tab_id: self.search_controller.convert_term(tid))
        tab.request_single_download.connect(lambda post, tid=tab_id: self.download_controller.submit_single(post, tid))
        tab.request_tag_jump.connect(self._open_tag_jump_tab)
        tab.request_next_page.connect(lambda tid=tab_id: self.search_controller.load_next_page(tid))
        tab.detail_opened.connect(lambda post, tid=tab_id: self._open_viewer(tid, post))
        tab.selection_count_changed.connect(lambda _count, tid=tab_id: self._update_batch_button(tid))
        tab.search_edit.textChanged.connect(lambda _text, current_tab=tab: self._update_favorite_button_state(current_tab))
        self.tabs[tab_id] = tab
        self.tab_states[tab_id] = state
        self._tab_tips[tab_id] = (DEFAULT_TAB_STATUS_TEXT, DEFAULT_TAB_STATUS_CLASS)
        self.stacked_widget.addWidget(tab)
        self.tab_bar.addTab(routeKey=tab_id, text=state.title)
        self._sync_tab_bar_width()
        self._set_current_tab(tab_id)
        self._update_tab_chrome()
        self._refresh_completer(tab)
        if state.query:
            tab.search_edit.setText(state.query)
            if auto_search:
                self.search_controller.start_search(tab_id, state.query)
        if self._active_tab_id() == tab_id:
            self._sync_tip_line(tab_id)
        return tab_id

    def close_current_tab(self):
        self._close_tab_by_id(self._active_tab_id())

    def _close_tab_by_id(self, tab_id: t.Optional[str]):
        if len(self.tabs) <= 1:
            return
        if not tab_id:
            return
        tab = self.tabs.pop(tab_id, None)
        self.tab_states.pop(tab_id, None)
        self._tab_tips.pop(tab_id, None)
        if tab is None:
            return
        if self._viewer_tab_id == tab_id and self.image_viewer.isVisible():
            self.image_viewer.hide()
            self._viewer_tab_id = None
        self.tab_bar.removeTabByKey(tab_id)
        self.stacked_widget.removeWidget(tab)
        tab.deleteLater()
        if self.stacked_widget.count():
            self._set_current_tab(self.stacked_widget.widget(0).objectName())
        self._update_tab_chrome()
        self._sync_tab_bar_width()

    def _set_current_tab(self, tab_id: str):
        tab = self.tabs.get(tab_id)
        if tab is None:
            return
        self.stacked_widget.setCurrentWidget(tab)
        self.tab_bar.setCurrentTab(tab_id)
        self._update_batch_button(tab_id)

    def _on_current_tab_changed(self, _index: int):
        widget = self.stacked_widget.currentWidget()
        if widget is None:
            return
        self.tab_bar.setCurrentTab(widget.objectName())
        self._update_batch_button(widget.objectName())
        self._update_tab_chrome()
        self._sync_tip_line(widget.objectName())

    def _on_tabbar_index_changed(self, index: int):
        tab_id = self._tab_id_at(index)
        if tab_id:
            self._set_current_tab(tab_id)

    def _on_tab_close_requested(self, index: int):
        self._close_tab_by_id(self._tab_id_at(index))

    def _tab_id_at(self, index: int) -> t.Optional[str]:
        if not 0 <= index < self.tab_bar.count():
            return None
        return self.tab_bar.tabItem(index).routeKey()

    def _tab_index(self, tab_id: str) -> int:
        item = self.tab_bar.tab(tab_id)
        return self.tab_bar.items.index(item) if item is not None else -1

    @staticmethod
    def _display_title_for_query(query: str, tab_index: int) -> str:
        canonical = canonicalize_search_term(query)
        if not canonical:
            return f"工作区 {tab_index}"
        if len(canonical) <= 18:
            return canonical
        return canonical[:16].rstrip() + ".."

    def _update_tab_title(self, tab_id: str, query: str):
        state = self.tab_states.get(tab_id)
        if state is None:
            return
        title = self._display_title_for_query(query, int(tab_id.rsplit("-", 1)[-1]))
        if title == state.title:
            return
        state.title = title
        index = self._tab_index(tab_id)
        if index >= 0:
            self.tab_bar.setTabText(index, state.title)
        self._update_tab_chrome()
        self._sync_tab_bar_width()

    def _update_tab_chrome(self):
        palette = DanbooruUiPalette.current()
        current_tab_id = self._active_tab_id()
        active_text_color = qcolor_from_css(palette.text)
        inactive_text_color = qcolor_from_css(palette.muted_text)
        self.tab_bar.setTabsClosable(len(self.tabs) > 1)
        for index in range(self.tab_bar.count()):
            item = self.tab_bar.tabItem(index)
            if item is None:
                continue
            tab_id = item.routeKey()
            state = self.tab_states.get(tab_id)
            item.setBorderRadius(12)
            self.tab_bar.setTabToolTip(index, state.title if state is not None else item.text())
            self.tab_bar.setTabTextColor(
                index,
                active_text_color if tab_id == current_tab_id else inactive_text_color,
            )

    def _active_tab_id(self) -> t.Optional[str]:
        widget = self.stacked_widget.currentWidget()
        return widget.objectName() if widget is not None else None

    def _set_tab_tip(self, tab_id: str, text: str, cls: str = DEFAULT_TAB_STATUS_CLASS):
        self._tab_tips[tab_id] = (text, cls or DEFAULT_TAB_STATUS_CLASS)
        if self._active_tab_id() == tab_id:
            self.tip_line.setText(_format_tip_rich_text(*self._tab_tips[tab_id]))

    def _sync_tip_line(self, tab_id: t.Optional[str] = None):
        effective_tab_id = tab_id or self._active_tab_id()
        text, cls = self._tab_tips.get(effective_tab_id, (DEFAULT_TAB_STATUS_TEXT, DEFAULT_TAB_STATUS_CLASS))
        self.tip_line.setText(_format_tip_rich_text(text, cls))

    def _current_card_metrics(self) -> DanbooruCardMetrics:
        return CARD_ZOOM_METRICS[self._card_zoom_index]

    def _apply_card_metrics(self):
        metrics = self._current_card_metrics()
        for tab in self.tabs.values():
            tab.set_card_metrics(metrics)
        self._update_zoom_buttons()

    def _zoom_in_cards(self):
        if self._card_zoom_index >= len(CARD_ZOOM_METRICS) - 1:
            return
        self._card_zoom_index += 1
        self._apply_card_metrics()

    def _zoom_out_cards(self):
        if self._card_zoom_index <= 0:
            return
        self._card_zoom_index -= 1
        self._apply_card_metrics()

    def _update_zoom_buttons(self):
        self.zoomIn.setEnabled(self._card_zoom_index < len(CARD_ZOOM_METRICS) - 1)
        self.zoomOut.setEnabled(self._card_zoom_index > 0)

    def _scroll_pivot_tabs(self, direction: int):
        bar = self.pivot_scroll.horizontalScrollBar()
        if bar.maximum() <= bar.minimum():
            return
        step = max(72, int(self.pivot_scroll.viewport().width() * 0.72))
        bar.setValue(bar.value() + direction * step)

    def _sync_pivot_scroll_controls(self):
        if not hasattr(self, "pivot_scroll"):
            return
        bar = self.pivot_scroll.horizontalScrollBar()
        has_overflow = bar.maximum() > bar.minimum()
        self.pivot_back_btn.setEnabled(has_overflow and bar.value() > bar.minimum())
        self.pivot_forward_btn.setEnabled(has_overflow and bar.value() < bar.maximum())

    def _sync_tab_bar_width(self):
        if not hasattr(self, "tab_bar"):
            return
        self.tab_bar.view.adjustSize()
        self.tab_bar.updateGeometry()
        QtCore.QTimer.singleShot(0, self._sync_pivot_scroll_controls)

    def _open_save_path(self):
        curr_os.open_folder(Path(DanbooruRuntimeConfig.from_conf().save_path))

    def _update_batch_button(self, tab_id: str):
        if self._active_tab_id() != tab_id:
            return
        state = self.tab_states.get(tab_id)
        count = len(state.selected_md5_set) if state else 0
        self.batch_download_btn.setDisabled(count == 0)
        if count <= 0:
            self.batch_download_badge.hide()
            return
        self.batch_download_badge.set_count(count)
        self.batch_download_badge.show()

    def _gui_logger(self):
        return getattr(getattr(self.parent_window, "gui", None), "log", None)

    def _log_search_request(self, tab_id: str, query: str, order: str, page: int, limit: int):
        logger = self._gui_logger()
        if logger is None:
            return
        params = build_danbooru_search_params(query, order=order, page=page, limit=limit)
        logger.info(f"[Danbooru] GET /posts.json tab={tab_id} params={params}")

    def _update_favorite_button_state(self, tab: DanbooruTabWidget, term: t.Optional[str] = None):
        canonical_term = canonicalize_search_term(term if term is not None else tab.search_edit.text())
        is_favorited = bool(canonical_term and canonical_term in danbooru_cfg.get_favorites())
        tab.favorite_btn.setToolTip("取消收藏搜索词" if is_favorited else "收藏搜索词")

    def _refresh_completer(self, tab: DanbooruTabWidget):
        history = danbooru_cfg.get_history()
        favorites = sorted(danbooru_cfg.get_favorites() - set(history))
        tab.update_completer(history + favorites)
        try:
            tab.favorite_btn.clicked.disconnect()
        except TypeError:
            pass
        tab.favorite_btn.clicked.connect(lambda _=False, tid=tab.state.tab_id: self._toggle_favorite(tid))
        self._update_favorite_button_state(tab)

    def _show_info(self, factory, content: str, duration: int = 3000):
        factory(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=self,
        )

    def _toggle_favorite(self, tab_id: str):
        tab = self.tabs.get(tab_id)
        if tab is None:
            return
        term = canonicalize_search_term(tab.search_edit.text())
        if not term:
            self._update_favorite_button_state(tab, term)
            return
        is_favorited = danbooru_cfg.toggle_favorite(term)
        self._refresh_completer(tab)
        self._update_favorite_button_state(tab, term)
        self._show_info(InfoBar.success if is_favorited else InfoBar.warning, f"{'已收藏' if is_favorited else '已取消收藏'}搜索词: {term}")

    def _open_tag_jump_tab(self, tag: str):
        self.image_viewer.hide()
        self._viewer_tab_id = None
        canonical_tag = canonicalize_search_term(tag)
        if not canonical_tag:
            return
        for tab_id, state in self.tab_states.items():
            if canonicalize_search_term(state.query) == canonical_tag:
                self._set_current_tab(tab_id)
                tab = self.tabs.get(tab_id)
                if tab is not None and not state.result_list and not state.loading:
                    self.search_controller.start_search(tab_id, canonical_tag)
                return
        active_tab_id = self._active_tab_id()
        active_state = self.tab_states.get(active_tab_id) if active_tab_id else None
        if active_tab_id and active_state and not active_state.query and not active_state.result_list and not active_state.loading:
            active_state.query = canonical_tag
            self.tabs[active_tab_id].search_edit.setText(canonical_tag)
            self.search_controller.start_search(active_tab_id, canonical_tag)
            return
        self.create_tab(initial_query=canonical_tag, auto_search=True)

    def _clear_viewer_context(self):
        self._viewer_tab_id = None

    @staticmethod
    def _detail_preview_url(post: DanbooruPost) -> t.Optional[str]:
        return post.large_file_url or post.file_url or post.preview_file_url

    @staticmethod
    def _detail_preview_error_message(post: DanbooruPost, error: str) -> str:
        first_line = (error or "").splitlines()[0].strip()
        ext = normalize_file_ext(post.file_ext)
        if is_unsupported_media_type(ext):
            return f"Preview Error\n原因: Viewer 暂不支持 {ext.upper()} 预览，请下载后在外部打开"
        if not DanbooruInterface._detail_preview_url(post):
            return "Preview Error\n原因: 当前条目没有可用的预览地址"
        if first_line == "invalid image data":
            media_hint = ext.upper() if ext else "未知格式"
            return f"Preview Error\n原因: 返回内容不是可渲染图片，当前资源格式为 {media_hint}"
        if first_line:
            return f"Preview Error\n原因: {first_line}"
        return "Preview Error\n原因: 未知错误"

    def _open_viewer(self, tab_id: str, post: DanbooruPost):
        tab = self.tabs.get(tab_id)
        card = tab.card_widgets.get(post.md5) if tab is not None else None
        already_downloaded = card.already_downloaded if card is not None else self.sql_recorder.check_dupe(post.md5)
        self._viewer_tab_id = tab_id
        cached_size = self._viewer_size_cache.get(post.post_id)
        if cached_size is not None:
            post.preview_width = cached_size.width()
            post.preview_height = cached_size.height()
        self.image_viewer.show_post(post, already_downloaded)
        self._sync_viewer_navigation()
        cached_pixmap = self._viewer_pixmap_cache.get(post.post_id)
        if cached_pixmap is not None and not cached_pixmap.isNull():
            self.image_viewer.set_image(post.post_id, cached_pixmap)
            self._preload_next_viewer_post(post)
            return
        if DanbooruImageViewer._post_size_hint(post) is None:
            self._probe_detail_preview_size(tab_id, post)
        self._load_detail_preview(tab_id, post)

    def _viewer_posts(self) -> list[DanbooruPost]:
        if not self._viewer_tab_id:
            return []
        state = self.tab_states.get(self._viewer_tab_id)
        return list(state.result_list) if state is not None else []

    def _viewer_post_index(self) -> int:
        if self.image_viewer.post is None:
            return -1
        current_md5 = self.image_viewer.post.md5
        for index, post in enumerate(self._viewer_posts()):
            if post.md5 == current_md5:
                return index
        return -1

    def _sync_viewer_navigation(self):
        posts = self._viewer_posts()
        index = self._viewer_post_index()
        self.image_viewer.set_navigation_enabled(index > 0, 0 <= index < len(posts) - 1)

    def _open_adjacent_viewer_post(self, step: int):
        posts = self._viewer_posts()
        index = self._viewer_post_index()
        target_index = index + step
        if index < 0 or target_index < 0 or target_index >= len(posts):
            return
        self._open_viewer(self._viewer_tab_id, posts[target_index])

    def _preload_next_viewer_post(self, current_post: t.Optional[DanbooruPost] = None):
        if not self._viewer_tab_id:
            return
        posts = self._viewer_posts()
        if not posts:
            return
        anchor = current_post or self.image_viewer.post
        if anchor is None:
            return
        for index, post in enumerate(posts):
            if post.md5 != anchor.md5:
                continue
            target_index = index + 1
            if target_index >= len(posts):
                return
            self._prefetch_detail_preview(self._viewer_tab_id, posts[target_index])
            return

    def _prefetch_detail_preview(self, tab_id: str, post: DanbooruPost):
        if post.post_id in self._viewer_pixmap_cache or post.post_id in self._viewer_prefetching_post_ids:
            return
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            return
        self._viewer_prefetching_post_ids.add(post.post_id)
        self.task_mgr.execute_simple_task(
            lambda: _fetch_pixmap(preview_url, 0),
            success_callback=lambda raw, pid=post.post_id: self._handle_detail_prefetch_success(pid, raw),
            error_callback=lambda err, current_post=post: self._handle_detail_prefetch_error(current_post, err),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-detail-prefetch-{tab_id}-{post.post_id}",
        )

    def _load_detail_preview(self, tab_id: str, post: DanbooruPost):
        preview_url = self._detail_preview_url(post)
        if not preview_url:
            if self.image_viewer.post is not None and self.image_viewer.post.post_id == post.post_id:
                self.image_viewer.set_placeholder(self._detail_preview_error_message(post, "no preview url"))
            return
        self.task_mgr.execute_simple_task(
            lambda: _fetch_pixmap(preview_url, 0),
            success_callback=lambda raw, pid=post.post_id, current_post=post: self._apply_detail_preview(pid, raw, current_post),
            error_callback=lambda err, pid=post.post_id, current_post=post: self._handle_detail_preview_error(pid, current_post, err),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-detail-preview-{tab_id}-{post.post_id}",
        )

    def _probe_detail_preview_size(self, tab_id: str, post: DanbooruPost):
        preview_url = post.large_file_url or post.file_url or post.preview_file_url
        if not preview_url:
            return
        self.task_mgr.execute_simple_task(
            lambda: _run_async(fetch_remote_image_size(preview_url)),
            success_callback=lambda size, pid=post.post_id: self._apply_detail_preview_size(pid, size),
            error_callback=lambda err, pid=post.post_id: self._log_detail_size_probe_error(pid, err),
            show_success_info=False,
            show_error_info=False,
            show_tooltip=False,
            task_id=f"danbooru-detail-size-{tab_id}-{post.post_id}",
        )

    def _apply_detail_preview_size(self, post_id: int, size: t.Optional[tuple[int, int]]):
        if not size:
            return
        qsize = QtCore.QSize(*size)
        cached_size = self._viewer_size_cache.get(post_id)
        if cached_size is None or (qsize.width() * qsize.height()) > (cached_size.width() * cached_size.height()):
            self._viewer_size_cache[post_id] = qsize
        self.image_viewer.set_placeholder_size(post_id, qsize)

    def _log_detail_size_probe_error(self, post_id: int, error: str):
        logger = self._gui_logger()
        if logger is not None:
            logger.warning(f"[Danbooru] detail size probe failed post_id={post_id}: {error}")

    def _log_detail_prefetch_error(self, post: DanbooruPost, error: str):
        logger = self._gui_logger()
        if logger is not None:
            logger.warning(f"[Danbooru] detail prefetch failed post_id={post.post_id}: {error}")

    def _handle_detail_prefetch_success(self, post_id: int, raw: bytes):
        self._viewer_prefetching_post_ids.discard(post_id)
        self._apply_detail_preview(post_id, raw)

    def _handle_detail_prefetch_error(self, post: DanbooruPost, error: str):
        self._viewer_prefetching_post_ids.discard(post.post_id)
        self._log_detail_prefetch_error(post, error)

    def _apply_detail_preview(self, post_id: int, raw: bytes, current_post: t.Optional[DanbooruPost] = None):
        pixmap = QPixmap()
        pixmap.loadFromData(raw, "PNG")
        if not pixmap.isNull():
            self._viewer_pixmap_cache[post_id] = pixmap
            pixmap_size = QtCore.QSize(pixmap.width(), pixmap.height())
            cached_size = self._viewer_size_cache.get(post_id)
            if cached_size is None or (pixmap_size.width() * pixmap_size.height()) > (cached_size.width() * cached_size.height()):
                self._viewer_size_cache[post_id] = pixmap_size
            is_current_post = self.image_viewer.post is not None and self.image_viewer.post.post_id == post_id
            self.image_viewer.set_image(post_id, pixmap)
            if is_current_post:
                self._preload_next_viewer_post(current_post)

    def _handle_detail_preview_error(self, post_id: int, post: DanbooruPost, error: str):
        logger = self._gui_logger()
        if logger is not None:
            logger.error(f"[Danbooru] detail preview failed post_id={post_id}: {error}")
        if self.image_viewer.post is not None and self.image_viewer.post.post_id == post_id:
            self.image_viewer.set_placeholder(self._detail_preview_error_message(post, error))

    def notify_download_result(self, md5_value: str, success: bool):
        self.download_result_signal.emit(md5_value, success)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_tab_bar_width()

    def closeEvent(self, event):
        try:
            theme_mgr.unsubscribe(self._apply_theme)
            self.image_viewer.hide()
            self.sql_recorder.close()
        finally:
            super().closeEvent(event)
