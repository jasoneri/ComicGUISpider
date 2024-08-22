# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'conf_dia.ui'
#
# Created by: PyQt5 UI code generator 5.15.10
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(500, 300)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Dialog.sizePolicy().hasHeightForWidth())
        Dialog.setSizePolicy(sizePolicy)
        Dialog.setMinimumSize(QtCore.QSize(500, 300))
        Dialog.setMaximumSize(QtCore.QSize(650, 400))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/dohnadohna_.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        Dialog.setWindowIcon(icon)
        self.gridLayout = QtWidgets.QGridLayout(Dialog)
        self.gridLayout.setObjectName("gridLayout")
        self.horizontalLayout_sv_path = QtWidgets.QHBoxLayout()
        self.horizontalLayout_sv_path.setObjectName("horizontalLayout_sv_path")
        self.label = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setMinimumSize(QtCore.QSize(0, 20))
        self.label.setMaximumSize(QtCore.QSize(60, 20))
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setObjectName("label")
        self.horizontalLayout_sv_path.addWidget(self.label)
        self.sv_pathEdit = QtWidgets.QLineEdit(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sv_pathEdit.sizePolicy().hasHeightForWidth())
        self.sv_pathEdit.setSizePolicy(sizePolicy)
        self.sv_pathEdit.setInputMask("")
        self.sv_pathEdit.setText("")
        self.sv_pathEdit.setObjectName("sv_pathEdit")
        self.horizontalLayout_sv_path.addWidget(self.sv_pathEdit)
        self.gridLayout.addLayout(self.horizontalLayout_sv_path, 0, 0, 1, 1)
        self.horizontalLayout_log_level = QtWidgets.QHBoxLayout()
        self.horizontalLayout_log_level.setObjectName("horizontalLayout_log_level")
        self.label_2 = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setMinimumSize(QtCore.QSize(0, 20))
        self.label_2.setMaximumSize(QtCore.QSize(60, 20))
        self.label_2.setAlignment(QtCore.Qt.AlignCenter)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_log_level.addWidget(self.label_2)
        self.logLevelComboBox = QtWidgets.QComboBox(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.logLevelComboBox.sizePolicy().hasHeightForWidth())
        self.logLevelComboBox.setSizePolicy(sizePolicy)
        self.logLevelComboBox.setObjectName("logLevelComboBox")
        self.logLevelComboBox.addItem("")
        self.logLevelComboBox.addItem("")
        self.logLevelComboBox.addItem("")
        self.logLevelComboBox.addItem("")
        self.horizontalLayout_log_level.addWidget(self.logLevelComboBox)
        self.gridLayout.addLayout(self.horizontalLayout_log_level, 1, 0, 1, 1)
        self.horizontalLayout_proxies = QtWidgets.QHBoxLayout()
        self.horizontalLayout_proxies.setObjectName("horizontalLayout_proxies")
        self.label_4 = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_4.sizePolicy().hasHeightForWidth())
        self.label_4.setSizePolicy(sizePolicy)
        self.label_4.setMinimumSize(QtCore.QSize(60, 20))
        self.label_4.setMaximumSize(QtCore.QSize(60, 20))
        self.label_4.setAlignment(QtCore.Qt.AlignCenter)
        self.label_4.setObjectName("label_4")
        self.horizontalLayout_proxies.addWidget(self.label_4)
        self.proxiesEdit = QtWidgets.QLineEdit(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.proxiesEdit.sizePolicy().hasHeightForWidth())
        self.proxiesEdit.setSizePolicy(sizePolicy)
        self.proxiesEdit.setMaximumSize(QtCore.QSize(16777215, 20))
        self.proxiesEdit.setObjectName("proxiesEdit")
        self.horizontalLayout_proxies.addWidget(self.proxiesEdit)
        self.gridLayout.addLayout(self.horizontalLayout_proxies, 2, 0, 1, 1)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setSizeConstraint(QtWidgets.QLayout.SetMaximumSize)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label_3 = QtWidgets.QLabel(Dialog)
        self.label_3.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_3.sizePolicy().hasHeightForWidth())
        self.label_3.setSizePolicy(sizePolicy)
        self.label_3.setMinimumSize(QtCore.QSize(60, 20))
        self.label_3.setMaximumSize(QtCore.QSize(60, 20))
        self.label_3.setAlignment(QtCore.Qt.AlignCenter)
        self.label_3.setObjectName("label_3")
        self.verticalLayout.addWidget(self.label_3)
        spacerItem = QtWidgets.QSpacerItem(20, 50, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.horizontalLayout.addLayout(self.verticalLayout)
        self.custom_mapEdit = QtWidgets.QTextEdit(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.custom_mapEdit.sizePolicy().hasHeightForWidth())
        self.custom_mapEdit.setSizePolicy(sizePolicy)
        self.custom_mapEdit.setObjectName("custom_mapEdit")
        self.horizontalLayout.addWidget(self.custom_mapEdit)
        self.gridLayout.addLayout(self.horizontalLayout, 3, 0, 1, 1)
        self.horizontalLayout_label_completer = QtWidgets.QHBoxLayout()
        self.horizontalLayout_label_completer.setObjectName("horizontalLayout_label_completer")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.label_completer = QtWidgets.QLabel(Dialog)
        self.label_completer.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_completer.sizePolicy().hasHeightForWidth())
        self.label_completer.setSizePolicy(sizePolicy)
        self.label_completer.setMinimumSize(QtCore.QSize(60, 20))
        self.label_completer.setMaximumSize(QtCore.QSize(60, 20))
        self.label_completer.setAlignment(QtCore.Qt.AlignCenter)
        self.label_completer.setObjectName("label_completer")
        self.verticalLayout_2.addWidget(self.label_completer)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout_2.addItem(spacerItem1)
        self.horizontalLayout_label_completer.addLayout(self.verticalLayout_2)
        self.completerEdit = QtWidgets.QTextEdit(Dialog)
        self.completerEdit.setToolTipDuration(-1)
        self.completerEdit.setObjectName("completerEdit")
        self.horizontalLayout_label_completer.addWidget(self.completerEdit)
        self.gridLayout.addLayout(self.horizontalLayout_label_completer, 4, 0, 1, 1)
        self.horizontalLayout_cv_path = QtWidgets.QHBoxLayout()
        self.horizontalLayout_cv_path.setObjectName("horizontalLayout_cv_path")
        self.label_5 = QtWidgets.QLabel(Dialog)
        self.label_5.setObjectName("label_5")
        self.horizontalLayout_cv_path.addWidget(self.label_5)
        self.cv_proj_pathEdit = QtWidgets.QLineEdit(Dialog)
        self.cv_proj_pathEdit.setObjectName("cv_proj_pathEdit")
        self.horizontalLayout_cv_path.addWidget(self.cv_proj_pathEdit)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.buttonBox.sizePolicy().hasHeightForWidth())
        self.buttonBox.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setStrikeOut(False)
        self.buttonBox.setFont(font)
        self.buttonBox.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.buttonBox.setAutoFillBackground(False)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Save)
        self.buttonBox.setCenterButtons(False)
        self.buttonBox.setObjectName("buttonBox")
        self.horizontalLayout_cv_path.addWidget(self.buttonBox)
        self.gridLayout.addLayout(self.horizontalLayout_cv_path, 5, 0, 1, 1)

        self.retranslateUi(Dialog)
        self.buttonBox.rejected.connect(Dialog.reject)  # type: ignore
        self.buttonBox.accepted.connect(Dialog.accept)  # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "config/配置"))
        self.label.setToolTip(_translate("Dialog", "save_path"))
        self.label.setText(_translate("Dialog", "存储路径"))
        self.sv_pathEdit.setToolTip(_translate("Dialog", "save_path"))
        self.label_2.setToolTip(_translate("Dialog", "log_level"))
        self.label_2.setText(_translate("Dialog", "日志等级"))
        self.logLevelComboBox.setItemText(0, _translate("Dialog", "WARNING"))
        self.logLevelComboBox.setItemText(1, _translate("Dialog", "DEBUG"))
        self.logLevelComboBox.setItemText(2, _translate("Dialog", "INFO"))
        self.logLevelComboBox.setItemText(3, _translate("Dialog", "ERROR"))
        self.label_4.setToolTip(_translate("Dialog", "proxies"))
        self.label_4.setText(_translate("Dialog", "代理"))
        self.proxiesEdit.setToolTip(_translate("Dialog", "proxies"))
        self.label_3.setToolTip(_translate("Dialog", "custom_map"))
        self.label_3.setText(_translate("Dialog", "映射"))
        self.label_completer.setToolTip(_translate("Dialog", "completer/preset"))
        self.label_completer.setText(_translate("Dialog", "预设"))
        self.completerEdit.setToolTip(_translate("Dialog", "completer/preset"))
        self.label_5.setToolTip(_translate("Dialog", "comic_viewer_proj_path"))
        self.label_5.setText(_translate("Dialog", "cv项目路径"))
        self.cv_proj_pathEdit.setToolTip(_translate("Dialog", "comic_viewer_proj_path"))
