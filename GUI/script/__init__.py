# ruff: noqa: E402
import contextlib
import sys
import pathlib
import os

from PySide6 import QtWidgets
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QFrame, QHBoxLayout, QSizePolicy,
    QCompleter, QFileDialog, QVBoxLayout, QStackedWidget, QWidget,
)
from PySide6.QtCore import Qt, QCoreApplication, QRect, QSize
from PySide6.QtGui import QIcon
from utils import install_qfluentwidgets_notice_filter

install_qfluentwidgets_notice_filter()

from qfluentwidgets import (
    NavigationItemPosition, FluentWindow,
    LineEdit, PasswordLineEdit, PrimaryPushButton,
    FluentIcon as FIF, StrongBodyLabel, InfoBar, InfoBarPosition,
    GroupHeaderCardWidget, PushButton, ScrollArea, SpinBox, ComboBox, RangeSettingCard
)

from assets import res
from utils import yaml, ori_path
from utils.config.qc import danbooru_cfg, cgs_cfg
from utils.script import conf as script_conf
from utils.script.image.danbooru.models import DanbooruRuntimeConfig
from GUI.core.doh_runtime import ScriptDoHStubRuntime
from GUI.core.exception_feedback import GuiExceptionFeedbackDispatcher, InfoBarExceptionPresenter
from GUI.uic.qfluent.components import DoHButtonController
from GUI.core.timer import safe_single_shot
from GUI.manager.async_task import summarize_error_message
from GUI.uic.qfluent.components.icons import CgsIcon


script_res = res.GUI.Script
uic_res = res.GUI.Uic


OFFSCREEN_FLUENT_FALLBACK = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
ScriptWindowBase = QFrame if OFFSCREEN_FLUENT_FALLBACK else FluentWindow
class _OffscreenNavigationInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OffscreenNavigationInterface")
        self.setFixedWidth(148)
        self.setStyleSheet(
            """
            QFrame#OffscreenNavigationInterface {
                background: #111111;
                border-right: 1px solid rgba(255, 255, 255, 0.12);
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)
        self._top_layout = QVBoxLayout()
        self._top_layout.setSpacing(8)
        self._bottom_layout = QVBoxLayout()
        self._bottom_layout.setSpacing(8)
        layout.addLayout(self._top_layout)
        layout.addStretch(1)
        layout.addLayout(self._bottom_layout)

    def add_button(self, button, bottom: bool = False):
        target_layout = self._bottom_layout if bottom else self._top_layout
        target_layout.addWidget(button)

    def addSeparator(self):
        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: rgba(255, 255, 255, 0.14); min-height: 1px; max-height: 1px; border: none;")
        self._top_layout.addWidget(separator)


class BaseServiceGroupCard(GroupHeaderCardWidget):
    """基础服务配置组卡片 - 高复用度的基类"""
    def __init__(self, parent=None, service_name="", config_key="", default_path=""):
        super().__init__(parent)
        self.setting_interface = parent
        self.service_name = service_name
        self.config_key = config_key
        self.setTitle(f"{service_name} Config")
        self.setBorderRadius(8)

        # 创建组件
        self.cookiesEdit = LineEdit()
        self.cookiesEdit.setPlaceholderText(f"{service_name} session cookie")
        self.cookiesEdit.setClearButtonEnabled(True)
        self.cookiesEdit.setMinimumWidth(400)

        self.pathButton = PushButton(uic_res.sv_path_desc_tip)
        self.pathButton.setFixedWidth(120)
        self.pathButton.clicked.connect(self._onSelectFolder)

        # 当前选择的路径
        config_data = getattr(script_conf, config_key, {}) if hasattr(script_conf, config_key) else {}
        self.current_path = config_data.get("sv_path", default_path)

        # 添加组件到分组中
        self.pathCard = self.addGroup(FIF.DOWNLOAD, uic_res.sv_path_desc, f"{self.current_path}", self.pathButton)
        self.addGroup(FIF.VPN, "Cookie 设置", "获取方法: 登录后网站首页F12开控制台\n查cookies, 字段名为 `session`", self.cookiesEdit)

    def _onSelectFolder(self):
        folder = QFileDialog.getExistingDirectory(self, f"选择{self.service_name}存储目录")
        if folder:
            wanted_p = pathlib.Path(folder)
            cgs_path = ori_path.parent if ori_path.parent.joinpath("scripts/CGS.py").exists() else ori_path
            cgs_flag = str(wanted_p).startswith(str(cgs_path))
            drive_flag = len(wanted_p.parts) == 1 and wanted_p.drive
            if cgs_flag or drive_flag:
                InfoBar.error(
                    title='', content="路径设置无效：不能设在盘符根或CGS相关目录内",
                    orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                    duration=5000, parent=self.setting_interface
                )
                return
            self.current_path = folder
            self.pathCard.setContent(self.current_path)
            self.setting_interface.saveBtn.click()

    def getCookieText(self):
        """获取Cookie文本"""
        return self.cookiesEdit.text().strip()

    def setCookieText(self, text):
        """设置Cookie文本"""
        self.cookiesEdit.setText(text)

    def getCurrentPath(self):
        """获取当前路径"""
        return self.current_path

    def setCurrentPath(self, path):
        """设置当前路径"""
        self.current_path = path


class KemonoGroupCard(BaseServiceGroupCard):
    """Kemono配置组卡片"""
    def __init__(self, parent=None):
        super().__init__(parent, "Kemono", "kemono", "D:/pic/kemono")


class DanbooruGroupCard(GroupHeaderCardWidget):
    SAVE_TYPE_OPTIONS = (
        ("danbooru_save_type_default", None),
        ("danbooru_save_type_search_tag", "search_tag"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setting_interface = parent

        self.setTitle("Danbooru Config")
        self.setBorderRadius(8)

        danbooru_conf = getattr(script_conf, "danbooru", {}) or {}
        self.current_path = danbooru_conf.get("save_path", "D:/pic/danbooru")

        self.downloadConcurrencyEdit = SpinBox(self)
        self.downloadConcurrencyEdit.setRange(1, 10)
        self.downloadConcurrencyEdit.setValue(int(danbooru_conf.get("download_concurrency", 3)))

        self.saveTypeBox = ComboBox(self)
        for text_key, value in self.SAVE_TYPE_OPTIONS:
            self.saveTypeBox.addItem(getattr(script_res, text_key), userData=value)
        self.setSaveType(danbooru_conf.get("save_type"))

        self.pathButton = PushButton(uic_res.sv_path_desc_tip)
        self.pathButton.setFixedWidth(120)
        self.pathButton.clicked.connect(self._onSelectFolder)

        self.pathCard = self.addGroup(FIF.DOWNLOAD, uic_res.sv_path_desc, self.current_path, self.pathButton)
        self.addGroup(CgsIcon.SV_TYPE, script_res.danbooru_save_mode, script_res.danbooru_save_mode_desc, self.saveTypeBox)
        self.addGroup(
            FIF.SPEED_HIGH, script_res.danbooru_download_concurrency, script_res.danbooru_download_concurrency_desc,
            self.downloadConcurrencyEdit,
        )
        self.viewRatioCard = RangeSettingCard(
            danbooru_cfg.view_ratio, FIF.ZOOM, 
            script_res.danbooru_view_ratio, script_res.danbooru_view_ratio_desc,
            self,
        )
        if self.groupWidgets:
            self.groupWidgets[-1].setSeparatorVisible(True)
        self.groupLayout.addWidget(self.viewRatioCard)

    def _onSelectFolder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 Danbooru 存储目录")
        if folder:
            wanted_p = pathlib.Path(folder)
            cgs_path = ori_path.parent if ori_path.parent.joinpath("scripts/CGS.py").exists() else ori_path
            cgs_flag = str(wanted_p).startswith(str(cgs_path))
            drive_flag = len(wanted_p.parts) == 1 and wanted_p.drive
            if cgs_flag or drive_flag:
                InfoBar.error(
                    title='', content="路径设置无效：不能设在盘符根或CGS相关目录内",
                    orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.TOP,
                    duration=5000, parent=self.setting_interface
                )
                return
            self.current_path = folder
            self.pathCard.setContent(self.current_path)
            self.setting_interface.saveBtn.click()

    def getCurrentPath(self):
        return self.current_path

    def setCurrentPath(self, path):
        self.current_path = path
        self.pathCard.setContent(path)

    def getDownloadConcurrency(self):
        return self.downloadConcurrencyEdit.value()

    def setDownloadConcurrency(self, concurrency):
        self.downloadConcurrencyEdit.setValue(int(concurrency or 3))

    def getSaveType(self):
        return self.saveTypeBox.currentData()

    def setSaveType(self, save_type):
        index = self.saveTypeBox.findData(save_type)
        self.saveTypeBox.setCurrentIndex(index if index >= 0 else 0)


class AiGroupCard(GroupHeaderCardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setting_interface = parent
        self.setTitle("AI Provider")
        self.setBorderRadius(8)

        self.urlEdit = LineEdit(self)
        self.urlEdit.setPlaceholderText("https://api.openai.com/v1")
        self.urlEdit.setClearButtonEnabled(True)
        self.urlEdit.setMinimumWidth(320)

        self.keyEdit = PasswordLineEdit(self)
        self.keyEdit.setPlaceholderText("api-key")
        self.keyEdit.setClearButtonEnabled(True)
        self.keyEdit.setMinimumWidth(320)

        self.modelEdit = LineEdit(self)
        self.modelEdit.setPlaceholderText("model name")
        self.modelEdit.setClearButtonEnabled(True)
        self.modelEdit.setMinimumWidth(240)

        self.addGroup(CgsIcon.URL, "Base URL", "OpenAI-compatible endpoint", self.urlEdit)
        self.addGroup(CgsIcon.KEY, "API Key", "Bearer token / api key", self.keyEdit)
        self.addGroup(FIF.ROBOT, "Model", "Chat model id", self.modelEdit)

    def set_provider(self, *, url: object = None, key: object = None, model: object = None):
        self.urlEdit.setText(str(url or ""))
        self.keyEdit.setText(str(key or ""))
        self.modelEdit.setText(str(model or ""))

    def get_provider_fields(self) -> dict:
        from utils.script.ai.kernel import AiProviderMgr

        return AiProviderMgr.normalize_fields(
            url=self.urlEdit.text(),
            key=self.keyEdit.text(),
            model=self.modelEdit.text(),
        )


class _SettingFillScrollArea(ScrollArea):
    """ScrollArea whose vertical sizeHint is 0 so parent layout can stretch it to fill remainder."""

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), 0)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(hint.width(), 0)


class SettingInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("SettingInterface")
        self.setupUi()

    def setupUi(self):
        _translate = QCoreApplication.translate
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # QVBoxLayout (not qfluent VBoxLayout): stretch factor must expand scroll above footer.
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.outer_layout.setSpacing(0)

        self.scroll_area = _SettingFillScrollArea(self)
        self.scroll_area.setObjectName("SettingInterfaceScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # content sizeHint must not inflate ScriptWindow min height (scriptWinRect owns geometry).
        self.scroll_area.setMinimumHeight(0)
        self.scroll_area.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        if hasattr(self.scroll_area, "enableTransparentBackground"):
            self.scroll_area.enableTransparentBackground()

        self.scroll_content = QWidget(self.scroll_area)
        self.scroll_content.setObjectName("SettingInterfaceScrollContent")
        self.scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.main_layout = QVBoxLayout(self.scroll_content)

        first_row = QHBoxLayout()
        proxies_label = StrongBodyLabel("代理/Proxy", self.scroll_content)
        self.imgProxiesEdit = LineEdit(self.scroll_content)
        self.imgProxiesEdit.setToolTip(_translate("SettingInterface", "proxies"))
        self.imgProxiesEdit.setPlaceholderText(_translate("SettingInterface", "example-of-v2rayN 127.0.0.1:10809"))
        completer = QCompleter(['127.0.0.1:10809'])
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.imgProxiesEdit.setCompleter(completer)
        self.imgProxiesEdit.setClearButtonEnabled(True)

        self.dohBtn = PushButton("DoH", self.scroll_content)
        self.dohBtn.setMaximumSize(QSize(80, 16777215))
        self.dohController = DoHButtonController(self.dohBtn, parent=self, on_saved=self._save_doh_config)
        first_row.addWidget(proxies_label)
        first_row.addWidget(self.imgProxiesEdit)
        first_row.addWidget(self.dohBtn)

        # Cards keep SettingInterface as parent so setting_interface/saveBtn wiring stays valid.
        self.kemono_group_card = KemonoGroupCard(self)
        self.danbooru_group_card = DanbooruGroupCard(self)
        self.ai_card = AiGroupCard(self)

        self.main_layout.addLayout(first_row)
        self.main_layout.addWidget(self.kemono_group_card)
        self.main_layout.addWidget(self.danbooru_group_card)
        self.main_layout.addWidget(self.ai_card)
        self.main_layout.addStretch(0)

        self.scroll_area.setWidget(self.scroll_content)

        # Save outside scroll: always pinned to SettingInterface bottom.
        self.footer = QWidget(self)
        self.footer.setObjectName("SettingInterfaceFooter")
        self.footer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.footer_row = QHBoxLayout(self.footer)
        self.footer_row.setContentsMargins(12, 8, 12, 12)
        self.saveBtn = PrimaryPushButton(FIF.SAVE, "", self.footer)
        self.saveBtn.clicked.connect(self.save_conf)
        self.footer_row.addWidget(self.saveBtn)

        self.outer_layout.addWidget(self.scroll_area, 1)
        self.outer_layout.addWidget(self.footer, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_scroll_area_height_to_parent()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_scroll_area_height_to_parent()

    def _sync_scroll_area_height_to_parent(self):
        """Parent-driven max height: scroll fills remainder above footer; min=0 keeps scriptWin shrinkable."""
        page_height = self.height()
        if page_height <= 0:
            return
        footer_height = self.footer.height() if self.footer.height() > 0 else self.footer.sizeHint().height()
        margins = self.outer_layout.contentsMargins()
        available_height = (
            page_height
            - footer_height
            - margins.top()
            - margins.bottom()
            - self.outer_layout.spacing()
        )
        if available_height < 0:
            available_height = 0
        self.scroll_area.setMinimumHeight(0)
        self.scroll_area.setMaximumHeight(available_height if available_height > 0 else 16777215)
        self.scroll_area.updateGeometry()
        self.outer_layout.activate()

    def show_self(self):
        """加载配置文件内容到各个编辑框"""
        with open(script_conf.file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f.read()) or {}

        self.imgProxiesEdit.setText(','.join(config_data.get('proxies') or []))
        kemono_config = config_data.get('kemono', {})
        self.kemono_group_card.setCookieText(kemono_config.get('cookie', ''))
        self.kemono_group_card.setCurrentPath(kemono_config.get('sv_path', ''))
        runtime_config = DanbooruRuntimeConfig.from_mapping(config_data.get('danbooru', {}), doh_url=cgs_cfg.doh.get_url())
        self.danbooru_group_card.setCurrentPath(runtime_config.save_path)
        self.danbooru_group_card.setSaveType(runtime_config.save_type)
        self.danbooru_group_card.setDownloadConcurrency(runtime_config.download_concurrency)
        from utils.script.ai.kernel import AiProviderMgr

        provider = AiProviderMgr(config_data.get("ai") or {}).provider
        self.ai_card.set_provider(url=provider.url, key=provider.key, model=provider.model)

    def _gui_logger(self):
        return self.parent_window.gui.log

    def _show_save_error(self, prefix: str, error: BaseException):
        logger = self._gui_logger()
        if logger is not None:
            logger.exception(f"[ScriptSettings] {prefix}")
        InfoBar.error(
            title='', content=f"{prefix}: {summarize_error_message(error)}",
            orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
            duration=8000, parent=self
        )

    def _save_doh_config(self, doh_url: str):
        danbooru = getattr(self.parent_window, "danbooruInterface", None)
        if danbooru is not None:
            danbooru.refresh_runtime_settings()
        if hasattr(self.parent_window, "doh_stub_runtime"):
            self.parent_window.doh_stub_runtime.ensure(doh_url)

    def save_conf(self):
        """保存配置到文件"""
        try:
            # 读取现有配置
            with open(script_conf.file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f.read()) or {}

            # 更新代理设置
            proxies_text = self.imgProxiesEdit.text().strip()
            if proxies_text:
                config_data['proxies'] = [p.strip() for p in proxies_text.split(',') if p.strip()]
            else:
                config_data['proxies'] = None

            # 更新kemono配置
            if 'kemono' not in config_data:
                config_data['kemono'] = {}
            config_data['kemono']['cookie'] = self.kemono_group_card.getCookieText()
            config_data['kemono']['sv_path'] = self.kemono_group_card.getCurrentPath()
            config_data['kemono']['redis_key'] = 'kemono'  # 固定值

            if 'danbooru' not in config_data:
                config_data['danbooru'] = {}
            config_data['danbooru']['save_path'] = self.danbooru_group_card.getCurrentPath()
            config_data['danbooru']['save_type'] = self.danbooru_group_card.getSaveType()
            config_data['danbooru']['download_concurrency'] = self.danbooru_group_card.getDownloadConcurrency()
            config_data['danbooru'].pop('doh_url', None)
            config_data['danbooru'].pop('redis_key', None)
            config_data['danbooru'].pop('page_size', None)

            config_data['ai'] = {
                "provider": self.ai_card.get_provider_fields(),
            }

            script_conf.update(**config_data)
            danbooru = getattr(self.parent_window, "danbooruInterface", None)
            if danbooru is not None:
                danbooru.refresh_runtime_settings()

            InfoBar.success(
                title='', content="配置保存成功",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=2500, parent=self
            )
        except Exception as e:
            self._show_save_error("配置保存失败", e)


class ScriptWindow(ScriptWindowBase):
    # Lazy interface factories: import+construct only when the nav entry is first needed.
    _INTERFACE_FACTORIES = {
        "danbooru": ("GUI.script.danbooru", "DanbooruInterface"),
        "kemono": ("GUI.script.kemono", "KemonoInterface"),
        "cbg": ("GUI.script.cbg", "CbgInterface"),
        "jsoneri": ("GUI.script.jsoneri", "JsoneriPalacesProbeInterface"),
        "settings": (None, "SettingInterface"),
    }

    def __init__(
        self,
        parent=None,
        *,
        script_entry_state: dict | None = None,
        feedback_dispatcher: GuiExceptionFeedbackDispatcher | None = None,
    ):
        super().__init__()
        self.gui = parent
        self.script_entry_state = script_entry_state or {}
        if OFFSCREEN_FLUENT_FALLBACK:
            self._setup_offscreen_shell()
        self._script_entry_specs: list[tuple[QFrame, bool]] = []
        self._mounted_keys: set[str] = set()
        self._feedback_dispatcher = feedback_dispatcher
        self._exception_feedback_scope = None
        self.doh_stub_runtime = ScriptDoHStubRuntime(self)
        self.danbooruInterface = None
        self.kemonoInterface = None
        self.cbgInterface = None
        self.jsoneriPalacesProbeInterface = None
        self.settingInterface = None
        self.doh_stub_runtime.ensure_from_config()

        self.initNavigation()
        self.initWindow()
        safe_single_shot(0, self.doh_stub_runtime.flush_warning)

    def _setup_offscreen_shell(self):
        self.setObjectName("OffscreenScriptWindow")
        self.setStyleSheet("QFrame#OffscreenScriptWindow { background: #f6f6f7; }")
        self._offscreen_nav_buttons = {}
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.navigationInterface = _OffscreenNavigationInterface(self)
        self.stackedWidget = QStackedWidget(self)
        self.main_layout.addWidget(self.navigationInterface)
        self.main_layout.addWidget(self.stackedWidget, 1)

    def _add_offscreen_subinterface(self, widget, text, position=None):
        button = PushButton(text, self.navigationInterface)
        button.setCheckable(True)
        button.setMinimumHeight(40)
        button.setStyleSheet(
            """
            PushButton {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: white;
                text-align: left;
                padding-left: 12px;
            }
            PushButton:checked {
                background: rgba(255, 255, 255, 0.14);
            }
            """
        )
        self.navigationInterface.add_button(button, bottom=position == NavigationItemPosition.BOTTOM)
        self.stackedWidget.addWidget(widget)
        self._offscreen_nav_buttons[widget] = button
        button.clicked.connect(lambda _=False, current_widget=widget: self._set_offscreen_current_widget(current_widget))
        if self.stackedWidget.count() == 1:
            self._set_offscreen_current_widget(widget)
        return widget

    def _set_offscreen_current_widget(self, widget):
        key = getattr(widget, "_script_lazy_key", None)
        if key is not None and key not in self._mounted_keys:
            widget = self._materialize_interface(key)
        self.stackedWidget.setCurrentWidget(widget)
        for current_widget, button in self._offscreen_nav_buttons.items():
            button.setChecked(current_widget is widget)

    def initNavigation(self):
        self._deferred_nav: dict[str, tuple] = {}
        self._stub_by_key: dict[str, QFrame] = {}
        entries = (
            ("danbooru", "danbooru_visible", ":/script/danbooru.svg", "Danbooru", NavigationItemPosition.TOP, False),
            ("kemono", "kemono_visible", ":/script/kemono.ico", "Kemono", NavigationItemPosition.TOP, False),
            ("cbg", "cbg_visible", ":/script/cbg.svg", "Cbg", NavigationItemPosition.TOP, True),
            ("jsoneri", "jsoneri_palaces_probe_visible", FIF.CLOUD, "jsoneriPalacesProbe", NavigationItemPosition.TOP, True),
        )
        first_key = None
        for key, visibility_key, icon, text, position, show_in_pure_mode in entries:
            if not self._script_entry_visible(visibility_key):
                continue
            self._script_entry_specs.append((key, show_in_pure_mode))
            if first_key is None:
                first_key = key
                interface = self._materialize_interface(key)
                self.addSubInterface(interface, icon, text, position)
            else:
                self._add_lazy_nav_entry(key, icon, text, position)

        if self._script_entry_visible("settings_visible"):
            self.navigationInterface.addSeparator()
            self._script_entry_specs.append(("settings", True))
            if first_key is None:
                interface = self._materialize_interface("settings")
                self.addSubInterface(interface, FIF.SETTING, "Settings", NavigationItemPosition.BOTTOM)
            else:
                self._add_lazy_nav_entry("settings", FIF.SETTING, "Settings", NavigationItemPosition.BOTTOM)

        if not OFFSCREEN_FLUENT_FALLBACK and hasattr(self, "stackedWidget"):
            self.stackedWidget.currentChanged.connect(self._on_stacked_current_changed)

    def _attr_name_for_key(self, key: str) -> str:
        return {
            "danbooru": "danbooruInterface",
            "kemono": "kemonoInterface",
            "cbg": "cbgInterface",
            "jsoneri": "jsoneriPalacesProbeInterface",
            "settings": "settingInterface",
        }[key]

    def _add_lazy_nav_entry(self, key: str, icon, text: str, position):
        self._deferred_nav[key] = (icon, text, position)
        stub = QFrame(self)
        stub.setObjectName(f"ScriptDeferredStub_{key}")
        stub._script_lazy_key = key  # type: ignore[attr-defined]
        self._stub_by_key[key] = stub
        self.addSubInterface(stub, icon, text, position)

    def _materialize_interface(self, key: str):
        if key in self._mounted_keys:
            return getattr(self, self._attr_name_for_key(key))
        module_path, class_name = self._INTERFACE_FACTORIES[key]
        if module_path is None:
            interface_cls = SettingInterface
        else:
            import importlib

            module = importlib.import_module(module_path)
            interface_cls = getattr(module, class_name)
        interface = interface_cls(self)
        attr = self._attr_name_for_key(key)
        setattr(self, attr, interface)
        self._mounted_keys.add(key)

        stub = self._stub_by_key.pop(key, None)
        if stub is not None:
            self._replace_nav_stub(key, stub, interface)
        if key == "settings":
            interface.show_self()
        if key == "danbooru" and self._feedback_dispatcher is not None and self._exception_feedback_scope is None:
            self._exception_feedback_scope = self._feedback_dispatcher.register_scope(
                owner=self,
                surfaces=(interface.image_viewer,),
                presenter=InfoBarExceptionPresenter(),
            )
        return interface

    def _replace_nav_stub(self, key: str, stub: QFrame, interface: QFrame):
        if OFFSCREEN_FLUENT_FALLBACK:
            index = self.stackedWidget.indexOf(stub)
            if index >= 0:
                was_current = self.stackedWidget.currentWidget() is stub
                self.stackedWidget.removeWidget(stub)
                self.stackedWidget.insertWidget(index, interface)
                button = self._offscreen_nav_buttons.pop(stub, None)
                if button is not None:
                    self._offscreen_nav_buttons[interface] = button
                    with contextlib.suppress(TypeError, RuntimeError):
                        button.clicked.disconnect()
                    button.clicked.connect(
                        lambda _=False, current_widget=interface: self._set_offscreen_current_widget(current_widget)
                    )
                if was_current:
                    self.stackedWidget.setCurrentWidget(interface)
        else:
            icon, text, position = self._deferred_nav.get(key, (FIF.APPLICATION, key, NavigationItemPosition.TOP))
            was_current = getattr(self, "stackedWidget", None) is not None and self.stackedWidget.currentWidget() is stub
            with contextlib.suppress(Exception):
                self.navigationInterface.removeWidget(stub.objectName())
            self.addSubInterface(interface, icon, text, position)
            if was_current:
                self.switchTo(interface)
        stub.deleteLater()

    def _on_stacked_current_changed(self, index: int):
        if index < 0 or not hasattr(self, "stackedWidget"):
            return
        widget = self.stackedWidget.widget(index)
        key = getattr(widget, "_script_lazy_key", None)
        if key is None or key in self._mounted_keys:
            return
        interface = self._materialize_interface(key)
        self.switchTo(interface)

    def _script_entry_visible(self, visibility_key: str) -> bool:
        return bool(self.script_entry_state.get(visibility_key, True))

    def apply_pure_entry_mode(self):
        for key, show_in_pure_mode in self._script_entry_specs:
            if show_in_pure_mode:
                continue
            interface = getattr(self, self._attr_name_for_key(key), None)
            stub = self._stub_by_key.get(key)
            target = interface or stub
            if target is None:
                continue
            if OFFSCREEN_FLUENT_FALLBACK:
                button = self._offscreen_nav_buttons.get(target)
                if button is not None:
                    button.hide()
            else:
                with contextlib.suppress(Exception):
                    self.navigationInterface.removeWidget(target.objectName())

        cbg = self._materialize_interface("cbg")
        if OFFSCREEN_FLUENT_FALLBACK:
            self._set_offscreen_current_widget(cbg)
        else:
            self.switchTo(cbg)

    def addSubInterface(self, interface, icon, text, position=NavigationItemPosition.TOP):
        if OFFSCREEN_FLUENT_FALLBACK:
            return self._add_offscreen_subinterface(interface, text, position)
        return super().addSubInterface(interface, icon, text, position)

    @staticmethod
    def _normalized_window_rect(x: int, y: int, width: int, height: int) -> QRect:
        """Keep restored geometry usable when a prior monitor was disconnected."""
        min_width, min_height = 640, 420
        width = max(min_width, int(width))
        height = max(min_height, int(height))
        proposed = QRect(int(x), int(y), width, height)
        screens = QApplication.screens()
        if not screens:
            return proposed

        def _visible_enough(rect: QRect) -> bool:
            for screen in screens:
                intersection = screen.availableGeometry().intersected(rect)
                # Require a usable title-bar / content strip so taskbar-only ghosts fail.
                if intersection.width() >= min(120, rect.width()) and intersection.height() >= 48:
                    return True
            return False

        if _visible_enough(proposed):
            return proposed

        primary = QApplication.primaryScreen() or screens[0]
        available = primary.availableGeometry()
        fitted_width = min(width, available.width())
        fitted_height = min(height, available.height())
        centered = QRect(
            available.x() + max(0, (available.width() - fitted_width) // 2),
            available.y() + max(0, (available.height() - fitted_height) // 2),
            fitted_width,
            fitted_height,
        )
        return centered

    def initWindow(self):
        saved_rect = cgs_cfg.scriptWinRect.value
        if saved_rect and len(saved_rect) >= 4:
            x, y, width, height = (int(value) for value in saved_rect[:4])
            geometry = self._normalized_window_rect(x, y, width, height)
            if geometry.x() != x or geometry.y() != y or geometry.width() != width or geometry.height() != height:
                gui_logger = getattr(self.gui, "log", None) if self.gui is not None else None
                if gui_logger is not None:
                    gui_logger.warning(
                        f"[ScriptWindow] restored geometry off-screen or invalid "
                        f"saved={[x, y, width, height]} -> applied="
                        f"[{geometry.x()}, {geometry.y()}, {geometry.width()}, {geometry.height()}]"
                    )
            self.setGeometry(geometry)
        elif self.gui:
            self.resize(max(850, self.gui.width()), self.gui.height())
        else:
            self.resize(850, 600)
        self.setWindowIcon(QIcon(':/CGS-logo.png'))
        self.setWindowTitle('CGS - ScriptTool')
        if self.settingInterface is not None:
            self.settingInterface.show_self()

    def server_mode_switch_blockers(self) -> list[str]:
        blockers = []
        for interface in (self.danbooruInterface, self.kemonoInterface, self.cbgInterface):
            if interface is None:
                continue
            blockers.extend(interface.server_mode_switch_blockers())
        return list(dict.fromkeys(blockers))

    def closeEvent(self, event):
        event.accept()
        if self._exception_feedback_scope is not None:
            self._exception_feedback_scope.close()
            self._exception_feedback_scope = None
        geometry = self._normalized_window_rect(self.x(), self.y(), self.width(), self.height())
        # Persist only a screen-safe rect so a disconnected monitor cannot trap the next open.
        cgs_cfg.scriptWinRect.value = [geometry.x(), geometry.y(), geometry.width(), geometry.height()]
        cgs_cfg.save()
        if self.danbooruInterface is not None:
            self.danbooruInterface.image_viewer.hide()
        if self.jsoneriPalacesProbeInterface is not None:
            self.jsoneriPalacesProbeInterface.close_service_window()
        if (
            self.gui is not None
            and not getattr(self.gui, "_closing", False)
            and not getattr(self.gui, "server_mode_switch_requested", False)
        ):
            safe_single_shot(10, self.gui.close)


if __name__ == '__main__':
    import GUI.src.material_ct
    app = QApplication(sys.argv)
    w = ScriptWindow()
    w.show()
    app.exec()
