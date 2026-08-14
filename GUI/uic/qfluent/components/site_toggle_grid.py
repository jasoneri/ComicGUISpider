# -*- coding: utf-8 -*-
"""Reusable site TogglePushButton grid (ConfDialog visibility / Subscribe site_proxy)."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from functools import partial

from PySide6 import QtWidgets
from PySide6.QtWidgets import QSizePolicy
from qfluentwidgets import TogglePushButton

from variables import SPIDERS_LABELS, Spider


class SiteToggleGrid(QtWidgets.QWidget):
    """Generic site toggle grid.

    Hosts inject checked semantics via ``bind_handlers``:
    - ConfDialog: chooseBox visibility (cgs_cfg.site_choices)
    - Subscribe GlobalPanel: use conf.proxies for site (yml site_proxy)
    """

    COLUMNS = 3

    def __init__(
        self,
        parent=None,
        *,
        site_indexes: Iterable[int] | None = None,
        labels: Mapping[int, str] | None = None,
    ):
        super().__init__(parent)
        self._labels = dict(labels) if labels is not None else dict(SPIDERS_LABELS)
        self.site_buttons: dict[int, TogglePushButton] = {}
        self._is_checked: Callable[[int], bool] | None = None
        self._set_checked: Callable[[int, bool], None] | None = None
        self._is_locked: Callable[[int], bool] | None = None
        self._suppress_toggle = False
        self._grid_host = QtWidgets.QWidget(self)
        self._grid_layout = QtWidgets.QGridLayout(self._grid_host)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setHorizontalSpacing(6)
        self._grid_layout.setVerticalSpacing(6)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._grid_host)
        self.setMinimumWidth(280)
        indexes = list(site_indexes) if site_indexes is not None else list(self._labels.keys())
        self.set_site_indexes(indexes)

    @staticmethod
    def format_site_label(site_index: int, label: str) -> str:
        if site_index in Spider and Spider(site_index) in Spider.specials():
            return f"{label}🔞"
        return label

    def set_site_indexes(self, indexes: Iterable[int]) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self.site_buttons.clear()
        ordered = sorted({int(index) for index in indexes})
        for offset, site_index in enumerate(ordered):
            label = self._labels.get(site_index) or str(site_index)
            button = TogglePushButton(self._grid_host)
            button.setText(self.format_site_label(site_index, label))
            button.setToolTip(button.text())
            button.setCheckable(True)
            button.setMinimumWidth(90)
            button.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
            self._grid_layout.addWidget(
                button,
                offset // self.COLUMNS,
                offset % self.COLUMNS,
            )
            self.site_buttons[site_index] = button
            button.toggled.connect(partial(self._on_button_toggled, site_index))
        self.reload_from_handlers()

    def bind_handlers(
        self,
        *,
        is_checked: Callable[[int], bool],
        set_checked: Callable[[int, bool], None],
        is_locked: Callable[[int], bool] | None = None,
    ) -> None:
        self._is_checked = is_checked
        self._set_checked = set_checked
        self._is_locked = is_locked
        self.reload_from_handlers()

    def reload_from_handlers(self) -> None:
        if self._is_checked is None:
            return
        self._suppress_toggle = True
        try:
            for site_index, button in self.site_buttons.items():
                locked = bool(self._is_locked(site_index)) if self._is_locked is not None else False
                checked = bool(self._is_checked(site_index))
                if locked:
                    checked = False
                button.setChecked(checked)
                button.setEnabled(not locked)
        finally:
            self._suppress_toggle = False

    def all_sites_selected(self) -> bool:
        unlocked = [
            button
            for site_index, button in self.site_buttons.items()
            if not (self._is_locked and self._is_locked(site_index))
        ]
        return bool(unlocked) and all(button.isChecked() for button in unlocked)

    def set_all_sites_selected(self, selected: bool) -> None:
        for site_index, button in self.site_buttons.items():
            if self._is_locked is not None and self._is_locked(site_index):
                continue
            button.setChecked(bool(selected))

    def _on_button_toggled(self, site_index: int, checked: bool) -> None:
        if self._suppress_toggle:
            return
        if self._is_locked is not None and self._is_locked(site_index):
            self._suppress_toggle = True
            try:
                self.site_buttons[site_index].setChecked(False)
            finally:
                self._suppress_toggle = False
            return
        if self._set_checked is not None:
            self._set_checked(site_index, bool(checked))
