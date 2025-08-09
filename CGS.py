# -*- coding: utf-8 -*-
import sys
from multiprocessing import freeze_support

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# 自己项目用到的
from GUI.gui import SpiderGUI
import GUI.src.material_ct

# from multiprocessing.managers import RemoteError
# sys.setrecursionlimit(5000)


def start():
    freeze_support()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    ui = SpiderGUI()
    sys.excepthook = ui.hook_exception
    QApplication.processEvents()
    app.exec_()


if __name__ == '__main__':
    start()
