import os
import json
import importlib

import psutil
import httpx
from PyQt5.QtCore import Qt, QObject
from qfluentwidgets import InfoBar, InfoBarPosition, setTheme

from assets import res
from variables import PYPI_SOURCE, VER, AGGR_SEARCH_IDXES, CLIP_IDXES, CGS_DOC
from utils import conf, ori_path, exc_p, uv_exc, env
from utils.website import EHentaiKits, Cache
from GUI.browser_window import BrowserWindow
from GUI.manager import _UpdateLauncher
from GUI.manager.async_task import AsyncTaskManager, TaskConfig
from GUI.uic.qfluent.components import CustomInfoBar
from GUI.core.theme import setupTheme, theme_mgr


transport=dict(proxy=f"http://{conf.proxies[0]}",retries=2) if conf.proxies else dict(retries=2)
data_cli = httpx.Client(transport=httpx.HTTPTransport(**transport))


class PreprocessManager(QObject):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui
        self.show_err = conf.log_level.lower() == "debug"
        self.task_manager = AsyncTaskManager(gui)

    def handle_choosebox_changed(self, index: int):
        special = {
            1: self._preprocess_manga_copy,
            2: self._preprocess_jm,
            3: self._preprocess_wnacg,
            4: self._preprocess_ehentai,
            6: self._preprocess_hitomi,
            7: self._preprocess_kemono,
        }
        if handler:= special.get(index):
            handler()
        elif hasattr(self.gui.spiderUtils, 'test_index'):
            self._preprocess_test_index()

        if index in AGGR_SEARCH_IDXES:
            self._add_aggr_search()
        if index in CLIP_IDXES:
            self.gui.clipBtn.setEnabled(1)

    def _cache_hit(self) -> bool:
        cache = getattr(self.gui.spiderUtils, "cachef", None)
        return bool(cache and cache.flag != "new")

    def _say_cache_or(self, success_msg: str):
        if self._cache_hit():
            self.gui.say("<br>➖ 缓存处于有效期内，跳过测试")
        else:
            self.gui.say(success_msg)

    def _try_add_hitomi_tool(self):
        if hasattr(self.gui, 'toolWin'):
            self.gui.toolWin.addHitomiTool()

    def _preprocess_manga_copy(self):
        def manga_copy_task():
            # 1. 更新加密缓存
            key = self.gui.spiderUtils.get_aes_key()
            return True
        
        def on_success(_):
            self._say_cache_or("<br>✅ 拷贝预处理完成")

        def on_error(_):
            self.gui.disable_start()
            self.gui.say("<br>❌ 解密获取失败，内置重启再试下")

        self.task_manager.execute_simple_task(
            task_func=manga_copy_task,
            success_callback=on_success,
            show_error_info=self.show_err, error_callback=on_error,
            tooltip_title="更新copy2相关缓存", task_id="manga_copy_preprocess"
        )

    def _preprocess_jm(self):
        def task():
            # 1. 更新域名缓存
            domain = self.gui.spiderUtils.get_domain()
            # 2. cookies处理？
            return True

        def on_success(_):
            self._say_cache_or("<br>✅ 已设置有效域名")


        def on_error(_):
            self.gui.disable_start()
            self.gui.say("<br>❌ 域名获取/测试失效，按内置浏览器引导操作")
            self.gui.do_publish()

        self.task_manager.execute_simple_task(
            task_func=task,
            success_callback=on_success, show_error_info=self.show_err, error_callback=on_error,
            tooltip_title="更新域名缓存", task_id="domain_preprocess"
        )

    def _preprocess_ehentai(self):
        eh_kits = EHentaiKits(conf)
        def ehentai_task():
            if not conf.cookies.get("ehentai"):
                raise ValueError("cookies_not_set")
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
                CustomInfoBar.show('', res.EHentai.ACCESS_FAIL, self.gui.textBrowser,
                    eh_kits.index, eh_kits.name)

        self.task_manager.execute_simple_task(
            task_func=ehentai_task,
            success_callback=lambda _: self.gui.say("<br>✅ exhentai 访问检测通过"),
            show_error_info=self.show_err, error_callback=on_error,
            tooltip_title="exhentai 访问检测", task_id="ehentai_preprocess"
        )

    def _preprocess_test_index(self):
        name = self.gui.spiderUtils.name
        index = self.gui.spiderUtils.index

        def task():
            self.gui.sut = self.gui.spiderUtils(conf)
            if not self.gui.sut.test_index():
                raise RuntimeError(f"access_fail:{name}:{index}")
            return True

        def on_error(_):
            self.gui.disable_start()
            CustomInfoBar.show('', self.gui.res.ACCESS_FAIL, self.gui.textBrowser,
                    index, name)

        self.task_manager.execute_simple_task(
            task_func=task,
            success_callback=lambda _: self.gui.say(f"<br>✅ {name} 访问检测通过"),
            show_error_info=self.show_err, error_callback=on_error,
            tooltip_title=f"{name} 访问检测", task_id=f"{name}_preprocess"
        )

    def _add_aggr_search(self):
        if not hasattr(self.gui.toolWin, 'asInterface'):
            self.gui.toolWin.addAggrSearchView()

    def _preprocess_wnacg(self):
        if conf.proxies:
            self.gui.say("🔔 已设置代理，跳过域名缓存处理")
        else:
            self._preprocess_jm()

    def _preprocess_hitomi(self):
        def hitomi_check():
            self.gui.sut = self.gui.spiderUtils(conf)
            if not self.gui.sut.test_index():
                raise RuntimeError(f"test-nozomi fail:{self.gui.spiderUtils.name}: {self.gui.spiderUtils.test_nozomi}")
            return True

        def on_error(_):
            CustomInfoBar.show('', self.gui.res.ACCESS_FAIL, self.gui.textBrowser,
                    self.gui.spiderUtils.index, self.gui.spiderUtils.name)

        self.task_manager.execute_simple_task(
            task_func=hitomi_check,
            success_callback=lambda _: self.gui.say("<br>✅ hitomi 访问检测通过"),
            error_callback=on_error,
            tooltip_title="hitomi 访问检测", task_id="hitomi_preprocess"
        )
        
        HITOMI_DB_URLS = [
            "https://github.com/jasoneri/ComicGUISpider/releases/download/preset/hitomi.db",
            res.Vars.hitomiDb_tmp_url,  # locale-based fallback 
        ]

        def _download_hitomi_db(db_path):
            """Try multiple sources, atomic replace via .tmp"""
            tmp_path = db_path.with_suffix('.db.tmp')
            errors = []
            for url in HITOMI_DB_URLS:
                try:
                    with data_cli.stream("GET", url, follow_redirects=True, timeout=30) as resp:
                        resp.raise_for_status()
                        with open(tmp_path, 'wb') as f:
                            for chunk in resp.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                    os.replace(str(tmp_path), str(db_path))
                    return True
                except Exception as e:
                    tmp_path.unlink(missing_ok=True)
                    errors.append(f"{url}: {e}")
            raise RuntimeError(f"all download sources failed: {'; '.join(errors)}")

        hitomi_db_path = ori_path.joinpath("assets/hitomi.db")
        if not hitomi_db_path.exists():
            self.gui.say("⚠️ hitomi db not found, downloading...")

            def on_db_download_success(_):
                self.gui.say("<br>✅ hitomi db downloaded")
                self._try_add_hitomi_tool()

            self.task_manager.execute_simple_task(
                task_func=lambda: _download_hitomi_db(hitomi_db_path),
                success_callback=on_db_download_success,
                error_callback=lambda _: self.gui.say("<br>❌ hitomi-db download failed"),
                tooltip_title="hitomi-db downloading", task_id="hitomi_db"
            )
        else:
            self._try_add_hitomi_tool()

    def _preprocess_kemono(self):
        kemono_flag = {}
        
        def triggle_or_not(k, v):
            def run_scriptWin():
                self.gui.hide()
                from GUI.script import ScriptWindow
                scriptWin = ScriptWindow(self.gui)
                setupTheme(scriptWin.kemonoInterface)
                setTheme(theme_mgr.theme.c)
                scriptWin.show()
            kemono_flag[k] = v
            if "services" in kemono_flag and "dependencies" in kemono_flag:
                services_result = kemono_flag["services"]
                dependencies_result = kemono_flag["dependencies"]

                if dependencies_result is not True:
                    _UpdateLauncher(VER, script=True).run()
                    self.gui.close()
                    return
                if services_result is not True:
                    return
                if "data" not in kemono_flag:
                    _data_check()
            if len(kemono_flag) == 3 and all(v is True for v in kemono_flag.values()):
                run_scriptWin()

        def _services_check():
            def services_check():
                running_processes = {proc.info['name'].lower() for proc in psutil.process_iter(['name'])}
                required_services = {
                    'motrix': any('motrix' in name for name in running_processes),
                    'redis-server': any('redis-server' in name for name in running_processes)
                }
                missing_services = [name.title() for name, running in required_services.items() if not running]
                if missing_services:
                    raise RuntimeError(missing_services)
                return True

            def on_success(_):
                if isinstance(_, bool) and _:
                    self.gui.say("✅ 后台服务检测")
                triggle_or_not("services", _)

            def on_err(_):
                self.gui.say("❌ 后台服务检测")
                CustomInfoBar.show(
                    title="服务检测失败",
                    content="Redis 或 Motrix 服务未运行，点击指南查看`前置须知`，安装并运行相关服务",
                    parent=self.gui.textBrowser,
                    url=f"{CGS_DOC}/feat/script", url_name="脚本集指南"
                )
                triggle_or_not("services", False)

            self.task_manager.execute_simple_task(
                task_func=services_check,
                success_callback=on_success,
                error_callback=on_err, show_error_info=self.show_err, 
                tooltip_title="检测服务运行情况", task_id="services_check"
            )

        def _dependencies_check():
            def dependencies_check(progress_callback=None):
                pkgs = ("redis", "pandas")
                missing = []
                for pkg in pkgs:
                    try:
                        importlib.import_module(pkg)
                    except ImportError:
                        missing.append(pkg)
                if not missing:
                    return True
                return missing

            def on_dependencies_check_process(progress_msg):
                self.gui.say(progress_msg)

            def on_err(_):
                self.gui.say("❌ 额外依赖检测")
                CustomInfoBar.show(
                    title="依赖安装失败",
                    content="点击按钮，查看`前置须知`的'uv安装脚本集依赖命令'部分（彻底关闭CGS后执行）",
                    parent=self.gui.textBrowser,
                    url=f"{CGS_DOC}/feat/script", url_name="脚本集指南"
                )
                triggle_or_not("dependencies", False)

            def on_dependencies_success(_):
                if _ is True:
                    self.gui.say("✅ 额外依赖检测")
                triggle_or_not("dependencies", _)

            config = TaskConfig(
                task_func=dependencies_check,
                success_callback=on_dependencies_success,
                progress_callback=on_dependencies_check_process,
                error_callback=on_err, show_error_info=self.show_err,
                tooltip_title="检测额外依赖是否安装", tooltip_content="处理中...",
            )
            self.task_manager.execute_task("dependencies_check", config)

        def _data_check():
            def data_check(progress_callback=None):
                def emit_progress(msg):
                    if progress_callback:
                        progress_callback(msg)

                from utils.script.image.kemono import KemonoAuthor, headers, Api
                def download_kemono_data():
                    emit_progress("正在更新缓存数据...")
                    url = Api.creators_txt
                    try:
                        with data_cli.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as resp:
                            resp.raise_for_status()
                            content = b""
                            for chunk in resp.iter_bytes():
                                content += chunk
                        json_data = json.loads(content.decode('utf-8'))
                        author_dict = {}
                        for item in json_data:
                            author_id = item['id']
                            author = KemonoAuthor(
                                id=author_id, name=item['name'], service=item['service'],
                                updated=item['updated'], favorited=item['favorited']
                            )
                            author_dict[author_id] = author
                        return author_dict
                    except Exception as e:
                        raise type(e)(f"数据下载失败: {str(e)}")
                
                cache = Cache("kemono_data.pkl")
                data = cache.run(download_kemono_data, 240, write_in=True)
                return True

            def on_data_check_process(progress_msg):
                # 处理进度信息的回调
                self.gui.say(progress_msg)

            def on_data_check_success(_):
                if isinstance(_, bool) and _:
                    self.gui.say("✅ 数据缓存检测")
                triggle_or_not("data", bool(_))

            data_checkconfig = TaskConfig(
                task_func=data_check,
                success_callback=on_data_check_success,
                progress_callback=on_data_check_process,
                tooltip_title="检测数据是否已缓存", tooltip_content="处理中...",
            )
            self.task_manager.execute_task("data_check", data_checkconfig)

        _services_check()
        _dependencies_check()

    def cleanup(self):
        self.task_manager.cleanup()
