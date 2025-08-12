# core/theme_manager.py
from enum import Enum
from typing import Callable, Dict, List
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme
from utils import conf


class CustTheme(Enum):
    LIGHT = "light"
    DARK  = "dark"


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


_DEFAULT_COLORS = {
    CustTheme.LIGHT: Light(),
    CustTheme.DARK: Dark() 
}


class ThemeManager:
    """单例式主题管理器 — 管理当前主题、调色板、订阅回调"""
    def __init__(self):
        self._theme = CustTheme.LIGHT
        self._mode: Dict[CustTheme, Dict[str,str]] = dict(_DEFAULT_COLORS)
        self._listeners: List[Callable[[CustTheme], None]] = []

    # ------------- 主题 API -------------
    def set_dark(self, setDark: bool):
        theme = CustTheme.DARK if setDark else CustTheme.LIGHT
        if theme == self._theme:
            return
        self._theme = theme
        for cb in list(self._listeners):
            try:
                cb(self._theme)
            except Exception:
                pass

    @property
    def theme(self):
        return self._mode[self._theme]

    def get_theme(self) -> CustTheme:
        return self._theme

    @property
    def font_color(self):
        return self.theme.font_color

    def apply_to_app(self, app: QApplication):
        app.setPalette(self.theme.palette)

    # ------------- 订阅者 -------------
    def subscribe(self, callback: Callable[[CustTheme], None]):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[CustTheme], None]):
        if callback in self._listeners:
            self._listeners.remove(callback)


theme_mgr = ThemeManager()


def _apply_theme_globally(theme: CustTheme):
    """
    Callback to apply theme changes to the entire application.
    It handles both the qfluentwidgets theme and the Qt palette.
    """
    if theme == CustTheme.DARK:
        setTheme(Theme.DARK)
    else:
        setTheme(Theme.LIGHT)
    
    app = QApplication.instance()
    if app:
        app.setPalette(theme_mgr.theme.palette)

theme_mgr.subscribe(_apply_theme_globally)


def setupTheme(self):
    def apply_theme_to_textbrowser(_t):
        color = theme_mgr.font_color
        css = f"""
p.theme-text {{ color: {color.text}; }}
font.theme-tip {{ color: {color.tip}; }}
font.theme-highlight {{ color: {color.highlight}; }}
font.theme-success {{ color: {color.success}; }}
font.theme-err {{ color: {color.err}; }}
"""
        doc = self.textBrowser.document()
        doc.setDefaultStyleSheet(css)

    theme_mgr.set_dark(conf.darkTheme)
    apply_theme_to_textbrowser(0)
    theme_mgr.subscribe(apply_theme_to_textbrowser)
