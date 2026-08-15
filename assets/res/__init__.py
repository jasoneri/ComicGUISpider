#!/usr/bin/python
# -*- coding: utf-8 -*-
import gettext
import pathlib
import hashlib
import types

from PySide6.QtCore import QLocale

from assets.res.transfer import main as translation_compile

"""usage of `<br>`：
    1. 一行话禁止加 `br` ，换行在 `self.say()` 前解决;
    2. 多行的一段话可在最后加 `br` ，禁止在段落起始处加 `br`
    
    1. forbid the use of `br` in one line, solve line break before `self.say()`;
    2. add `br` at the end of a paragraph with multiple lines, forbid the use of `br` at the beginning of a paragraph
"""

_path = pathlib.Path(__file__).parent
lang = None
_ = None
i18n = None
Vars = None
GUI = None
Terms = None
SPIDER = None
EHentai = None
Updater = None


def getUserLanguage():
    sys_lang = QLocale.system().name()
    if _path.joinpath(f'locale/{sys_lang}.yml').exists():
        return sys_lang
    return 'en_US'


lang = getUserLanguage()


def is_compiled(current_lang):
    mo_path = _path.joinpath(f'locale/{current_lang}/LC_MESSAGES/res.mo')
    hash_path = _path.joinpath(f'locale/{current_lang}.hash')
    yml_path = _path.joinpath(f'locale/{current_lang}.yml')
    if not (mo_path.exists() and hash_path.exists()):
        return False
    with open(hash_path, 'r', encoding='utf-8') as f:
        return hashlib.sha256(yml_path.read_bytes()).hexdigest() == f.read()


class TranslationNamespace(str):
    """gettext-backed attribute path (e.g. res.GUI.Uic.menu_show_completer).

    Contract (stable since locale easily / must not regress):
    - Hit: return plain translated ``str``.
    - Miss: gettext returns the msgid; we still return a ``TranslationNamespace``
      so nested paths keep working (``GUI.Uic.xxx``), **and** the object itself
      is a ``str`` (the msgid). Call sites may pass it to ``QObject.tr`` / menus
      without TypeError — missing yml keys degrade to raw key text, not crash.

    Historically this was ``SimpleNamespace`` and miss returned a non-str object;
    that only exploded once GUI started doing ``widget.tr(self.res.some_new_key)``
    on chooseBox / search context menu (C2 online-fav path).
    """

    def __new__(cls, prefix: str):
        return str.__new__(cls, str(prefix or ""))

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        # ``self`` is already the dotted prefix string.
        nested_prefix = f"{self}.{name}" if self else name
        value = _(nested_prefix)
        if value == nested_prefix:
            return TranslationNamespace(nested_prefix)
        return value


# 自动创建所有翻译命名空间
def create_translation_namespaces():
    modules = {}
    
    # 顶级命名空间 (如 Vars, GUI, Updater)
    for module_name in ['Vars', 'GUI', 'Terms', 'Updater', 'SPIDER', 'EHentai']:
        modules[module_name] = TranslationNamespace(module_name)
    return types.SimpleNamespace(**modules)


def set_language(new_lang: str):
    """
    设置并加载新的语言翻译。
    这个函数会重新编译（如果需要），加载翻译文件，并更新所有模块级变量。
    """
    global lang, _, i18n, Vars, GUI, Terms, SPIDER, EHentai, Updater

    lang = new_lang
    if not is_compiled(lang):
        translation_compile(_path, lang)

    gettext.bindtextdomain('res', str(_path / 'locale'))
    gettext.textdomain('res')
    try:
        _translation = gettext.translation('res', str(_path / 'locale'), languages=[lang], fallback=False)
        _ = _translation.gettext
    except FileNotFoundError as e:
        print(str(e))
        _ = gettext.gettext

    i18n = create_translation_namespaces()

    Vars = i18n.Vars
    GUI = i18n.GUI
    Terms = i18n.Terms
    SPIDER = i18n.SPIDER
    EHentai = i18n.EHentai
    Updater = i18n.Updater


initial_lang = getUserLanguage()
set_language(initial_lang)
