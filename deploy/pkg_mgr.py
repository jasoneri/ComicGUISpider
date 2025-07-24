import argparse
import sys
import importlib
import platform
import subprocess
import pathlib

import httpx
import tqdm
from loguru import logger

p = pathlib.Path(__file__).parent
def which_env():
    os_type = platform.system()
    if os_type == "Darwin":
        # 判断Mac架构
        arch = platform.machine()
        if arch == "arm64":
            return "mac_arm64"
        elif arch == "x86_64":
            return "mac_x86_64"
        else:
            return "mac_x86_64"
    else:
        return "win"


class PkgMgr:
    def __init__(self, locale="zh-CN", run_path=None, debug_signal=None):
        self.cli = httpx.Client()
        self.locale = locale
        self.run_path = run_path or p
        self.debug_signal = debug_signal
        if self.run_path.joinpath("scripts/CGS.py").exists():
            self.proj_p = self.run_path.joinpath("scripts")
        elif self.run_path.joinpath("CGS.py").exists():
            self.proj_p = self.run_path
        else:
            raise FileNotFoundError(f"CGS.py not found, unsure env. check your run path > [{self.run_path}].")
        self.env = which_env()
        self.set_assets()

    def github_speed(self, url):
        if self.locale == "zh-CN":
            url = url.replace("raw.githubusercontent.com/jasoneri/ComicGUISpider/refs/heads/GUI", 
                              "gitee.com/json_eri/ComicGUISpider/raw/GUI")
        return url
    
    def set_assets(self):
        # 使用pyproject.toml替代requirements文件
        self.pyproject_url = self.github_speed("https://raw.githubusercontent.com/jasoneri/ComicGUISpider/refs/heads/GUI/pyproject.toml")
        self.pyproject = self.proj_p.joinpath("pyproject.toml")

    def print(self, *args, **kwargs):
        if self.debug_signal:
            self.debug_signal.emit(*args, **kwargs)
        print(*args, **kwargs)

    def dl(self):
        def _dl(url, out):
            with self.cli.stream("GET", url) as r:
                with open(out, "wb") as f:
                    for chunk in tqdm.tqdm(r.iter_bytes(1000), desc=f"downloading {out.name}"):
                        f.write(chunk)
            self.print(f"[downloaded] {out.name}")

        def _dl_uv():
            cmd = ["install", "uv"]
            if self.locale == "zh-CN":
                cmd.extend(["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
            import pip
            exitcode = pip.main(cmd)
            self.print(f"[pip install uv exitcode] {exitcode}")

        if self.env.startswith("win"):
            _dl_uv()
        _dl(self.pyproject_url, self.pyproject)

    def uv_install_pkgs(self):
        self.print("uv sync installing packages...")
        if self.env.startswith("win"):
            # Windows 使用原有的 uv 逻辑
            uv = importlib.import_module("uv")
            cmd = [uv.find_uv_bin(), "sync", "--python", sys.executable]
        else:
            cmd = ["uv", "sync"]
        if self.locale == "zh-CN":
            cmd.extend(["--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple"])
        self.print("[uv_sync cmd]" + " ".join(cmd))
        process = subprocess.Popen(
            cmd, cwd=self.run_path,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True
        )
        full_output = []
        while True:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break  # 进程结束且无输出时退出
                continue
            line = line.strip()
            full_output.append(line)
            # 实时发送信号
            self.print(line)
        # 读取剩余输出
        remaining = process.stdout.read()
        if remaining:
            for line in remaining.splitlines():
                cleaned_line = line.strip()
                full_output.append(cleaned_line)
                self.print(cleaned_line)
        # 等待进程结束
        exit_code = process.wait()
        if exit_code == 0:
            self.print("[!uv_install_pkgs done!]")
        return exit_code, full_output

    @logger.catch(reraise=True)
    def run(self):
        self.dl()
        exit_code, full_output = self.uv_install_pkgs()
        return exit_code, full_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--locale", default="zh-CN", help="locale")
    args = parser.parse_args()
    pkg_mgr = PkgMgr(args.locale)
    # pkg_mgr = PkgMgr("zh-CN")
    pkg_mgr.run()
