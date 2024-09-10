#!/usr/bin/python
# -*- coding: utf-8 -*-
import pathlib
import re
import subprocess

font = "Hiragino Sans GB"


# 对应`冬青黑体简体中文`，想要换其他字体可聚焦搜索`字体册`，在目标字体右键`访达中显示`，可以看到字体文件，把字体名替换掉`font`的值即可
# 字体册仅支持能访达/系统alias能搜索出的字体，如果是下载的字体，可以看`macOS.font_replace _repl`


class macOS:
    default_sv_path = pathlib.Path.home().joinpath("Downloads/Comic")

    def __init__(self, _p):
        self.proj_p = _p

    @staticmethod
    def open_folder(_p):
        subprocess.run(['open', _p])

    def env_init(self):
        # 1. 更换字体
        self.font_replace()
        # 2. requirements.txt去掉window相关的包
        self.handle_requirements()

    def font_replace(self):
        def _repl(content):
            """下载的字体用绝对路径时可以用以下注释了的替换方法"""
            # font_path = "/Users/Shared/.../xxx.ttc"
            # if "QFontDatabase" not in content:
            #     content = ("from PyQt5.QtGui import QFontDatabase\n"
            #                f"font_path = '{font_path}'\n"
            #                f"_id = QFontDatabase.addApplicationFont(font_path)\n") + content
            # new_content = re.sub(r'font = .*?\n.*?font\.setFamily\(".*?"\)',
            #                      f'font = QFontDatabase.font("{font}", "Regular", 11)', content, re.M)
            new_content = re.sub(r'font\.setFamily\(".*?"\)', f'font.setFamily("{font}")', content)
            return new_content
        uic_p = self.proj_p.joinpath("GUI/uic")
        for _f in ["ui_ensure_dia.py", "browser.py", "ui_mainwindow.py"]:
            self.file_content_replace(uic_p.joinpath(_f), _repl)

    def handle_requirements(self):
        self.file_content_replace(
            self.proj_p.joinpath('requirements.txt'),
            lambda content: re.sub(r"twisted-iocpsupport==.*\n", "", content)
        )

    @staticmethod
    def file_content_replace(file, repl_func):
        with open(file, 'r+', encoding='utf-8') as fp:
            content = fp.read()
            new_content = repl_func(content)
            fp.seek(0)
            fp.truncate()
            fp.write(new_content)
