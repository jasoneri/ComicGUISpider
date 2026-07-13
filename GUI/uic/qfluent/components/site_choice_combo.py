#!/usr/bin/python
# -*- coding: utf-8 -*-
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from qfluentwidgets.components.widgets.combo_box import MenuAnimationType

from variables import SPIDERS_LABELS
from utils.config.qc import cgs_cfg


class SiteChoiceComboController:
    def __init__(self, combo):
        self.combo = combo
        self.visible_indexes = set(range(combo.count()))
        combo._showComboMenu = self.show_menu

    def apply_configured_choices(self, *, reset_current=True):
        hidden = cgs_cfg.site_choices.hidden(SPIDERS_LABELS.keys())
        self.visible_indexes = {
            index
            for index in range(self.combo.count())
            if index == 0 or index not in hidden
        }
        if reset_current and self.combo.currentIndex() in hidden:
            self.combo.setCurrentIndex(0)
        return hidden

    def set_site_visible(self, site_index: int, visible: bool, *, reset_current=True):
        if visible or site_index == 0:
            self.visible_indexes.add(site_index)
        else:
            self.visible_indexes.discard(site_index)
        if reset_current and not visible and self.combo.currentIndex() == site_index:
            self.combo.setCurrentIndex(0)

    def show_menu(self):
        combo = self.combo
        if not combo.items:
            return
        menu = combo._createComboMenu()
        actions_by_index = {}
        for index, item in enumerate(combo.items):
            if index not in self.visible_indexes:
                continue
            action = QAction(item.icon, item.text)
            action.setEnabled(item.isEnabled)
            menu.addAction(action)
            actions_by_index[index] = action
        if not actions_by_index:
            return

        menu.view.itemClicked.connect(lambda item: combo._onItemClicked(combo.findText(item.text().lstrip())))
        if menu.view.width() < combo.width():
            menu.view.setMinimumWidth(combo.width())
            menu.adjustSize()

        menu.setMaxVisibleItems(combo.maxVisibleItems())
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.closedSignal.connect(combo._onDropMenuClosed)
        combo.dropMenu = menu

        default_action = actions_by_index.get(combo.currentIndex())
        if default_action is not None:
            menu.setDefaultAction(default_action)

        x = -menu.width()//2 + menu.layout().contentsMargins().left() + combo.width()//2
        pd = combo.mapToGlobal(QPoint(x, combo.height()))
        hd = menu.view.heightForAnimation(pd, MenuAnimationType.DROP_DOWN)
        pu = combo.mapToGlobal(QPoint(x, 0))
        hu = menu.view.heightForAnimation(pu, MenuAnimationType.PULL_UP)
        if hd >= hu:
            menu.view.adjustSize(pd, MenuAnimationType.DROP_DOWN)
            menu.exec(pd, aniType=MenuAnimationType.DROP_DOWN)
        else:
            menu.view.adjustSize(pu, MenuAnimationType.PULL_UP)
            menu.exec(pu, aniType=MenuAnimationType.PULL_UP)
