#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
from PyQt5.QtCore import Qt
from qfluentwidgets import (
    MessageBoxBase, TextBrowser, SubtitleLabel, StateToolTip
)
from assets import res
from utils.docs import MarkdownConverter


class UpdaterMessageBox(MessageBoxBase):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.gui = parent
        self.yesButton.setText(res.Updater.update_ensure)
        self.textBrowser = TextBrowser(self)
        # self.textBrowser.setWordWrapMode(QtGui.QTextOption.NoWrap)  # 禁用自动换行
        self.textBrowser.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # 需要时显示水平滚动条
        if title:
            self.titleLabel = SubtitleLabel(title)
            self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.textBrowser)
        self.widget.setMinimumWidth(int(parent.width() * 0.8))

    def validate(self):
        self.gui.updaterStateTooltip = StateToolTip("Updating", res.Updater.doing, self.gui.textBrowser)
        self.gui.updaterStateTooltip.show()
        self.gui.conf_dia.puThread.update_signal.emit()
        return True

    def show_release_note(self, note):
        def _format_note(note):
            note = note.split("\n---")[0]
            return re.sub(r'\s*\(\s*[0-9a-f]{40}.*\)', '', note)
        html_text = MarkdownConverter.convert_html(_format_note(note))
        self.textBrowser.setHtml(html_text)
        self.gui.conf_dia.hide()
        self.show()
