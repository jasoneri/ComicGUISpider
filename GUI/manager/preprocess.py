import httpx
from PyQt5.QtCore import QObject
from qfluentwidgets import InfoBar, InfoBarPosition
from PyQt5.QtCore import Qt

from assets import res
from utils import conf, ori_path
from utils.website import EHentaiKits
from GUI.browser_window import BrowserWindow
from GUI.manager.async_task import AsyncTaskManager
from GUI.uic.qfluent.components import CustomInfoBar


class PreprocessManager(QObject):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.task_manager = AsyncTaskManager(gui)

    def handle_choosebox_changed(self, index: int):
        match index:
            case 1:
                self._preprocess_manga_copy()
            case 2 | 3:
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
            self.gui.spiderUtils.get_aes_key()
            return True
        
        def on_success(_):
            if getattr(self.gui.spiderUtils, "cachef") and self.gui.spiderUtils.cachef.flag != "new":
                self.gui.say("<br>➖ 缓存处于有效期内，跳过测试")
            else:
                self.gui.say("<br>✅ 拷贝预处理完成")

        def on_error(_):
            self.gui.disable_start()
            self.gui.say("<br>❌ 解密获取失败，点击 rV按钮 > statusTool > 更新拷贝")

        self.task_manager.execute_simple_task(
            task_func=manga_copy_task,
            success_callback=on_success,
            show_error_info=False, error_callback=on_error,
            tooltip_title="更新copy2相关缓存", task_id="manga_copy_preprocess"
        )

    def _preprocess_jm(self):
        def task():
            # 1. 更新域名缓存
            domain = self.gui.spiderUtils.get_domain()
            # 2. cookies处理？
            return True

        def on_success(_):
            if getattr(self.gui.spiderUtils, "cachef") and self.gui.spiderUtils.cachef.flag != "new":
                self.gui.say("<br>➖ 缓存处于有效期内，跳过测试")
            else:
                self.gui.say("<br>✅ 已设置有效域名")

        def on_error(_):
            self.gui.disable_start()
            self.gui.say("<br>❌ 域名获取/测试失效，点击 rV按钮 > domainTool, 按指示操作")

        self.task_manager.execute_simple_task(
            task_func=task,
            success_callback=on_success, show_error_info=False, error_callback=on_error,
            tooltip_title="更新域名缓存", task_id="domain_preprocess"
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
            self.gui.disable_start()
            CustomInfoBar.show('', self.gui.res.ACCESS_FAIL, self.gui.textBrowser,
                    self.gui.spiderUtils.index, self.gui.spiderUtils.name)

        self.task_manager.execute_simple_task(
            task_func=mangabz_task,
            success_callback=lambda _: self.gui.say("<br>✅ mangabz 访问检测通过"),
            show_error_info=False, error_callback=on_error,
            tooltip_title="mangabz 访问检测", task_id="mangabz_preprocess"
        )

    def _preprocess_hitomi(self):
        def hitomi_check():
            self.gui.spiderUtils = self.gui.spiderUtils(conf)
            if not self.gui.spiderUtils.test_index():
                raise RuntimeError(f"access_fail:{self.gui.spiderUtils.name}:{self.gui.spiderUtils.index}")
            return True

        def on_error(error):
            CustomInfoBar.show('', self.gui.res.ACCESS_FAIL, self.gui.textBrowser,
                    self.gui.spiderUtils.index, self.gui.spiderUtils.name)

        self.task_manager.execute_simple_task(
            task_func=hitomi_check,
            success_callback=lambda _: self.gui.say("<br>✅ hitomi 访问检测通过"),
            error_callback=on_error,
            tooltip_title="hitomi 访问检测", task_id="hitomi_preprocess"
        )

        def dl_db():
            with httpx.stream("GET", res.Vars.hitomiDb_tmp_url, follow_redirects=True) as resp:
                with open(hitomi_db_path, 'wb') as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)

        hitomi_db_path = ori_path.joinpath("assets/hitomi.db")
        if not hitomi_db_path.exists():
            self.gui.say("⚠️ hitomi db not found, ready to download..")
            def on_db_download_success(_):
                self.gui.say("<br>✅ hitomi db downloaded")
                if hasattr(self.gui, 'toolWin'):
                    self.gui.toolWin.addHitomiTool()

            self.task_manager.execute_simple_task(
                task_func=dl_db,
                success_callback=on_db_download_success,
                error_callback=lambda _: self.gui.say("<br>❌ hitomi-db failed"),
                tooltip_title="hitomi-db predownloading", task_id="hitomi_db"
            )

    def cleanup(self):
        self.task_manager.cleanup()
