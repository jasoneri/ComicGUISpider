from __future__ import annotations

from PySide6.QtWidgets import QMenu

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


def tray_context_menu_stylesheet() -> str:
    """Opaque native QMenu chrome for the system-tray icon menu."""
    return _render_section("tray_context_menu")


def apply_tray_context_menu_theme(menu: QMenu | None) -> None:
    """Apply the active tray-menu theme to a menu and all of its submenus."""
    if menu is None:
        return
    stylesheet = tray_context_menu_stylesheet()
    for context_menu in (menu, *menu.findChildren(QMenu)):
        context_menu.setStyleSheet(stylesheet)


def apply_manage_dialog_theme(dialog) -> None:
    """Paint ManageDialog panels without cascading into Fluent popups.

    ``QWidget.setStyleSheet`` on the dialog still matches descendants — including
    ComboBoxMenu / ToolTip if they stay parented under the dialog. Keep every
    rule objectName-scoped (tray.qss contract) and re-apply Fluent sheets on
    known popup classes after the dialog sheet is set.
    """
    if dialog is None:
        return
    dialog.setStyleSheet(build_dialog_stylesheet())
    _reassert_fluent_popup_styles(dialog)


def _reassert_fluent_popup_styles(root) -> None:
    """Force Fluent MENU/TOOL_TIP sheets onto live popups under ``root``."""
    from qfluentwidgets import RoundMenu, ToolTip
    from qfluentwidgets.common.style_sheet import FluentStyleSheet

    for menu in root.findChildren(RoundMenu):
        FluentStyleSheet.MENU.apply(menu)
        # Collapse the translucent outer shell that reads as a ghost mask ring.
        _collapse_round_menu_ghost_shell(menu)
    for tip in root.findChildren(ToolTip):
        FluentStyleSheet.TOOL_TIP.apply(tip)
        harden_tray_tooltip(tip)


def _tray_popup_fill_color() -> str:
    """Opaque fill matching Fluent MenuActionListWidget for the active theme."""
    return "#2b2b2b" if current_theme_name() == "dark" else "#f9f9f9"


def _collapse_round_menu_ghost_shell(menu) -> None:
    """Kill Windows ghost ring around RoundMenu **before first show**.

    Root cause (proven with QScreen.grabWindow vs widget.grab on real
    ServerManageDialog + ComboBox):
    1. Fluent ``menu.qss``: ``RoundMenu { background: transparent }`` + layout
       margins 12/8/12/20 for drop-shadow.
    2. ``ComboBoxMenu`` adds ``view.setViewportMargins(0, 2, 0, 6)``.
    3. Widget grab corners alpha=0; Windows DWM fills those holes + translucent
       pad with an opaque gray rectangle → user "ghost mask / FlyoutViewBase".
    4. Main GUI is not immune; trayDialog on dark desktop makes it obvious.

    Fix (before show / before native window create):
    - WA_TranslucentBackground OFF
    - zero hBoxLayout + viewport margins, kill graphics shadow
    - **replace** stylesheet (do not append onto Fluent transparent rules)
    - square opaque fill matching list (no radius corner holes)
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette

    if menu.isVisible():
        menu.hide()

    fill = _tray_popup_fill_color()
    text = "#f1f5f9" if current_theme_name() == "dark" else "#0f172a"
    hover = "rgba(255,255,255,0.06)" if current_theme_name() == "dark" else "rgba(0,0,0,0.06)"
    border = "rgba(255,255,255,0.10)" if current_theme_name() == "dark" else "rgba(0,0,0,0.10)"

    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    menu.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
    menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)

    layout = getattr(menu, "hBoxLayout", None)
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    set_shadow = getattr(menu, "setShadowEffect", None)
    if callable(set_shadow):
        set_shadow(blurRadius=0, offset=(0, 0), color=QColor(0, 0, 0, 0))

    view = getattr(menu, "view", None)
    if view is not None:
        view.setGraphicsEffect(None)
        view.setViewportMargins(0, 0, 0, 0)
        view.setAutoFillBackground(True)
        view_palette = view.palette()
        view_palette.setColor(QPalette.ColorRole.Base, QColor(fill))
        view_palette.setColor(QPalette.ColorRole.Window, QColor(fill))
        view_palette.setColor(QPalette.ColorRole.Text, QColor(text))
        view.setPalette(view_palette)

    # Full replace — never leave Fluent "background: transparent" in the cascade.
    menu.setStyleSheet(
        f"""
        RoundMenu {{
            background-color: {fill};
            border: none;
            border-radius: 0px;
            padding: 0px;
            margin: 0px;
        }}
        MenuActionListWidget {{
            background-color: {fill};
            border: 1px solid {border};
            border-radius: 0px;
            outline: none;
            padding: 2px 0px;
            font: 13px 'Segoe UI', 'Microsoft YaHei UI';
            color: {text};
        }}
        MenuActionListWidget::item {{
            background-color: transparent;
            color: {text};
            border: none;
            border-radius: 4px;
            margin: 0px 4px;
            padding: 6px 12px;
        }}
        MenuActionListWidget::item:hover,
        MenuActionListWidget::item:selected {{
            background-color: {hover};
            color: {text};
        }}
        MenuActionListWidget::item:disabled {{
            color: rgba(148, 163, 184, 0.7);
        }}
        """
    )
    menu.setAutoFillBackground(True)
    palette = menu.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(fill))
    palette.setColor(QPalette.ColorRole.Base, QColor(fill))
    palette.setColor(QPalette.ColorRole.Text, QColor(text))
    menu.setPalette(palette)
    menu.adjustSize()


def harden_tray_tooltip(tip) -> None:
    """Make a Fluent tooltip opaque before its native popup is shown."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette

    fill = _tray_popup_fill_color()
    text = "#f1f5f9" if current_theme_name() == "dark" else "#0f172a"
    border = "rgba(255,255,255,0.10)" if current_theme_name() == "dark" else "rgba(0,0,0,0.10)"
    tip.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    tip.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
    tip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = tip.layout()
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
    container = getattr(tip, "container", None)
    if container is not None:
        container.setGraphicsEffect(None)
    tip.setStyleSheet(
        f"""
        ToolTip {{
            background-color: {fill};
            border: none;
            border-radius: 0px;
            padding: 0px;
            margin: 0px;
        }}
        ToolTip > #container {{
            background-color: {fill};
            border: 1px solid {border};
            border-radius: 0px;
            padding: 6px 10px;
        }}
        ToolTip QLabel, ToolTip #contentLabel {{
            background: transparent;
            border: none;
            color: {text};
            font: 12px 'Segoe UI', 'Microsoft YaHei UI';
        }}
        """
    )
    tip.setAutoFillBackground(True)
    palette = tip.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(fill))
    tip.setPalette(palette)
    tip.adjustSize()


def install_tray_combo_menu_hardening(combo) -> None:
    """Wrap ComboBox menu create so shell collapse runs before first show/exec."""
    if combo is None or getattr(combo, "_cgs_tray_menu_hardened", False):
        return

    original_create = combo._createComboMenu

    def _create_hardened_menu():
        menu = original_create()
        _collapse_round_menu_ghost_shell(menu)
        # Also wrap exec: ComboBoxMenu.exec → adjustSize → super.exec(show).
        # Re-apply collapse immediately before the native window is shown.
        original_exec = menu.exec

        def _exec_hardened(pos, ani=True, aniType=None):
            _collapse_round_menu_ghost_shell(menu)
            if aniType is None:
                return original_exec(pos, ani)
            return original_exec(pos, ani, aniType)

        menu.exec = _exec_hardened  # type: ignore[method-assign]
        return menu

    combo._createComboMenu = _create_hardened_menu  # type: ignore[method-assign]
    combo._cgs_tray_menu_hardened = True


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
