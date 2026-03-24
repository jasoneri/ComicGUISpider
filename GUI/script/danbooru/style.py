import html
from functools import lru_cache
from pathlib import Path
import re
from string import Template
from dataclasses import dataclass

from PySide6 import QtGui

from GUI.core.font import font_color
from GUI.core.theme import CustTheme, theme_mgr

DEFAULT_TAB_STATUS_TEXT = "空词搜索进入首页"
DEFAULT_TAB_STATUS_CLASS = "theme-tip"

CARD_WIDTH_BASE = 228
CARD_PREVIEW_BASE_HEIGHT = 168
CARD_PREVIEW_MIN_HEIGHT = 156
CARD_PREVIEW_MAX_HEIGHT = 182
CARD_PREVIEW_WIDTH_PADDING = 20
CARD_ZOOM_WIDTHS = (148, 188, 228, 268, 308, 348, 388)
DEFAULT_CARD_ZOOM_INDEX = 2

_RGB_COLOR_RE = re.compile(
    r"(?P<fn>rgb|rgba)\(\s*(?P<r>\d{1,3})\s*,\s*(?P<g>\d{1,3})\s*,\s*(?P<b>\d{1,3})"
    r"(?:\s*,\s*(?P<a>[\d.]+))?\s*\)$",
    re.IGNORECASE,
)
_QSS_SECTION_RE = re.compile(
    r"/\*\s*@section\s+(?P<name>[\w.-]+)\s*\*/(?P<body>.*?)/\*\s*@endsection\s*\*/",
    re.DOTALL,
)
_QSS_TOKEN_RE = re.compile(
    r"/\*\s*@tokens\s+(?P<name>[\w.-]+)\s*\*/(?P<body>.*?)/\*\s*@endtokens\s*\*/",
    re.DOTALL,
)
_DANBOORU_QSS_PATH = Path(__file__).with_name("theme.qss")


@dataclass(frozen=True, slots=True)
class DanbooruCardMetrics:
    width: int
    preview_base_height: int
    preview_min_height: int
    preview_max_height: int

    @property
    def preview_content_width(self) -> int:
        return max(1, self.width - CARD_PREVIEW_WIDTH_PADDING)


def _build_card_metrics(width: int) -> DanbooruCardMetrics:
    scale = width / CARD_WIDTH_BASE
    return DanbooruCardMetrics(
        width=width,
        preview_base_height=max(1, int(round(CARD_PREVIEW_BASE_HEIGHT * scale))),
        preview_min_height=max(1, int(round(CARD_PREVIEW_MIN_HEIGHT * scale))),
        preview_max_height=max(1, int(round(CARD_PREVIEW_MAX_HEIGHT * scale))),
    )


CARD_ZOOM_METRICS = tuple(_build_card_metrics(width) for width in CARD_ZOOM_WIDTHS)
DEFAULT_CARD_METRICS = CARD_ZOOM_METRICS[DEFAULT_CARD_ZOOM_INDEX]


def _current_theme_name() -> str:
    return "dark" if theme_mgr.get_theme() == CustTheme.DARK else "light"


def _parse_qss_tokens(body: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"Invalid Danbooru QSS token line: {raw_line!r}")
        tokens[key.strip()] = value.strip().rstrip(";")
    return tokens


@lru_cache(maxsize=1)
def _load_qss_document() -> tuple[dict[str, Template], dict[str, dict[str, str]]]:
    raw = _DANBOORU_QSS_PATH.read_text(encoding="utf-8")
    sections = {
        match.group("name"): Template(match.group("body").strip())
        for match in _QSS_SECTION_RE.finditer(raw)
    }
    token_sets = {
        match.group("name"): _parse_qss_tokens(match.group("body"))
        for match in _QSS_TOKEN_RE.finditer(raw)
    }
    if not sections:
        raise RuntimeError(f"No Danbooru QSS sections found in {_DANBOORU_QSS_PATH}")
    if not token_sets:
        raise RuntimeError(f"No Danbooru QSS token sets found in {_DANBOORU_QSS_PATH}")
    return sections, token_sets


def get_danbooru_qss_tokens() -> dict[str, str]:
    _, token_sets = _load_qss_document()
    theme_name = _current_theme_name()
    tokens = token_sets.get(theme_name)
    if tokens is None:
        raise KeyError(f"Danbooru QSS token set is missing theme {theme_name!r}")
    return dict(tokens)


def reload_danbooru_qss() -> None:
    _load_qss_document.cache_clear()


def _render_qss_section(name: str, **overrides: str) -> str:
    sections, _ = _load_qss_document()
    template = sections.get(name)
    if template is None:
        raise KeyError(f"Danbooru QSS section is missing {name!r}")
    tokens = get_danbooru_qss_tokens()
    tokens.update({key: str(value) for key, value in overrides.items()})
    return template.substitute(tokens).strip()


@dataclass(frozen=True, slots=True)
class DanbooruUiPalette:
    canvas: str
    shell: str
    shell_border: str
    card: str
    card_hover: str
    downloaded_card: str
    downloaded_hover: str
    preview: str
    preview_hover: str
    section: str
    section_border: str
    text: str
    muted_text: str
    status_text: str
    viewer_frame: str
    viewer_border: str
    viewer_image: str
    viewer_tag: str
    viewer_tag_hover: str
    selection_border: str
    title_accent: str
    pivot_selected: str
    pivot_button_hover: str
    pivot_button_pressed: str

    @classmethod
    def current(cls) -> "DanbooruUiPalette":
        tokens = get_danbooru_qss_tokens()
        return cls(
            canvas=tokens["CANVAS"],
            shell=tokens["SHELL"],
            shell_border=tokens["SHELL_BORDER"],
            card=tokens["CARD_BACKGROUND_IDLE"],
            card_hover=tokens["CARD_HOVER_BORDER_IDLE"],
            downloaded_card=tokens["CARD_BACKGROUND_DOWNLOADED"],
            downloaded_hover=tokens["CARD_HOVER_BORDER_DOWNLOADED"],
            preview=tokens["CARD_PREVIEW_BACKGROUND"],
            preview_hover=tokens["CARD_PREVIEW_BACKGROUND_HOVER"],
            section=tokens["SECTION_BACKGROUND"],
            section_border=tokens["SECTION_BORDER"],
            text=tokens["TEXT"],
            muted_text=tokens["MUTED_TEXT"],
            status_text=tokens["STATUS_TEXT"],
            viewer_frame=tokens["VIEWER_FRAME"],
            viewer_border=tokens["VIEWER_BORDER"],
            viewer_image=tokens["VIEWER_IMAGE"],
            viewer_tag=tokens["VIEWER_TAG"],
            viewer_tag_hover=tokens["VIEWER_TAG_HOVER"],
            selection_border=tokens["SELECTION_BORDER"],
            title_accent=tokens["TITLE_ACCENT"],
            pivot_selected=tokens["PIVOT_SELECTED"],
            pivot_button_hover=tokens["PIVOT_BUTTON_HOVER"],
            pivot_button_pressed=tokens["PIVOT_BUTTON_PRESSED"],
        )


def qcolor_from_css(color: str) -> QtGui.QColor:
    qcolor = QtGui.QColor(color)
    if qcolor.isValid():
        return qcolor

    match = _RGB_COLOR_RE.fullmatch(color.strip())
    if match is None:
        raise ValueError(f"Unsupported color literal: {color}")

    red = min(255, int(match.group("r")))
    green = min(255, int(match.group("g")))
    blue = min(255, int(match.group("b")))
    alpha_group = match.group("a")
    if alpha_group is None:
        return QtGui.QColor(red, green, blue)

    alpha_value = float(alpha_group)
    if alpha_value <= 1:
        return QtGui.QColor.fromRgbF(red / 255, green / 255, blue / 255, alpha_value)
    return QtGui.QColor(red, green, blue, min(255, int(round(alpha_value))))


def format_tip_rich_text(text: str, cls: str = DEFAULT_TAB_STATUS_CLASS) -> str:
    color = theme_mgr.font_color
    css = (
        f"font.theme-tip {{ color: {color.tip}; }}"
        f"font.theme-success {{ color: {color.success}; }}"
        f"font.theme-err {{ color: {color.err}; }}"
    )
    safe_text = html.escape(text or "").replace("\n", "<br/>")
    fallback_color = {
        "theme-success": color.success,
        "theme-err": color.err,
    }.get(cls, color.tip)
    return f"<style>{css}</style>{font_color(safe_text, cls=cls or DEFAULT_TAB_STATUS_CLASS, color=fallback_color)}"


def build_card_stylesheet(palette: DanbooruUiPalette, already_downloaded: bool) -> str:
    _ = palette
    tokens = get_danbooru_qss_tokens()
    return _render_qss_section(
        "card",
        CARD_BACKGROUND=tokens["CARD_BACKGROUND_DOWNLOADED"] if already_downloaded else tokens["CARD_BACKGROUND_IDLE"],
        CARD_BORDER=tokens["CARD_BORDER_DOWNLOADED"] if already_downloaded else tokens["CARD_BORDER_IDLE"],
        CARD_HOVER_BORDER=(
            tokens["CARD_HOVER_BORDER_DOWNLOADED"] if already_downloaded else tokens["CARD_HOVER_BORDER_IDLE"]
        ),
    )


def build_viewer_stylesheet(palette: DanbooruUiPalette) -> str:
    _ = palette
    return _render_qss_section("viewer")


def build_tab_stylesheet(palette: DanbooruUiPalette) -> str:
    _ = palette
    return _render_qss_section("tab")


def build_interface_stylesheet(palette: DanbooruUiPalette) -> str:
    _ = palette
    return _render_qss_section("interface")


def build_title_label_stylesheet(palette: DanbooruUiPalette) -> str:
    _ = palette
    return _render_qss_section("title_label_inline")


def build_tip_line_stylesheet(palette: DanbooruUiPalette) -> str:
    _ = palette
    return _render_qss_section("tip_line_inline")


def build_network_label_stylesheet(palette: DanbooruUiPalette) -> str:
    _ = palette
    return _render_qss_section("network_label_inline")
