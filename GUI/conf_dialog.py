#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import json
import pathlib
import codecs

import yaml
from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QSizePolicy, QFileDialog, QCompleter
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from qfluentwidgets import (
    FluentIcon as FIF, PushButton, PrimaryPushButton, TransparentPushButton, 
    PushSettingCard, InfoBarPosition, TransparentToggleToolButton,
)
import uncurl

from assets import res
from variables import SPIDERS, COOKIES_PLACEHOLDER, COOKIES_SUPPORT
from utils import conf, convert_punctuation as cp, exc_p
from GUI.thread import ProjUpdateThread
from GUI.uic.conf_dia import Ui_Dialog as Ui_ConfDialog
from GUI.manager import Updater, Proj
from GUI.core.theme import theme_mgr, CustTheme
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
            cgs_path = exc_p
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
        self.concurr_numLabel.setText(_translate("Dialog", res.GUI.Uic.confDia_labelConcurrNum))
        # 添加cookie类型选项
        support = list(COOKIES_PLACEHOLDER.keys())
        for cookie_type in support:
            self.cookiesBox.addItem(cookie_type)
        
        self.pypiSourceBox.setItemText(0, _translate("Dialog", "pypi"))
        self.pypiSourceBox.setItemText(1, _translate("Dialog", "清华源"))
        self.pypiSourceBox.setItemText(2, _translate("Dialog", "阿里源"))
        self.pypiSourceBox.setItemText(3, _translate("Dialog", "华为源"))
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

        self.darkTheme = TransparentToggleToolButton(FIF.QUIET_HOURS)
        def switch_mode():
            if self.darkTheme.isChecked():
                conf.darkTheme = True
            else:
                conf.darkTheme = False
            theme_mgr.set_dark(conf.darkTheme)
        self.darkTheme.clicked.connect(switch_mode)
        self.horizontalLayout_proxies.addWidget(self.darkTheme)

    def show_self(self):  # can't naming `show`. If done, just run code once
        # 1. Text类配置
        for _ in ('proxies', 'custom_map', "completer", "clip_db"):
            getattr(self, f"{_}Edit").setText(self.transfer_to_gui(getattr(conf, _) or ""))
        # 处理cookies配置
        self._load_cookie_config()
        self.logLevelComboBox.setCurrentIndex(self.logLevelComboBox.findText(getattr(conf, "log_level")))
        self.pypiSourceBox.setCurrentIndex(getattr(conf, "pypi_source"))
        # 2. CheckBox类配置
        for _ in ('addUuid', 'isDeduplicate', "darkTheme"):
            getattr(self, f"{_}").setChecked(getattr(conf, f"{_}"))
        # 3. SpinBox类配置
        for _ in ('clip_read_num', 'concurr_num'):
            getattr(self, f"{_}Edit").setValue(int(getattr(conf, _)))
        super(ConfDialog, self).show()
        # 4. SettingCard卡片类配置
        self.sv_path_card.setContent(str(getattr(conf, "sv_path")))

    def _on_cookie_type_changed(self, cookie_type):
        conf.cookies.switch(cookie_type)
        self._update_cookie_display()

    def _load_cookie_config(self):
        current_type = conf.cookies.current_type
        self.cookiesBox.setCurrentText(current_type)
        self._update_cookie_display()

    def _update_cookie_display(self):
        self.cookiesEdit.setText(self.transfer_to_gui(conf.cookies.show(), is_cookies=True))
        self.cookiesEdit.setPlaceholderText(COOKIES_PLACEHOLDER.get(conf.cookies.current_type, ""))

    @staticmethod
    def transfer_to_gui(val, is_cookies=False) -> str:
        if isinstance(val, list):
            return ",".join(val)
        elif isinstance(val, dict):
            if not val:
                return ""
            if is_cookies:
                return "{\n" + \
            "\n".join([f"""'{k}': {v if not isinstance(v, str) else f"'{v}'"},""" for k, v in val.items()]) + "\n}"
            return "\n".join([f"{k}: {v}" for k, v in val.items()]).replace("'", "")
            # return yaml.dump(val, allow_unicode=True)
        else:
            return str(val)

    def save_conf(self):
        sv_path = self.sv_path_card.contentLabel.text()
        self.format_cookie()

        config = {
            "sv_path": sv_path,
            "custom_map": yaml.safe_load(cp(getattr(self, "custom_mapEdit").toPlainText())),
            "completer": yaml.safe_load(cp(getattr(self, "completerEdit").toPlainText())),
            "proxies": cp(self.proxiesEdit.text()).replace(" ", "").split(",") if self.proxiesEdit.text() else None,
            "log_level": getattr(self, "logLevelComboBox").currentText(),
            "pypi_source": getattr(self, "pypiSourceBox").currentIndex(),
            "addUuid": getattr(self, "addUuid").isChecked(),
            "isDeduplicate": getattr(self, "isDeduplicate").isChecked(),
            "darkTheme": getattr(self, "darkTheme").isChecked(),
            "clip_db": getattr(self, "clip_dbEdit").text(),
            "clip_read_num": getattr(self, "clip_read_numEdit").value(),
            "concurr_num": getattr(self, "concurr_numEdit").value()
        }
        conf.update(**config)

    def format_cookie(self):
        """格式化并保存当前cookiesEdit的内容到当前所选"""
        cookies_str = cp(getattr(self, "cookiesEdit").toPlainText()).replace("cookies = ", "")
        if cookies_str:
            try:
                if cookies_str.startswith("curl"):
                    cookies_str = codecs.decode(cookies_str, 'unicode_escape')
                    context = uncurl.parse_context(cookies_str)
                    cookie_data = dict(context.cookies)
                else:
                    assert isinstance(ast.literal_eval(cookies_str), dict)
                    cookie_data = ast.literal_eval(cookies_str)
            except (SyntaxError, ValueError, AssertionError) as e:
                self.cookiesEdit.setText("")
                raise SyntaxError(res.GUI.cookies_copy_err)
        else:
            cookie_data = {}

        # 验证并精简cookie_data到required_fields
        current_type = conf.cookies.current_type
        required_fields = COOKIES_SUPPORT.get(current_type, set())
        if required_fields and cookie_data:
            cookie_keys = set(cookie_data.keys())
            if not required_fields.issubset(cookie_keys):
                missing_keys = required_fields - cookie_keys
                raise ValueError(f"miss cookies: {', '.join(missing_keys)}")
            # 精简cookie_data，只保留required_fields中的字段
            cookie_data = {key: cookie_data[key] for key in required_fields}

        conf.cookies.update_current(cookie_data)
