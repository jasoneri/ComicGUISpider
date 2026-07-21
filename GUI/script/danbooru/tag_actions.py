from __future__ import annotations

import typing as t

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QPlainTextEdit, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon as FIF, InfoBar, InfoBarPosition, PrimaryPushButton, PushButton,
    StrongBodyLabel, TogglePushButton, TransparentToolButton,
)
from qframelesswindow import FramelessDialog

from utils.script.image.danbooru.models import DanbooruPost
from utils.script.image.danbooru.tag_prompt import TagPrompt
from utils.script.jsoneri.imgpalace_job import (
    DEFAULT_ACTION_NAME,
    action_preset,
    iter_action_preset_names,
)

if t.TYPE_CHECKING:
    from .interface import DanbooruInterface
    from .viewer import DanbooruImageViewer


class TagExportPanel(FramelessDialog):
    copy_requested = Signal()
    imgpalace_requested = Signal()

    COLUMNS = 3

    def __init__(self, post: DanbooruPost, parent=None):
        # parent must be the viewer window so the panel stays above the post surface.
        super().__init__(parent)
        self.prompt = TagPrompt(post)
        self._tag_buttons: dict[str, TogglePushButton] = {}
        self.setObjectName("DanbooruTagExportPanel")
        self.resize(520, 640)
        self.setMinimumSize(440, 480)
        self._setup_ui()
        self._load_tags()

    def selected_action_name(self) -> str:
        return str(self.action_combo.currentData() or DEFAULT_ACTION_NAME)

    def selected_action_payload(self) -> dict:
        return action_preset(self.selected_action_name())

    def prompt_body_text(self) -> str:
        """General-only visual prompt (no character/artist/copyright soup)."""
        return self.prompt.prompt_body()

    def prompt_text(self) -> str:
        """Clipboard composition: general body + optional labeled identity block."""
        return self.prompt.prompt_text()

    def _setup_ui(self):
        self.titleBar.minBtn.hide()
        self.titleBar.maxBtn.hide()
        self.titleBar.closeBtn.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(14, 8, 14, 4)
        self.title_label = StrongBodyLabel("Tag 导出", self)
        self.count_label = BodyLabel("0 selected", self)
        self.count_label.setObjectName("DanbooruTagExportCount")
        self.close_btn = TransparentToolButton(self)
        self.close_btn.setIcon(QIcon(":/close.svg"))
        self.close_btn.setIconSize(QtCore.QSize(18, 18))
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.title_label)
        header.addWidget(self.count_label, 1)
        header.addWidget(self.close_btn)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(14, 0, 14, 8)
        toolbar.setSpacing(8)
        self.select_all_btn = PushButton("恢复默认(General)", self)
        self.select_all_btn.clicked.connect(self._select_default_groups)
        self.toggle_select_btn = TransparentToolButton(FIF.CHECKBOX, self)
        self.toggle_select_btn.setIconSize(QtCore.QSize(18, 18))
        self.toggle_select_btn.setToolTip("全选")
        self.toggle_select_btn.clicked.connect(self._toggle_select_all)
        toolbar.addWidget(self.select_all_btn)
        toolbar.addWidget(self.toggle_select_btn)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chips_host = QWidget(self.scroll)
        self.chips_layout = QVBoxLayout(self.chips_host)
        self.chips_layout.setContentsMargins(14, 4, 14, 8)
        self.chips_layout.setSpacing(10)
        self.scroll.setWidget(self.chips_host)
        root.addWidget(self.scroll, 1)

        preview_block = QVBoxLayout()
        preview_block.setContentsMargins(14, 4, 14, 4)
        preview_block.setSpacing(4)
        preview_block.addWidget(StrongBodyLabel("Prompt 预览", self))
        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(140)
        self.preview.setObjectName("DanbooruTagExportPreview")
        preview_block.addWidget(self.preview)
        root.addLayout(preview_block)

        # Action = imgPalace job intent only (not clipboard). Choices come from the
        # registry so new product actions extend in one place, not a second hardcoded list.
        imgpalace_row = QHBoxLayout()
        imgpalace_row.setContentsMargins(14, 4, 14, 4)
        imgpalace_row.setSpacing(8)
        imgpalace_row.addWidget(BodyLabel("Action", self))
        self.action_combo = ComboBox(self)
        self._populate_action_combo()
        imgpalace_row.addWidget(self.action_combo, 1)
        self.imgpalace_btn = PushButton("to_imgPalace", self)
        self.imgpalace_btn.setIcon(FIF.SEND)
        self.imgpalace_btn.clicked.connect(self.imgpalace_requested.emit)
        imgpalace_row.addWidget(self.imgpalace_btn)
        root.addLayout(imgpalace_row)

        copy_row = QHBoxLayout()
        copy_row.setContentsMargins(14, 4, 14, 14)
        self.copy_btn = PrimaryPushButton("Copy", self)
        self.copy_btn.setIcon(FIF.COPY)
        self.copy_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.copy_btn.clicked.connect(self.copy_requested.emit)
        copy_row.addWidget(self.copy_btn, 1)
        root.addLayout(copy_row)

    def _populate_action_combo(self):
        self.action_combo.clear()
        preset_names = iter_action_preset_names()
        if not preset_names:
            raise RuntimeError("imgPalace action registry is empty")
        for preset_name in preset_names:
            self.action_combo.addItem(preset_name, userData=preset_name)
        default_index = self.action_combo.findData(DEFAULT_ACTION_NAME)
        self.action_combo.setCurrentIndex(default_index if default_index >= 0 else 0)

    def _load_tags(self):
        for label, tags in self.prompt.groups:
            if not tags:
                continue
            section = StrongBodyLabel(label, self.chips_host)
            self.chips_layout.addWidget(section)
            grid_host = QWidget(self.chips_host)
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            for offset, tag in enumerate(tags):
                button = TogglePushButton(grid_host)
                button.setText(tag)
                button.setToolTip(tag)
                button.setCheckable(True)
                button.setChecked(self.prompt.is_selected(tag))
                button.setMinimumWidth(96)
                button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                button.toggled.connect(lambda checked, current_tag=tag: self._set_tag_selected(current_tag, checked))
                grid.addWidget(button, offset // self.COLUMNS, offset % self.COLUMNS)
                self._tag_buttons[tag] = button
            self.chips_layout.addWidget(grid_host)
        self.chips_layout.addStretch(1)
        self._refresh_preview()

    def _set_all_checked(self, checked: bool):
        for button in self._tag_buttons.values():
            button.setChecked(checked)
        self._refresh_preview()

    def _set_tag_selected(self, tag: str, selected: bool):
        self.prompt.set_selected(tag, selected)
        self._refresh_preview()

    def _all_tags_checked(self) -> bool:
        return bool(self._tag_buttons) and all(button.isChecked() for button in self._tag_buttons.values())

    def _toggle_select_all(self):
        self._set_all_checked(not self._all_tags_checked())

    def _sync_toggle_select_btn(self):
        if self._all_tags_checked():
            self.toggle_select_btn.setIcon(FIF.CANCEL)
            self.toggle_select_btn.setToolTip("取消全选")
        else:
            self.toggle_select_btn.setIcon(FIF.CHECKBOX)
            self.toggle_select_btn.setToolTip("全选")

    def _select_default_groups(self):
        self.prompt.restore_defaults()
        for tag, button in self._tag_buttons.items():
            button.setChecked(self.prompt.is_selected(tag))
        self._refresh_preview()

    def _refresh_preview(self):
        text = self.prompt.prompt_text()
        body = self.prompt.prompt_body()
        self.preview.setPlainText(text)
        self.count_label.setText(f"{len(selected)} selected")
        self.copy_btn.setEnabled(bool(text.strip()))
        self.imgpalace_btn.setEnabled(bool(body.strip()))
        self._sync_toggle_select_btn()


class DanbooruTagActionController(QtCore.QObject):
    def __init__(
        self,
        gui,
        parent: "DanbooruInterface",
        *,
        browser_opener: t.Callable[[str, str | None], None] | None = None,
        job_sender: t.Callable[..., None] | None = None,
    ):
        super().__init__(parent)
        if gui is None:
            raise ValueError("DanbooruTagActionController requires gui")
        if parent is None:
            raise ValueError("DanbooruTagActionController requires parent interface")
        self.gui = gui
        self.interface = parent
        self._browser_opener = browser_opener
        self._job_sender = job_sender
        self._panel: TagExportPanel | None = None
        self._viewer: "DanbooruImageViewer | None" = None
        self._send_in_flight = False

    def open_export_panel(self, viewer: "DanbooruImageViewer"):
        self._viewer = viewer
        if viewer.post is None:
            self._show_info(InfoBar.warning, "当前没有可导出的 post", 2500)
            return
        if self._panel is not None:
            self._panel.close()
            self._panel = None
        panel = TagExportPanel(viewer.post, parent=viewer)
        panel.copy_requested.connect(lambda: self._on_copy(panel))
        panel.imgpalace_requested.connect(lambda: self._on_imgpalace(panel))
        panel.destroyed.connect(self._on_panel_destroyed)
        self._panel = panel
        panel.show()
        panel.raise_()
        panel.activateWindow()

    def _on_panel_destroyed(self, *_args):
        self._panel = None
        self._viewer = None

    def _show_info(self, factory, content: str, duration: int = 3000):
        # Export feedback is scoped to the viewer surface (panel parent), never the interface tab.
        parent = self._viewer if self._viewer is not None else self.interface.image_viewer
        return factory(
            title="",
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=parent,
        )

    def _on_copy(self, panel: TagExportPanel):
        text = panel.prompt_text()
        if not text.strip():
            self._show_info(InfoBar.warning, "请先选择要导出的 tag", 2500)
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            raise RuntimeError("QApplication.clipboard() is unavailable")
        clipboard.setText(text)
        self._show_info(InfoBar.success, "Prompt 已复制", 2000)

    def _on_imgpalace(self, panel: TagExportPanel):
        if self._send_in_flight:
            return
        body = panel.prompt_body_text()
        if not body.strip():
            self._show_info(InfoBar.warning, "请先在 General 中选择 tag", 2500)
            return
        text = panel.prompt_text()
        self._send_in_flight = True
        panel.imgpalace_btn.setEnabled(False)
        try:
            if self._browser_opener is not None:
                self._browser_opener("raw-image", None)
            else:
                self._show_info(
                    InfoBar.warning,
                    "imgPalace 尚未就绪，请先配置 jsoneriPalaces",
                    3500,
                )
            if self._job_sender is not None:
                self._job_sender(
                    post=panel.prompt.post,
                    tags_prompt=body,
                    identity=panel.prompt.identity(),
                    clipboard_text=text,
                    action=panel.selected_action_payload(),
                )
            else:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(text)
                self._show_info(
                    InfoBar.success,
                    "Prompt 已复制；提交到 imgPalace 尚未启用",
                    3500,
                )
        finally:
            self._send_in_flight = False
            panel.imgpalace_btn.setEnabled(bool(panel.prompt_body_text().strip()))
