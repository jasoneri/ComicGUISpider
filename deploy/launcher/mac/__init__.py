#!/usr/bin/python
# -*- coding: utf-8 -*-
import pathlib
import re
import subprocess

font = "Hiragino Sans GB"
# 对应`冬青黑体简体中文`，想要换其他字体可聚焦搜索`字体集`，在目标字体右键`访达中显示`，可以看到字体文件，把字体名替换掉`font`的值即可


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
        uic_p = self.proj_p.joinpath("GUI/uic")
        for _f in ["ui_ensure_dia.py", "browser.py", "ui_mainwindow.py"]:
            self.file_content_replace(
                uic_p.joinpath(_f),
                lambda content: content.replace('微软雅黑', font)
            )

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
