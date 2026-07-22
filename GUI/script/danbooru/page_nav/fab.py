from __future__ import annotations

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QRect
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon as FIF,
    FlyoutViewBase,
    LineEdit,
    PrimaryToolButton,
    PushButton,
    ScrollArea,
    ToggleButton,
    setCustomStyleSheet,
)
from shiboken6 import isValid

from .model import PageNavState
from .policy import PageNavPolicy

_JUMP_ROW_HEIGHT = 28
_PANEL_WIDTH = 120
_PANEL_MAX_HEIGHT = 300
_PANEL_GAP = 8
_HOST_MARGIN = 8


def _apply_fluent_qss(widget: QWidget, stylesheet: str):
    qss = stylesheet or ""
    setCustomStyleSheet(widget, qss, qss)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class PageNavPanel(FlyoutViewBase):
    """
    In-host panel (child of DanbooruInterface), not a top-level Popup Flyout.

    Uses FlyoutViewBase.paintEvent for Fluent rounded chrome / day-night colors,
    while staying clipped inside scriptWin and avoiding Windows layered-window
    UpdateLayeredWindowIndirect failures from translucent popups.
    """

    page_selected = Signal(int)
    jump_submitted = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DanbooruPageNavPanel")
        self.setFixedWidth(_PANEL_WIDTH)
        self.setMaximumHeight(_PANEL_MAX_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        jump_row = QHBoxLayout()
        jump_row.setContentsMargins(0, 0, 0, 0)
        jump_row.setSpacing(6)
        jump_row.setAlignment(Qt.AlignVCenter)

        self.jump_edit = LineEdit(self)
        self.jump_edit.setObjectName("DanbooruPageNavJumpEdit")
        self.jump_edit.setPlaceholderText("")
        self.jump_edit.setClearButtonEnabled(True)
        self.jump_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.jump_edit.returnPressed.connect(self._emit_jump_from_edit)

        self.jump_btn = PrimaryToolButton(FIF.RIGHT_ARROW, self)
        self.jump_btn.setObjectName("DanbooruPageNavJumpBtn")
        self.jump_btn.setToolTip("跳转")
        self.jump_btn.setCursor(Qt.PointingHandCursor)
        self.jump_btn.setIconSize(QSize(12, 12))
        self.jump_btn.clicked.connect(self._emit_jump_from_edit)

        jump_row.addWidget(self.jump_edit, 1, Qt.AlignVCenter)
        jump_row.addWidget(self.jump_btn, 0, Qt.AlignVCenter)
        layout.addLayout(jump_row)
        self._lock_jump_row_geometry()

        self.scroll = ScrollArea(self)
        self.scroll.setObjectName("DanbooruPageNavScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.enableTransparentBackground()
        self.list_host = QWidget(self.scroll)
        self.list_host.setObjectName("DanbooruPageNavListHost")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(5)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_host)
        layout.addWidget(self.scroll, 1)

        self._page_buttons: list[ToggleButton] = []

    def addWidget(self, widget: QWidget, stretch=0, align=Qt.AlignLeft):
        self.layout().addWidget(widget, stretch, align)

    def set_pages(self, items: list[int | None], *, current_page: int):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._page_buttons.clear()
        for entry in reversed(items):
            if entry is None:
                ellipsis = BodyLabel("· · ·", self.list_host)
                ellipsis.setAlignment(Qt.AlignCenter)
                ellipsis.setObjectName("DanbooruPageNavEllipsis")
                self.list_layout.insertWidget(self.list_layout.count() - 1, ellipsis)
                continue
            button = ToggleButton(str(entry), self.list_host)
            button.setObjectName("DanbooruPageNavChip")
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(entry == current_page)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setFixedHeight(_JUMP_ROW_HEIGHT)
            button.clicked.connect(lambda _checked=False, page=entry: self.page_selected.emit(page))
            self.list_layout.insertWidget(self.list_layout.count() - 1, button)
            self._page_buttons.append(button)
        self._scroll_to_current()

    def _scroll_to_current(self):
        for button in self._page_buttons:
            if not button.isChecked():
                continue
            QtCore.QTimer.singleShot(0, lambda current=button: self._ensure_button_visible(current))
            return

    def _ensure_button_visible(self, button: ToggleButton):
        if not isValid(self) or not isValid(button):
            return
        self.scroll.ensureWidgetVisible(button, 0, _JUMP_ROW_HEIGHT)

    def apply_compact_edit_style(self, stylesheet: str):
        if not isValid(self):
            return
        if stylesheet:
            _apply_fluent_qss(self.jump_edit, stylesheet)
        self._lock_jump_row_geometry()

    def _lock_jump_row_geometry(self):
        if not isValid(self):
            return
        row_height = _JUMP_ROW_HEIGHT
        self.jump_edit.setFixedHeight(row_height)
        self.jump_edit.setMinimumHeight(row_height)
        self.jump_edit.setMaximumHeight(row_height)
        self.jump_btn.setIconSize(QSize(12, 12))
        self.jump_btn.setFixedSize(row_height, row_height)
        self.jump_btn.setMinimumSize(row_height, row_height)
        self.jump_btn.setMaximumSize(row_height, row_height)
        QtCore.QTimer.singleShot(0, self._relock_jump_row_geometry)

    def _relock_jump_row_geometry(self):
        if not isValid(self):
            return
        row_height = _JUMP_ROW_HEIGHT
        if self.jump_edit.height() != row_height:
            self.jump_edit.setFixedHeight(row_height)
        if self.jump_btn.width() != row_height or self.jump_btn.height() != row_height:
            self.jump_btn.setFixedSize(row_height, row_height)

    def _emit_jump_from_edit(self):
        text = self.jump_edit.text().strip()
        if not text:
            return
        try:
            page = int(text)
        except ValueError:
            return
        self.jump_submitted.emit(page)


class PageNavFab(PushButton):
    panel_toggled = Signal(bool)
    page_jump_requested = Signal(int)
    jump_rejected = Signal(str, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DanbooruPageNavFab")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(0, _JUMP_ROW_HEIGHT)
        self.setMaximumHeight(_JUMP_ROW_HEIGHT)
        self.setText("1")
        self.setToolTip("页码")
        self._panel: PageNavPanel | None = None
        self._policy = PageNavPolicy()
        self._state = PageNavState.from_counts(current_page=1, total_count=None, query_is_empty=True)
        self._stylesheet = ""
        self._shadow_color = QtGui.QColor(0, 0, 0, 36)
        self._fab_shadow = QGraphicsDropShadowEffect(self)
        self._fab_shadow.setBlurRadius(14)
        self._fab_shadow.setOffset(0, 4)
        self._fab_shadow.setColor(self._shadow_color)
        self.setGraphicsEffect(self._fab_shadow)
        self.clicked.connect(self.toggle_panel)

    def set_policy(self, policy: PageNavPolicy):
        self._policy = policy

    def apply_theme(self, *, stylesheet: str, shadow_color: QtGui.QColor):
        self._stylesheet = stylesheet or ""
        self._shadow_color = QtGui.QColor(shadow_color)
        _apply_fluent_qss(self, self._stylesheet)
        self._fab_shadow.setColor(self._shadow_color)
        panel = self._panel
        if panel is not None and isValid(panel):
            panel.apply_compact_edit_style(self._stylesheet)

    def set_state(self, state: PageNavState):
        self._state = state
        self.setText(self._policy.fab_label(state))
        self.setEnabled(not state.loading)
        self.adjustSize()
        panel = self._panel
        if panel is not None and isValid(panel) and panel.isVisible():
            panel.set_pages(
                self._policy.visible_page_items(self._state),
                current_page=self._state.current_page,
            )
            self._position_panel()

    def ensure_panel(self) -> PageNavPanel:
        host = self.parentWidget()
        if self._panel is not None and isValid(self._panel):
            if host is not None and self._panel.parentWidget() is not host:
                self._panel.setParent(host)
            return self._panel
        panel = PageNavPanel(host)
        panel.page_selected.connect(self._on_page_selected)
        panel.jump_submitted.connect(self._on_page_selected)
        if self._stylesheet:
            panel.apply_compact_edit_style(self._stylesheet)
        self._panel = panel
        return panel

    def toggle_panel(self):
        panel = self.ensure_panel()
        if panel.isVisible():
            self.close_panel()
            return
        panel.set_pages(
            self._policy.visible_page_items(self._state),
            current_page=self._state.current_page,
        )
        self._position_panel()
        panel.show()
        panel.raise_()
        self.raise_()
        panel._relock_jump_row_geometry()
        panel.jump_edit.setFocus(Qt.OtherFocusReason)
        self.panel_toggled.emit(True)

    def close_panel(self):
        panel = self._panel
        if panel is None or not isValid(panel) or not panel.isVisible():
            return
        panel.hide()
        self.panel_toggled.emit(False)

    def _position_panel(self):
        panel = self._panel
        host = self.parentWidget()
        if panel is None or host is None or not isValid(panel) or not isValid(host):
            return

        panel.adjustSize()
        preferred_height = min(max(panel.sizeHint().height(), 200), _PANEL_MAX_HEIGHT)
        host_rect = host.rect()
        available_height = max(80, host_rect.height() - 2 * _HOST_MARGIN)
        panel_height = min(preferred_height, available_height)
        panel.setFixedHeight(panel_height)
        panel_width = panel.width() or _PANEL_WIDTH

        fab_top_left = self.mapTo(host, QPoint(0, 0))
        fab_rect = QRect(fab_top_left, self.size())

        # Prefer above FAB; if not enough room, place below; always clamp into host.
        x = fab_rect.right() - panel_width + 1
        y_above = fab_rect.top() - panel_height - _PANEL_GAP
        y_below = fab_rect.bottom() + _PANEL_GAP
        if y_above >= _HOST_MARGIN:
            y = y_above
        elif y_below + panel_height <= host_rect.height() - _HOST_MARGIN:
            y = y_below
        else:
            y = max(_HOST_MARGIN, host_rect.height() - panel_height - _HOST_MARGIN)

        x = max(_HOST_MARGIN, min(x, host_rect.width() - panel_width - _HOST_MARGIN))
        y = max(_HOST_MARGIN, min(y, host_rect.height() - panel_height - _HOST_MARGIN))
        panel.move(x, y)
        panel.raise_()

    def _on_page_selected(self, page: int):
        decision = self._policy.clamp_jump(self._state, page)
        if not decision.accepted:
            self.jump_rejected.emit(decision.reason, decision.target_page)
            return
        self.close_panel()
        self.page_jump_requested.emit(int(decision.target_page))
