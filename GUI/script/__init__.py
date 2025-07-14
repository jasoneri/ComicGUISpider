import sys
import pathlib

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication, QFrame, QHBoxLayout, QSizePolicy, QCompleter, QFileDialog
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon

from qfluentwidgets import (
    NavigationItemPosition, FluentWindow,
    LineEdit, PrimaryPushButton,
    VBoxLayout, FluentIcon as FIF, StrongBodyLabel, InfoBar, InfoBarPosition,
    GroupHeaderCardWidget, PushButton
)

from utils import yaml, ori_path
from utils.script.image.kemono import conf
from GUI.script.kemono import KemonoInterface


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

        self.pathButton = PushButton("选择目录")
        self.pathButton.setFixedWidth(120)
        self.pathButton.clicked.connect(self._onSelectFolder)

        # 当前选择的路径
        config_data = getattr(conf, config_key, {}) if hasattr(conf, config_key) else {}
        self.current_path = config_data.get("sv_path", default_path)

        # 添加组件到分组中
        self.addGroup(FIF.VPN, "Cookie 设置", "获取方法: 登录后网站首页F12开控制台\n查cookies, 字段名为 `session`", self.cookiesEdit)
        self.pathCard = self.addGroup(FIF.DOWNLOAD, "存储路径", f"{self.current_path}", self.pathButton)

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


class NekohouseGroupCard(BaseServiceGroupCard):
    """Nekohouse配置组卡片"""
    def __init__(self, parent=None):
        super().__init__(parent, "Nekohouse", "nekohouse", "D:/pic/nekohouse")


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
        self.imgProxiesEdit.setPlaceholderText(_translate("SettingInterface", "example-of-v2rayN 127.0.0.1:10809"))
        completer = QCompleter(['127.0.0.1:10809'])
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.imgProxiesEdit.setCompleter(completer)
        self.imgProxiesEdit.setClearButtonEnabled(True)
        first_row.addWidget(proxies_label)
        first_row.addWidget(self.imgProxiesEdit)
        
        self.kemono_group_card = KemonoGroupCard(self)
        self.nekohouse_group_card = NekohouseGroupCard(self)

        # 第四行：保存按钮
        forth_row = QHBoxLayout()
        self.saveBtn = PrimaryPushButton(FIF.SAVE, "", self)
        self.saveBtn.clicked.connect(self.save_conf)
        forth_row.addWidget(self.saveBtn)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.main_layout.addLayout(first_row)
        self.main_layout.addWidget(self.kemono_group_card)
        self.main_layout.addWidget(self.nekohouse_group_card)
        self.main_layout.addItem(spacerItem)
        self.main_layout.addLayout(forth_row)

    def show_self(self):
        """加载配置文件内容到各个编辑框"""
        with open(conf.file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f.read())

        self.imgProxiesEdit.setText(','.join(config_data.get('proxies') or []))
        kemono_config = config_data.get('kemono', {})
        self.kemono_group_card.setCookieText(kemono_config.get('cookie', ''))
        self.kemono_group_card.setCurrentPath(kemono_config.get('sv_path', ''))
        nekohouse_config = config_data.get('nekohouse', {})
        self.nekohouse_group_card.setCookieText(nekohouse_config.get('cookie', ''))
        self.nekohouse_group_card.setCurrentPath(nekohouse_config.get('sv_path', ''))


    def save_conf(self):
        """保存配置到文件"""
        try:
            # 读取现有配置
            with open(conf.file, 'r', encoding='utf-8') as f:
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

            # 更新nekohouse配置
            if 'nekohouse' not in config_data:
                config_data['nekohouse'] = {}
            config_data['nekohouse']['cookie'] = self.nekohouse_group_card.getCookieText()
            config_data['nekohouse']['sv_path'] = self.nekohouse_group_card.getCurrentPath()
            config_data['nekohouse']['redis_key'] = 'nekohouse'  # 固定值

            # 更新conf对象属性，参考GUI\conf_dialog.py的save_conf方法
            conf.update(**config_data)

            InfoBar.success(
                title='', content="配置保存成功",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=2500, parent=self
            )
        except Exception as e:
            InfoBar.error(
                title='', content=f"配置保存失败: {str(e)}",
                orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                duration=8000, parent=self
            )


class ScriptWindow(FluentWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.gui = parent
        self.kemonoInterface = KemonoInterface(self)
        self.settingInterface = SettingInterface(self)

        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.kemonoInterface, ':/letter/k.png', 'Kemono')
        self.navigationInterface.addSeparator()
        self.addSubInterface(self.settingInterface, FIF.SETTING, 'Settings', NavigationItemPosition.BOTTOM)

    def initWindow(self):
        if self.gui:
            self.resize(self.gui.width(), self.gui.height())
        else:
            self.resize(750, 600)
        self.setWindowIcon(QIcon(':/CGS-logo.png'))
        self.setWindowTitle('CGS - ScriptTool')

        # 初始化设置界面的内容
        self.settingInterface.show_self()
        
    def closeEvent(self, event):
        event.accept()
        self.gui.close()

if __name__ == '__main__':
    import GUI.src.material_ct
    app = QApplication(sys.argv)
    w = ScriptWindow()
    w.show()
    app.exec()
