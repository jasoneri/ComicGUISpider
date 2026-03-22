import html
import re
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
        if theme_mgr.get_theme() == CustTheme.DARK:
            return cls(
                canvas="#09090b",
                shell="rgba(18, 18, 20, 0.98)",
                shell_border="rgba(244, 244, 245, 0.10)",
                card="rgba(24, 24, 27, 0.98)",
                card_hover="rgba(228, 228, 231, 0.44)",
                downloaded_card="rgba(59, 47, 35, 0.90)",
                downloaded_hover="rgba(213, 182, 140, 0.82)",
                preview="rgba(244, 244, 245, 0.06)",
                preview_hover="rgba(244, 244, 245, 0.12)",
                section="rgba(28, 28, 31, 0.96)",
                section_border="rgba(244, 244, 245, 0.08)",
                text="rgba(250, 250, 250, 0.97)",
                muted_text="rgba(212, 212, 216, 0.72)",
                status_text="rgba(228, 228, 231, 0.82)",
                viewer_frame="rgba(15, 15, 17, 0.75)",
                viewer_border="rgba(244, 244, 245, 0.10)",
                viewer_image="rgba(244, 244, 245, 0.05)",
                viewer_tag="rgba(255, 255, 255, 0.04)",
                viewer_tag_hover="rgba(255, 255, 255, 0.08)",
                selection_border="rgba(226, 232, 240, 0.92)",
                title_accent="#f4f4f5",
                pivot_selected="rgba(46, 46, 51, 0.98)",
                pivot_button_hover="rgba(244, 244, 245, 0.10)",
                pivot_button_pressed="rgba(244, 244, 245, 0.14)",
            )
        return cls(
            canvas="#f5f5f4",
            shell="rgba(250, 250, 249, 0.98)",
            shell_border="rgba(39, 39, 42, 0.10)",
            card="rgba(255, 255, 255, 0.99)",
            card_hover="rgba(39, 39, 42, 0.26)",
            downloaded_card="rgba(236, 229, 220, 0.98)",
            downloaded_hover="rgba(131, 104, 74, 0.62)",
            preview="rgba(39, 39, 42, 0.05)",
            preview_hover="rgba(39, 39, 42, 0.09)",
            section="rgba(245, 245, 244, 0.97)",
            section_border="rgba(39, 39, 42, 0.08)",
            text="rgba(9, 9, 11, 0.97)",
            muted_text="rgba(63, 63, 70, 0.74)",
            status_text="rgba(39, 39, 42, 0.80)",
            viewer_frame="rgba(255, 255, 255, 0.75)",
            viewer_border="rgba(39, 39, 42, 0.10)",
            viewer_image="rgba(39, 39, 42, 0.04)",
            viewer_tag="rgba(255, 255, 255, 0.92)",
            viewer_tag_hover="rgba(244, 244, 245, 0.98)",
            selection_border="rgba(24, 24, 27, 0.88)",
            title_accent="#18181b",
            pivot_selected="rgba(255, 255, 255, 0.98)",
            pivot_button_hover="rgba(39, 39, 42, 0.07)",
            pivot_button_pressed="rgba(39, 39, 42, 0.11)",
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
    return f"""
        DanbooruCardWidget {{
            background: {palette.downloaded_card if already_downloaded else palette.card};
            border: 1px solid {palette.downloaded_hover if already_downloaded else palette.shell_border};
            border-radius: 20px;
        }}
        DanbooruCardWidget:hover {{
            border-color: {palette.downloaded_hover if already_downloaded else palette.card_hover};
        }}
        DanbooruCardWidget[selected="true"] {{
            border: 2px solid {palette.selection_border};
        }}
        QPushButton#DanbooruCardPreview {{
            border: none;
            border-radius: 16px;
            background: {palette.preview};
            color: {palette.muted_text};
            text-align: center;
        }}
        QPushButton#DanbooruCardPreview:hover {{
            background: {palette.preview_hover};
        }}
    """


def build_viewer_stylesheet(palette: DanbooruUiPalette) -> str:
    return f"""
        QFrame#DanbooruImageViewerFrame {{
            background: {palette.viewer_frame};
            border: 1px solid {palette.viewer_border};
            border-radius: 20px;
        }}
        QLabel#DanbooruImageLabel {{
            color: {palette.muted_text};
            background: {palette.viewer_image};
            border-radius: 16px;
        }}
        QLabel#DanbooruImageHint {{
            color: {palette.muted_text};
            background: transparent;
            padding: 0 18px;
        }}
        QWidget#DanbooruTagsContainer {{
            background: transparent;
        }}
        QLabel#DanbooruTagSectionTitle {{
            color: {palette.muted_text};
            font-weight: 600;
            padding: 8px 2px 2px 2px;
        }}
        PushButton#DanbooruTagButton {{
            color: {palette.text};
            background: {palette.viewer_tag};
            border: 1px solid {palette.viewer_border};
            border-radius: 12px;
            min-height: 16px;
            padding: 0 6px;
            text-align: left;
        }}
        PushButton#DanbooruTagButton:hover {{
            background: {palette.viewer_tag_hover};
        }}
    """


def build_tab_stylesheet(palette: DanbooruUiPalette) -> str:
    return f"""
        QFrame#DanbooruSearchQueryGroup {{
            background: {palette.section};
            border: 1px solid {palette.section_border};
            border-radius: 18px;
        }}
        QWidget#DanbooruGridContent {{
            background: transparent;
        }}
        QAbstractScrollArea#DanbooruGridScrollArea {{
            background: transparent;
            border: none;
        }}
    """


def build_interface_stylesheet(palette: DanbooruUiPalette) -> str:
    return f"""
        DanbooruInterface {{
            background: {palette.canvas};
        }}
        QFrame#DanbooruContentShell,
        QWidget#DanbooruTitleBlock {{
            background: {palette.shell};
            border: 1px solid {palette.shell_border};
            border-radius: 12px;
        }}
        QFrame#DanbooruPivotShell {{
            background: {palette.shell};
            border: 1px solid {palette.shell_border};
            border-radius: 12px;
        }}
        QLabel#DanbooruSubtitle {{
            color: {palette.muted_text};
        }}
        QLabel#DanbooruTabCaption {{
            color: {palette.muted_text};
            padding: 0 6px 0 2px;
        }}
        QWidget#DanbooruPivotTabBarView {{
            background: transparent;
        }}
        QAbstractScrollArea#DanbooruPivotScrollArea {{
            background: transparent;
            border: none;
        }}
        TransparentToolButton#DanbooruPivotScrollButton {{
            color: {palette.status_text};
            background: transparent;
            border: none;
            border-radius: 18px;
        }}
        TransparentToolButton#DanbooruPivotScrollButton:hover {{
            background: {palette.pivot_button_hover};
        }}
        TransparentToolButton#DanbooruPivotScrollButton:pressed {{
            background: {palette.pivot_button_pressed};
        }}
        TransparentToolButton#DanbooruPivotScrollButton:disabled {{
            color: {palette.muted_text};
            background: transparent;
            border: none;
        }}
        QAbstractScrollArea#DanbooruPivotScrollArea TabToolButton {{
            color: {palette.status_text};
            background: transparent;
            border: none;
            border-radius: 10px;
        }}
        QAbstractScrollArea#DanbooruPivotScrollArea TabToolButton:hover {{
            background: {palette.pivot_button_hover};
        }}
        QAbstractScrollArea#DanbooruPivotScrollArea TabToolButton:pressed {{
            background: {palette.pivot_button_pressed};
        }}
    """


def build_title_label_stylesheet(palette: DanbooruUiPalette) -> str:
    return f"color: {palette.title_accent}; letter-spacing: 0.5px;"


def build_tip_line_stylesheet(palette: DanbooruUiPalette) -> str:
    return f"padding-left: 8px; color: {palette.muted_text};"
