#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
import pathlib

from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog

from GUI.uic.conf_dia import Ui_Dialog as Ui_ConfDialog
from variables import SPIDERS
from utils import conf, yaml, convert_punctuation as cp


class ConfDialog(QDialog, Ui_ConfDialog):
    def __init__(self, parent=None):
        super(ConfDialog, self).__init__(parent)
        self.setupUi(self)

    def setupUi(self, Dialog):
        super(ConfDialog, self).setupUi(Dialog)
        self.buttonBox.accepted.connect(self.save_conf)
        tip = QtCore.QCoreApplication.translate("Dialog", F"序号对应：{json.dumps(SPIDERS)}")
        self.completerEdit.setToolTip(tip)
        self.label_completer.setToolTip(tip)

    def show_self(self):  # can't naming `show`. If done, just run code once
        for _ in ('sv_path', 'proxies', 'custom_map', 'cv_proj_path', "completer"):
            getattr(self, f"{_}Edit").setText(self.transfer_to_gui(getattr(conf, _) or ""))
        self.logLevelComboBox.setCurrentIndex(self.logLevelComboBox.findText(getattr(conf, "log_level")))
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
        sv_path = getattr(self, f"sv_pathEdit").text()
        cv_proj_path_str = getattr(self, f"cv_proj_pathEdit").text()
        config = {
            "sv_path": sv_path,
            "cv_proj_path": cv_proj_path_str,
            "custom_map": yaml.safe_load(cp(getattr(self, f"custom_mapEdit").toPlainText())),
            # TODO[7](2024-08-19): gui进程出错时仍然没记录至log里，如上述yaml的格式保存错误
            "completer": yaml.safe_load(cp(getattr(self, f"completerEdit").toPlainText())),
            "proxies": cp(self.proxiesEdit.text()).replace(" ", "").split(",") if self.proxiesEdit.text() else None,
            "log_level": getattr(self, "logLevelComboBox").currentText()
        }
        conf.update(**config)

        if cv_proj_path_str:  # 联动comic_viewer更改
            cv_proj_path = pathlib.Path(cv_proj_path_str)
            if cv_proj_path.joinpath("scripts").exists():
                cv_proj_path = cv_proj_path.joinpath("scripts")
            cv_conf = cv_proj_path.joinpath("backend/conf.yml")
            if not cv_conf.exists():
                return
            with open(cv_conf, 'w', encoding='utf-8') as fp:
                yaml_data = yaml.dump({"path": sv_path}, allow_unicode=True)
                fp.write(yaml_data)
