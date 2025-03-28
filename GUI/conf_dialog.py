#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import json

from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QSizePolicy
from qfluentwidgets import FluentIcon as FIF, PushButton, PrimaryPushButton, TransparentPushButton

from assets import res
from variables import SPIDERS
from utils import conf, yaml, convert_punctuation as cp
from GUI.uic.conf_dia import Ui_Dialog as Ui_ConfDialog
from GUI.uic.qfluent.action_factory import Updater, DescCreator, ProjUpdateThread, Proj
from GUI.uic.qfluent.components import SupportView, CustomFlyout


class ConfDialog(QDialog, Ui_ConfDialog):
    def __init__(self, parent=None):
        super(ConfDialog, self).__init__(parent)
        self.gui = parent
        self.setupUi(self)

    def setupUi(self, Dialog):
        super(ConfDialog, self).setupUi(Dialog)
        self.acceptBtn.clicked.connect(self.save_conf)
        self.acceptBtn.setIcon(FIF.SAVE)
        self.cancelBtn.setIcon(FIF.CLOSE)
        tip = QtCore.QCoreApplication.translate("Dialog", F"idx corresponds/序号对应：\n{json.dumps(SPIDERS)}")
        self.completerEdit.setToolTip(tip)
        self.label_completer.setToolTip(tip)
        self.insert_btn()

    def insert_btn(self):
        def _create_desc():
            DescCreator.run()
        self.descBtn = PrimaryPushButton(FIF.LIBRARY, res.GUI.Uic.confDia_descBtn)
        self.descBtn.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.descBtn.setMaximumSize(QtCore.QSize(110, 16777215))
        self.descBtn.clicked.connect(_create_desc)
        def _regular_update():
            self.puThread = ProjUpdateThread(self)
            Updater(self.gui).run()
        self.updateBtn = PushButton(FIF.UPDATE, res.GUI.Uic.confDia_updateBtn)
        self.updateBtn.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.updateBtn.setMaximumSize(QtCore.QSize(110, 16777215))
        self.updateBtn.clicked.connect(_regular_update)
        self.supportBtn = TransparentPushButton(FIF.CAFE, res.GUI.Uic.confDia_supportBtn)
        self.supportBtn.clicked.connect(lambda: CustomFlyout.make(
            view=SupportView(Proj.url, self), target=self.supportBtn, parent=self
        ))
        
        self.bottom_btn_horizontalLayout.insertWidget(0, self.supportBtn)
        self.bottom_btn_horizontalLayout.insertWidget(0, self.updateBtn)
        self.bottom_btn_horizontalLayout.insertWidget(0, self.descBtn)

    def show_self(self):  # can't naming `show`. If done, just run code once
        # 1. Text类配置
        for _ in ('sv_path', 'proxies', 'custom_map', "completer", "eh_cookies", "clip_db"):
            getattr(self, f"{_}Edit").setText(self.transfer_to_gui(getattr(conf, _) or ""))
        self.logLevelComboBox.setCurrentIndex(self.logLevelComboBox.findText(getattr(conf, "log_level")))
        # 2. CheckBox类配置
        for _ in ('addUuid', 'isDeduplicate'):
            getattr(self, f"{_}").setChecked(getattr(conf, f"{_}"))
        # 3. SpinBox类配置
        getattr(self, "clip_read_numEdit").setValue(int(getattr(conf, "clip_read_num")))
        super(ConfDialog, self).show()

    @staticmethod
    def transfer_to_gui(val) -> str:
        if isinstance(val, list):
            return ",".join(val)
        elif isinstance(val, dict):
            return "\n".join([f"{k}: {v}" for k, v in val.items()]).replace("'", "")
            # return yaml.dump(val, allow_unicode=True)
        else:
            return str(val)

    def save_conf(self):
        sv_path = getattr(self, "sv_pathEdit").text()
        eh_cookies_str = cp(getattr(self, "eh_cookiesEdit").toPlainText()).replace("cookies = ", "")
        if not conf.eh_cookies and eh_cookies_str:
            try:
                assert isinstance(ast.literal_eval(eh_cookies_str), dict)
            except (SyntaxError, ValueError, AssertionError):
                raise SyntaxError(res.GUI.cookies_copy_err)
        config = {
            "sv_path": sv_path,
            "custom_map": yaml.safe_load(cp(getattr(self, "custom_mapEdit").toPlainText())),
            "completer": yaml.safe_load(cp(getattr(self, "completerEdit").toPlainText())),
            "eh_cookies": yaml.safe_load(eh_cookies_str),
            "proxies": cp(self.proxiesEdit.text()).replace(" ", "").split(",") if self.proxiesEdit.text() else None,
            "log_level": getattr(self, "logLevelComboBox").currentText(),
            "addUuid": getattr(self, "addUuid").isChecked(),
            "isDeduplicate": getattr(self, "isDeduplicate").isChecked(),
            "clip_db": getattr(self, "clip_dbEdit").text(),
            "clip_read_num": getattr(self, "clip_read_numEdit").value()
        }
        conf.update(**config)
