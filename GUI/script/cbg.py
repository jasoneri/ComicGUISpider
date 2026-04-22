from __future__ import annotations

import typing as t
from pathlib import Path

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QVBoxLayout, QRubberBand, QSizePolicy, QStackedWidget, QWidget
from qfluentwidgets import (
    CompactSpinBox, FlowLayout, FluentIcon as FIF, ImageLabel, InfoBar, InfoBarPosition, PrimaryToolButton, TransparentToolButton,
    PushSettingCard, ScrollArea, StrongBodyLabel, TogglePushButton, ToolButton, TeachingTipTailPosition, LineEdit
)

from GUI.manager.async_task import AsyncTaskManager
from GUI.core.theme import CustTheme, theme_mgr
from GUI.core.theme.qss_template import read_templated_qss_tokens, render_templated_qss_section
from GUI.script.danbooru.style import DEFAULT_CARD_METRICS, DanbooruCardMetrics
from GUI.uic.qfluent.components import CustomInfoBar, CustomTeachingTip
from utils import ori_path, conf, conf_dir
from utils.config.qc import cbg_cfg
from utils.script.cbg import (
    ALLOWED_RANDOM_COUNTS,
    build_userscript,
    canonicalize_random_count,
    import_cbg_api_bundle,
    normalize_path,
    pick_random_paths,
    scan_png_files,
    unique_paths,
)


_TEMPLATE_PATH = ori_path.joinpath("assets/cbg_sample.js")
_CBG_QSS_PATH = ori_path.joinpath("GUI/core/theme/cbg.qss")
_TAMPERMONKEY_URL = "https://www.tampermonkey.net/index.php"
_CBG_SPONSOR_URL = "https://app.unifans.io/c/jsoneri"
_CARD_CONTENT_MARGIN = 4
_CARD_PREVIEW_RADIUS = 16.0


def _current_theme_name() -> str:
    return "dark" if theme_mgr.get_theme() == CustTheme.DARK else "light"


def _get_cbg_qss_tokens() -> dict[str, str]:
    return read_templated_qss_tokens(_CBG_QSS_PATH, _current_theme_name())


def _build_cbg_interface_stylesheet() -> str:
    return render_templated_qss_section(_CBG_QSS_PATH, _current_theme_name(), "interface")


def _delete_flow_item(item) -> None:
    if item is None:
        return
    if isinstance(item, QWidget):
        item.deleteLater()
        return
    widget = item.widget() if hasattr(item, "widget") else None
    if widget is not None:
        widget.deleteLater()


class CbgPathCard(PushSettingCard):
    path_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__("选择目录", FIF.FOLDER, "PNG 目录", "未选择", parent)
        self.setObjectName("CbgPathCard")
        self._current_path = ""
        self.clicked.connect(self._select_folder)

    def set_path(self, path_text: str) -> None:
        normalized = str(path_text or "").strip()
        self._current_path = normalized
        self.setContent(normalized or "未选择")

    def _select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 Cbg PNG 目录", self._current_path or "")
        if not folder:
            return
        self.set_path(folder)
        self.path_selected.emit(folder)


class CbgRandomCountSpinBox(CompactSpinBox):
    def __init__(self, initial_value: object, parent=None):
        super().__init__(parent)
        self.setRange(ALLOWED_RANDOM_COUNTS[0], ALLOWED_RANDOM_COUNTS[-1])
        self.setSingleStep(5)
        self.setValue(canonicalize_random_count(initial_value))
        self.editingFinished.connect(self._snap_to_allowed)

    def _snap_to_allowed(self) -> None:
        normalized = canonicalize_random_count(self.value())
        if normalized == self.value():
            return
        self.blockSignals(True)
        self.setValue(normalized)
        self.blockSignals(False)


class CbgCardWidget(QFrame):
    selection_changed = Signal(object, bool)

    def __init__(self, path: Path, parent=None, metrics: DanbooruCardMetrics = DEFAULT_CARD_METRICS):
        super().__init__(parent)
        self.path = path.resolve()
        self.metrics = metrics
        self._selected = False
        self._preview_pixmap = QPixmap()
        self._preview_size = self._derive_preview_size()
        self.preview_height = self._preview_size.height()
        self.setObjectName(f"CbgCard_{self.path.stem}")
        self.setToolTip(str(self.path))
        self._setup_ui()
        self._load_preview()
        self.apply_theme()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("cbgCard", True)
        self.setProperty("selected", self._selected)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_CARD_CONTENT_MARGIN, _CARD_CONTENT_MARGIN, _CARD_CONTENT_MARGIN, _CARD_CONTENT_MARGIN)
        layout.setSpacing(0)

        self.preview_frame = QFrame(self)
        self.preview_frame.setObjectName("CbgCardPreviewFrame")
        self.preview_frame.setProperty("cbgPreviewFrame", True)
        self.preview_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.preview_frame.setCursor(Qt.PointingHandCursor)
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.preview_label = ImageLabel(self.preview_frame)
        self.preview_label.setObjectName("CbgCardPreview")
        self.preview_label.setBorderRadius(
            int(_CARD_PREVIEW_RADIUS),
            int(_CARD_PREVIEW_RADIUS),
            int(_CARD_PREVIEW_RADIUS),
            int(_CARD_PREVIEW_RADIUS),
        )
        self.preview_label.setCursor(Qt.PointingHandCursor)
        self.preview_label.clicked.connect(self._toggle_selection)
        self.preview_label.setAttribute(Qt.WA_TranslucentBackground, True)
        preview_layout.addWidget(self.preview_label)

        layout.addWidget(self.preview_frame, 0, Qt.AlignLeft | Qt.AlignTop)

        self._sync_geometry()

    def _source_preview_size(self) -> QtCore.QSize:
        if not self._preview_pixmap.isNull():
            return self._preview_pixmap.size()
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

    def _toggle_selection(self) -> None:
        self.set_selected(not self._selected, emit_signal=True)

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool, *, emit_signal: bool = False) -> None:
        selected = bool(selected)
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", selected)
        self.apply_theme()
        if emit_signal:
            self.selection_changed.emit(self, selected)

    def set_preview_pixmap(self, pixmap: QPixmap) -> None:
        self._preview_pixmap = QPixmap(pixmap)
        self._sync_geometry()
        self._apply_preview_icon()

    def _preview_target_size(self) -> QtCore.QSize:
        return QtCore.QSize(self.preview_width, max(1, self.preview_height))

    def _build_preview_icon(self) -> QPixmap:
        if self._preview_pixmap.isNull():
            return QPixmap()
        return QPixmap(self._preview_pixmap)

    def _apply_preview_icon(self) -> None:
        preview = self._build_preview_icon()
        self.preview_label.setImage(preview)
        if preview.isNull():
            self.preview_label.setFixedSize(self._preview_target_size())
            return
        self.preview_label.setScaledSize(self._preview_target_size())

    def _load_preview(self) -> None:
        reader = QImageReader(str(self.path))
        if not reader.canRead():
            return
        reader.setAutoTransform(True)
        source_size = reader.size()
        if source_size.isValid():
            reader.setScaledSize(source_size.scaled(self._preview_target_size(), Qt.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            return
        self.set_preview_pixmap(QPixmap.fromImage(image))

    def _sync_geometry(self) -> None:
        self._preview_size = self._derive_preview_size()
        self.preview_height = self._preview_size.height()
        self.preview_frame.setFixedSize(self._preview_size)
        self.preview_label.setFixedSize(self._preview_size)
        self.setFixedSize(self.sizeHint())

    def apply_theme(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.preview_frame.style().unpolish(self.preview_frame)
        self.preview_frame.style().polish(self.preview_frame)
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()
        self.update()

    def apply_metrics(self, metrics: DanbooruCardMetrics) -> None:
        self.metrics = metrics
        self._sync_geometry()
        if not self._preview_pixmap.isNull():
            self._apply_preview_icon()
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

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton:
            return
        if self.childAt(event.position().toPoint()) is not None:
            return
        self._toggle_selection()


class CbgSelectionController(QtCore.QObject):
    selection_count_changed = Signal(int)

    def __init__(self, interface: "CbgInterface"):
        super().__init__(interface)
        self.interface = interface
        self._selection_band = QRubberBand(QRubberBand.Rectangle, self.interface.scroll_area.viewport())
        self._selection_band.hide()
        self._drag_origin: t.Optional[QtCore.QPoint] = None
        self._drag_active = False
        self._drag_source: t.Optional[QWidget] = None
        self._drag_seed: set[Path] = set()
        self._install_source(self.interface.scroll_area.viewport())
        self._install_source(self.interface.scroll_content)
        self.apply_theme()

    def apply_theme(self) -> None:
        tokens = _get_cbg_qss_tokens()
        self._selection_band.setStyleSheet(
            f"border: 2px dashed {tokens['CARD_SELECTION_BORDER']}; background: {tokens['CARD_SELECTION_FILL_END']};"
        )

    def bind_card(self, card: CbgCardWidget) -> None:
        card.selection_changed.connect(self._on_card_selection_changed)
        self._install_source(card)
        self._install_source(card.preview_frame)
        self._install_source(card.preview_label)
        self._apply_card_selection(card, card.path in self.interface._selected_paths, emit_count=False)

    def selection_count(self) -> int:
        return len(self.interface._selected_paths)

    def clear(self) -> None:
        self._reset_drag_state()
        self.set_selected_paths(set())

    def set_selected_paths(self, paths: t.Iterable[Path], *, emit_count: bool = True) -> None:
        target_paths = {path.resolve() for path in paths if path.resolve() in self.interface.cards}
        current_paths = set(self.interface._selected_paths)
        if target_paths == current_paths:
            return
        for path in current_paths - target_paths:
            self._apply_card_selection(self.interface.cards[path], False, emit_count=False)
        for path in target_paths - current_paths:
            self._apply_card_selection(self.interface.cards[path], True, emit_count=False)
        if emit_count:
            self.selection_count_changed.emit(self.selection_count())

    def _apply_card_selection(self, card: CbgCardWidget, selected: bool, *, emit_count: bool = True) -> None:
        card.set_selected(selected)
        if card.is_selected():
            self.interface._selected_paths.add(card.path)
        else:
            self.interface._selected_paths.discard(card.path)
        if emit_count:
            self.selection_count_changed.emit(self.selection_count())

    def _on_card_selection_changed(self, card: CbgCardWidget, selected: bool) -> None:
        if selected:
            self.interface._selected_paths.add(card.path)
        else:
            self.interface._selected_paths.discard(card.path)
        self.selection_count_changed.emit(self.selection_count())

    def _install_source(self, widget: QWidget) -> None:
        widget.setProperty("cbgDragSelectSource", True)
        widget.installEventFilter(self)

    def _reset_drag_state(self) -> None:
        was_active = self._drag_active
        self._drag_origin = None
        self._drag_active = False
        self._drag_source = None
        self._drag_seed.clear()
        self._selection_band.hide()
        if was_active:
            QApplication.restoreOverrideCursor()

    def _viewport_point(self, global_pos: QtCore.QPoint) -> QtCore.QPoint:
        viewport = self.interface.scroll_area.viewport()
        point = viewport.mapFromGlobal(global_pos)
        rect = viewport.rect()
        return QtCore.QPoint(
            min(max(point.x(), rect.left()), rect.right()),
            min(max(point.y(), rect.top()), rect.bottom()),
        )

    def _begin_drag(self) -> None:
        if self._drag_active or self._drag_origin is None:
            return
        self._drag_active = True
        self._selection_band.setGeometry(QtCore.QRect(self._drag_origin, QtCore.QSize()))
        self._selection_band.show()
        if hasattr(self._drag_source, "setDown"):
            self._drag_source.setDown(False)
        QApplication.setOverrideCursor(Qt.CrossCursor)

    def _update_drag_band(self, global_pos: QtCore.QPoint) -> None:
        if self._drag_origin is None:
            return
        rect = QtCore.QRect(self._drag_origin, self._viewport_point(global_pos)).normalized()
        self._selection_band.setGeometry(rect)

    def _selected_paths_for_rect(self, selection_rect: QtCore.QRect) -> set[Path]:
        if selection_rect.width() < 5 and selection_rect.height() < 5:
            return set(self._drag_seed)
        viewport = self.interface.scroll_area.viewport()
        hit_paths = set(self._drag_seed)
        for path, card in self.interface.cards.items():
            card_rect = QtCore.QRect(card.mapTo(viewport, QtCore.QPoint(0, 0)), card.size())
            if selection_rect.intersects(card_rect):
                hit_paths.add(path)
        return hit_paths

    def eventFilter(self, obj, event):
        if not bool(getattr(obj, "property", lambda *_args: False)("cbgDragSelectSource")):
            return super().eventFilter(obj, event)

        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            if event.button() != Qt.LeftButton:
                return super().eventFilter(obj, event)
            self._drag_origin = self._viewport_point(event.globalPosition().toPoint())
            self._drag_active = False
            self._drag_source = obj
            self._drag_seed = set(self.interface._selected_paths)
            return False

        if event_type == QtCore.QEvent.MouseMove:
            if self._drag_origin is None:
                return super().eventFilter(obj, event)
            current_point = self._viewport_point(event.globalPosition().toPoint())
            if not self._drag_active:
                if (current_point - self._drag_origin).manhattanLength() < QApplication.startDragDistance():
                    return False
                self._begin_drag()
            self._update_drag_band(event.globalPosition().toPoint())
            self.set_selected_paths(self._selected_paths_for_rect(self._selection_band.geometry()))
            return True

        if event_type == QtCore.QEvent.MouseButtonRelease:
            if event.button() == Qt.RightButton:
                self.clear()
                return True
            if self._drag_origin is None:
                return super().eventFilter(obj, event)
            drag_was_active = self._drag_active
            target_paths = self._selected_paths_for_rect(self._selection_band.geometry()) if drag_was_active else set()
            self._reset_drag_state()
            if drag_was_active:
                self.set_selected_paths(target_paths)
                return True
            return False

        return super().eventFilter(obj, event)


class CbgInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("CbgInterface")
        self.task_mgr = AsyncTaskManager(self.parent_window.gui)
        self.card_metrics = DEFAULT_CARD_METRICS
        self.cards: dict[Path, CbgCardWidget] = {}
        self._scanned_paths: list[Path] = []
        self._selected_paths: set[Path] = set()
        self._setup_ui()
        self.selection_controller = CbgSelectionController(self)
        self.selection_controller.selection_count_changed.connect(self._on_selection_count_changed)
        theme_mgr.subscribe(self._apply_theme)
        self.destroyed.connect(lambda *_args: self.task_mgr.cleanup())
        self._restore_persisted_state()
        self._apply_theme()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 14)
        self.main_layout.setSpacing(12)

        self.first_row = QHBoxLayout()
        self.first_row.setContentsMargins(0, 0, 0, 0)
        self.first_row.setSpacing(12)

        self.path_card = CbgPathCard(self)
        self.path_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.path_card.path_selected.connect(self._scan_selected_root)
        card_height = self.path_card.height()

        self.apiBtn = TransparentToolButton(QIcon(':/script/api.svg'), self)
        self.apiBtn.setIconSize(QtCore.QSize(30, 38))
        self.apiBtn.clicked.connect(self.api_tip_show)

        self.random_frame = QFrame(self)
        self.random_frame.setObjectName("CbgRandomFrame")
        self.random_frame.setMinimumHeight(card_height)
        self.random_frame.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        random_layout = QHBoxLayout(self.random_frame)
        random_layout.setContentsMargins(12, 10, 12, 10)
        random_layout.setSpacing(8)

        self.containBtn = TogglePushButton("包含此前", self.random_frame)
        self.containBtn.setChecked(bool(cbg_cfg.includePrevious.value))
        self.containBtn.toggled.connect(lambda checked: cbg_cfg.set(cbg_cfg.includePrevious, bool(checked)))

        self.numBox = CbgRandomCountSpinBox(cbg_cfg.randomCount.value, self.random_frame)
        self.numBox.setMinimumHeight(36)
        self.numBox.valueChanged.connect(
            lambda value: cbg_cfg.set(cbg_cfg.randomCount, canonicalize_random_count(value))
        )

        self.ensureBtn = ToolButton(QIcon(':/script/random.svg'), self.random_frame)
        self.ensureBtn.setFixedSize(38, 38)
        self.ensureBtn.setIconSize(QtCore.QSize(24, 24))
        self.ensureBtn.clicked.connect(self._select_random_paths)

        random_layout.addWidget(self.containBtn)
        random_layout.addWidget(self.numBox)
        random_layout.addWidget(self.ensureBtn)

        self.genBtn = PrimaryToolButton(QIcon(':/script/generate.svg'), self)
        self.genBtn.setIconSize(QtCore.QSize(28, 28))
        self.genBtn.setObjectName("CbgGenerateButton")
        self.genBtn.setMinimumHeight(card_height)
        self.genBtn.setDisabled(True)
        self.genBtn.clicked.connect(self._generate_userscript)

        self.first_row.addWidget(self.path_card)
        self.first_row.addWidget(self.apiBtn)
        self.first_row.addWidget(self.random_frame)
        self.first_row.addWidget(self.genBtn)
        self.main_layout.addLayout(self.first_row)

        self.second_row = QFrame(self)
        self.second_row.setObjectName("CbgSecondRow")
        self.second_row.setVisible(False)
        self.main_layout.addWidget(self.second_row)

        self.grid_shell = QFrame(self)
        self.grid_shell.setObjectName("CbgGridShell")
        grid_layout = QVBoxLayout(self.grid_shell)
        grid_layout.setContentsMargins(12, 12, 12, 12)
        grid_layout.setSpacing(0)

        self.grid_stack = QStackedWidget(self.grid_shell)
        self.empty_page = QWidget(self.grid_stack)
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setContentsMargins(18, 18, 18, 18)
        empty_layout.addStretch(1)
        self.empty_label = StrongBodyLabel("选择 PNG 目录后会在这里展示卡片", self.empty_page)
        self.empty_label.setObjectName("CbgEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_label, 0, Qt.AlignCenter)
        empty_layout.addStretch(1)

        self.scroll_area = ScrollArea(self.grid_stack)
        self.scroll_area.setObjectName("CbgGridScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setToolTip("左键拖拽框选，右键可清空选择")
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("CbgGridContent")
        self.flow_layout = FlowLayout(self.scroll_content)
        self.flow_layout.setContentsMargins(2, 2, 2, 2)
        self.flow_layout.setHorizontalSpacing(4)
        self.flow_layout.setVerticalSpacing(4)
        self.scroll_area.setWidget(self.scroll_content)

        self.grid_stack.addWidget(self.empty_page)
        self.grid_stack.addWidget(self.scroll_area)
        grid_layout.addWidget(self.grid_stack)
        self.main_layout.addWidget(self.grid_shell, 1)

    def api_tip_show(self):
        def on_imported(target_dir: Path) -> None:
            self._scan_selected_root(str(target_dir))
            InfoBar.success(
                title="", content="导入完成，已切换到新目录", orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM, duration=2500, parent=self
            )
            apply_btn = PrimaryToolButton(FIF.ACCEPT)
            ib = CustomInfoBar.show_custom(
                title="", content="是否应用到 cgs 的 bg_path", parent=self, _type="INFORMATION", widgets=[apply_btn],
            )
            def do():
                conf.update(bg_path=target_dir)
                ib.close()
            apply_btn.clicked.connect(do)

        def log_error(error: str) -> None:
            logger = getattr(self.parent_window, "log", None)
            if logger is not None:
                logger.error(error)

        def do():
            api_url = str(apiEdit.text() or "").strip()
            if not api_url:
                InfoBar.warning(
                    title="", content="请先粘贴 API 链接", orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM, duration=2500, parent=self
                )
                return
            started = self.task_mgr.execute_simple_task(
                import_cbg_api_bundle,
                success_callback=on_imported, error_callback=log_error, tooltip_title="import resource", tooltip_content="read remote", show_success_info=False,
                tooltip_parent=self, task_id="cbg_api_import", api_url=api_url, output_root=conf_dir.joinpath("cbg"),
            )
            if started:
                tip.close()

        apiEdit = LineEdit(self)
        apiEdit.setMinimumWidth(320)
        apiEdit.setPlaceholderText("使用 引力圈 赞助方案获取 api, 然后复制到此处")
        apiEdit.setClearButtonEnabled(True)
        accept_btn = PrimaryToolButton(FIF.ACCEPT)
        linkBtn = TransparentToolButton(FIF.LINK)
        linkBtn.clicked.connect(lambda *_args: QtGui.QDesktopServices.openUrl(QtCore.QUrl(_CBG_SPONSOR_URL)))
        tip = CustomTeachingTip.create(
            [apiEdit,linkBtn,accept_btn], target=self.apiBtn, parent=self.apiBtn, tailPosition=TeachingTipTailPosition.TOP_RIGHT,
        )
        apiEdit.returnPressed.connect(accept_btn.click)
        accept_btn.clicked.connect(do)

    def _restore_persisted_state(self) -> None:
        raw_scan_root = str(cbg_cfg.scanRoot.value or "").strip()
        scan_root = str(normalize_path(raw_scan_root)) if raw_scan_root else ""
        self.path_card.set_path(scan_root)
        self.containBtn.blockSignals(True)
        self.containBtn.setChecked(bool(cbg_cfg.includePrevious.value))
        self.containBtn.blockSignals(False)
        self.numBox.blockSignals(True)
        self.numBox.setValue(canonicalize_random_count(cbg_cfg.randomCount.value))
        self.numBox.blockSignals(False)
        if scan_root:
            self._scan_selected_root(scan_root)
        else:
            self.grid_stack.setCurrentWidget(self.empty_page)

    def _apply_theme(self, *_args) -> None:
        self.setStyleSheet(_build_cbg_interface_stylesheet())
        for card in self.cards.values():
            card.apply_theme()
        self.selection_controller.apply_theme()

    def _clear_cards(self) -> None:
        while self.flow_layout.count():
            _delete_flow_item(self.flow_layout.takeAt(0))
        self.cards.clear()

    def _show_empty_state(self, text: str) -> None:
        self.empty_label.setText(text)
        self.grid_stack.setCurrentWidget(self.empty_page)

    def _reset_scan_result(self, text: str) -> None:
        self.selection_controller.clear()
        self._clear_cards()
        self._scanned_paths = []
        self._show_empty_state(text)

    def _rebuild_cards(self, paths: list[Path]) -> None:
        self.selection_controller.clear()
        self._clear_cards()
        self._scanned_paths = list(paths)
        if not paths:
            return self._show_empty_state("empty PNG")
        for path in paths:
            card = CbgCardWidget(path, self.scroll_content, metrics=self.card_metrics)
            self.cards[path] = card
            self.flow_layout.addWidget(card)
            self.selection_controller.bind_card(card)
        self.grid_stack.setCurrentWidget(self.scroll_area)

    def _scan_selected_root(self, raw_root: str) -> None:
        normalized_root = str(normalize_path(raw_root)) if str(raw_root or "").strip() else ""
        cbg_cfg.set(cbg_cfg.scanRoot, normalized_root)
        self.path_card.set_path(normalized_root)
        if not normalized_root:
            return self._reset_scan_result("选择 PNG 目录后会在这里展示卡片")
        root_path = Path(normalized_root)
        if not root_path.exists():
            return self._reset_scan_result("当前目录不存在")
        if not root_path.is_dir():
            return self._reset_scan_result("当前路径不是目录")

        self._rebuild_cards(scan_png_files(root_path))

    def _select_random_paths(self) -> None:
        if not self._scanned_paths:
            return
        target_count = canonicalize_random_count(self.numBox.value())
        selected_paths = pick_random_paths(
            self._scanned_paths,
            recorded_paths=unique_paths(cbg_cfg.generatedPaths.value or []),
            target_count=target_count,
            include_recorded=self.containBtn.isChecked(),
        )
        self.selection_controller.set_selected_paths(selected_paths)

    def _ordered_selected_paths(self) -> list[Path]:
        return [path for path in self._scanned_paths if path in self._selected_paths]

    def _generate_userscript(self) -> None:
        selected_paths = self._ordered_selected_paths()
        if not selected_paths:
            return
        template_text = _TEMPLATE_PATH.read_text(encoding="utf-8")
        userscript = build_userscript(selected_paths, template_text)
        QApplication.clipboard().setText(userscript)
        cbg_cfg.set(
            cbg_cfg.generatedPaths,
            [str(path) for path in unique_paths(selected_paths)],
        )
        CustomInfoBar.show(
            "", "已复制进剪贴板，导入到浏览器油猴脚本中使用",
            self, _TAMPERMONKEY_URL, "Tampermonkey", _type="SUCCESS", position=InfoBarPosition.BOTTOM,
        )

    def _on_selection_count_changed(self, count: int) -> None:
        self.genBtn.setEnabled(count > 0)
