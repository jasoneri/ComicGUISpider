# patch_ui.py
import pathlib
from copy import deepcopy
import re
import argparse

_p = pathlib.Path(__file__).parent.parent
# 定义需要替换的控件映射
REPLACE_MAP = {
    "QLineEdit": "LineEdit",
    "QTextBrowser": "TextBrowser",
    "QTextEdit": "TextEdit",
    "QComboBox": "ComboBox",
    "QCheckBox": "CheckBox",
    "QSpinBox": "CompactSpinBox",
}
DEFAULT_CUSTOM_SUB = {
    "import material_ct_rc\n": ""
}


class ConvertBase:
    def __init__(self, old, new, custom_sub=None, custom_fluent_widgets=None, extra_import=''):
        self.old = old
        with open(_p.joinpath(old), 'r', encoding='utf8') as f:
            self.content = f.read()
        self.new = new
        self.custom_sub = custom_sub or {}
        self.custom_fluent_widgets = custom_fluent_widgets or []
        self.extra_import = extra_import

    def convert_ui_file(self):
        # 处理导入语句替换 --------------------------------------------------------------
        # 添加 qfluentwidgets 的导入（去重处理）
        import_part = 'from qfluentwidgets import ' + ', '.join(
            sorted(set(REPLACE_MAP.values()) | set(self.custom_fluent_widgets))
        )
        content = deepcopy(self.content)
        content = content.replace(
            r'from PyQt5 import QtCore, QtGui, QtWidgets',
            f'from PyQt5 import QtCore, QtGui, QtWidgets\n{import_part}{self.extra_import}'
        )
        # 替换控件实例化代码 ------------------------------------------------------------
        for origin, new in REPLACE_MAP.items():
            # 替换形如 QtWidgets.QComboBox 的引用
            content = content.replace(f'QtWidgets.{origin}', new)
        with open(_p.joinpath(self.new), 'w', encoding='utf8') as f:
            f.write(content)

    def run(self):
        for _o, _n in {**self.custom_sub, **DEFAULT_CUSTOM_SUB}.items():
            self.content = re.sub(_o, _n, self.content)
        self.convert_ui_file()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='转换UI文件为Fluent风格')
    parser.add_argument('filename', help='要转换的UI文件名（不含路径）')
    args = parser.parse_args()
    
    file = f"{args.filename}.py"
    match args.filename:
        case "conf_dia":
            cb = ConvertBase('conf_dia.py', 'conf_dia.py', custom_sub={
                "= QtWidgets.QLabel": "= StrongBodyLabel",
                "acceptBtn = QtWidgets.QToolButton": "acceptBtn = PrimaryToolButton",
                "cancelBtn = QtWidgets.QToolButton": "cancelBtn = TransparentToolButton",
            }, 
            custom_fluent_widgets=['StrongBodyLabel', 'TransparentToolButton', 'PrimaryToolButton'])
        case "browser":
            cb = ConvertBase('browser.py', 'browser.py', custom_sub={
                "topHintBox = QtWidgets.QToolButton": "topHintBox = TransparentToggleToolButton",
                "ensureBtn = QtWidgets.QToolButton": "ensureBtn = PrimaryToolButton",
                "QtWidgets.QToolButton": "TransparentToolButton",
            }, custom_fluent_widgets=['TransparentToolButton', 'PrimaryToolButton', 'TransparentToggleToolButton'])
        case _:
            cb = ConvertBase(file, file)
    cb.run()
