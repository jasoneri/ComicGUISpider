#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import json
import pathlib

from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QSizePolicy, QFileDialog, QCompleter
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from qfluentwidgets import FluentIcon as FIF, PushButton, PrimaryPushButton, TransparentPushButton, PushSettingCard, InfoBarPosition

from assets import res
from variables import SPIDERS
from utils import conf, yaml, convert_punctuation as cp, ori_path
from GUI.thread import ProjUpdateThread
from GUI.uic.conf_dia import Ui_Dialog as Ui_ConfDialog
from GUI.uic.qfluent.action_factory import Updater, Proj
from GUI.uic.qfluent.components import SupportView, CustomFlyout, CustomInfoBar


class SvPathCard(PushSettingCard):
    def __init__(self, parent=None):
        super().__init__(res.GUI.Uic.sv_path_desc_tip, FIF.DOWNLOAD, 
                         res.GUI.Uic.sv_path_desc, "D:/Comic", parent)
        self.conf_dia = parent
        self.clicked.connect(self._onSelectFolder)

    def _onSelectFolder(self):
        folder = QFileDialog.getExistingDirectory(self, res.GUI.Uic.sv_path_desc_tip)
        if folder:
            wanted_p = pathlib.Path(folder)
            cgs_path = ori_path.parent if ori_path.parent.joinpath("scripts/CGS.py").exists() else ori_path
            cgs_flag = str(wanted_p).startswith(str(cgs_path))
            drive_flag = len(wanted_p.parts) == 1 and wanted_p.drive
            if cgs_flag or drive_flag:
                CustomInfoBar.show("", res.GUI.Uic.confDia_svPathWarning, self.conf_dia, 
                    "https://jasoneri.github.io/ComicGUISpider/config/#%E9%85%8D%E7%BD%AE%E9%A1%B9-%E5%AF%B9%E5%BA%94-yml-%E5%AD%97%E6%AE%B5", 
                    "conf desc", _type="ERROR", position=InfoBarPosition.TOP)
                return
            self.setContent(folder)


class ConfDialog(QDialog, Ui_ConfDialog):
    def __init__(self, parent=None):
        super(ConfDialog, self).__init__(parent)
        self.gui = parent
        self.setupUi(self)

    def setupUi(self, Dialog):
        super(ConfDialog, self).setupUi(Dialog)
        self.retranslateUiAgain(Dialog)
        self.acceptBtn.clicked.connect(self.save_conf)
        self.acceptBtn.setIcon(FIF.SAVE)
        self.cancelBtn.setIcon(FIF.CLOSE)
        tip = QtCore.QCoreApplication.translate("Dialog", F"idx corresponds/序号对应：\n{json.dumps(SPIDERS)}")
        self.completerEdit.setToolTip(tip)
        self.label_completer.setToolTip(tip)
        self._preset()
        self.insert_btn()

    def retranslateUiAgain(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        self.label_2.setText(_translate("Dialog", res.GUI.Uic.confDia_labelLogLevel))
        self.isDeduplicate.setText(_translate("Dialog", res.GUI.Uic.confDia_labelDedup))
        self.addUuid.setText(_translate("Dialog", res.GUI.Uic.confDia_labelAddUuid))
        self.label_4.setText(_translate("Dialog", res.GUI.Uic.confDia_labelProxy))
        self.label_3.setText(_translate("Dialog", res.GUI.Uic.confDia_labelMap))
        self.label_completer.setText(_translate("Dialog", res.GUI.Uic.confDia_labelPreset))
        self.label_6.setText(_translate("Dialog", res.GUI.Uic.confDia_labelClipDb))
        self.label_7.setText(_translate("Dialog", res.GUI.Uic.confDia_labelClipNum))
        
    def _preset(self):
        self.sv_path_card = SvPathCard(self)
        self.sv_path_Layout.addWidget(self.sv_path_card)
        
        completer = QCompleter(['127.0.0.1:10809'])
        completer.setFilterMode(QtCore.Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.proxiesEdit.setCompleter(completer)
        self.proxiesEdit.setClearButtonEnabled(True)
    
    def insert_btn(self):
        def _create_desc():
            QDesktopServices.openUrl(QUrl('https://jasoneri.github.io/ComicGUISpider/'))
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
        for _ in ('proxies', 'custom_map', "completer", "eh_cookies", "clip_db"):
            getattr(self, f"{_}Edit").setText(self.transfer_to_gui(getattr(conf, _) or ""))
        self.logLevelComboBox.setCurrentIndex(self.logLevelComboBox.findText(getattr(conf, "log_level")))
        # 2. CheckBox类配置
        for _ in ('addUuid', 'isDeduplicate'):
            getattr(self, f"{_}").setChecked(getattr(conf, f"{_}"))
        # 3. SpinBox类配置
        getattr(self, "clip_read_numEdit").setValue(int(getattr(conf, "clip_read_num")))
        super(ConfDialog, self).show()
        # 4. SettingCard卡片类配置
        self.sv_path_card.setContent(str(getattr(conf, "sv_path")))

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
        sv_path = self.sv_path_card.contentLabel.text()
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
