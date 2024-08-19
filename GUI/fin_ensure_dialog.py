#!/usr/bin/python
# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QDialog
from GUI.uic.ui_ensure_dia import Ui_FinEnsureDialog


class FinEnsureDialog(QDialog, Ui_FinEnsureDialog):
    def __init__(self, parent=None):
        super(FinEnsureDialog, self).__init__(parent)
        self.setupUi(self)

    def setupUi(self, ensureDialog):
        super(FinEnsureDialog, self).setupUi(ensureDialog)
