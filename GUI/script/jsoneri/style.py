from __future__ import annotations

from utils import ori_path
from GUI.core.theme import CustTheme, theme_mgr
from GUI.core.theme.qss_template import render_templated_qss_section

_JSONERI_QSS_PATH = ori_path.joinpath("GUI/core/theme/jsoneri.qss")


def _current_theme_name() -> str:
    return "dark" if theme_mgr.get_theme() == CustTheme.DARK else "light"


def build_interface_stylesheet() -> str:
    return render_templated_qss_section(_JSONERI_QSS_PATH, _current_theme_name(), "interface")


def build_checking_layer_stylesheet(accent_color: str) -> str:
    return render_templated_qss_section(
        _JSONERI_QSS_PATH, _current_theme_name(), "checking_layer", CHECKING_ACCENT=accent_color,
    )


def build_connection_dot_stylesheet(connection_color: str) -> str:
    return render_templated_qss_section(
        _JSONERI_QSS_PATH, _current_theme_name(), "connection_dot", CONNECTION_COLOR=connection_color,
    )


def build_site_preview_shell_stylesheet() -> str:
    return render_templated_qss_section(_JSONERI_QSS_PATH, _current_theme_name(), "site_preview_shell")
