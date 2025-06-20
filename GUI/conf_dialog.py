#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import json
import pathlib

from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QSizePolicy, QFileDialog, QCompleter
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from qfluentwidgets import (
    FluentIcon as FIF, PushButton, PrimaryPushButton, TransparentPushButton, 
    PushSettingCard, InfoBarPosition
)
from assets import res
from variables import SPIDERS, COOKIES_PLACEHOLDER, COOKIES_SUPPORT
from utils import conf, yaml, convert_punctuation as cp, ori_path, ConfCookie
from GUI.thread import ProjUpdateThread
from GUI.uic.conf_dia import Ui_Dialog as Ui_ConfDialog
from GUI.manager import Updater, Proj
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
                    "https://jasoneri.github.io/ComicGUISpider/config/#配置项-对应-yml-字段", 
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
        # 添加cookie类型选项
        support = list(COOKIES_PLACEHOLDER.keys())
        for cookie_type in support:
            self.cookiesBox.addItem(cookie_type)
        self.cookiesBox.setCurrentText(support[0])

    def _preset(self):
        self.sv_path_card = SvPathCard(self)
        self.sv_path_Layout.addWidget(self.sv_path_card)
        
        completer = QCompleter(['127.0.0.1:10809'])
        completer.setFilterMode(QtCore.Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.proxiesEdit.setCompleter(completer)
        self.proxiesEdit.setClearButtonEnabled(True)

        # 连接信号
        self.cookiesBox.currentTextChanged.connect(self._on_cookie_type_changed)
    
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
        for _ in ('proxies', 'custom_map', "completer", "clip_db"):
            getattr(self, f"{_}Edit").setText(self.transfer_to_gui(getattr(conf, _) or ""))
        # 处理cookies配置
        self._load_cookie_config()
        self.logLevelComboBox.setCurrentIndex(self.logLevelComboBox.findText(getattr(conf, "log_level")))
        # 2. CheckBox类配置
        for _ in ('addUuid', 'isDeduplicate'):
            getattr(self, f"{_}").setChecked(getattr(conf, f"{_}"))
        # 3. SpinBox类配置
        getattr(self, "clip_read_numEdit").setValue(int(getattr(conf, "clip_read_num")))
        super(ConfDialog, self).show()
        # 4. SettingCard卡片类配置
        self.sv_path_card.setContent(str(getattr(conf, "sv_path")))

    def _on_cookie_type_changed(self, cookie_type):
        """当cookie类型改变时，先保存当前内容，再切换显示新的cookie"""
        self.format_cookie(conf.cookies.current_type)
        # 切换到新的cookie类型
        conf.cookies.switch(cookie_type)
        # 显示新的cookie内容
        current_cookie_data = conf.cookies.show()
        self.cookiesEdit.setText(self.transfer_to_gui(current_cookie_data))
        self.cookiesEdit.setPlaceholderText(COOKIES_PLACEHOLDER.get(conf.cookies.current_type, ""))

    def _load_cookie_config(self):
        """加载cookie配置到界面"""
        current_type = conf.cookies.current_type
        self.cookiesBox.setCurrentText(current_type)

        # 显示当前选中的cookie
        current_cookie_data = conf.cookies.show()
        self.cookiesEdit.setText(self.transfer_to_gui(current_cookie_data))
        self.cookiesEdit.setPlaceholderText(COOKIES_PLACEHOLDER.get(current_type, ""))

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
        self.format_cookie(conf.cookies.current_type)

        config = {
            "sv_path": sv_path,
            "custom_map": yaml.safe_load(cp(getattr(self, "custom_mapEdit").toPlainText())),
            "completer": yaml.safe_load(cp(getattr(self, "completerEdit").toPlainText())),
            "proxies": cp(self.proxiesEdit.text()).replace(" ", "").split(",") if self.proxiesEdit.text() else None,
            "log_level": getattr(self, "logLevelComboBox").currentText(),
            "addUuid": getattr(self, "addUuid").isChecked(),
            "isDeduplicate": getattr(self, "isDeduplicate").isChecked(),
            "clip_db": getattr(self, "clip_dbEdit").text(),
            "clip_read_num": getattr(self, "clip_read_numEdit").value()
        }
        conf.update(**config)

    def format_cookie(self, cookies_type):
        """格式化并保存当前cookiesEdit的内容到ConfCookie缓存"""
        cookies_str = cp(getattr(self, "cookiesEdit").toPlainText()).replace("cookies = ", "")

        if cookies_str:
            try:
                assert isinstance(ast.literal_eval(cookies_str), dict)
                cookie_data = ast.literal_eval(cookies_str)
            except (SyntaxError, ValueError, AssertionError):
                try:
                    assert isinstance(yaml.safe_load(cookies_str), dict)
                    cookie_data = yaml.safe_load(cookies_str)
                except (SyntaxError, ValueError, AssertionError):
                    self.cookiesEdit.setText("")
                    raise SyntaxError(res.GUI.cookies_copy_err)
        else:
            cookie_data = {}

        # 验证并精简cookie_data到required_fields
        required_fields = COOKIES_SUPPORT.get(cookies_type, set())
        if required_fields and cookie_data:
            cookie_keys = set(cookie_data.keys())
            if not required_fields.issubset(cookie_keys):
                missing_keys = required_fields - cookie_keys
                raise ValueError(f"miss cookies: {', '.join(missing_keys)}")
            # 精简cookie_data，只保留required_fields中的字段
            cookie_data = {key: cookie_data[key] for key in required_fields}

        original_type = conf.cookies.current_type
        conf.cookies.switch(cookies_type)
        conf.cookies.update_current(cookie_data)
        conf.cookies.switch(original_type)
