from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FlowLayout, FluentIcon as FIF, IndeterminateProgressRing, ProgressRing,
    LineEdit, PlainTextEdit, PushButton, ScrollArea, SegmentedWidget, PrimaryToolButton,
    Slider, StrongBodyLabel, TogglePushButton, ToolButton, TransparentToolButton,
    ImageLabel,
)
from qframelesswindow import FramelessDialog

from GUI.uic.qfluent.components.icons import CgsIcon
from utils.config.qc import danbooru_cfg
from utils.script import conf as script_conf
from utils.script.ai.kernel import AiProviderConfigSession
from utils.script.image.anima import anima_spec as comfy_prompt_spec
from utils.script.image.anima import danbooru_anima as _comfy_workflow
from utils.script.image.anima.comfy_client import (
    COMFY_UNET_PRESETS,
    is_comfy_configured,
)
from utils.script.image.anima.prompt_doc import PromptDoc, split_prompt
from utils.script.image.danbooru.models import DanbooruPost
from utils.script.image.danbooru.tag_prompt import TagPrompt
from utils.script.jsoneri.imgpalace_job import (
    DEFAULT_ACTION_NAME,
    action_preset,
    iter_action_preset_names,
)

from .comfy.fav_chips import ComfyFavoritesChipGroups, TagChipButton
from .comfy.prompt import (
    GROUP_TO_SECTION,
    ComfyPromptHighlighter,
    category_map_for_groups,
    insert_tag_into_text,
    iter_tag_spans,
    load_comfy_palette,
    remove_tag_from_text,
    section_map_for_groups,
)
from .comfy.tag_groups_state import (
    TagGroupsState,
    _token_aliases,
    lexicon_for_panel,
)

# PromptDoc section → TagPrompt label / danbooru category (fav SECTION_OPTIONS).
_SECTION_TO_GROUP_LABEL = {
    "character": "Character",
    "artist": "Artist",
    "series": "Copyright",
    "body": "General",
    "prefix": "Meta",
    "subject": "General",
}


def is_imgpalace_configured() -> bool:
    """Configuration presence = capability: non-empty jsoneri token enables imgPalace row."""
    section = getattr(script_conf, "jsoneriPalacesProbe", None) or {}
    if not isinstance(section, dict):
        return False
    return bool(str(section.get("token") or "").strip())


def _copy_pixmap(source: QPixmap | None) -> QPixmap:
    if source is None or source.isNull():
        return QPixmap()
    return source.copy()


def _tags_from_prompt_groups(groups) -> tuple[str, ...]:
    """Flatten TagPrompt-style groups into stable unique tokens (first-seen order)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for _label, tags in groups or ():
        for tag in tags:
            token = str(tag or "").strip()
            if not token:
                continue
            key = comfy_prompt_spec.normalize_tag(token)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(token)
    return tuple(ordered)


@dataclass
class CurrentImg:
    post: DanbooruPost
    pic: QPixmap


@dataclass
class AttachImg:
    """附着物：与 CurrentImg-tags 同源的 groups 结构 + 展示用 pic。"""

    pic: QPixmap
    groups: tuple[tuple[str, tuple[str, ...]], ...]
    source: str  # "viewer" | "comfy"
    post_id: int | None = None
    job_id: str | None = None

    @property
    def tags(self) -> tuple[str, ...]:
        return _tags_from_prompt_groups(self.groups)


class TagExportPanel(FramelessDialog):
    copy_requested = Signal()
    imgpalace_requested = Signal()
    comfy_requested = Signal(str)
    comfy_nl_requested = Signal()
    comfy_jobs_requested = Signal()

    def __init__(
        self,
        post: DanbooruPost,
        parent=None,
        *,
        current_img_pic: QPixmap | None = None,
    ):
        # parent must be the viewer window so the panel stays above the post surface.
        super().__init__(parent)
        self.prompt = TagPrompt(post)
        self.currentImg = CurrentImg(post=post, pic=_copy_pixmap(current_img_pic))
        self.attachImg: AttachImg | None = None
        self._tag_buttons: dict[str, TogglePushButton] = {}
        self._palette_buttons: dict[str, TogglePushButton] = {}
        self._attached_tag_buttons: dict[str, TogglePushButton] = {}
        self._attached_tag_sections: dict[str, str] = {}
        self.comfy_known = section_map_for_groups(self.prompt.groups)
        self._comfy_categories = category_map_for_groups(self.prompt.groups)
        self._preview_dirty = False
        self._applying_generated = False
        self._comfy_nl_busy = False
        self.setObjectName("DanbooruTagExportPanel")
        self.setMinimumSize(440, 480)
        self._setup_ui()
        self._restore_comfy_settings_from_config()
        self._load_tags()
        # 打开即全选（角色/画师/作品/General/Meta），与 toggle_select_btn 勾选态一致；
        # restore 按钮仍回到 General-only。
        self._set_all_checked(True)
        self._restore_geometry_from_config()
        self._sync_preview_side_images()
        # _load_tags / fav chips 会再挂一批 QPushButton；setup 末尾那次清 default 不够。
        self._disable_dialog_default_buttons()

    def selected_action_name(self) -> str:
        return str(self.action_combo.currentData() or DEFAULT_ACTION_NAME)

    def selected_action_payload(self) -> dict:
        return action_preset(self.selected_action_name())

    def prompt_body_text(self) -> str:
        """imgPalace 用的 visual body。

        clean：chip 选中态打包的 General/Meta（身份组不进 soup）。
        dirty：preview 已是用户手改/Fav/attached toggle 的最终文本，body 与整段预览同源。
        """
        if self._preview_dirty:
            return self.preview.toPlainText().strip()
        return self.prompt.prompt_body()

    def prompt_text(self) -> str:
        """剪贴板 / 导出文本。

        clean：TagPrompt 的 body + identity 块（与 chip 选中态一致）。
        dirty：preview 是唯一真相源（手改、Fav、attached toggle 都只写这里）。
        """
        if self._preview_dirty:
            return self.preview.toPlainText()
        return self.prompt.prompt_text()

    def selected_comfy_unet(self) -> str:
        return str(self.comfy_unet_combox.currentData() or "turbo")

    @staticmethod
    def _normalized_panel_rect(x: int, y: int, width: int, height: int) -> QRect:
        """把记忆的几何限制在可用屏幕内，避免断连显示器把面板卡出视野。"""
        screens = QApplication.screens()
        minimum_width = 440
        minimum_height = 480
        safe_width = max(minimum_width, int(width))
        safe_height = max(minimum_height, int(height))
        proposed = QRect(int(x), int(y), safe_width, safe_height)
        if not screens:
            return proposed

        def is_visible_enough(rect: QRect) -> bool:
            for screen in screens:
                intersection = rect.intersected(screen.availableGeometry())
                if intersection.width() >= min(rect.width(), 200) and intersection.height() >= min(rect.height(), 160):
                    return True
            return False

        if is_visible_enough(proposed):
            return proposed

        primary = QApplication.primaryScreen() or screens[0]
        available = primary.availableGeometry()
        fitted_width = min(safe_width, available.width())
        fitted_height = min(safe_height, available.height())
        return QRect(
            available.x() + max(0, (available.width() - fitted_width) // 2),
            available.y() + max(0, (available.height() - fitted_height) // 2),
            fitted_width,
            fitted_height,
        )

    def _restore_geometry_from_config(self):
        saved_rect = danbooru_cfg.get_tag_export_panel_rect()
        if saved_rect:
            geometry = self._normalized_panel_rect(*saved_rect)
            self.setGeometry(geometry)
            return
        self.resize(520, 640)

    def _persist_geometry_to_config(self):
        geometry = self._normalized_panel_rect(self.x(), self.y(), self.width(), self.height())
        danbooru_cfg.save_tag_export_panel_rect(
            geometry.x(), geometry.y(), geometry.width(), geometry.height()
        )

    def checkpoint_panel_prefs(self) -> None:
        """Single write entry for TagExportPanel preference bags (not Search/Favorites).

        Geometry + Comfy generation prefs + fav-group SECTION map. Call sites may be
        many (close / copy / imgPalace / comfy); implementation stays here.
        """
        self._persist_geometry_to_config()
        self._persist_comfy_settings_to_config()
        self._persist_fav_group_sections_to_config()

    def closeEvent(self, event):
        session = getattr(self, "_ai_provider_session", None)
        if session is not None:
            try:
                session.state_changed.disconnect(self._on_ai_provider_state_changed)
            except (RuntimeError, TypeError):
                pass
        self.checkpoint_panel_prefs()
        super().closeEvent(event)

    def _restore_comfy_settings_from_config(self):
        """在 _setup_ui 之后、_load_tags 之前恢复 Comfy 生成设置。

        blockSignals 避免 preset 回填触发 _on_comfy_preset_changed（此时 palette
        chips 尚未构建）；_load_tags 末尾的 _sync_score_chip_state + _refresh_preview
        会按恢复后的 preset 统一刷新。denoise 只改按钮文案，无预览副作用。
        """
        saved_preset = danbooru_cfg.get_tag_export_comfy_unet()
        preset_index = self.comfy_unet_combox.findData(saved_preset)
        if preset_index < 0:
            preset_index = self.comfy_unet_combox.findData("turbo")
        self.comfy_unet_combox.blockSignals(True)
        self.comfy_unet_combox.setCurrentIndex(max(0, preset_index))
        self.comfy_unet_combox.blockSignals(False)

        self.wd14_btn.blockSignals(True)
        self.wd14_btn.setChecked(danbooru_cfg.get_tag_export_wd14_enabled())
        self.wd14_btn.blockSignals(False)

        # 勿 blockSignals：qfluent Slider 靠 valueChanged 挪手柄；挡信号会只改 value 不改视觉。
        self.denoise_slider.setValue(danbooru_cfg.get_tag_export_denoise())

    def _persist_comfy_settings_to_config(self):
        danbooru_cfg.save_tag_export_comfy_unet(self.selected_comfy_unet())
        # WD14 不可用时 set_wd14_status 会强制取消勾选；那是能力门控，不是用户改偏好。
        # 只在按钮可交互时写回 qconfig，否则会把「想开但当前不可用」冲成 False。
        if self.wd14_btn.isEnabled():
            danbooru_cfg.save_tag_export_wd14_enabled(self.wd14_btn.isChecked())
        danbooru_cfg.save_tag_export_denoise(self.denoise_slider.value())

    def _persist_fav_group_sections_to_config(self):
        """TagExportPanel/FavGroupSections bag only — never favorites content or push."""
        fav_chip_groups = getattr(self, "_comfy_fav_chips", None)
        if fav_chip_groups is None:
            return
        section_snapshot = getattr(fav_chip_groups, "section_snapshot", None)
        if not callable(section_snapshot):
            return
        danbooru_cfg.save_tag_export_fav_group_sections(section_snapshot())

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
        self.close_btn = TransparentToolButton(self)
        self.close_btn.setIcon(QIcon(":/close.svg"))
        self.close_btn.setIconSize(QtCore.QSize(18, 18))
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.title_label)
        header.addWidget(self.close_btn)
        root.addLayout(header)

        segment_row = QHBoxLayout()
        segment_row.setContentsMargins(14, 0, 14, 8)
        segment_row.setSpacing(8)
        self.content_segment = SegmentedWidget(self)
        self.content_segment.setObjectName("DanbooruTagExportSegment")
        self.content_stack = QStackedWidget(self)
        self.content_stack.setObjectName("DanbooruTagExportStack")

        post_tags_page = QWidget(self.content_stack)
        post_tags_layout = QVBoxLayout(post_tags_page)
        post_tags_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = ScrollArea(post_tags_page)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.enableTransparentBackground()
        self.chips_host = QWidget(self.scroll)
        self.chips_layout = QVBoxLayout(self.chips_host)
        self.chips_layout.setContentsMargins(14, 4, 14, 8)
        self.chips_layout.setSpacing(10)
        self.scroll.setWidget(self.chips_host)
        post_tags_layout.addWidget(self.scroll)

        favorite_tags_page = QWidget(self.content_stack)
        self.favorite_tags_layout = QVBoxLayout(favorite_tags_page)
        self.favorite_tags_layout.setContentsMargins(0, 0, 0, 0)
        self.favorite_tags_layout.setSpacing(0)

        attached_tags_page = QWidget(self.content_stack)
        attached_tags_layout = QVBoxLayout(attached_tags_page)
        attached_tags_layout.setContentsMargins(0, 0, 0, 0)
        attached_tags_layout.setSpacing(0)
        self.attached_scroll = ScrollArea(attached_tags_page)
        self.attached_scroll.setWidgetResizable(True)
        self.attached_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attached_scroll.enableTransparentBackground()
        self.attached_chips_host = QWidget(self.attached_scroll)
        self.attached_chips_layout = QVBoxLayout(self.attached_chips_host)
        self.attached_chips_layout.setContentsMargins(14, 4, 14, 8)
        self.attached_chips_layout.setSpacing(10)
        self.attached_empty_label = BodyLabel("尚未附着图片", self.attached_chips_host)
        self.attached_empty_label.setObjectName("DanbooruTagExportAttachedEmpty")
        self.attached_chips_layout.addWidget(self.attached_empty_label)
        self.attached_chips_layout.addStretch(1)
        self.attached_scroll.setWidget(self.attached_chips_host)
        attached_tags_layout.addWidget(self.attached_scroll)

        # Segment 顺序：CurrentImg-tags | Fav-tags | Attached-tags(最右，仅有 AttachImg 时出现)。
        self._content_pages = {
            "post_tags": post_tags_page,
            "fav_tags": favorite_tags_page,
            "attached_tags": attached_tags_page,
        }
        self.content_stack.addWidget(post_tags_page)
        self.content_stack.addWidget(favorite_tags_page)
        self.content_stack.addWidget(attached_tags_page)
        self.content_segment.addItem(
            "post_tags",
            "CurrentImg-tags",
            onClick=lambda _checked=False: self._select_content_page("post_tags"),
        )
        self.content_segment.addItem(
            "fav_tags",
            "Fav-tags",
            onClick=lambda _checked=False: self._select_content_page("fav_tags"),
        )
        # Attached-tags 不在初始 segment 中；有 AttachImg 时再 add 到最右侧。
        self.content_segment.setCurrentItem("post_tags")
        self.content_stack.setCurrentWidget(post_tags_page)
        segment_row.addWidget(self.content_segment, 1)
        root.addLayout(segment_row)
        root.addWidget(self.content_stack, 1)

        preview_block = QVBoxLayout()
        preview_block.setContentsMargins(14, 4, 14, 4)
        preview_block.setSpacing(4)
        preview_header = QHBoxLayout()
        preview_header.setSpacing(6)
        preview_header.addWidget(StrongBodyLabel("Prompt 预览", self))
        self.count_label = BodyLabel("0", self)
        self.count_label.setObjectName("DanbooruTagExportCount")
        # 紧挨标题，不占独立 copy_row；右侧工具组仍靠 stretch 顶到行尾。
        self.copy_btn = TransparentToolButton(FIF.COPY, self)
        self.copy_btn.setIconSize(QtCore.QSize(18, 18))
        self.copy_btn.setToolTip("复制 Prompt")
        self.copy_btn.clicked.connect(self.copy_requested.emit)
        preview_header.addWidget(self.copy_btn)
        preview_header.addWidget(self.count_label)
        preview_header.addStretch(1)
        self.clear_attach_btn = TransparentToolButton(CgsIcon.SCRIPT_TAG_CLEAR_ATTACH, self)
        self.clear_attach_btn.setObjectName("DanbooruTagExportClearAttachBtn")
        self.clear_attach_btn.setIconSize(QtCore.QSize(18, 18))
        self.clear_attach_btn.setToolTip("清除附着图（Attached-tags）")
        self.clear_attach_btn.clicked.connect(self._clear_attach_img)
        self.clear_attach_btn.hide()
        self.select_all_btn = TransparentToolButton(CgsIcon.SCRIPT_TAG_RESTORE, self)
        self.select_all_btn.setIconSize(QtCore.QSize(18, 18))
        self.select_all_btn.setToolTip("恢复默认(General)")
        self.select_all_btn.clicked.connect(self._select_default_groups)
        self.toggle_select_btn = TransparentToolButton(CgsIcon.SCRIPT_TAG_SELECT_ALL, self)
        self.toggle_select_btn.setIconSize(QtCore.QSize(18, 18))
        self.toggle_select_btn.setToolTip("全选")
        self.toggle_select_btn.clicked.connect(self._toggle_select_all)
        self.format_btn = TransparentToolButton(CgsIcon.SCRIPT_TAG_FORMAT, self)
        self.format_btn.setIconSize(QtCore.QSize(18, 18))
        self.format_btn.setToolTip("格式化 Prompt")
        self.format_btn.clicked.connect(self._format_preview)
        preview_header.addWidget(self.clear_attach_btn)
        preview_header.addWidget(self.select_all_btn)
        preview_header.addWidget(self.toggle_select_btn)
        preview_header.addWidget(self.format_btn)
        preview_block.addLayout(preview_header)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(6)
        self.preview = PlainTextEdit(self)
        self.preview.setMaximumHeight(140)
        self.preview.setObjectName("DanbooruTagExportPreview")
        self._comfy_highlighter = ComfyPromptHighlighter(
            self.preview.document(),
            known=self.comfy_known,
            categories=self._comfy_categories,
        )

        # 两侧列：图高 = preview 高 − 标题 − spacing，使整列与 preview 对齐。
        # 上下序 SoT：.trellis/spec/backend/tag-export-attach-contract.md (CGS007 §3)
        #   CurrentImg: caption → label；AttachImg: label → caption（禁止对调对齐）
        self._side_img_col_spacing = 4
        self.currentImg_col = QWidget(self)
        self.currentImg_col.setObjectName("DanbooruTagExportCurrentImgCol")
        current_img_layout = QVBoxLayout(self.currentImg_col)
        current_img_layout.setContentsMargins(0, 0, 0, 0)
        current_img_layout.setSpacing(self._side_img_col_spacing)
        self.currentImg_caption = StrongBodyLabel("CurrentImg", self.currentImg_col)
        self.currentImg_label = ImageLabel(self.currentImg_col)
        self.currentImg_label.setObjectName("DanbooruTagExportCurrentImg")
        self.currentImg_label.setScaledContents(False)
        self.currentImg_label.setAlignment(Qt.AlignCenter)
        current_img_layout.addWidget(self.currentImg_caption)
        current_img_layout.addWidget(self.currentImg_label, 0, Qt.AlignHCenter | Qt.AlignTop)
        current_img_layout.addStretch(1)
        self.currentImg_col.hide()

        self.attachImg_col = QWidget(self)
        self.attachImg_col.setObjectName("DanbooruTagExportAttachImgCol")
        attach_img_layout = QVBoxLayout(self.attachImg_col)
        attach_img_layout.setContentsMargins(0, 0, 0, 0)
        attach_img_layout.setSpacing(self._side_img_col_spacing)
        self.attachImg_label = ImageLabel(self.attachImg_col)
        self.attachImg_label.setObjectName("DanbooruTagExportAttachImg")
        self.attachImg_label.setScaledContents(False)
        self.attachImg_label.setAlignment(Qt.AlignCenter)
        self.attachImg_caption = StrongBodyLabel("AttachImg", self.attachImg_col)
        attach_img_layout.addWidget(self.attachImg_label, 0, Qt.AlignHCenter | Qt.AlignTop)
        attach_img_layout.addWidget(self.attachImg_caption)
        attach_img_layout.addStretch(1)
        self.attachImg_col.hide()

        preview_row.addWidget(self.currentImg_col, 0)
        preview_row.addWidget(self.preview, 1)
        preview_row.addWidget(self.attachImg_col, 0)

        preview_block.addLayout(preview_row)

        root.addLayout(preview_block)

        self.comfy_nl_row = QWidget(self)
        comfy_nl_layout = QHBoxLayout(self.comfy_nl_row)
        comfy_nl_layout.setContentsMargins(14, 4, 14, 4)
        comfy_nl_layout.setSpacing(8)
        self.comfy_nl_input = LineEdit(self.comfy_nl_row)
        self.comfy_nl_input.setPlaceholderText("描述要修改的内容")
        self.comfy_nl_input.textChanged.connect(self._sync_comfy_nl_controls)
        comfy_nl_layout.addWidget(self.comfy_nl_input, 1)
        self.comfy_nl_btn = ToolButton(CgsIcon.SCRIPT_TAG_AI_MERGE, self.comfy_nl_row)
        self.comfy_nl_btn.setObjectName("ComfyNlButton")
        self.comfy_nl_btn.setFixedSize(QtCore.QSize(32, 32))
        self.comfy_nl_btn.setIconSize(QtCore.QSize(18, 18))
        self.comfy_nl_btn.setToolTip("AI 合并 Prompt")
        self.comfy_nl_btn.clicked.connect(self.comfy_nl_requested.emit)

        # Keep the progress host as a separate layout item with the same size as
        # the send button. Busy state swaps these two items instead of overlaying
        # a spinner on top of a still-present button.
        self.comfy_nl_indeterminate_ring_host = QWidget(self.comfy_nl_row)
        self.comfy_nl_indeterminate_ring_host.setObjectName("ComfyNlIndeterminateRingHost")
        self.comfy_nl_indeterminate_ring_host.setFixedSize(QtCore.QSize(32, 32))
        self.comfy_nl_indeterminate_ring = IndeterminateProgressRing(
            self.comfy_nl_indeterminate_ring_host, start=False
        )
        self.comfy_nl_indeterminate_ring.setFixedSize(QtCore.QSize(18, 18))
        self.comfy_nl_indeterminate_ring.setStrokeWidth(3)
        self.comfy_nl_indeterminate_ring.move(7, 7)
        self.comfy_nl_indeterminate_ring_host.hide()
        comfy_nl_layout.addWidget(self.comfy_nl_btn)
        comfy_nl_layout.addWidget(self.comfy_nl_indeterminate_ring_host)
        root.addWidget(self.comfy_nl_row)

        # Action = imgPalace job intent only (not clipboard). Choices come from the
        # registry so new product actions extend in one place, not a second hardcoded list.
        # QWidget host so conf-empty can hide the whole row (layout alone cannot setVisible).
        self.imgpalace_row = QWidget(self)
        imgpalace_layout = QHBoxLayout(self.imgpalace_row)
        imgpalace_layout.setContentsMargins(14, 4, 14, 4)
        imgpalace_layout.setSpacing(8)
        imgpalace_layout.addWidget(BodyLabel("Action", self.imgpalace_row))
        self.action_combo = ComboBox(self.imgpalace_row)
        self._populate_action_combo()
        imgpalace_layout.addWidget(self.action_combo, 1)
        self.imgpalace_btn = PushButton("to_imgPalace", self.imgpalace_row)
        self.imgpalace_btn.setIcon(CgsIcon.SCRIPT_TAG_TO_IMGPALACE)
        self.imgpalace_btn.clicked.connect(self.imgpalace_requested.emit)
        imgpalace_layout.addWidget(self.imgpalace_btn)
        root.addWidget(self.imgpalace_row)

        # ComfyUI UNET presets are registry data so adding a model does not require
        # another GUI branch.
        self.comfy_row = QWidget(self)
        comfy_layout = QHBoxLayout(self.comfy_row)
        comfy_layout.setContentsMargins(14, 4, 14, 4)
        comfy_layout.setSpacing(8)
        comfy_layout.addWidget(BodyLabel("Comfy UNET", self.comfy_row))
        self.comfy_unet_combox = ComboBox(self.comfy_row)
        for preset_key, preset in COMFY_UNET_PRESETS.items():
            preset_label = str(preset.get("label") or preset_key)
            if not preset_label.casefold().startswith("anima "):
                preset_label = f"Anima {preset_label}"
            self.comfy_unet_combox.addItem(preset_label, userData=preset_key)
        self.comfy_unet_combox.setCurrentIndex(0)
        self.comfy_unet_combox.currentIndexChanged.connect(self._on_comfy_preset_changed)
        comfy_layout.addWidget(self.comfy_unet_combox, 1)
        # 图内补全：让 WD14 从图片本身读 tag，补上 danbooru 标注遗漏的部分。
        # 可用性由外部注入（见 set_wd14_status），面板不自己发网络请求。
        self.wd14_btn = TogglePushButton("图内补全", self.comfy_row)
        self.wd14_btn.setCheckable(True)
        self.wd14_btn.setEnabled(False)
        self.wd14_btn.setToolTip("检测 WD14 节点中…")
        comfy_layout.addWidget(self.wd14_btn)
        # 任务队列/历史进独立弹窗，这里只放一颗图标按钮：面板已有 6 排控件，
        # 再加一排纵列就是用户抱怨过的「ux 逻辑被拉长」。
        self.comfy_jobs_btn = TransparentToolButton(CgsIcon.SCRIPT_TAG_COMFY_QUEUE, self.comfy_row)
        self.comfy_jobs_btn.setIconSize(QtCore.QSize(18, 18))
        self.comfy_jobs_btn.setToolTip("Comfy 任务队列")
        self.comfy_jobs_btn.clicked.connect(self.comfy_jobs_requested.emit)
        comfy_layout.addWidget(self.comfy_jobs_btn)
        self.comfy_generate_btn = PrimaryToolButton(CgsIcon.SCRIPT_TAG_COMFY_GENERATE, self.comfy_row)
        self.comfy_generate_btn.setFixedSize(QtCore.QSize(32, 32))
        self.comfy_generate_btn.setIconSize(QtCore.QSize(18, 18))
        self.comfy_generate_btn.clicked.connect(lambda: self.comfy_requested.emit(str(self.comfy_unet_combox.currentData())))
        comfy_layout.addWidget(self.comfy_generate_btn)

        # 与 comfy_nl 同模式：host 占位 = ToolButton 32×32，busy 时 swap 显隐。
        # 旧 112×32 + move(40/47) 是 PushButton「to Comfy」文案期的宽度，图标按钮会空出一截。
        self.comfy_progress_ring_host = QWidget(self.comfy_row)
        self.comfy_progress_ring_host.setObjectName("ComfyProgressRingHost")
        self.comfy_progress_ring_host.setFixedSize(QtCore.QSize(32, 32))
        self.comfy_progress_ring = ProgressRing(self.comfy_progress_ring_host)
        self.comfy_progress_ring.setTextVisible(False)
        self.comfy_progress_ring.setFixedSize(QtCore.QSize(32, 32))
        self.comfy_progress_ring.setRange(0, 100)
        self.comfy_progress_ring.move(0, 0)
        self.comfy_indeterminate_ring = IndeterminateProgressRing(
            self.comfy_progress_ring_host, start=False
        )
        self.comfy_indeterminate_ring.setFixedSize(QtCore.QSize(18, 18))
        self.comfy_indeterminate_ring.setStrokeWidth(3)
        self.comfy_indeterminate_ring.move(7, 7)
        self.comfy_indeterminate_ring.raise_()
        self.comfy_progress_ring_host.hide()
        comfy_layout.addWidget(self.comfy_progress_ring_host)
        root.addWidget(self.comfy_row)

        # 重绘强度：一个滑块取代「文生图/图生图」模式选择器（design §11.3a，Krita 语义）。
        # 100% 走空白 latent，低于 100% 以当前图为起点。与 comfy_row 同门控。
        self.strength_row = QWidget(self)
        strength_layout = QHBoxLayout(self.strength_row)
        strength_layout.setContentsMargins(14, 0, 14, 14)
        strength_layout.setSpacing(8)
        strength_layout.addWidget(BodyLabel("重绘强度", self.strength_row))
        self.denoise_slider = Slider(Qt.Horizontal, self.strength_row)
        self.denoise_slider.setRange(10, 100)
        self.denoise_slider.setValue(100)
        # 实测区间必须写在这里：按 Krita 惯例拖到 50% 在本模型上是空转，
        # 不告知用户就会被判定成「功能坏了」。只如实告知，不替用户钳制取值。
        self.denoise_slider.setToolTip(
            "重绘强度：turbo 需 ≥85% 才会改动内容，base / aesthetic 约 60% 起效。"
        )
        self.denoise_slider.valueChanged.connect(self._on_denoise_changed)
        strength_layout.addWidget(self.denoise_slider, 1)
        self.denoise_label = BodyLabel("100%", self.strength_row)
        strength_layout.addWidget(self.denoise_label)
        root.addWidget(self.strength_row)

        self._sync_integration_row_visibility()
        # LLM provider 与 fav-tags-translate 共用同一状态机；settings 保存会推 state_changed。
        self._ai_provider_session = AiProviderConfigSession.instance()
        self._ai_provider_session.state_changed.connect(self._on_ai_provider_state_changed)
        self._sync_comfy_nl_row_visibility()

        # 必须等 comfy_generate_btn 建成后再接：槽会读它。早接一行，高亮器构造期的
        # rehighlight 就会先把 _preview_dirty 置真、再抛 AttributeError 被 Qt
        # 钩子吞掉，结果是面板开出来 prompt 永远空白且 chip 全部失灵。
        # 选 contentsChange 而非 textChanged：纯格式变化只发后者，不是用户编辑。
        self.preview.document().contentsChange.connect(self._mark_preview_dirty)
        # SegmentedItem / PushButton 在 QDialog 内会被标成 autoDefault/default；
        # SearchLineEdit 回车会被 QDialog 当成“点 default 按钮”，跳回 CurrentImg-tags。
        self._disable_dialog_default_buttons()

    def _disable_dialog_default_buttons(self, root: QWidget | None = None) -> None:
        """禁止 Dialog 把任意 QPushButton 当作 Enter 默认按钮。

        SegmentedToolItem 等是 ToolButton，没有 setAutoDefault；只处理真有该 API 的按钮。
        """
        host = root if root is not None else self
        for button in host.findChildren(QPushButton):
            if hasattr(button, "setAutoDefault"):
                button.setAutoDefault(False)
            if hasattr(button, "setDefault"):
                button.setDefault(False)

    def _select_content_page(self, page_key: str):
        page = self._content_pages.get(page_key)
        if page is None:
            return
        self.content_stack.setCurrentWidget(page)
        # attached_tags 可能已从 segment remove；对非法 routeKey 调 setCurrentItem
        # 会在 pivot 内部 RouteKeyError（见 _sync_attached_segment_visibility）。
        segment_items = getattr(self.content_segment, "items", None) or {}
        if page_key not in segment_items:
            return
        # qfluent Pivot.setCurrentItem 在 route 已是 current 时直接 return，
        # 且不会强制 relayout。动态 addItem 后首次切换必须能再次点中。
        if self.content_segment.currentRouteKey() == page_key:
            item = segment_items.get(page_key)
            if item is not None:
                item.setSelected(True)
            self.content_segment.update()
            return
        self.content_segment.setCurrentItem(page_key)
        # 动态插入的 item 在同事件循环内 size/x 可能仍为 0；slideAni 会画错选中层挡住点击。
        # 下一帧再对齐 indicator（CGS007 segment 动态项）。
        QtCore.QTimer.singleShot(0, lambda key=page_key: self._realign_segment_indicator(key))

    def _realign_segment_indicator(self, page_key: str) -> None:
        segment_items = getattr(self.content_segment, "items", None) or {}
        if page_key not in segment_items:
            return
        if self.content_segment.currentRouteKey() != page_key:
            return
        item = segment_items[page_key]
        if item.width() <= 1:
            # 仍未 layout：再 defer 一次。
            QtCore.QTimer.singleShot(0, lambda key=page_key: self._realign_segment_indicator(key))
            return
        adjust = getattr(self.content_segment, "_adjustIndicatorPos", None)
        if callable(adjust):
            adjust()
        slide_animation = getattr(self.content_segment, "slideAni", None)
        if slide_animation is not None and hasattr(slide_animation, "setValue"):
            geometry_fn = getattr(self.content_segment, "currentIndicatorGeometry", None)
            if callable(geometry_fn):
                try:
                    slide_animation.setValue(geometry_fn())
                except Exception:
                    pass
        self.content_segment.update()

    def _on_ai_provider_state_changed(self, _previous, _current):
        self._sync_comfy_nl_row_visibility()

    def _sync_comfy_nl_row_visibility(self):
        """comfy_nl_row：仅 LLM provider 已配置时可见（与 fav-translate 同门控）。"""
        session = getattr(self, "_ai_provider_session", None)
        ai_configured = session.is_configured() if session is not None else False
        self.comfy_nl_row.setVisible(ai_configured)
        self.comfy_nl_row.setEnabled(ai_configured)
        self._sync_comfy_nl_controls()

    def _sync_integration_row_visibility(self):
        """Configuration presence = row availability; no enable switches."""
        imgpalace_configured = is_imgpalace_configured()
        self.imgpalace_row.setVisible(imgpalace_configured)
        self.imgpalace_row.setEnabled(imgpalace_configured)

        comfy_configured = is_comfy_configured()
        self.comfy_row.setVisible(comfy_configured)
        self.comfy_row.setEnabled(comfy_configured)
        self.strength_row.setVisible(comfy_configured)
        self.strength_row.setEnabled(comfy_configured)

    def _sync_comfy_nl_controls(self, *_args):
        enabled = (
            self.comfy_nl_row.isEnabled()
            and not self._comfy_nl_busy
        )
        self.comfy_nl_input.setEnabled(enabled)
        self.comfy_nl_btn.setEnabled(enabled and bool(self.comfy_nl_input.text().strip()))

    def comfy_nl_instruction(self) -> str:
        return self.comfy_nl_input.text().strip()

    def set_comfy_nl_busy(self, busy: bool):
        self._comfy_nl_busy = bool(busy)
        if self._comfy_nl_busy:
            self.comfy_nl_btn.hide()
            self.comfy_nl_indeterminate_ring_host.show()
            self.comfy_nl_indeterminate_ring.start()
        else:
            self.comfy_nl_indeterminate_ring.stop()
            self.comfy_nl_indeterminate_ring_host.hide()
            self.comfy_nl_btn.show()
        self._sync_comfy_nl_controls()

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
        # CurrentImg 分组在上（高频）；palette（Quality/Score/…）在下（低频）。
        for label, tags in self.prompt.groups:
            if not tags:
                continue
            section = StrongBodyLabel(label, self.chips_host)
            self.chips_layout.addWidget(section)
            flow_host = QWidget(self.chips_host)
            flow = FlowLayout(flow_host)
            flow.setContentsMargins(0, 0, 0, 0)
            flow.setHorizontalSpacing(6)
            flow.setVerticalSpacing(6)
            for tag in tags:
                button = TagChipButton(flow_host)
                button.setToolTip(tag)
                button.setCheckable(True)
                button.setChecked(self.prompt.is_selected(tag))
                button.set_full_text(tag)
                button.toggled.connect(lambda checked, current_tag=tag: self._set_tag_selected(current_tag, checked))
                flow.addWidget(button)
                self._tag_buttons[tag] = button
            self.chips_layout.addWidget(flow_host)
        self._load_comfy_palette()
        self._comfy_fav_chips = ComfyFavoritesChipGroups(
            host=self._content_pages["fav_tags"],
            layout=self.favorite_tags_layout,
            editor=self.preview,
            known=self.comfy_known,
            prompt_getter=self.comfy_prompt_text,
            replace_prompt=self.replace_preview_text,
            # Fav SECTION=character 等必须登记进 known，否则高亮白字 + attach 进 General。
            register_section=self.register_preview_tag_section,
        )
        self._sync_score_chip_state()
        self._refresh_preview()

    def _load_comfy_palette(self):
        palette = load_comfy_palette()
        selected_safety = comfy_prompt_spec.safety_tag_for_rating(self.prompt.post.rating)
        for group in palette["groups"]:
            section = StrongBodyLabel(group["label"], self.chips_host)
            self.chips_layout.addWidget(section)
            flow_host = QWidget(self.chips_host)
            flow = FlowLayout(flow_host)
            flow.setContentsMargins(0, 0, 0, 0)
            flow.setHorizontalSpacing(6)
            flow.setVerticalSpacing(6)
            tags = getattr(comfy_prompt_spec, group["source"])
            for tag in tags:
                button = TagChipButton(flow_host)
                button.setToolTip(tag)
                button.setCheckable(True)
                if group["source"] == "SAFETY_TAGS":
                    button.setChecked(tag == selected_safety)
                button.toggled.connect(
                    lambda checked, current_tag=tag: self._toggle_palette_tag(current_tag, checked)
                )
                button.set_full_text(tag)
                flow.addWidget(button)
                self._palette_buttons[tag] = button
            self.chips_layout.addWidget(flow_host)

    def _sync_score_chip_state(self):
        disabled = self.selected_comfy_unet() == "aesthetic"
        tooltip = "Aesthetic preset does not use score tags" if disabled else "score tag"
        for tag in comfy_prompt_spec.SCORE_TAGS:
            button = self._palette_buttons.get(tag)
            if button is not None:
                button.setEnabled(not disabled)
                button.setToolTip(tooltip)

    def _on_comfy_preset_changed(self):
        self._sync_score_chip_state()
        self._refresh_preview()

    def _generated_comfy_prompt(self) -> str:
        """从当前 chip 选中态拼出系统回填 prompt（一次入口内完成 payload + prefix）。"""
        field_by_label = {
            "Character": "tag_string_character",
            "Artist": "tag_string_artist",
            "Copyright": "tag_string_copyright",
            "General": "tag_string_general",
            "Meta": "tag_string_meta",
        }
        payload = {field: "" for field in field_by_label.values()}
        aesthetic = self.selected_comfy_unet() == "aesthetic"
        for label, tags in self.prompt.groups:
            selected = [
                tag
                for tag in tags
                if self.prompt.is_selected(tag)
                and not (aesthetic and comfy_prompt_spec.is_score_tag(tag))
            ]
            payload[field_by_label[label]] = " ".join(selected)

        quality_prefix = COMFY_UNET_PRESETS[self.selected_comfy_unet()]["quality_prefix"]
        safety = comfy_prompt_spec.safety_tag_for_rating(self.prompt.post.rating)
        if safety:
            parts = [
                part.strip()
                for part in quality_prefix.split(",")
                if part.strip() and part.strip() not in comfy_prompt_spec.SAFETY_TAGS
            ]
            if safety not in parts:
                parts.append(safety)
            quality_prefix = ", ".join(parts)

        return _comfy_workflow.build_anima_prompt(
            payload,
            quality_prefix=quality_prefix,
            include_meta=bool(payload["tag_string_meta"]),
        )["prompt"]

    def _mark_preview_dirty(self, *_args):
        if self._applying_generated:
            return
        self._preview_dirty = True
        # 与 _sync_preview_chrome 同一套 enable 口径，禁止只开 comfy 漏掉 copy。
        self._sync_preview_chrome()

    def comfy_prompt_text(self) -> str:
        """Comfy 提交原文：永远是编辑器内容，与 chip 选中态解耦。"""
        return self.preview.toPlainText()

    def comfy_prompt_violations(self):
        return PromptDoc.from_text(
            self.preview.toPlainText(),
            known=self.comfy_known,
            normalize=False,
        ).violations()

    def wd14_enabled(self) -> bool:
        return self.wd14_btn.isEnabled() and self.wd14_btn.isChecked()

    def selected_denoise(self) -> float:
        return self.denoise_slider.value() / 100

    def set_comfy_progress(self, current: int = 0, maximum: int = 0, node: str = ""):
        """在提交按钮原位显示确定进度环和持续运行指示。"""
        self.comfy_generate_btn.hide()
        self.comfy_progress_ring_host.show()
        if maximum > 0:
            percent = min(100, max(0, int(current * 100 / maximum)))
            self.comfy_progress_ring.setValue(percent)
        else:
            self.comfy_progress_ring.setValue(0)
        self.comfy_indeterminate_ring.show()
        self.comfy_indeterminate_ring.start()

    def clear_comfy_progress(self):
        self.comfy_indeterminate_ring.stop()
        self.comfy_indeterminate_ring.hide()
        self.comfy_progress_ring_host.hide()
        self.comfy_progress_ring.setValue(0)
        self.comfy_progress_ring_host.setToolTip("")
        self.comfy_generate_btn.show()
        self._on_denoise_changed(self.denoise_slider.value())

    def _on_denoise_changed(self, value: int):
        self.denoise_label.setText(f"{value}%")

    def set_wd14_status(self, available: bool, reason: str):
        """由控制器注入探测结果。不可用时**说明原因**，而不是留一个哑掉的开关。"""
        self.wd14_btn.setEnabled(available)
        if not available:
            self.wd14_btn.setChecked(False)
        self.wd14_btn.setToolTip(reason if reason else "让 WD14 从图片本身补充 danbooru 遗漏的 tag")

    def merge_wd14_tags(self, tags: str) -> int:
        """把 WD14 补充 tag 并入编辑器，返回实际新增条数。

        经 `PromptDoc.merge_tags` 去重并按 M3 段序重排，与 🪄 共用同一实现；
        各写一套，「补全后」与「补全前再格式化」就会给出两段不同的文本。
        """
        document = PromptDoc.from_text(self.comfy_prompt_text(), known=self.comfy_known)
        merged = document.merge_tags(split_prompt(tags))
        added = len(split_prompt(merged.to_text())) - len(split_prompt(document.to_text()))
        self.replace_preview_text(merged.to_text())
        return added

    def replace_preview_text(self, text: str) -> bool:
        """整体替换但保留 undo 栈 —— `setPlainText` 会清空它，Ctrl+Z 就废了。"""
        if text == self.preview.toPlainText():
            return False
        cursor = self.preview.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        return True

    def apply_comfy_controls_from_snapshot(self, snapshot: dict) -> None:
        """仅还原 unet / denoise / wd14；不改 preview、不清 chips。"""
        if not isinstance(snapshot, dict):
            raise TypeError("apply_comfy_controls_from_snapshot requires a dict snapshot")
        unet_key = str(snapshot.get("unet") or "turbo")
        try:
            denoise_percent = int(snapshot.get("denoise", 100))
        except (TypeError, ValueError):
            denoise_percent = 100
        denoise_percent = max(10, min(100, denoise_percent))
        wd14_wanted = bool(snapshot.get("wd14"))

        preset_index = self.comfy_unet_combox.findData(unet_key)
        if preset_index < 0:
            preset_index = self.comfy_unet_combox.findData("turbo")
        # blockSignals：避免 preset 变更触发 _on_comfy_preset_changed → 用 chip 态整段盖掉用户 preview。
        self.comfy_unet_combox.blockSignals(True)
        self.comfy_unet_combox.setCurrentIndex(max(0, preset_index))
        self.comfy_unet_combox.blockSignals(False)

        # qfluent Slider 的手柄位置挂在 valueChanged→_adjustHandlePos 上。
        # blockSignals(True) 再 setValue 只会改内部 value/标签，手柄仍停在旧位置。
        self.denoise_slider.setValue(denoise_percent)
        if self.denoise_slider.value() != denoise_percent:
            self._on_denoise_changed(self.denoise_slider.value())
            adjust_handle = getattr(self.denoise_slider, "_adjustHandlePos", None)
            if callable(adjust_handle):
                adjust_handle()

        if self.wd14_btn.isEnabled():
            self.wd14_btn.blockSignals(True)
            self.wd14_btn.setChecked(wd14_wanted)
            self.wd14_btn.blockSignals(False)

        self._sync_score_chip_state()
        self._sync_preview_chrome()

    def set_attach_img(self, attach: AttachImg | None) -> None:
        """单槽附着：覆盖 self.attachImg，重建 Attached-tags（全未激活），不改 preview。"""
        self.attachImg = attach
        self._rebuild_attached_tags_page()
        # 必须先处理 segment 路由（含 remove 前切走 currentRouteKey），再刷侧栏/按钮。
        self._sync_attached_segment_visibility()
        self._sync_preview_side_images()
        self._sync_clear_attach_btn()
        if attach is not None:
            # 动态 addItem 后同帧 setCurrentItem 会因 item 宽为 0 画错选中层；
            # 先切 stack，下一帧再选 segment（可直接点 Attached-tags，不必经 Fav）。
            self.content_stack.setCurrentWidget(self._content_pages["attached_tags"])
            QtCore.QTimer.singleShot(
                0, lambda: self._select_content_page("attached_tags")
            )

    def _clear_attach_img(self) -> None:
        """清除唯一 AttachImg；不剥离 preview 里已注入的 token。"""
        if self.attachImg is None:
            return
        self.set_attach_img(None)

    def _sync_clear_attach_btn(self) -> None:
        clear_btn = getattr(self, "clear_attach_btn", None)
        if clear_btn is None:
            return
        has_attach = self.attachImg is not None
        clear_btn.setVisible(has_attach)
        clear_btn.setEnabled(has_attach)

    def _sync_attached_segment_visibility(self) -> None:
        """无 AttachImg 时 segment 不出现 Attached-tags；有则挂在最右侧。

        qfluent Pivot.removeWidget 不会清 stale `_currentRouteKey`（仅 items 空时才置 None）。
        若当前选中 attached_tags 时直接 remove，paintEvent / setCurrentItem 会
        RouteKeyError: `attached_tags` is illegal。必须先切到仍存在的 route 再 remove。
        """
        route_key = "attached_tags"
        has_attach = self.attachImg is not None
        items = getattr(self.content_segment, "items", None) or {}
        if has_attach:
            if route_key not in items:
                self.content_segment.addItem(
                    route_key,
                    "Attached-tags",
                    onClick=lambda _checked=False: self._select_content_page(route_key),
                )
                # 动态 add 的 SegmentedItem 同样会被 Dialog 标 default，需再清一次。
                self._disable_dialog_default_buttons(self.content_segment)
                # 强制布局，避免新 item 宽高为 0 时 slideAni 画在错误位置挡住点击。
                self.content_segment.adjustSize()
                self.content_segment.updateGeometry()
                parent_layout = self.content_segment.parentWidget()
                if parent_layout is not None:
                    parent_layout.updateGeometry()
            return
        if route_key not in items:
            return
        # 先离开 attached_tags，再 remove（见上 RouteKeyError）。
        if self.content_segment.currentRouteKey() == route_key:
            fallback_key = "post_tags"
            if fallback_key in items:
                self.content_stack.setCurrentWidget(self._content_pages[fallback_key])
                self.content_segment.setCurrentItem(fallback_key)
            else:
                self.content_segment._currentRouteKey = None
        self.content_segment.removeWidget(route_key)

    def register_preview_tag_section(self, tag: str, section: str) -> None:
        """Learn a tag→section into comfy_known + highlighter categories (CGS007).

        Fav-tags SECTION_OPTIONS and Attached-tags toggles insert with an explicit
        section. Without registering here:
        - highlighter paints white (no category)
        - submit/attach lexicon misses Character (no @ marker) → General dump
        """
        token = str(tag or "").strip()
        section_key = str(section or "").strip()
        if not token or not section_key:
            return
        label = _SECTION_TO_GROUP_LABEL.get(section_key)
        if label is None and section_key in GROUP_TO_SECTION:
            # Accept TagPrompt labels too.
            label = section_key
            section_key = GROUP_TO_SECTION[section_key]
        if label is None:
            return
        for alias in _token_aliases(token):
            self.comfy_known[alias] = section_key
        category = comfy_prompt_spec.GROUP_TO_CATEGORY.get(label)
        if category is not None:
            for alias in _token_aliases(token):
                bare = alias[1:] if str(alias).startswith("@") else alias
                self._comfy_categories.setdefault(alias, category)
                self._comfy_categories.setdefault(bare, category)
                normalized = comfy_prompt_spec.normalize_tag(bare)
                self._comfy_categories.setdefault(normalized, category)
        highlighter = getattr(self, "_comfy_highlighter", None)
        if highlighter is not None:
            highlighter.set_maps(self.comfy_known, self._comfy_categories)

    def snapshot_tag_groups(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Submit-time SoT via TagGroupsState (all five labels, not chip-subset only).

        Classifies the exact editor_prompt with CurrentImg groups **plus**
        comfy_known (includes fav SECTION=character / artist inserts).
        """
        state = TagGroupsState.capture_for_submit(
            editor_prompt=self.comfy_prompt_text(),
            prompt=self.prompt,
            extra_known=self.comfy_known,
        )
        return state.as_groups()

    def attach_from_comfy(
        self,
        *,
        pic: QPixmap | None,
        editor_prompt: str,
        snapshot: dict,
        job_id: str | None = None,
    ) -> None:
        """Comfy 成图附着：AttachImg + 仅还原 comfy 控件；禁止覆盖 preview。

        Groups resolution is ONLY TagGroupsState.resolve_for_attach (CGS007 FSM).
        """
        state = TagGroupsState.resolve_for_attach(
            snapshot=snapshot if isinstance(snapshot, dict) else None,
            editor_prompt=editor_prompt,
            lexicon=lexicon_for_panel(self),
        )
        attach = AttachImg(
            pic=_copy_pixmap(pic),
            groups=state.as_groups(),
            source="comfy",
            job_id=str(job_id) if job_id else None,
        )
        self.set_attach_img(attach)
        self.apply_comfy_controls_from_snapshot(snapshot)

    def attach_from_viewer_post(
        self,
        post: DanbooruPost,
        *,
        pic: QPixmap | None = None,
    ) -> None:
        """viewer 当前 post 附着：TagGroupsState.from_viewer_post → 全未激活。"""
        state = TagGroupsState.from_viewer_post(post)
        attach = AttachImg(
            pic=_copy_pixmap(pic),
            groups=state.as_groups(),
            source="viewer",
            post_id=int(getattr(post, "post_id", 0) or 0) or None,
        )
        self.set_attach_img(attach)

    def _clear_attached_chips_layout(self) -> None:
        while self.attached_chips_layout.count():
            item = self.attached_chips_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            if widget is self.attached_empty_label:
                widget.hide()
                continue
            widget.setParent(None)
            widget.deleteLater()
        self._attached_tag_buttons.clear()
        self._attached_tag_sections.clear()

    def _rebuild_attached_tags_page(self) -> None:
        """与 CurrentImg-tags 相同：按 groups 分段 StrongBodyLabel + FlowLayout chips。"""
        self._clear_attached_chips_layout()
        attach = self.attachImg
        if attach is None:
            self.attached_empty_label.setText("尚未附着图片")
            self.attached_empty_label.show()
            self.attached_chips_layout.addWidget(self.attached_empty_label)
            self.attached_chips_layout.addStretch(1)
            return

        self.attached_empty_label.hide()
        groups = attach.groups or ()
        if not groups:
            empty = BodyLabel("附着物无可用 tags", self.attached_chips_host)
            self.attached_chips_layout.addWidget(empty)
            self.attached_chips_layout.addStretch(1)
            return

        for label, tags in groups:
            if not tags:
                continue
            section = StrongBodyLabel(label, self.attached_chips_host)
            self.attached_chips_layout.addWidget(section)
            flow_host = QWidget(self.attached_chips_host)
            flow = FlowLayout(flow_host)
            flow.setContentsMargins(0, 0, 0, 0)
            flow.setHorizontalSpacing(6)
            flow.setVerticalSpacing(6)
            section_key = GROUP_TO_SECTION.get(label, "body")
            for tag in tags:
                button = TagChipButton(flow_host)
                button.setObjectName("DanbooruAttachedTagChip")
                button.setToolTip(tag)
                button.setCheckable(True)
                button.setChecked(False)
                button.set_full_text(tag)
                button.toggled.connect(
                    lambda checked, current_tag=tag: self._on_attached_tag_toggled(
                        current_tag, checked
                    )
                )
                flow.addWidget(button)
                self._attached_tag_buttons[tag] = button
                self._attached_tag_sections[tag] = section_key
            self.attached_chips_layout.addWidget(flow_host)
        self.attached_chips_layout.addStretch(1)

    def _on_attached_tag_toggled(self, tag: str, checked: bool) -> None:
        current = self.preview.toPlainText()
        section = self._attached_tag_sections.get(tag, "body")
        if checked:
            self.register_preview_tag_section(tag, section)
            next_text = insert_tag_into_text(
                current,
                tag,
                section=section,
                known=self.comfy_known,
            )
        else:
            next_text = remove_tag_from_text(current, tag)
        if next_text != current:
            self.replace_preview_text(next_text)
        self._preview_dirty = True
        self._sync_preview_chrome()

    @staticmethod
    def _side_image_target_size(source: QPixmap, height: int) -> QSize:
        target_height = max(1, int(height))
        if source is None or source.isNull() or source.height() <= 0:
            return QSize(max(1, target_height // 2), target_height)
        target_width = max(1, round(target_height * source.width() / source.height()))
        return QSize(target_width, target_height)

    def _paint_side_image_label(self, label: ImageLabel, source: QPixmap, height: int) -> None:
        target = self._side_image_target_size(source, height)
        label.setFixedSize(target)
        label.setScaledContents(False)
        if source is None or source.isNull():
            label.clear()
            return
        scaled = source.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def _side_image_display_height(self) -> int:
        """图本身高度 = preview 高 − 标题行 − 列 spacing，使整列与 preview 齐高。"""
        preview_height = max(1, self.preview.height() or self.preview.maximumHeight() or 140)
        caption = getattr(self, "currentImg_caption", None)
        caption_height = 0
        if caption is not None:
            caption_height = max(
                caption.sizeHint().height(),
                caption.height(),
                caption.fontMetrics().height(),
            )
        spacing = int(getattr(self, "_side_img_col_spacing", 4) or 0)
        return max(1, preview_height - caption_height - spacing)

    def _sync_preview_side_images(self) -> None:
        has_attach = self.attachImg is not None
        self.currentImg_col.setVisible(has_attach)
        self.attachImg_col.setVisible(has_attach)
        if not has_attach:
            return
        image_height = self._side_image_display_height()
        self._paint_side_image_label(self.currentImg_label, self.currentImg.pic, image_height)
        self._paint_side_image_label(self.attachImg_label, self.attachImg.pic, image_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.attachImg is not None:
            self._sync_preview_side_images()

    def showEvent(self, event):
        super().showEvent(event)
        if self.attachImg is not None:
            self._sync_preview_side_images()

    def apply_returned_job_snapshot(self, snapshot: dict) -> None:
        """Deprecated：旧 tagsReturn 整段写回。正式路径仅还原 comfy 控件（不改 preview）。"""
        self.apply_comfy_controls_from_snapshot(snapshot)

    def apply_returned_job_prompt(self, prompt: str) -> None:
        """Deprecated：不再写 preview；仅 no-op 兼容旧调用签名。"""
        del prompt

    def _format_preview(self):
        current = self.preview.toPlainText()
        formatted = PromptDoc.from_text(current, known=self.comfy_known).to_text()
        if self.replace_preview_text(formatted):
            self.preview.setFocus()

    def _toggle_palette_tag(self, tag: str, checked: bool):
        if checked:
            cursor = self.preview.textCursor()
            cursor.movePosition(QTextCursor.End)
            if self.preview.toPlainText().strip():
                cursor.insertText(", ")
            cursor.insertText(comfy_prompt_spec.normalize_tag(tag))
            return
        text = self.preview.toPlainText()
        target = comfy_prompt_spec.normalize_tag(tag)
        spans = [
            (start, end)
            for current, start, end in iter_tag_spans(text)
            if current == target
        ]
        if not spans:
            return
        cursor = QTextCursor(self.preview.document())
        cursor.beginEditBlock()
        for start, end in reversed(spans):
            left, right = start, end
            if text[max(0, start - 2):start] == ", ":
                left -= 2
            elif text[end:end + 2] == ", ":
                right += 2
            cursor.setPosition(left)
            cursor.setPosition(right, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        cursor.endEditBlock()

    def _section_for_post_tag(self, tag: str) -> str:
        """当前图 tag → PromptDoc 段位；与 fav chips 共用同一套插入语义。"""
        for label, tags in self.prompt.groups:
            if tag in tags:
                return GROUP_TO_SECTION[label]
        return "body"

    def _apply_post_tag_to_preview(self, tag: str, selected: bool) -> None:
        """post tag chip 始终对 preview 做局部增删，不依赖 dirty 全量回填。

        旧路径：clean 时整段 setPlainText(generated)，dirty 后直接 return。
        Fav 页一点就会把 dirty 置真，切回 post_tags 后 chip 再也写不进 preview。
        对象化口径：preview 是唯一源，chip 只 patch 自己的 token。
        """
        current = self.preview.toPlainText()
        if selected:
            next_text = insert_tag_into_text(
                current,
                tag,
                section=self._section_for_post_tag(tag),
                known=self.comfy_known,
            )
        else:
            next_text = remove_tag_from_text(current, tag)
        if next_text != current:
            self.replace_preview_text(next_text)

    def _set_all_checked(self, checked: bool):
        for tag, button in self._tag_buttons.items():
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
            self.prompt.set_selected(tag, checked)
        if not self._preview_dirty:
            # 仍是系统生成态：一次全量回填比逐 token patch 更干净。
            self._refresh_preview(force_generated=True)
            return
        # dirty：保留 Fav/手改 token，只 patch 当前图 tags。
        current = self.preview.toPlainText()
        next_text = current
        for tag in self._tag_buttons:
            if checked:
                next_text = insert_tag_into_text(
                    next_text,
                    tag,
                    section=self._section_for_post_tag(tag),
                    known=self.comfy_known,
                )
            else:
                next_text = remove_tag_from_text(next_text, tag)
        if next_text != current:
            self.replace_preview_text(next_text)
        self._sync_preview_chrome()

    def _set_tag_selected(self, tag: str, selected: bool):
        self.prompt.set_selected(tag, selected)
        if self._preview_dirty:
            self._apply_post_tag_to_preview(tag, selected)
            self._sync_preview_chrome()
            return
        self._refresh_preview()

    def _toggle_select_all(self):
        all_checked = bool(self._tag_buttons) and all(
            button.isChecked() for button in self._tag_buttons.values()
        )
        self._set_all_checked(not all_checked)

    def _select_default_groups(self):
        self.prompt.restore_defaults()
        self._preview_dirty = False
        for tag, button in self._tag_buttons.items():
            button.blockSignals(True)
            button.setChecked(self.prompt.is_selected(tag))
            button.blockSignals(False)
        selected_safety = comfy_prompt_spec.safety_tag_for_rating(self.prompt.post.rating)
        for tag, button in self._palette_buttons.items():
            button.blockSignals(True)
            button.setChecked(tag == selected_safety)
            button.blockSignals(False)
        self._refresh_preview(force_generated=True)

    def _sync_preview_chrome(self):
        """按钮可用性只看导出用的最终文本，不看 chip 勾选数量。

        手改 / attached toggle 后 chip 可能全空，但 preview 有字 → copy/comfy 必须可点。
        """
        export_text = self.prompt_text().strip()
        body = self.prompt_body_text().strip()
        selected_count = sum(1 for button in self._tag_buttons.values() if button.isChecked())
        self.count_label.setText(f"{selected_count}")
        self.copy_btn.setEnabled(bool(export_text))
        self.imgpalace_btn.setEnabled(bool(body))
        self.comfy_generate_btn.setEnabled(bool(export_text))
        all_checked = bool(self._tag_buttons) and all(
            button.isChecked() for button in self._tag_buttons.values()
        )
        if all_checked:
            self.toggle_select_btn.setIcon(CgsIcon.SCRIPT_TAG_SELECT_NONE)
            self.toggle_select_btn.setToolTip("取消全选")
        else:
            self.toggle_select_btn.setIcon(CgsIcon.SCRIPT_TAG_SELECT_ALL)
            self.toggle_select_btn.setToolTip("全选")

    def _refresh_preview(self, *, force_generated: bool = False):
        generated = self._generated_comfy_prompt()
        if force_generated or not self._preview_dirty:
            if self.preview.toPlainText() != generated:
                # 显式声明「这次是系统回填，不是用户编辑」。不能用 QSignalBlocker：
                # 装在 document 上会连高亮器一起挡掉，装在 widget 上又挡不住 contentsChange。
                self._applying_generated = True
                try:
                    self.preview.setPlainText(generated)
                finally:
                    self._applying_generated = False
            if force_generated:
                self._preview_dirty = False
        self._sync_preview_chrome()


