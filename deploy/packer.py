#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code packer
env-python: developer

thanks mengdeer589/PythonSizeCruncher
"""
import json
import os
import sys
import shutil
import pathlib
import stat
import argparse
from itertools import chain

from pydos2unix import dos2unix
import py7zr

from tqdm import tqdm
from loguru import logger

prog_path = pathlib.Path(__file__).parent.parent
if pathlib.Path("/build").exists():
    print("Running in CI environment")
    tmp_p = pathlib.Path(r"/tmp")
else:
    print("Running in local environment")
    tmp_p = prog_path.parent.joinpath("temp")
path = prog_path.parent
sys.path.append(str(prog_path))

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
        import httpx    
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
    zip_file = path.joinpath(f'{_proj}.7z')
    preset_zip_file = tmp_p.joinpath(f'{_proj}_preset.7z')

    def __init__(self, default_specified: tuple, ver: str):
        self.default_specified = default_specified
        self.ver = ver

    @classmethod
    def bat_to_exe(cls):
        """最好只做一次，减少指定脚本的修改次数/生成 从而减少引发的风险"""
        executor = path.parent.joinpath(r'Bat_To_Exe_Converter\Bat_To_Exe_Converter.exe')
        # command = f"cd {path} && {cls.executor} /bat {bat_file} /exe {exe_file} /icon {icon} /x64 {args_str}"
        # 主运行使用 PyStand 壳，不再重复造exe了，容易被杀软误杀
        # exe生成后需要扔到 https://habo.qq.com/ 做检测，必须是`未发现风险`
        ...

    def pre_packup(self):
        with open(path.joinpath(r"scripts/version.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "current": self.ver, "stable": "", "dev": ""
            }, f, indent=4)

    def packup(self, runtime_init=False):
        self.pre_packup()
        zip_file = self.zip_file
        specified = self.default_specified
        mode = "a"
        if runtime_init:
            # {proj}_preset.7z: only include runtime. If env changed, re-packup it
            if self.preset_zip_file.exists():
                logger.debug(f"[ preset_zip_file exists ] run normal packup")
                logger.debug(f"[ if need init ] delete '{self.preset_zip_file}' manually later")
                return self.packup()
            zip_file = self.preset_zip_file
            specified = ('runtime', '_pystand_static.int',
                         f'{self._proj}.exe')
            mode = "w"
        elif self.preset_zip_file.exists():
            shutil.copy(self.preset_zip_file, self.zip_file)
        # 仅 CI 环境，处理 【过滤.git后的script、CGS.bat】 进经 workflow 安装了 runtime 全部依赖的 perset 包
        with py7zr.SevenZipFile(zip_file, mode, filters=[{"id": py7zr.FILTER_LZMA2}]) as zip_f:
            for file in tqdm(tuple(specified)):
                if file == f'{Proj.proj}.bat':
                    zip_f.write(path.joinpath(f"scripts/deploy/launcher/{file}"), arcname=file)
                elif path.joinpath(file).exists():
                    zip_f.writeall(file)
        if not self.zip_file.exists():
            self.packup()


class PackerMacOS(Packer):
    _proj = f"{Proj.proj}-macOS"
    zip_file = path.joinpath(f'{_proj}.7z')
    preset_zip_file = tmp_p.joinpath(f'{_proj}_preset.7z')
    scripts_path = "CGS.app/Contents/Resources/scripts"

    def __init__(self, ver):
        super(PackerMacOS, self).__init__(tuple(), ver)

    def pre_packup(self):
        """ 1. 预处理CGS.app的结构
            2. dos2unix处理项目文本文件"""
        super(PackerMacOS, self).pre_packup()
        mac_7z_p = path.joinpath(self.scripts_path.rsplit("/", maxsplit=1)[0])
        mac_7z_p.mkdir(parents=True, exist_ok=True)
        mac_scripts_path = mac_7z_p.joinpath("scripts")
        if mac_scripts_path.exists():
            shutil.rmtree(mac_scripts_path, ignore_errors=True)
        shutil.move(path.joinpath("scripts"), mac_scripts_path)

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


def packup_windows(ver):
    # # clean()
    Clean.end_work(path.joinpath("scripts").rglob("__pycache__"), path.joinpath("runtime").rglob("__pycache__"),
        (path.joinpath("scripts/log"), path.joinpath("scripts/deploy/gitee_t.json")))  # step 0 必清runtime cache，太大了
    packer = Packer(('scripts', f'{Proj.proj}.bat'), ver=ver)
    packer.packup()  # step 2
    # # Clean.end_work(('CGS.7z',))  # step 4
    # # If error occur, exegesis previous step and run again


def packup_mac(ver):
    packer_mac = PackerMacOS(ver=ver)
    packer_mac.packup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['windows', 'mac'])
    parser.add_argument('-v', '--version', help='current tag version')
    args = parser.parse_args()
    
    if args.command == 'windows':
        packup_windows(args.version)
    elif args.command == 'mac':
        packup_mac(args.version)
