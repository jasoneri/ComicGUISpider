import sys
import pathlib
import os

from PySide6 import QtWidgets
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QSizePolicy, QCompleter, QFileDialog, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Qt, QCoreApplication, QSize
from PySide6.QtGui import QIcon
from utils import install_qfluentwidgets_notice_filter

install_qfluentwidgets_notice_filter()

from qfluentwidgets import (
    NavigationItemPosition, FluentWindow,
    LineEdit, PrimaryPushButton,
    VBoxLayout, FluentIcon as FIF, StrongBodyLabel, InfoBar, InfoBarPosition,
    GroupHeaderCardWidget, PushButton, SpinBox, ComboBox, RangeSettingCard
)

from assets import res
from utils import yaml, ori_path
from utils.config.qc import danbooru_cfg, cgs_cfg
from utils.script import conf as script_conf
from utils.script.image.danbooru.models import DanbooruRuntimeConfig
from GUI.core.doh_runtime import ScriptDoHStubRuntime
from GUI.uic.qfluent.components import DoHButtonController
from GUI.core.timer import safe_single_shot
from GUI.manager.async_task import summarize_error_message
from GUI.script.danbooru import DanbooruInterface
from GUI.script.kemono import KemonoInterface


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
        self.setTitle(f"{service_name} 配置")
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
        self.addGroup(
            FIF.FOLDER,
            script_res.danbooru_save_mode,
            script_res.danbooru_save_mode_desc,
            self.saveTypeBox,
        )
        self.addGroup(
            FIF.SPEED_HIGH,
            script_res.danbooru_download_concurrency,
            script_res.danbooru_download_concurrency_desc,
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


class SettingInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent_window = parent
        self.setObjectName("SettingInterface")
        self.setupUi()

    def setupUi(self):
        _translate = QCoreApplication.translate
        self.main_layout = VBoxLayout(self)

        # 第一行：代理设置
        first_row = QHBoxLayout()
        proxies_label = StrongBodyLabel("代理", self)
        self.imgProxiesEdit = LineEdit(self)
        self.imgProxiesEdit.setToolTip(_translate("SettingInterface", "proxies"))
        self.imgProxiesEdit.setPlaceholderText(_translate("SettingInterface", 
                                                          "example-of-v2rayN 127.0.0.1:10809"))
        completer = QCompleter(['127.0.0.1:10809'])
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.imgProxiesEdit.setCompleter(completer)
        self.imgProxiesEdit.setClearButtonEnabled(True)
        first_row.addWidget(proxies_label)
        first_row.addWidget(self.imgProxiesEdit)

        second_row = QHBoxLayout()
        self.dohBtn = PushButton("DoH", self)
        self.dohBtn.setMaximumSize(QSize(80, 16777215))
        second_row.addStretch()
        second_row.addWidget(self.dohBtn)
        self.dohController = DoHButtonController(
            self.dohBtn, parent=self, on_saved=self._save_doh_config,
        )
        
        self.kemono_group_card = KemonoGroupCard(self)
        self.danbooru_group_card = DanbooruGroupCard(self)

        # 第四行：保存按钮
        forth_row = QHBoxLayout()
        self.saveBtn = PrimaryPushButton(FIF.SAVE, "", self)
        self.saveBtn.clicked.connect(self.save_conf)
        forth_row.addWidget(self.saveBtn)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.main_layout.addLayout(first_row)
        self.main_layout.addLayout(second_row)
        self.main_layout.addWidget(self.kemono_group_card)
        self.main_layout.addWidget(self.danbooru_group_card)
        self.main_layout.addItem(spacerItem)
        self.main_layout.addLayout(forth_row)

    def show_self(self):
        """加载配置文件内容到各个编辑框"""
        with open(script_conf.file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f.read()) or {}

        self.imgProxiesEdit.setText(','.join(config_data.get('proxies') or []))
        kemono_config = config_data.get('kemono', {})
        self.kemono_group_card.setCookieText(kemono_config.get('cookie', ''))
        self.kemono_group_card.setCurrentPath(kemono_config.get('sv_path', ''))
        runtime_config = DanbooruRuntimeConfig.from_mapping(
            config_data.get('danbooru', {}),
            doh_url=cgs_cfg.get_doh_url(),
        )
        self.danbooru_group_card.setCurrentPath(runtime_config.save_path)
        self.danbooru_group_card.setSaveType(runtime_config.save_type)
        self.danbooru_group_card.setDownloadConcurrency(runtime_config.download_concurrency)

    def _gui_logger(self):
        return getattr(getattr(self.parent_window, "gui", None), "log", None)

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
        if hasattr(self.parent_window, "danbooruInterface"):
            self.parent_window.danbooruInterface.refresh_runtime_settings()
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

            script_conf.update(**config_data)
            if hasattr(self.parent_window, "danbooruInterface"):
                self.parent_window.danbooruInterface.refresh_runtime_settings()

            InfoBar.success(
                title='', content="配置保存成功",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=2500, parent=self
            )
        except Exception as e:
            self._show_save_error("配置保存失败", e)


class ScriptWindow(ScriptWindowBase):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        if OFFSCREEN_FLUENT_FALLBACK:
            self._setup_offscreen_shell()
        self.doh_stub_runtime = ScriptDoHStubRuntime(self)
        self.danbooruInterface = DanbooruInterface(self)
        self.kemonoInterface = KemonoInterface(self)
        self.settingInterface = SettingInterface(self)
        self.doh_stub_runtime.ensure_from_config()

        self.initNavigation()
        self.initWindow()
        safe_single_shot(0, self.doh_stub_runtime.flush_warning)

    def _setup_offscreen_shell(self):
        self.setObjectName("OffscreenScriptWindow")
        self.setStyleSheet(
            """
            QFrame#OffscreenScriptWindow {
                background: #f6f6f7;
            }
            """
        )
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
        self.stackedWidget.setCurrentWidget(widget)
        for current_widget, button in self._offscreen_nav_buttons.items():
            button.setChecked(current_widget is widget)

    def initNavigation(self):
        self.addSubInterface(self.danbooruInterface, ':/script/danbooru.svg', 'Danbooru')
        self.addSubInterface(self.kemonoInterface, ':/script/kemono.ico', 'Kemono')
        self.navigationInterface.addSeparator()
        self.addSubInterface(self.settingInterface, FIF.SETTING, 'Settings', NavigationItemPosition.BOTTOM)

    def addSubInterface(self, interface, icon, text, position=NavigationItemPosition.TOP):
        if OFFSCREEN_FLUENT_FALLBACK:
            return self._add_offscreen_subinterface(interface, text, position)
        return super().addSubInterface(interface, icon, text, position)

    def initWindow(self):
        if self.gui:
            self.resize(max(850, self.gui.width()), self.gui.height())
        else:
            self.resize(850, 600)
        self.setWindowIcon(QIcon(':/CGS-logo.png'))
        self.setWindowTitle('CGS - ScriptTool')

        # 初始化设置界面的内容
        self.settingInterface.show_self()
        
    def closeEvent(self, event):
        event.accept()
        self.danbooruInterface.image_viewer.hide()
        if self.gui is not None:
            safe_single_shot(10, self.gui.close)
        

if __name__ == '__main__':
    import GUI.src.material_ct
    app = QApplication(sys.argv)
    w = ScriptWindow()
    w.show()
    app.exec()
