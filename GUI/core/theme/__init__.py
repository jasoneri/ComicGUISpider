from enum import Enum
from typing import Callable

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, isDarkTheme, qconfig, setTheme

from utils.config.qc import cgs_cfg
from .mid import MidNodeColors, create_dark_mid_colors, create_light_mid_colors


class CustTheme(Enum):
    LIGHT = "light"
    DARK = "dark"


class LightFontColor:
    text = "black"
    tip = "blue"
    highlight = "purple"
    success = "green"
    err = "red"


class DarkFontColor:
    text = "white"
    tip = "aqua"
    highlight = "gold"
    err = "lightcoral"
    success = "lightgreen"


class Light:
    def __init__(self):
        self.palette = QPalette()
        self.palette.setColor(QPalette.Window, QColor(245, 245, 245))
        self.palette.setColor(QPalette.WindowText, QColor(40, 40, 40))
        self.palette.setColor(QPalette.Base, QColor(255, 255, 255))
        self.palette.setColor(QPalette.AlternateBase, QColor(238, 238, 238))
        self.palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
        self.palette.setColor(QPalette.ToolTipText, QColor(40, 40, 40))
        self.palette.setColor(QPalette.Text, QColor(40, 40, 40))
        self.palette.setColor(QPalette.Button, QColor(230, 230, 230))
        self.palette.setColor(QPalette.ButtonText, QColor(40, 40, 40))
        self.palette.setColor(QPalette.BrightText, QColor(239, 83, 80))
        self.palette.setColor(QPalette.Highlight, QColor(100, 181, 246))
        self.palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.font_color = LightFontColor
        self.c = Theme.LIGHT
        self.mid_colors: MidNodeColors = create_light_mid_colors()


class Dark:
    def __init__(self):
        self.palette = QPalette()
        self.palette.setColor(QPalette.Window, QColor(53, 53, 53))
        self.palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
        self.palette.setColor(QPalette.Base, QColor(35, 35, 35))
        self.palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        self.palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        self.palette.setColor(QPalette.Text, QColor(220, 220, 220))
        self.palette.setColor(QPalette.Button, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
        self.palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        self.palette.setColor(QPalette.Highlight, QColor(61, 174, 255))
        self.palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        self.font_color = DarkFontColor
        self.c = Theme.DARK
        self.mid_colors: MidNodeColors = create_dark_mid_colors()


_THEME_SCHEMES = {
    CustTheme.LIGHT: Light(),
    CustTheme.DARK: Dark(),
}
_THEME_CALLBACK_ATTR = "_cgs_theme_callback"
_THEME_CLEANUP_ATTR = "_cgs_theme_cleanup_bound"


class ThemeManager:
    """QFluent theme adapter with CGS-derived palette/font helpers."""

    def __init__(self):
        self._listeners: list[Callable[[CustTheme], None]] = []
        self._bootstrapped = False
        qconfig.themeChanged.connect(self._on_qfluent_theme_changed)

    def _bootstrap(self):
        if self._bootstrapped:
            return
        self._bootstrapped = True
        setTheme(self.themeMode, save=False)
        self.apply_to_app()

    def _ensure_bootstrapped(self):
        if QApplication.instance() is None:
            return
        self._bootstrap()

    def _on_qfluent_theme_changed(self, _theme_mode):
        self.apply_to_app()
        current_theme = self.currentTheme
        for callback in tuple(self._listeners):
            callback(current_theme)

    @property
    def themeMode(self) -> Theme:
        return cgs_cfg.themeMode.value

    @property
    def currentTheme(self) -> CustTheme:
        self._ensure_bootstrapped()
        return CustTheme.DARK if isDarkTheme() else CustTheme.LIGHT

    @property
    def is_dark(self) -> bool:
        return self.currentTheme == CustTheme.DARK

    @property
    def theme(self):
        return _THEME_SCHEMES[self.currentTheme]

    def get_theme(self) -> CustTheme:
        return self.currentTheme

    @property
    def font_color(self):
        return self.theme.font_color

    @property
    def mid_colors(self) -> MidNodeColors:
        return self.theme.mid_colors

    def set_theme_mode(self, theme_mode: Theme, *, save: bool = False, lazy: bool = False):
        self._ensure_bootstrapped()
        setTheme(theme_mode, save=save, lazy=lazy)

    def set_dark(self, set_dark: bool, *, save: bool = False, lazy: bool = False):
        self.set_theme_mode(Theme.DARK if set_dark else Theme.LIGHT, save=save, lazy=lazy)

    def apply_to_app(self, app: QApplication | None = None):
        target = app or QApplication.instance()
        if target is not None:
            target.setPalette(self.theme.palette)

    def subscribe(self, callback: Callable[[CustTheme], None]):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[CustTheme], None]):
        if callback in self._listeners:
            self._listeners.remove(callback)


theme_mgr = ThemeManager()


def setupTheme(widget):
    theme_mgr._ensure_bootstrapped()

    def apply_theme(_theme):
        color = theme_mgr.font_color
        css = f"""
p.theme-text {{ color: {color.text}; }}
font.theme-tip {{ color: {color.tip}; }}
font.theme-highlight {{ color: {color.highlight}; }}
font.theme-success {{ color: {color.success}; }}
font.theme-err {{ color: {color.err}; }}
"""
        widget.textBrowser.document().setDefaultStyleSheet(css)

    previous = getattr(widget, _THEME_CALLBACK_ATTR, None)
    if previous is not None:
        theme_mgr.unsubscribe(previous)

    setattr(widget, _THEME_CALLBACK_ATTR, apply_theme)
    if not getattr(widget, _THEME_CLEANUP_ATTR, False):
        def _cleanup(_obj=None):
            callback = getattr(widget, _THEME_CALLBACK_ATTR, None)
            if callback is not None:
                theme_mgr.unsubscribe(callback)
                setattr(widget, _THEME_CALLBACK_ATTR, None)

        widget.destroyed.connect(_cleanup)
        setattr(widget, _THEME_CLEANUP_ATTR, True)

    apply_theme(theme_mgr.currentTheme)
    theme_mgr.subscribe(apply_theme)
