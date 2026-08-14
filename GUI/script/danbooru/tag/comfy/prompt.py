from __future__ import annotations

import json
import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from GUI.core.theme import theme_mgr
from utils.config import ori_path
from utils.script.image.anima import anima_spec
from utils.script.image.anima.prompt_doc import PromptDoc, split_prompt


_PALETTE_PATH = ori_path.joinpath(
    "utils", "script", "image", "anima", "styles", "anima_palette.json"
)
_GROUP_SECTIONS = {
    "Character": "character",
    "Artist": "artist",
    "Copyright": "series",
    "General": "body",
    "Meta": "prefix",
}

# post tag 分组 → PromptDoc 段位，与 fav_chips SECTION_OPTIONS 对齐。
GROUP_TO_SECTION = dict(_GROUP_SECTIONS)


def load_comfy_palette() -> dict:
    with _PALETTE_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def section_map_for_groups(groups) -> dict[str, str]:
    known = {}
    for label, tags in groups:
        section = _GROUP_SECTIONS[label]
        for tag in tags:
            normalized = anima_spec.normalize_tag(tag)
            known.setdefault(normalized, section)
            if section == "artist":
                known.setdefault(f"@{normalized}", section)
    return known


def category_map_for_groups(groups) -> dict[str, int]:
    categories = {}
    for label, tags in groups:
        category = anima_spec.GROUP_TO_CATEGORY[label]
        for tag in tags:
            normalized = anima_spec.normalize_tag(tag)
            categories.setdefault(normalized, category)
            categories.setdefault(normalized.lstrip("@"), category)
    return categories


def iter_tag_spans(text: str):
    for match in re.finditer(r"[^,\n]+", str(text or "")):
        raw = match.group(0)
        tag = raw.strip()
        if not tag:
            continue
        start = match.start() + len(raw) - len(raw.lstrip())
        yield tag, start, start + len(tag)


def insert_tag_into_text(
    text: str,
    tag: str,
    *,
    section: str,
    known: dict[str, str] | None = None,
) -> str:
    """在原文里局部插入一个 tag，不做整篇规范化/重排。

    走 `PromptDoc.insert_tag(...).to_text()` 会把 long_hair 静默改成 long hair，
    也会打乱用户已摆好的顺序。chip 切换只该改那一个 token。
    """
    before = PromptDoc.from_text(text, known=known or {})
    if before.contains_tag(tag):
        return text
    after = before.insert_tag(tag, section=section)
    before_tokens = list(before.tokens())
    after_tokens = list(after.tokens())
    inserted_token = None
    remaining = list(before_tokens)
    for candidate in after_tokens:
        if candidate in remaining:
            remaining.remove(candidate)
            continue
        inserted_token = candidate
        break
    if inserted_token is None:
        return text
    token_index = after_tokens.index(inserted_token)
    anchor = next(
        (
            candidate
            for candidate in reversed(after_tokens[:token_index])
            if candidate in before_tokens
        ),
        None,
    )
    # 局部拼接必须用原始 split：from_text 会按段归并，用户空格/括号会被重写。
    tokens = split_prompt(text)
    if not tokens:
        return inserted_token
    if anchor is None:
        return ", ".join([inserted_token, *tokens])
    bare_anchor = anima_spec.normalize_tag(anchor).strip().lstrip("@")
    position = next(
        (
            index
            for index, current in enumerate(tokens)
            if anima_spec.normalize_tag(current).strip().lstrip("@") == bare_anchor
        ),
        None,
    )
    if position is None:
        return ", ".join([*tokens, inserted_token])
    return ", ".join([*tokens[: position + 1], inserted_token, *tokens[position + 1 :]])


def remove_tag_from_text(text: str, tag: str) -> str:
    """按裸形删掉一个 token，其余原文逐字保留。"""
    target = anima_spec.normalize_tag(tag).strip().lstrip("@")
    kept = [
        token
        for token in split_prompt(text)
        if anima_spec.normalize_tag(token).strip().lstrip("@") != target
    ]
    return ", ".join(kept)


class ComfyPromptHighlighter(QSyntaxHighlighter):
    def __init__(self, document, known=None, categories=None):
        super().__init__(document)
        self._known = dict(known or {})
        self._categories = dict(categories or {})
        self._theme_callback = self._apply_theme
        theme_mgr.subscribe(self._theme_callback)
        self.destroyed.connect(self._unsubscribe_theme)
        self._apply_theme(theme_mgr.currentTheme)

    def _unsubscribe_theme(self, *_args):
        theme_mgr.unsubscribe(self._theme_callback)

    def _apply_theme(self, _theme=None):
        self.rehighlight()

    def set_maps(self, known, categories):
        self._known = dict(known)
        self._categories = dict(categories)
        self.rehighlight()

    def highlightBlock(self, text: str):
        document = PromptDoc.from_text(
            text,
            known=self._known,
            normalize=False,
        )
        # violations 的 key 是 normalize=False 下的原文 token，与 iter_tag_spans
        # 切出的 span 逐字同源；此处再规范化一次会把 long_hair 查成 long hair，
        # 结果只有 model-ref 能命中，下划线/括号违规永远标不出来。
        violations = dict(document.violations())
        for tag, start, end in iter_tag_spans(text):
            reason = violations.get(tag)
            if reason == "model-ref":
                color = theme_mgr.font_color.err
            elif reason is not None:
                color = theme_mgr.font_color.highlight
            else:
                normalized = anima_spec.normalize_tag(tag)
                category = self._categories.get(normalized)
                if category is None:
                    category = self._categories.get(normalized.lstrip("@"))
                if category is None and normalized.startswith("@"):
                    category = anima_spec.GROUP_TO_CATEGORY["Artist"]
                elif category is None and anima_spec.is_prefix_tag(normalized):
                    category = anima_spec.GROUP_TO_CATEGORY["General"]
                if category is None:
                    continue
                color = anima_spec.category_color(category, theme_mgr.is_dark)
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color))
            self.setFormat(start, end - start, text_format)


__all__ = [
    "ComfyPromptHighlighter",
    "GROUP_TO_SECTION",
    "category_map_for_groups",
    "insert_tag_into_text",
    "iter_tag_spans",
    "load_comfy_palette",
    "remove_tag_from_text",
    "section_map_for_groups",
]
