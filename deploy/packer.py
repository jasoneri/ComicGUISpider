#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code packer
env-python: developer

thanks mengdeer589/PythonSizeCruncher
"""
import json
import os
import shutil
import pathlib
import stat
import datetime
import zipfile
from itertools import chain

from pydos2unix import dos2unix
import httpx
import py7zr

from tqdm import tqdm
from loguru import logger
from github import Github, Auth

# import github.Requester  # REMARK(2024-08-08): modified in package: HTTPSRequestsConnectionClass.session.proxies


path = pathlib.Path(__file__).parent
api_github = "https://api.github.com"
github_token = "**create token by your github account**"
proxies = {"https://": f"http://127.0.0.1:10809"}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Origin": "https://github.com",
    "Connection": "keep-alive",
    "Referer": "https://github.com/",
    "Priority": "u=0",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "TE": "trailers"
}
preset = {
    "python": ["api-ms-win-core", "base_library.zip", ".tcl", "tclIndex", "MSVCP140.dll", "cacert.pem", "cp936.enc",
               "__init__", "python.exe", "pythonw.exe", "VCRUNTIME140_1.dll"],
    "matplotlib": ["matplotlibrc", ".load-order", "matplotlib.svg"], "request": ["msgcat-1.6.1.tm"],
    "plotly": ["plotly.json", "plotly.min.js", "package_data\\templates"], "pyecharts": ["pyecharts"],
    "pyqtwebengine": ["QtWebEngineProcess.exe", "icudtl.dat", "qtwebengine_devtools_resources.pak",
                      "qtwebengine_resources", "qt.conf"], "streamlit": ["streamlit\\static"],
    "trame_vtk": ["static_viewer.html"], "python-docx": ["docx\\templates"], "python-pptx": ["pptx\\templates"],
    "scrapy": ["mime.types"]}


features_fix_stable = """
## 🎁 Features

## 🐞 Fix
"""


features_fix_preview = """
## 🎁 Features
🔳 为命令行Cli增加简易GUI  

## 🐞 Fix
✅ 序号输入扩展：输入框支持单个负数，例`-3`表示选择倒数三个（不影响已有输入规则）  
✅ ✨兼容 `去重样式提示` & `子任务条` 至剪贴板预览窗口中  
🔳 修正`子任务条`在某些场景不起效的情况     
"""


class ReleasesDesc:
    stable = f"""{features_fix_stable}

---

<details>
<summary>（❗️新用户必看）开箱即用说明 👈点击展开</summary>

### ⚡️下载
window系统下载`CGS.7z`，macOS系统下载`CGS-macOS.7z`  
下载慢的话，可右键复制下载链接到 [github资源加速](https://github.akams.cn/) 网站进行下载

### 🚀运行
win系统解压后双击运行 `CGS.exe`  
mac系统则需先阅读解压后的`desc_macOS.html`（mac专用的初次使用指引）

### 📢更新
推荐使用内置的`CGS-更新`  
更新后窗口显示`更新完毕`才算更新成功，闪退或错误提示是失败，失败可尝试删除`scripts/version`文件再运行

> ⚠️使用绿色包覆盖旧版本软件的话，请备份配置文件 `scripts/conf.yml`与`scripts/record.db` ⚠️

### 💻macOS app说明
macOS由于认证签名收费，app初次打开会有限制，正确操作如下
```
1. 对任一app右键打开，报错不要丢垃圾篓，直接关闭
2. 再对同一app右键打开，此时弹出窗口有打开选项，能打开了
3. 后续就能双击打开，不用右键打开了
```
</details>

---
遇到问题 提issue 或 [回到项目主页](https://github.com/jasoneri/ComicGUISpider) 下方找群进群询问  
> ⚠️解压的软件路径需纯英文/英标（含中文会导致QT错误等闪退）
"""


class Proj:
    proj = "CGS"
    name = "ComicGUISpider"
    github_author = "jasoneri"

    def __repr__(self):
        return self.proj


class Clean:
    """aim at runtime like site-packages"""

    @staticmethod
    def clean_packages():
        """clean site-packages"""
        package_p = path.joinpath('site-packages')
        for p in tqdm(package_p.glob("[psw][ieh][pte]*")):  # pip, set-tools, wheel, not need
            shutil.rmtree(str(p), ignore_errors=True)

    @staticmethod
    def fit():
        """execute this script, and let project work fully with package as much as possible"""
        if not path.joinpath("fit.py").exists():
            script_url = "https://jsd.vxo.im/gh/mengdeer589/PythonSizeCruncher@main/main.py"
            with httpx.Client(headers=headers, proxies=proxies) as sess:
                r = sess.get(script_url)
                with open(path.joinpath("fit.py"), 'w', encoding='utf-8') as f:
                    f.write(r.text.replace('self.wm_iconbitmap', '...  # self.wm_iconbitmap').replace('\r', ''))
        with open(path.joinpath('white_files.json'), 'w', encoding='utf-8') as f:
            json.dump(preset, f, ensure_ascii=False)
        error_code = os.system(f"cd {path} && python fit.py")

    @staticmethod
    def end_work(*specified: iter):
        def delete(func, _path, execinfo):
            os.chmod(_path, stat.S_IWUSR)
            func(_path)

        waiting = chain(*specified) if specified else \
            ("site-packages_new", "fit.py", "white_files.json",
             "site-packages_文件移动清单.txt", "scripts/.git")
        for p in tqdm(waiting):
            _p = path.joinpath(p)
            if _p.exists():
                shutil.rmtree(_p, onerror=delete) if _p.is_dir() else os.remove(_p)


class Packer(Proj):
    _proj = Proj.proj
    executor = path.parent.joinpath(r'Bat_To_Exe_Converter\Bat_To_Exe_Converter.exe')
    zip_file = path.joinpath(f'{_proj}.7z')
    preset_zip_file = path.joinpath(f'{_proj}_preset.7z')

    def __init__(self, default_specified: tuple):
        self.default_specified = default_specified

    @classmethod
    def bat_to_exe(cls):
        """最好只做一次，减少指定脚本的修改次数/生成 从而减少引发的风险"""
        def _do(bat_file, exe_file, icon, *args):
            args_str = " ".join(args)
            command = f"cd {path} && {cls.executor} /bat {bat_file} /exe {exe_file} /icon {icon} /x64 {args_str}"
            error_code = os.system(command)
            if error_code:  # Unreliable, need raise error make next step run correctly
                raise OSError(f"[ fail - packup {bat_file}], error_code: {error_code}")
            else:
                logger.info(f"[ success {bat_file} ]")

        # 主运行使用 PyStand 壳，不再重复造exe了，容易被杀软误杀
        # _do(path.joinpath(rf"scripts/deploy/launcher/update.bat"), path.joinpath(rf"{proj}-更新.exe"),
        #     path.joinpath(rf"scripts/assets/{proj}.ico"))
        _do(path.joinpath(rf"scripts/deploy/launcher/update.bat"), path.joinpath(rf"{cls._proj}-使用说明.exe"),
            path.joinpath(rf"scripts/assets/icon.png"))
        # exe生成后需要扔到 https://habo.qq.com/ 做检测，必须是`未发现风险`

    def packup(self, runtime_init=False):
        zip_file = self.zip_file
        specified = self.default_specified
        mode = "a"
        if runtime_init:
            # {proj}_preset.7z: only include runtime and site-packages. If env changed, re-packup it
            if self.preset_zip_file.exists():
                logger.debug(f"[ preset_zip_file exists ] run normal packup")
                logger.debug(f"[ if need init ] delete '{self.preset_zip_file}' manually later")
                return self.packup()
            zip_file = self.preset_zip_file
            specified = ('runtime', 'site-packages', '_pystand_static.int',
                         f'{self._proj}.exe', f'{self._proj}-更新.exe', f'{self._proj}-使用说明.exe')
            mode = "w"
        else:
            shutil.copy(self.preset_zip_file, self.zip_file)
        with py7zr.SevenZipFile(zip_file, mode, filters=[{"id": py7zr.FILTER_LZMA2}]) as zip_f:
            for file in tqdm(tuple(specified)):
                if path.joinpath(file).exists():
                    zip_f.writeall(file)
        if not self.zip_file.exists():
            self.packup()

    @staticmethod
    def upload(zip_file):
        date_now = datetime.datetime.now().strftime("%Y%m%d")
        repo = Proj.name
        if github_token.startswith("**create"):
            raise ValueError("[ you forget to replace your github token ] ")
        auth = Auth.Token(github_token)
        g = Github(auth=auth)
        user = g.get_user()
        release = user.get_repo(repo).get_latest_release()
        # delete asset
        """github note:
        If you upload an asset with the same filename as another uploaded asset,
        you'll receive an error and must delete the old file before you can re-upload the new asset."""
        _asset = list(filter(lambda x: x.name == zip_file, release.assets))
        if _asset:
            _asset[0].delete_asset()
        # upload asset
        release.upload_asset(str(path.joinpath(zip_file)), name=zip_file)
        # update release
        text = ReleasesDesc.preview
        release.update_release(name=f"{date_now} - v1.6.3", message=text)


class PackerMacOS(Packer):
    _proj = f"{Proj.proj}-macOS"
    zip_file = path.joinpath(f'{_proj}.7z')
    preset_zip_file = path.joinpath(f'{_proj}_preset.7z')
    scripts_path = "CGS.app/Contents/Resources/scripts"

    def __init__(self, default_specified=None):
        super().__init__(default_specified)

    def pre_packup(self):
        """ 1。预处理CGS.app的结构
            2. dos2unix处理项目文本文件"""
        mac_7z_p = path.joinpath(self.scripts_path.rsplit("/", maxsplit=1)[0])
        mac_7z_p.mkdir(parents=True, exist_ok=True)
        mac_scripts_path = mac_7z_p.joinpath("scripts")
        if mac_scripts_path.exists():
            shutil.rmtree(mac_scripts_path, ignore_errors=True)
        shutil.move(path.joinpath(Proj.name), mac_scripts_path)

        targets = [
            mac_scripts_path.rglob("*.bash"), mac_scripts_path.rglob("*.md"), mac_scripts_path.rglob("*.py"),
            mac_scripts_path.rglob("*.json"), mac_scripts_path.rglob("*.yml"), mac_scripts_path.rglob("*.html"),
        ]
        for _p in tqdm(chain(*targets)):
            with open(_p, "rb+") as fp:
                buffer = dos2unix(fp)
                fp.seek(0)
                fp.truncate()
                fp.write(buffer)

    def packup(self, runtime_init=False):
        self.pre_packup()
        zip_file = self.zip_file
        specified = (self.scripts_path,)
        mode = "a"
        shutil.copy(self.preset_zip_file, self.zip_file)
        with py7zr.SevenZipFile(zip_file, mode, filters=[{"id": py7zr.FILTER_LZMA2}]) as zip_f:
            for file in tqdm(tuple(specified)):
                if path.joinpath(file).exists():
                    zip_f.writeall(path.joinpath(file), arcname=file)
        if not self.zip_file.exists():
            self.packup()


def clean():
    """almost run few times in upfront"""
    Clean.clean_packages()
    Clean.fit()
    Clean.end_work()


def env_supplement():
    manifest = [  # it will change, but user no need care it
        "site-packages/execjs/runtime_names.py",
        "site-packages/execjs/_abstract_runtime.py",
        "site-packages/execjs/_abstract_runtime_context.py",
        "site-packages/execjs/_exceptions.py",
        "site-packages/execjs/_external_runtime.py",
        "site-packages/execjs/_json2.py",
        "site-packages/execjs/_misc.py",
        "site-packages/execjs/_pyv8runtime.py",
        "site-packages/execjs/_runner_sources.py",
        "site-packages/execjs/_runtimes.py",
        "site-packages/execjs/__init__.py",
        "site-packages/execjs/__main__.py"
    ]
    zip_file = path.joinpath(f'env_supplement0930.zip')
    with zipfile.ZipFile(zip_file, 'w') as zip_f:
        for file in tqdm(tuple(manifest)):
            if path.joinpath(file).exists():
                zip_f.write(file)
    ...


def common_packup():
    # # clean()
    # Clean.end_work(path.joinpath("scripts").rglob("__pycache__"), path.joinpath("site-packages").rglob("__pycache__"),
    #                (path.joinpath("scripts/log"), path.joinpath("scripts/version"),
    #                 path.joinpath("scripts/deploy/gitee_t.json")))  # step 0 必清site-packages cache，太大了
    # # Packer.bat_to_exe()  # step 1
    # packer = Packer(('scripts', f'{Proj.proj}.bat'))
    # packer.packup()  # step 2
    # # packer.upload('CGS.7z')  # step 3
    # # Clean.end_work(('CGS.7z',))  # step 4
    # # If error occur, exegesis previous step and run again
    #
    # # env_supplement()
    packer_mac = PackerMacOS()
    packer_mac.packup()
