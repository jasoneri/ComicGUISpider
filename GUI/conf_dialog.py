#!/usr/bin/python
# -*- coding: utf-8 -*-
import ast
import json
import pathlib
import codecs
from functools import partial

import yaml
from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog, QSizePolicy, QFileDialog, QCompleter, QApplication
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl, Qt
from qfluentwidgets import (
    FluentIcon as FIF, PushButton, PrimaryPushButton, TransparentPushButton, 
    PushSettingCard, InfoBarPosition, TransparentToggleToolButton, InfoBar
)
import uncurl

from assets import res
from variables import SPIDERS, COOKIES_PLACEHOLDER, COOKIES_SUPPORT, LANG
from utils import conf, convert_punctuation as cp, exc_p
from GUI.thread import ProjUpdateThread
from GUI.uic.conf_dia import Ui_Dialog as Ui_ConfDialog
from GUI.manager import Updater, Proj
from GUI.core.theme import theme_mgr
from GUI.uic.qfluent.components import (
    SupportView, CustomFlyout, CustomInfoBar, ExpandSettings, TextEditWithBg
)


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
        self._init_flag = True
        self.gui = parent
        self.setupUi(self)

    def setupUi(self, Dialog):
        super(ConfDialog, self).setupUi(Dialog)
        self.retranslateUiAgain(Dialog)
        self.acceptBtn.clicked.connect(self.save_conf)
        self.acceptBtn.setIcon(FIF.SAVE)
        self.cancelBtn.setIcon(FIF.CLOSE)
        self.insert_btn()
        self._preset()
        self._repaint_textEdit()

    def retranslateUiAgain(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        self.label_2.setText(_translate("Dialog", res.GUI.Uic.confDia_labelLogLevel))
        self.label_4.setText(_translate("Dialog", res.GUI.Uic.confDia_labelProxy))
        self.label_completer.setText(_translate("Dialog", res.GUI.Uic.confDia_labelPreset))
        self.label_6.setText(_translate("Dialog", res.GUI.Uic.confDia_labelClipDb))
        self.label_7.setText(_translate("Dialog", res.GUI.Uic.confDia_labelClipNum))
        self.concurr_numLabel.setText(_translate("Dialog", res.GUI.Uic.confDia_labelConcurrNum))
        # 添加cookie类型选项
        support = list(COOKIES_PLACEHOLDER.keys())
        for cookie_type in support:
            self.cookiesBox.addItem(cookie_type)
        self.pypiSourceBox.addItem("")
        self.pypiSourceBox.addItem("")
        self.pypiSourceBox.addItem("")
        self.pypiSourceBox.addItem("")
        self.pypiSourceBox.setItemText(0, _translate("Dialog", "pypi"))
        self.pypiSourceBox.setItemText(1, _translate("Dialog", "清华源"))
        self.pypiSourceBox.setItemText(2, _translate("Dialog", "阿里源"))
        self.pypiSourceBox.setItemText(3, _translate("Dialog", "华为源"))
        self.cookiesBox.setCurrentText(support[0])
        
        for k, ui_key in LANG.items():
            self.langBox.addItem(ui_key, userData=k)

    def _repaint_textEdit(self):
        for imge in ("cookies", "completer", "custom_map"):
            imgew = f"{imge}Edit"
            _ = getattr(self, imgew, None)
            if _:
                _.setParent(None)
                _.deleteLater()
            textEditWidget = TextEditWithBg(self)
            textEditWidget.setObjectName(imgew)
            textEditWidget.set_fixed_image(f":/configDialog/{imge}.png")
            setattr(self, imgew, textEditWidget)
            getattr(self, f"horizontalLayout_label_{imge}").insertWidget(1, textEditWidget)
        tip = QtCore.QCoreApplication.translate("Dialog", F"idx corresponds/序号对应：\n{json.dumps(SPIDERS)}")
        self.completerEdit.setToolTip(tip)
        self.label_completer.setToolTip(tip)

    def _preset(self):
        self.sv_path_card = SvPathCard(self)
        self.dialogVLayout.insertWidget(0, self.sv_path_card)
        
        completer = QCompleter(['127.0.0.1:10809'])
        completer.setFilterMode(QtCore.Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.proxiesEdit.setCompleter(completer)
        self.proxiesEdit.setClearButtonEnabled(True)

    def insert_btn(self):
        self.descBtn = PrimaryPushButton(FIF.LIBRARY, res.GUI.Uic.confDia_descBtn)
        self.descBtn.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.descBtn.setMaximumSize(QtCore.QSize(110, 16777215))
        self.updateBtn = PushButton(FIF.UPDATE, res.GUI.Uic.confDia_updateBtn)
        self.updateBtn.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.updateBtn.setMaximumSize(QtCore.QSize(110, 16777215))
        self.supportBtn = TransparentPushButton(FIF.CAFE, res.GUI.Uic.confDia_supportBtn)
        
        self.bottom_btn_horizontalLayout.insertWidget(0, self.supportBtn)
        self.bottom_btn_horizontalLayout.insertWidget(0, self.updateBtn)
        self.bottom_btn_horizontalLayout.insertWidget(0, self.descBtn)

        self.isDeduplicate = TransparentToggleToolButton(FIF.FILTER)
        self.addUuid = TransparentToggleToolButton(FIF.FLAG)
        self.darkTheme = TransparentToggleToolButton(FIF.QUIET_HOURS)
        self.horizontalLayout_log_level.addWidget(self.isDeduplicate)
        self.horizontalLayout_log_level.addWidget(self.addUuid)
        self.horizontalLayout_log_level.addWidget(self.darkTheme)
        
        self.advBtn = TransparentPushButton(FIF.MORE, res.GUI.Uic.confDia_show_adv_settings, self)
        self._adv_content = ExpandSettings(self)
        self.expandLayout.insertWidget(0, self.advBtn)
        self.expandLayout.addWidget(self._adv_content)

    def refresh_size_for_expand(self, _):
        QApplication.processEvents()
        if _:
            self.adjustSize()
        else:
            self.resize(0, 0)
        screen_geom = QApplication.primaryScreen().availableGeometry()
        max_allowed = int(screen_geom.height() * 0.9)
        if self.height() > max_allowed:
            self.setMaximumHeight(max_allowed)
            self.resize(self.width(), max_allowed)

    def bind_logic(self):
        def _open_docs():
            QDesktopServices.openUrl(QUrl('https://jasoneri.github.io/ComicGUISpider/'))
        self.descBtn.clicked.connect(_open_docs)
        def _switch_mode():
            if self.darkTheme.isChecked():
                conf.darkTheme = True
            else:
                conf.darkTheme = False
            theme_mgr.set_dark(conf.darkTheme)
        self.darkTheme.clicked.connect(_switch_mode)
        def _regular_update():
            self.puThread = ProjUpdateThread(self)
            Updater(self.gui).run()
        self.updateBtn.clicked.connect(_regular_update)
        self.supportBtn.clicked.connect(lambda: CustomFlyout.make(
            view=SupportView(Proj.url, self), target=self.supportBtn, parent=self
        ))
        def _tip_lang_change(idx):
            if self.langBox.itemData(idx) != conf.lang:
                InfoBar.success(
                    title="", content=res.GUI.ui_lang_need_reboot,
                    orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                    duration=5000, parent=self
                )
        self.langBox.activated.connect(_tip_lang_change)
        self.cookiesBox.currentTextChanged.connect(self._on_cookie_type_changed)
        def _tip_on(is_checked: bool, tip_content=None):
            if is_checked:
                InfoBar.success(
                    title="", content=tip_content,
                    orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                    duration=4000, parent=self
                )
        self.isDeduplicate.toggled.connect(partial(_tip_on, tip_content=res.GUI.Uic.confDia_tip_deduplicate_on))
        self.addUuid.toggled.connect(partial(_tip_on, tip_content=res.GUI.Uic.confDia_tip_adduuid_on))
        self.kbShowDhb.toggled.connect(partial(_tip_on, tip_content=res.GUI.Uic.confDia_tip_kbshowdhb_on))

    def show_self(self):  # can't naming `show`. If done, just run code once
        # 1. Text类配置
        for _ in ('proxies', 'custom_map', "completer", "clip_db"):
            getattr(self, f"{_}Edit").setText(self.transfer_to_gui(getattr(conf, _) or ""))
        # 处理cookies配置
        self._load_cookie_config()
        # 2. CheckBox类配置
        for _ in ('addUuid', 'isDeduplicate', "darkTheme", "kbShowDhb"):
            getattr(self, f"{_}").setChecked(getattr(conf, f"{_}"))
        # 3. SpinBox类配置
        for _ in ('clip_read_num', 'concurr_num'):
            getattr(self, f"{_}Edit").setValue(int(getattr(conf, _)))
        super(ConfDialog, self).show()
        # 4. SettingCard卡片类配置
        self.sv_path_card.setContent(str(getattr(conf, "sv_path")))
        # 5. ComboBox类
        self.logLevelComboBox.setCurrentIndex(self.logLevelComboBox.findText(getattr(conf, "log_level")))
        self.pypiSourceBox.setCurrentIndex(getattr(conf, "pypi_source"))
        self.langBox.setCurrentIndex(self.langBox.findData(getattr(conf, "lang")))
        # 仅当 初次confdia ui创建 & conf值设入ui后，才绑定槽函数
        if self._init_flag:
            self.bind_logic()
            self._init_flag = False

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
            "log_level": getattr(self, "logLevelComboBox").currentText(),
            "lang": getattr(self, "langBox").currentData(),
            "concurr_num": getattr(self, "concurr_numEdit").value(),
            "isDeduplicate": getattr(self, "isDeduplicate").isChecked(),
            "addUuid": getattr(self, "addUuid").isChecked(),
            "darkTheme": getattr(self, "darkTheme").isChecked(),
            "kbShowDhb": getattr(self, "kbShowDhb").isChecked(),
            "proxies": cp(self.proxiesEdit.text()).replace(" ", "").split(",") if self.proxiesEdit.text() else None,
            "pypi_source": getattr(self, "pypiSourceBox").currentIndex(),
            "custom_map": yaml.safe_load(cp(getattr(self, "custom_mapEdit").toPlainText())),
            "completer": yaml.safe_load(cp(getattr(self, "completerEdit").toPlainText())),
            "clip_db": getattr(self, "clip_dbEdit").text(),
            "clip_read_num": getattr(self, "clip_read_numEdit").value(),
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
