from __future__ import annotations

import typing as t

from PySide6 import QtCore
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from .fab import PageNavFab
from .model import PageNavState
from .policy import PageNavPolicy

if t.TYPE_CHECKING:
    pass


class PageNavController(QObject):
    page_jump_requested = Signal(int)
    jump_rejected = Signal(str, object)
    panel_opened = Signal()
    panel_closed = Signal()

    def __init__(self, parent: QObject | None = None, *, policy: PageNavPolicy | None = None):
        super().__init__(parent)
        self.policy = policy or PageNavPolicy()
        self._host: QWidget | None = None
        self._fab: PageNavFab | None = None
        self._margin = 8
        self._state = PageNavState.from_counts(current_page=1, total_count=None, query_is_empty=True)
        self._reposition_scheduled = False

    @property
    def fab(self) -> PageNavFab | None:
        return self._fab

    def attach(self, host: QWidget) -> PageNavFab:
        if self._fab is not None and self._host is host:
            return self._fab
        if self._host is not None and self._host is not host:
            self._host.removeEventFilter(self)
        self._host = host
        if self._fab is not None:
            self._fab.setParent(host)
        else:
            self._fab = PageNavFab(host)
            self._fab.set_policy(self.policy)
            self._fab.page_jump_requested.connect(self.page_jump_requested.emit)
            self._fab.jump_rejected.connect(self.jump_rejected.emit)
            self._fab.panel_toggled.connect(self._on_panel_toggled)
        self._fab.show()
        self._fab.raise_()
        host.installEventFilter(self)
        self.set_state(self._state)
        # Host geometry is often still zero during interface __init__; schedule after layout.
        self.reposition()
        self.schedule_reposition()
        return self._fab

    def set_state(self, state: PageNavState):
        self._state = state
        if self._fab is not None:
            self._fab.set_state(state)
            # Label width changes (1 → 1/3 → 12/48); re-pin bottom-right after adjustSize.
            self.reposition()

    def set_enabled(self, enabled: bool):
        if self._fab is not None:
            self._fab.setEnabled(bool(enabled) and not self._state.loading)

    def close_panel(self):
        if self._fab is not None:
            self._fab.close_panel()

    def apply_theme(self, **kwargs):
        if self._fab is not None:
            self._fab.apply_theme(**kwargs)
            self.reposition()

    def schedule_reposition(self):
        if self._reposition_scheduled:
            return
        self._reposition_scheduled = True
        QtCore.QTimer.singleShot(0, self._run_scheduled_reposition)

    def _run_scheduled_reposition(self):
        self._reposition_scheduled = False
        self.reposition()

    def reposition(self):
        if self._fab is None or self._host is None:
            return
        host_rect = self._host.rect()
        if host_rect.width() <= 0 or host_rect.height() <= 0:
            self.schedule_reposition()
            return
        self._fab.adjustSize()
        fab_size = self._fab.size()
        if fab_size.width() <= 0 or fab_size.height() <= 0:
            fab_size = self._fab.sizeHint()
        x = max(0, host_rect.width() - fab_size.width() - self._margin)
        y = max(0, host_rect.height() - fab_size.height() - self._margin)
        self._fab.move(x, y)
        self._fab.raise_()
        # Keep open panel pinned inside host after resize / FAB move.
        panel = self._fab._panel
        if panel is not None and panel.isVisible():
            self._fab._position_panel()

    def eventFilter(self, obj, event):
        if obj is self._host:
            event_type = event.type()
            if event_type in (
                QtCore.QEvent.Resize,
                QtCore.QEvent.Show,
                QtCore.QEvent.LayoutRequest,
            ):
                self.reposition()
            elif event_type == QtCore.QEvent.ShowToParent:
                self.schedule_reposition()
            elif event_type == QtCore.QEvent.MouseButtonPress:
                # Click outside panel (still inside host) closes it; stays in-window.
                fab = self._fab
                if fab is not None:
                    panel = fab._panel
                    if panel is not None and panel.isVisible():
                        click_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                        if not panel.geometry().contains(click_pos) and not fab.geometry().contains(click_pos):
                            fab.close_panel()
        return super().eventFilter(obj, event)

    def _on_panel_toggled(self, opened: bool):
        if opened:
            self.panel_opened.emit()
        else:
            self.panel_closed.emit()
