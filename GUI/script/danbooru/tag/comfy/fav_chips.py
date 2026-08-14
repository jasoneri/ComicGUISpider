from __future__ import annotations

from dataclasses import dataclass, field
import typing as t

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, FlowLayout, PlainTextEdit, ScrollArea, SegmentedToolWidget,
    SegmentedWidget, SingleDirectionScrollArea, TogglePushButton, SearchLineEdit,
)
from qfluentwidgets.components.widgets.line_edit import CompleterMenu

from GUI.uic.qfluent.components.icons import CgsIcon
from utils.config.qc import danbooru_cfg
from utils.script.image.anima.prompt_doc import PromptDoc

from .prompt import insert_tag_into_text, remove_tag_from_text



MIN_TAG_CHIP_WIDTH = 72
MAX_TAG_CHIP_WIDTH = 280
_ELIDE_RESERVED_WIDTH = 48


def _disable_dialog_enter_default(widget: QWidget) -> None:
    """QDialog 只会对 QPushButton 走 Enter→default；ToolButton 没有这套 API。"""
    if hasattr(widget, "setAutoDefault"):
        widget.setAutoDefault(False)
    if hasattr(widget, "setDefault"):
        widget.setDefault(False)


class TagChipButton(TogglePushButton):
    """A fixed-size tag chip shared by post tags and favorite tags."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # TagExportPanel 是 QDialog：chip 若带 autoDefault，SearchLineEdit 回车会误点它。
        _disable_dialog_enter_default(self)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        return QSize(
            min(max(size.width(), MIN_TAG_CHIP_WIDTH), MAX_TAG_CHIP_WIDTH),
            size.height(),
        )

    def set_full_text(self, text: str) -> None:
        self.setText(
            self.fontMetrics().elidedText(
                text,
                Qt.TextElideMode.ElideRight,
                MAX_TAG_CHIP_WIDTH - _ELIDE_RESERVED_WIDTH,
            )
        )


# routeKey = PromptDoc 段位；顺序即 SegmentedToolWidget 从左到右。
SECTION_OPTIONS = (
    ("body", "通用 (body)", CgsIcon.SCRIPT_TAG_SECTION_BODY),
    ("character", "角色 (character)", CgsIcon.SCRIPT_TAG_SECTION_CHARACTER),
    ("artist", "作者 (artist)", CgsIcon.SCRIPT_TAG_SECTION_ARTIST),
    ("series", "系列 (series)", CgsIcon.SCRIPT_TAG_SECTION_SERIES),
)
SECTION_VALUES = frozenset(value for value, _label, _icon in SECTION_OPTIONS)


def default_section_for_group(group_name: str) -> str:
    """只按组名给出一次性默认建议，避免把用户自定义组名当成段位契约。"""
    lowered = group_name.casefold()
    if "作者" in group_name or "artist" in lowered:
        return "artist"
    if "角色" in group_name or "character" in lowered or "char" in lowered:
        return "character"
    if "作品" in group_name or "系列" in group_name or "series" in lowered or "copyright" in lowered:
        return "series"
    return "body"


@dataclass
class _FavoriteGroupState:
    name: str
    tags: tuple[str, ...]
    section_segment: SegmentedToolWidget
    content: QWidget
    content_layout: FlowLayout
    search_edit: SearchLineEdit
    buttons: dict[str, TogglePushButton] = field(default_factory=dict)
    built: bool = False
    selected_section: str = "body"


class ComfyFavoritesChipGroups:
    """在独立的分组子页中展示收藏 tags，并把 chip 操作映射到编辑器。"""

    def __init__(
        self,
        *,
        host: QWidget,
        layout: QVBoxLayout,
        editor: PlainTextEdit,
        known: dict[str, str],
        prompt_getter: t.Callable[[], str],
        replace_prompt: t.Callable[[str], object],
        register_section: t.Callable[[str, str], None] | None = None,
    ):
        self._host = host
        self._layout = layout
        self._editor = editor
        self._known = known
        self._prompt_getter = prompt_getter
        self._replace_prompt = replace_prompt
        # Panel learns fav SECTION into comfy_known / highlighter (character → green).
        self._register_section = register_section
        self.group_states: dict[str, _FavoriteGroupState] = {}
        self._group_keys: list[str] = []
        self._group_pages: dict[str, QWidget] = {}

        # SegmentedWidget 本身不滚动；组多时右侧项会被裁切、点不到。
        # 横向 SingleDirectionScrollArea 包一层，保留 fluent 分段样式又能滚到后续组。
        self.group_segment_scroll = SingleDirectionScrollArea(self._host, orient=Qt.Orientation.Horizontal)
        self.group_segment_scroll.setObjectName("ComfyFavoriteGroupSegmentScroll")
        self.group_segment_scroll.setWidgetResizable(False)
        self.group_segment_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.group_segment_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.group_segment_scroll.setFrameShape(self.group_segment_scroll.Shape.NoFrame)
        self.group_segment_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.group_segment_scroll.enableTransparentBackground()

        self.group_segment = SegmentedWidget(self.group_segment_scroll)
        self.group_segment.setObjectName("ComfyFavoriteGroupSegment")
        self.group_segment.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.group_segment_scroll.setWidget(self.group_segment)

        self.group_stack = QStackedWidget(self._host)
        self.group_stack.setObjectName("ComfyFavoriteGroupStack")
        self._layout.addWidget(self.group_segment_scroll)
        self._layout.addWidget(self.group_stack, 1)

        payload = danbooru_cfg.fav.payload
        if not isinstance(payload, dict):
            raise ValueError("danbooru_cfg.fav.payload must be a dict")
        for group_name, raw_tags in payload.items():
            if not isinstance(group_name, str) or not group_name.strip():
                raise ValueError("danbooru favorite group name must be a non-empty string")
            if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
                raise ValueError(f"danbooru favorite group {group_name!r} must contain string tags")
            self._add_group(group_name, tuple(raw_tags))

        # Preference bag only (TagExportPanel/FavGroupSections) — not Search/Favorites content.
        self.restore_sections(danbooru_cfg.get_tag_export_fav_group_sections())

        self._sync_group_segment_scroll_geometry()
        if self._group_keys:
            first_key = self._group_keys[0]
            self.group_segment.setCurrentItem(first_key)
            self.group_stack.setCurrentWidget(self._group_pages[first_key])
            self._build_group(self.group_states[first_key])
            self._ensure_group_segment_visible(first_key)

        # 文本既可能由键盘修改，也可能由格式化按钮或 WD14 回灌；统一监听文档变化，
        # 才不会让 chip 选中态只在点击 chip 后正确。
        # 但 contentsChange 是**逐次编辑**触发的：直连 refresh 等于每敲一个键就
        # 重解析 prompt 并遍历全部 chip，normal 组实测 421 条，打字会卡住。
        # 故经单发定时器合并到一次。
        self._refresh_timer = QTimer(editor)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh)
        self._editor.document().contentsChange.connect(self._schedule_refresh)
        self.refresh()

    def _schedule_refresh(self, *_args) -> None:
        self._refresh_timer.start()

    def _add_group(self, group_name: str, tags: tuple[str, ...]) -> None:
        page = QWidget(self.group_stack)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(10, 8, 10, 8)
        page_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(BodyLabel("插入到", page))

        # icon-only 四选一：与 content_segment 同族 Segmented*，选中态一眼可见。
        section_segment = SegmentedToolWidget(page)
        section_segment.setObjectName("ComfyFavoriteSectionSegment")
        default_section = default_section_for_group(group_name)
        if default_section not in SECTION_VALUES:
            raise RuntimeError(f"favorite section option is missing: {default_section}")

        state_holder: dict[str, _FavoriteGroupState | None] = {"state": None}

        def _on_section_click(section_key: str, _checked: bool = False) -> None:
            state = state_holder["state"]
            if state is None:
                return
            state.selected_section = section_key
            state.section_segment.setCurrentItem(section_key)

        for section_key, section_label, section_icon in SECTION_OPTIONS:
            section_segment.addItem(
                section_key,
                section_icon,
                onClick=lambda _checked=False, key=section_key: _on_section_click(key, _checked),
            )
            item = section_segment.items.get(section_key)
            if item is not None:
                item.setToolTip(section_label)
                _disable_dialog_enter_default(item)
        section_segment.setCurrentItem(default_section)
        search_edit = SearchLineEdit(page)
        search_edit.setObjectName("ComfyFavoriteGroupSearch")
        search_edit.setPlaceholderText("搜索本组 tag")
        search_edit.setClearButtonEnabled(True)
        search_edit.setMinimumWidth(140)
        header.addWidget(section_segment)
        header.addWidget(BodyLabel(str(len(tags)), page), 1)
        header.addStretch(1)
        header.addWidget(search_edit)
        page_layout.addLayout(header)

        scroll = ScrollArea(page)
        scroll.setObjectName("ComfyFavoriteGroupScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.enableTransparentBackground()
        content = QWidget(scroll)
        content_layout = FlowLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setHorizontalSpacing(6)
        content_layout.setVerticalSpacing(6)
        scroll.setWidget(content)
        page_layout.addWidget(scroll, 1)

        state = _FavoriteGroupState(
            name=group_name,
            tags=tags,
            section_segment=section_segment,
            content=content,
            content_layout=content_layout,
            search_edit=search_edit,
            selected_section=default_section,
        )
        state_holder["state"] = state
        search_edit.returnPressed.connect(search_edit.search)
        search_edit.searchSignal.connect(
            lambda text, current_state=state: self._on_group_search(current_state, text)
        )
        self.group_states[group_name] = state
        self._group_pages[group_name] = page
        self.group_stack.addWidget(page)
        self.group_segment.addItem(
            group_name,
            group_name,
            onClick=lambda _checked=False, key=group_name: self._select_group(key),
        )
        group_item = self.group_segment.items.get(group_name)
        if group_item is not None:
            _disable_dialog_enter_default(group_item)
        self._group_keys.append(group_name)
        self._sync_group_segment_scroll_geometry()

    def _sync_group_segment_scroll_geometry(self) -> None:
        """让分段条按内容伸展宽度，滚动区高度贴合分段条，避免竖向留白或裁切。"""
        self.group_segment.adjustSize()
        segment_hint = self.group_segment.sizeHint()
        self.group_segment.resize(
            max(segment_hint.width(), self.group_segment.minimumSizeHint().width()),
            max(segment_hint.height(), 32),
        )
        self.group_segment_scroll.setFixedHeight(max(self.group_segment.height() + 6, 38))

    def _ensure_group_segment_visible(self, group_key: str) -> None:
        item = self.group_segment.items.get(group_key)
        if item is None:
            return
        self.group_segment_scroll.ensureWidgetVisible(item, 24, 0)

    def _select_group(self, group_key: str) -> None:
        page = self._group_pages.get(group_key)
        state = self.group_states.get(group_key)
        if page is None or state is None:
            return
        self.group_stack.setCurrentWidget(page)
        self.group_segment.setCurrentItem(group_key)
        self._ensure_group_segment_visible(group_key)
        self._build_group(state)

    def _build_group(self, state: _FavoriteGroupState) -> None:
        if state.built:
            return
        document = PromptDoc.from_text(self._prompt_getter(), known=self._known)
        for tag in state.tags:
            button = TagChipButton(state.content)
            button.setObjectName("ComfyFavoriteTagChip")
            button.setProperty("comfy_favorite_tag", tag)
            button.setToolTip(tag)
            button.setCheckable(True)
            button.setChecked(document.contains_tag(tag))
            button.set_full_text(danbooru_cfg.display_tag(tag))
            button.toggled.connect(
                lambda checked, current_tag=tag, current_state=state:
                self._on_tag_toggled(current_state, current_tag, checked)
            )
            state.content_layout.addWidget(button)
            state.buttons[tag] = button
        state.built = True

    def _on_group_search(self, state: _FavoriteGroupState, query: str) -> None:
        """在当前 fav-group 内匹配 tag，向下弹出 CompleterMenu；点选后激活对应 chip。"""
        needle = query.strip().casefold()
        if not needle:
            return

        matched_labels: list[str] = []
        label_to_tag: dict[str, str] = {}
        for tag in state.tags:
            display = danbooru_cfg.display_tag(tag)
            if needle not in tag.casefold() and needle not in display.casefold():
                continue
            label = display
            if label in label_to_tag and label_to_tag[label] != tag:
                label = f"{display} · {tag}"
            matched_labels.append(label)
            label_to_tag[label] = tag

        if not matched_labels:
            return

        # 先建 chip，保证 menu 点选时 TogglePushButton 已存在。
        self._build_group(state)
        menu = CompleterMenu(state.search_edit)
        menu.setItems(matched_labels)
        menu.setMaxVisibleItems(min(max(len(matched_labels), 8), 16))
        menu.activated.connect(
            lambda label, mapping=label_to_tag, current_state=state:
            self._activate_tag_chip(current_state, mapping[label])
        )
        state.search_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        menu.popup()

    def _activate_tag_chip(self, state: _FavoriteGroupState, tag: str) -> None:
        self._build_group(state)
        button = state.buttons.get(tag)
        if button is None:
            raise KeyError(f"favorite tag chip missing after build: group={state.name!r} tag={tag!r}")
        if not button.isChecked():
            button.setChecked(True)
        scroll_area = state.content.parentWidget()
        while scroll_area is not None and not isinstance(scroll_area, ScrollArea):
            scroll_area = scroll_area.parentWidget()
        if scroll_area is not None:
            scroll_area.ensureWidgetVisible(button, 12, 12)

    def _on_tag_toggled(
        self,
        state: _FavoriteGroupState,
        tag: str,
        checked: bool,
    ) -> None:
        current = self._prompt_getter()
        if checked:
            section = state.selected_section or state.section_segment.currentRouteKey()
            if section not in SECTION_VALUES:
                raise ValueError(f"Unknown Comfy favorite insertion section: {section!r}")
            # MUST register before insert so known/highlighter/submit lexicon see Character.
            if self._register_section is not None:
                self._register_section(tag, section)
            next_text = insert_tag_into_text(
                current, tag, section=section, known=self._known
            )
        else:
            next_text = remove_tag_from_text(current, tag)
        if next_text != current:
            self._replace_prompt(next_text)
        self.refresh()

    def refresh(self, *_args) -> None:
        document = PromptDoc.from_text(self._prompt_getter(), known=self._known)
        for state in self.group_states.values():
            if not state.built:
                continue
            for tag, button in state.buttons.items():
                button.blockSignals(True)
                button.setChecked(document.contains_tag(tag))
                button.blockSignals(False)

    def section_snapshot(self) -> dict[str, str]:
        """Memory map group_name → section for panel checkpoint (no I/O)."""
        snapshot: dict[str, str] = {}
        for group_name, state in self.group_states.items():
            section = state.selected_section or default_section_for_group(group_name)
            if section not in SECTION_VALUES:
                section = default_section_for_group(group_name)
            snapshot[group_name] = section
        return snapshot

    def restore_sections(self, mapping: dict[str, str] | None) -> None:
        """Apply saved sections to in-memory state + segment widgets. Missing → name default."""
        saved = mapping if isinstance(mapping, dict) else {}
        for group_name, state in self.group_states.items():
            section = str(saved.get(group_name) or "").strip()
            if section not in SECTION_VALUES:
                section = default_section_for_group(group_name)
            state.selected_section = section
            state.section_segment.setCurrentItem(section)


__all__ = [
    "ComfyFavoritesChipGroups",
    "SECTION_OPTIONS",
    "TagChipButton",
    "default_section_for_group",
]
