# -*- coding: utf-8 -*-
# GUI
from PyQt5.QtWidgets import QApplication
import GUI.src.material_ct

# 自己项目用到的
from GUI.gui import SpiderGUI
import sys
from multiprocessing import freeze_support

# from multiprocessing.managers import RemoteError
# sys.setrecursionlimit(5000)

if __name__ == '__main__':
    freeze_support()
    app = QApplication(sys.argv)
    # app.setStyle("Fusion")
    ui = SpiderGUI()
    QApplication.processEvents()
    app.exec_()
