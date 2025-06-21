from PyQt5.QtCore import QObject
from qfluentwidgets import InfoBar, InfoBarPosition
from PyQt5.QtCore import Qt

from utils import conf
from utils.website import EHentaiKits
from GUI.browser_window import BrowserWindow
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components import CustomInfoBar
from assets import res


class PreprocessManager(QObject):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.task_manager = AsyncTaskManager(gui)

    def handle_choosebox_changed(self, index: int):
        match index:
            case 1:
                self._preprocess_manga_copy()
            case 2:
                self._preprocess_jm()
            case 4:
                self._preprocess_ehentai()
            case 5:
                self._preprocess_mangabz()
            case 6:
                self._preprocess_hitomi()

    def _preprocess_manga_copy(self):
        def manga_copy_task():
            # 1. 更新加密缓存
            return True

        def on_error(_):
            pass

        self.task_manager.execute_simple_task(
            task_func=manga_copy_task,
            success_callback=lambda _: self.gui.say("<br>✅ 拷贝预处理完成"), 
            show_error_info=False, error_callback=on_error,
            tooltip_title="更新copy2相关缓存", task_id="manga_copy_preprocess"
        )

    def _preprocess_jm(self):
        def jm_task():
            # 1. 更新域名缓存
            domain = self.gui.spiderUtils.get_domain()
            # 2. cookies处理？
            return True

        def on_success(_):
            if getattr(self.gui.spiderUtils, "inValidity", False):
                self.gui.say("<br>➖ 域名缓存处于有效期48小时内，跳过测试")
            else:
                self.gui.say("<br>✅ 已设置有效域名")

        def on_error(_):
            self.gui.disable_start(True)
            self.gui.say("<br>❌ 域名获取/测试失效，点击 rV按钮 > domainTool, 按指示操作")

        self.task_manager.execute_simple_task(
            task_func=jm_task,
            success_callback=on_success, show_error_info=False, error_callback=on_error,
            tooltip_title="更新jm域名缓存", task_id="jm_preprocess"
        )

    def _preprocess_ehentai(self):
        def ehentai_task():
            if not conf.cookies.get("ehentai"):
                raise ValueError("cookies_not_set")
            eh_kits = EHentaiKits(conf)
            if not eh_kits.test_index():
                raise RuntimeError("access_fail")
            BrowserWindow.eh_kits = eh_kits
            return True

        def on_error(error):
            self.gui.disable_start()
            error_msg = str(error)
            if "cookies_not_set" in error_msg:
                InfoBar.error(
                    title='', content=res.EHentai.COOKIES_NOT_SET,
                    orient=Qt.Horizontal, isClosable=True, position=InfoBarPosition.BOTTOM,
                    duration=-1, parent=self.gui.textBrowser
                )
            elif "access_fail" in error_msg:
                eh_kits = EHentaiKits(conf)
                CustomInfoBar.show('', res.EHentai.ACCESS_FAIL, self.gui.textBrowser,
                    eh_kits.index, eh_kits.name)

        self.task_manager.execute_simple_task(
            task_func=ehentai_task,
            success_callback=lambda _: self.gui.say("<br>✅ exhentai 访问检测通过"),
            show_error_info=False, error_callback=on_error,
            tooltip_title="exhentai 访问检测", task_id="ehentai_preprocess"
        )

    def _preprocess_mangabz(self):
        def mangabz_task():
            self.gui.spiderUtils = self.gui.spiderUtils(conf)
            if not self.gui.spiderUtils.test_index():
                raise RuntimeError(f"access_fail:{self.gui.spiderUtils.name}:{self.gui.spiderUtils.index}")
            return True

        def on_error(_):
            CustomInfoBar.show('', self.gui.res.ACCESS_FAIL, self.gui.textBrowser,
                    self.gui.spiderUtils.index, self.gui.spiderUtils.name)

        self.task_manager.execute_simple_task(
            task_func=mangabz_task,
            success_callback=lambda _: self.gui.say("<br>✅ mangabz 访问检测通过"),
            show_error_info=False, error_callback=on_error,
            tooltip_title="mangabz 访问检测", task_id="mangabz_preprocess"
        )

    def _preprocess_hitomi(self):
        def hitomi_task():
            self.gui.spiderUtils = self.gui.spiderUtils(conf)
            if not self.gui.spiderUtils.test_index():
                raise RuntimeError(f"access_fail:{self.gui.spiderUtils.name}:{self.gui.spiderUtils.index}")
            return True

        def on_error(error):
            CustomInfoBar.show('', self.gui.res.ACCESS_FAIL, self.gui.textBrowser,
                    self.gui.spiderUtils.index, self.gui.spiderUtils.name)

        self.task_manager.execute_simple_task(
            task_func=hitomi_task,
            success_callback=lambda _: self.gui.say("<br>✅ hitomi 访问检测通过"),
            error_callback=on_error,
            tooltip_title="hitomi 访问检测", task_id="hitomi_preprocess"
        )

    def cleanup(self):
        self.task_manager.cleanup()
