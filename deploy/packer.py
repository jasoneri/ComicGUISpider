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
from itertools import chain

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
release_desc = """开箱即用
---
解压双击运行 `CGS.exe`

下载很慢 ？到压缩包的下载链接右键复制到 https://github.akams.cn/ 上进行下载加速

一般情况下，使用包内的更新程序 `CGS-更新.exe` 即可<br>
特殊情况，如运行环境需要变化时，需要在此页面下绿色安装包 (包更新未必是最新，更新日期参照标题) 
> 绿色包保证 `运行环境` 的更新，更新程序保证 `代码` 的更新，<br>
> 所以会有包更新没跟上代码更新，优先以内置的`CGS-更新.exe` 为主

---
其他问题 [回到项目主页](https://github.com/jasoneri/ComicGUISpider) 下方找群进群询问"""


class Proj:
    proj = "CGS"
    name = "ComicGUISpider"

    def __repr__(self):
        return self.proj


proj = Proj()


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
            script_url = "https://jsd.cdn.zzko.cn/gh/mengdeer589/PythonSizeCruncher@main/main.py"
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


class Packer:
    github_author = "jasoneri"
    executor = path.parent.joinpath(r'Bat_To_Exe_Converter\Bat_To_Exe_Converter.exe')
    zip_file = path.joinpath(f'{proj}.7z')
    preset_zip_file = path.joinpath(f'{proj}_preset.7z')

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
        _do(path.joinpath(rf"scripts/deploy/launcher/update.bat"), path.joinpath(rf"{proj}-更新.exe"),
            path.joinpath(rf"scripts/deploy/launcher/{proj}.ico"))
        _do(path.joinpath(rf"scripts/deploy/launcher/update.bat"), path.joinpath(rf"{proj}-使用说明.exe"),
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
            specified = ('runtime', 'site-packages')
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
        repo = proj.name
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
        text = release_desc
        release.update_release(name=f"{date_now} - v1.6.0", message=text)


def clean():
    """almost run few times in upfront"""
    Clean.clean_packages()
    Clean.fit()
    Clean.end_work()


if __name__ == '__main__':
    # clean()                   # step 0
    Clean.end_work(path.joinpath("scripts").rglob("__pycache__"),
                   (path.joinpath("scripts/log"), path.joinpath("scripts/version")))
    # Packer.bat_to_exe()  # step 1
    packer = Packer(('scripts', f'{proj}.exe', f'{proj}-更新.exe', f'{proj}-使用说明.exe', '_pystand_static.int'))
    packer.packup()  # step 2
    # packer.upload('CGS.7z')  # step 3
    # Clean.end_work(('CGS.7z',))  # step 4
    # If error occur, exegesis previous step and run again
