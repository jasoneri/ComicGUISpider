from __future__ import annotations

from utils import ori_path
from GUI.core.theme import CustTheme, theme_mgr
from GUI.core.theme.qss_template import read_templated_qss_tokens, render_templated_qss_section

_TRAY_QSS_PATH = ori_path.joinpath("GUI/core/theme/tray.qss")

_CHIP_SECTION_BY_STATUS = {
    "ready": "chip_ready",
    "completed": "chip_ready",
    "running": "chip_running",
    "starting": "chip_starting",
    "failed": "chip_failed",
    "error": "chip_failed",
    "unavailable": "chip_neutral",
    "foreground-blocked": "chip_neutral",
    "idle": "chip_idle",
    "queued": "chip_idle",
}


def current_theme_name() -> str:
    return "dark" if theme_mgr.get_theme() == CustTheme.DARK else "light"


def get_tray_tokens() -> dict[str, str]:
    return read_templated_qss_tokens(_TRAY_QSS_PATH, current_theme_name())


def tray_token(name: str) -> str:
    return get_tray_tokens()[name]


def _render_section(section_name: str, **overrides: str) -> str:
    return render_templated_qss_section(_TRAY_QSS_PATH, current_theme_name(), section_name, **overrides)


def build_dialog_stylesheet() -> str:
    return "\n".join(
        (
            _render_section("dialog"),
            _render_section("schedule"),
            _render_section("server"),
            _render_section("mcp"),
        )
    )


def chip_stylesheet(status: str) -> str:
    normalized = str(status or "-")
    section_name = _CHIP_SECTION_BY_STATUS.get(normalized, "chip_idle")
    return _render_section(section_name)


def muted_label_stylesheet() -> str:
    return f"color:{tray_token('MUTED')};"


def body_text_stylesheet() -> str:
    return f"color:{tray_token('TEXT')};"


def accent_info_label_stylesheet() -> str:
    return f"color:{tray_token('ACCENT_INFO')};"


def accent_ok_label_stylesheet() -> str:
    return f"color:{tray_token('ACCENT_OK')};"


def error_label_stylesheet() -> str:
    return f"color:{tray_token('ERROR_TEXT')};"


def section_heading_stylesheet() -> str:
    return f"color:{tray_token('MUTED')};font-weight:600;"


def detail_title_stylesheet() -> str:
    return f"color:{tray_token('TEXT')};font-weight:600;"


def site_badge_stylesheet() -> str:
    return (
        f"background:{tray_token('PANEL_BG')};color:{tray_token('MUTED')};"
        f"border:1px solid {tray_token('BORDER')};"
        "border-radius:3px;padding:1px 4px;font-size:9px;font-weight:600;"
    )


def run_id_chip_stylesheet() -> str:
    return (
        f"background:{tray_token('PANEL_BG')};color:{tray_token('MUTED')};"
        f"border:1px solid {tray_token('BORDER')};border-radius:3px;padding:1px 6px;"
    )


def pkl_detail_stylesheet() -> str:
    return (
        f"background:{tray_token('PANEL_BG')};color:{tray_token('MUTED')};"
        f"border:1px solid {tray_token('BORDER')};border-radius:4px;padding:4px;"
    )


def latest_banner_stylesheet() -> str:
    return (
        f"background:{tray_token('BANNER_BG')};color:{tray_token('BANNER_TEXT')};"
        f"border:1px solid {tray_token('BANNER_BORDER')};border-radius:4px;padding:3px 6px;"
    )


def cover_placeholder_stylesheet(*, small: bool = False) -> str:
    if small:
        return (
            f"background:{tray_token('COVER_BG')};border:1px solid {tray_token('BORDER')};"
            f"border-radius:4px;color:{tray_token('MUTED')};font-size:9px;"
        )
    return (
        f"background:{tray_token('COVER_BG')};border:1px solid {tray_token('BORDER')};"
        f"border-radius:4px;color:{tray_token('COVER_PLACEHOLDER')};font-size:10px;"
    )


def stage_rail_line_stylesheet() -> str:
    return f"background:{tray_token('BORDER')};border:none;"


def stage_dot_stylesheet(state: str) -> str:
    if state == "done":
        accent = tray_token("ACCENT_OK")
        return f"background:{accent};border:2px solid {accent};border-radius:5px;"
    if state == "active":
        accent = tray_token("ACCENT_INFO")
        return f"background:{accent};border:2px solid {accent};border-radius:5px;"
    return (
        f"background:{tray_token('PANEL_BG')};border:2px solid {tray_token('DOT_PENDING')};"
        "border-radius:5px;"
    )


def stage_text_stylesheet(state: str) -> str:
    if state == "done":
        color = tray_token("ACCENT_OK")
    elif state == "active":
        color = tray_token("ACCENT_INFO")
    else:
        color = tray_token("MUTED")
    return f"color:{color};font-size:9px;"


def source_card_stylesheet() -> str:
    return (
        f"#ScheduleSourceCard{{background:{tray_token('CARD_BG')};border:1px solid {tray_token('BORDER')};border-radius:6px;}}"
        f"#ScheduleSourceCard:hover{{background:{tray_token('CARD_BG_SEL')};}}"
    )


def pending_card_stylesheet(*, selected: bool = False) -> str:
    background = tray_token("CARD_BG_SEL") if selected else tray_token("CARD_BG")
    return (
        f"#SchedulePendingCard{{background:{background};border:1px solid {tray_token('BORDER')};border-radius:6px;}}"
        f"#SchedulePendingCard:hover{{background:{tray_token('CARD_BG_SEL')};}}"
    )


def mcp_muted_label_stylesheet() -> str:
    return f"color:{tray_token('MCP_MUTED')};"


def mcp_heading_stylesheet() -> str:
    return f"font-weight:600;color:{tray_token('MCP_TEXT')};"


def progress_done_color() -> str:
    return tray_token("PROGRESS_DONE")
