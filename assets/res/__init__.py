#!/usr/bin/python
# -*- coding: utf-8 -*-
import gettext
import pathlib
import hashlib
import types

from PyQt5.QtCore import QLocale

from assets.res.transfer import main as translation_compile

"""usage of `<br>`：
    1. 一行话禁止加 `br` ，换行在 `self.say()` 前解决;
    2. 多行的一段话可在最后加 `br` ，禁止在段落起始处加 `br`
    
    1. forbid the use of `br` in one line, solve line break before `self.say()`;
    2. add `br` at the end of a paragraph with multiple lines, forbid the use of `br` at the beginning of a paragraph
"""


def getUserLanguage():
    sys_lang = QLocale.system().name()
    if _path.joinpath(f'locale/{sys_lang}.yml').exists():
        return sys_lang
    return 'en_US'


_path = pathlib.Path(__file__).parent
lang = getUserLanguage()


def is_compiled():
    if not (_path.joinpath(f'locale/{lang}/LC_MESSAGES/res.mo').exists() and \
        _path.joinpath(f'locale/{lang}.hash').exists()):
            return False
    with open(_path.joinpath(f'locale/{lang}.hash'), 'r', encoding='utf-8') as f:
        return hashlib.sha256(_path.joinpath(f'locale/{lang}.yml').read_bytes()).hexdigest() == f.read()


_ = is_compiled()
if not _:
    translation_compile(_path, lang)

gettext.bindtextdomain('res', str(_path / 'locale'))
gettext.textdomain('res')

try:
    _translation = gettext.translation('res', str(_path / 'locale'), languages=[lang], fallback=False)
    _ = _translation.gettext
except FileNotFoundError as e:
    print(str(e))
    _ = gettext.gettext


class TranslationNamespace(types.SimpleNamespace):
    """动态加载翻译项的命名空间"""
    def __init__(self, prefix, **kwargs):
        self._prefix = prefix
        super().__init__(**kwargs)
        
    def __getattr__(self, name):
        # 动态创建嵌套命名空间
        if name.startswith('_'):
            return super().__getattr__(name)
            
        nested_prefix = f"{self._prefix}.{name}" if self._prefix else name
        value = _(nested_prefix)
        
        # 如果返回的是原始键（未翻译），尝试创建嵌套命名空间
        if value == nested_prefix:
            return TranslationNamespace(nested_prefix)
        return value

# 自动创建所有翻译命名空间
def create_translation_namespaces():
    modules = {}
    
    # 顶级命名空间 (如 Vars, GUI, Updater)
    for module_name in ['Vars', 'GUI', 'Updater', 'SPIDER', 'EHentai']:
        modules[module_name] = TranslationNamespace(module_name)
    return types.SimpleNamespace(**modules)


# 创建动态翻译对象
i18n = create_translation_namespaces()

Vars = i18n.Vars
GUI = i18n.GUI
SPIDER = i18n.SPIDER
EHentai = i18n.EHentai
Updater = i18n.Updater
