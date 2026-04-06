import sys
import typing as t

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon as FIF, PrimaryToolButton, PushButton, ScrollArea, TransparentToggleToolButton, TransparentToolButton
from qframelesswindow.utils import startSystemMove

from GUI.core.timer import safe_single_shot
from GUI.uic.qfluent.components import FlexImageLabel
from utils.script.image.danbooru.models import DanbooruPost

from .core import DanbooruViewerFitCalculator, DanbooruViewerFitResult, delete_flow_item as _delete_flow_item
from .style import DanbooruUiPalette, build_viewer_stylesheet

def _iter_tag_groups(post: DanbooruPost) -> list[tuple[str, list[str]]]:
    groups = [
        ("Character", list(filter(None, post.tag_string_character.split(" ")))),
        ("Artist", list(filter(None, post.tag_string_artist.split(" ")))),
        ("Copyright", list(filter(None, post.tag_string_copyright.split(" ")))),
        ("General", list(filter(None, post.tag_string_general.split(" ")))),
    ]
    return [(label, tags) for label, tags in groups if tags]

class DanbooruImageViewer(QWidget):
    tag_clicked = Signal(str)
    download_requested = Signal(object)
    previous_requested = Signal()
    next_requested = Signal()
    closed = Signal()

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
        self.previous_btn.clicked.connect(self.previous_requested.emit)
        self.next_btn = TransparentToolButton(FIF.RIGHT_ARROW, self.frame)
        self.next_btn.setFixedSize(34, 34)
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
                startSystemMove(self, event.globalPosition().toPoint())
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
        downloadable = self.post is not None and DanbooruPost.is_supported_file_ext(self.post.file_ext) and not self._already_downloaded
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
