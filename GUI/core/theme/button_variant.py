# -*- coding: utf-8 -*-
"""按钮变种（button variant）：集中色板 + 属性标记，不限按钮类型与状态。

qfluentwidgets 仅有 primary（ThemeColor）单变体；本模块在其之上提供项目的命名变体
扩展。规则与色板集中在 ``GUI/core/theme/subscribe.qss``：tokens 定义 ``BTN_<NAME>_*``
色板，``@section variant`` 定义状态规则——此处只做应用，py 里不塞 qss 内容。

为何必须 widget 级应用而非窗口级 qss：fluent 自带按钮 qss 挂在 widget 自身，Qt 层级上
widget 自身 sheet 绝对压过祖先 sheet（离屏实测：窗口级 ``QToolButton#X[variant]:checked``
4 段特异性仍输给 fluent ``ToggleToolButton:checked`` 的 2 段），窗口级盖不过。
``setCustomStyleSheet`` 是 qfluent 官方组合式 API：追加声明置于 fluent 源之后，同特异性
后者胜出；且随主题切换经 styleSheetManager 整体重渲染，浅红不丢。

用法::

    button.setProperty("variant", "danger")
    apply_button_variant(button)

新增变种 = subscribe.qss 的 tokens 加一组色 + variant section 加三条规则，py 零改动。
"""
from __future__ import annotations

from PySide6.QtWidgets import QAbstractButton

from qfluentwidgets.common.style_sheet import setCustomStyleSheet

from GUI.core.theme.qss_template import render_templated_qss_section
from utils import ori_path

_QSS_PATH = ori_path.joinpath("GUI/core/theme/subscribe.qss")


def apply_button_variant(button: QAbstractButton) -> None:
    """把 subscribe.qss 的 variant 段应用到按钮（light/dark 双主题随切换重渲染）。

    按钮需先 ``setProperty("variant", "<name>")``；规则按属性名匹配，未标记的按钮
    应用本段也无任何效果（选择器不命中），故可安全地对任意按钮调用。
    """
    light = render_templated_qss_section(_QSS_PATH, "light", "variant")
    dark = render_templated_qss_section(_QSS_PATH, "dark", "variant")
    setCustomStyleSheet(button, light, dark)
