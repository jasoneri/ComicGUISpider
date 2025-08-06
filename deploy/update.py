#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code update"""
import os
import json
import shutil
import pathlib
import platform
import subprocess

import httpx
from tqdm import tqdm
from colorama import init, Fore
from packaging.version import parse

from assets import res as ori_res
from variables import PYPI_SOURCE
from utils import conf, exc_p, uv_exc, env


curr_os = platform.system()
if curr_os.startswith("Darwin"):
    curr_os = "macOS"
init(autoreset=True)
path = pathlib.Path(__file__).parent.parent.parent
existed_proj_p = path.joinpath('scripts')
if not existed_proj_p.exists():
    existed_proj_p = path.joinpath('ComicGUISpider')
temp_p = path.joinpath('__temp')
temp_p.mkdir(exist_ok=True)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
}

updater_logger = conf.cLog(name="GUI")
res = ori_res.Updater


class TokenHandler:
    token_file = existed_proj_p.joinpath('deploy/token.json')

    def __init__(self):
        self.token = self.check_token()

    @property
    def headers(self):
        return {**headers, 'Authorization': self.token} if self.token else headers

    def check_token(self):
        if not self.token_file.exists():
            return None
        with open(self.token_file, 'r', encoding='utf-8') as f:
            token = f.read().strip()
            return f"Bearer {token}"


class GitHandler:
    speedup_prefix = "https://gh.llkk.cc/"
    api_prefix = "https://api.github.com"

    def __init__(self, owner, proj_name, branch):
        self.sess = httpx.Client()
        self.releases_api = f"{self.api_prefix}/repos/{owner}/{proj_name}/releases"
        self.branch_commit_api = f" {owner}/{proj_name}/commits?sha={branch}"
        self.commit_api = f"{self.api_prefix}/repos/{owner}/{proj_name}/commits"
        self.zipball_url = f"{self.api_prefix}/repos/{owner}/{proj_name}/zipball"
        self.src_url = f"{self.zipball_url}/{branch}"
        t_handler = TokenHandler()
        self.headers = t_handler.headers

    # src_url = f"{self.speedup_prefix}https://github.com/{self.github_author}/{proj_name}/archive/refs/heads/{branch}.zip"

    def normal_req(self, *args, **kwargs):
        resp = self.sess.get(*args, headers=self.headers, **kwargs)
        if not str(resp.status_code).startswith("2"):
            raise ValueError(resp.text)
        return resp.json()

    def get_commit_info(self, commit):
        resp_json = self.normal_req(f"{self.commit_api}/{commit}")
        return resp_json

    def get_releases_info(self) -> tuple:
        releases_resp_json = self.normal_req(self.releases_api)
        dev_release = next((release for release in releases_resp_json if release.get('prerelease')), releases_resp_json[0])
        stable_release = next((release for release in releases_resp_json if not release.get('prerelease')), releases_resp_json[0])
        return dev_release, stable_release

    def download_src_code(self, _url=None, zip_name="src.zip"):
        """proj less than 1Mb, actually just take little second"""
        zip_file = temp_p.joinpath(zip_name)
        with self.sess.stream("GET", _url or self.src_url, follow_redirects=True) as resp:
            with open(zip_file, 'wb') as f:
                size = 50 * 1024
                for chunk in tqdm(resp.iter_bytes(size), ncols=80,
                                  ascii=True, desc=Fore.BLUE + f"[ {res.code_downloading}.. ]"):
                    f.write(chunk)
        return zip_file


class BackupManager:
    def __init__(self):
        self.backup_dir = temp_p.joinpath("backup")
        if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir, ignore_errors=True)
        self.ignore_patterns = [self.backup_dir.name, '*.pyc', '__pycache__', 'log', '*.db']

    def _safe_operation(self, operation: callable, error_msg: str, *args, **kwargs) -> bool:
        try:
            operation(*args, **kwargs)
            return True
        except Exception as e:
            updater_logger.warning(f"BackupWarning: {error_msg}: {e}")
            return False

    def _safe_remove(self, _path, is_dir=False):
        return self._safe_operation(shutil.rmtree if is_dir else os.remove, f"BackupDeleteError: {_path}", _path)

    def _safe_move(self, _src, _dst):
        return self._safe_operation(shutil.move, f"BackupMoveError: {_src} -> {_dst}", _src, _dst)
    
    def _check_file_access(self, _path):
        try:
            if _path.is_file():
                with open(_path, 'a', encoding='utf-8'): pass
            return True
        except (IOError, OSError):
            return False

    def create_backup(self):
        if self.backup_dir.exists() and not self._safe_remove(self.backup_dir, is_dir=True):
            raise RuntimeError("BackupCleanError: fail clean old backup")
        try:
            shutil.copytree(existed_proj_p.absolute(), self.backup_dir, ignore=shutil.ignore_patterns(*self.ignore_patterns))
        except Exception as e:
            self.cleanup()
            raise e

    def restore_backup(self):
        if not self.backup_dir.exists():
            raise FileNotFoundError("BackupNotFoundError: backup directory not found")
        self._check_destination_access()
        _failed_items = set()
        for _item in self.backup_dir.iterdir():
            _src = self.backup_dir / _item.name
            _dst = existed_proj_p / _item.name
            if _dst.exists() and not self._safe_remove(_dst, is_dir=_dst.is_dir()):
                _failed_items.add(_item.name)
            if not self._safe_move(_src, existed_proj_p):
                _failed_items.add(_item.name)
        if _failed_items:
            raise RuntimeError(f"BackupRestoreError: [{', '.join(_failed_items)}]")
        self.cleanup()

    def _check_destination_access(self):
        _inaccessible_files = [_dst for _item in self.backup_dir.iterdir() 
                             if (_dst := existed_proj_p / _item.name).exists() 
                             and not self._check_file_access(_dst)]
        if _inaccessible_files:
            raise RuntimeError(f"BackupAccessError: [{', '.join(_inaccessible_files)}]")

    def cleanup(self):
        if self.backup_dir.exists():
            self._safe_remove(self.backup_dir, is_dir=True)


class Proj:
    proj = "CGS"
    github_author = "jasoneri"
    name = "ComicGUISpider"
    branch = "GUI"
    url = f"https://github.com/{github_author}/{name}"

    ver = ""
    first_flag = False
    local_ver = None
    local_ver_file = existed_proj_p.joinpath('version.json')
    changed_files = []
    update_flag = "local"
    update_info = {}
    updated_success_flag = True

    def __init__(self, debug_signal=None):
        self.git_handler = GitHandler(self.github_author, self.name, self.branch)
        self.debug_signal = debug_signal

    def print(self, *args, **kwargs):
        if self.debug_signal:
            self.debug_signal.emit(*args, **kwargs)
        print(*args, **kwargs)

    def check_existed_version(self):
        if not self.local_ver_file.exists():
            self.first_flag = True
        else:
            with open(self.local_ver_file, 'r', encoding='utf-8') as f:
                version_info = json.load(f)
                return version_info.get('current', 'v0.0.0')
        return 'v0.0.0'

    def check(self):
        self.local_ver = local_ver = self.check_existed_version()
        latest_dev_info, latest_stable_info = self.git_handler.get_releases_info()
        ver_local = parse(self.local_ver.lstrip('v'))
        ver_dev = parse(latest_dev_info.get('tag_name').lstrip('v'))
        ver_stable = parse(latest_stable_info.get('tag_name').lstrip('v'))
        if ver_local < ver_stable:
            self.update_flag = 'stable'
            self.update_info = latest_stable_info
        elif ver_local < ver_dev:
            self.update_flag = 'dev'
            self.update_info = latest_dev_info
        updater_logger.info(f"local_ver: {self.local_ver}")

    def local_update(self, ver=None):
        self.ver = ver or self.update_info.get('tag_name') or self.local_ver
        backuper = BackupManager()
        backuper.create_backup()
        try:
            cmd = [uv_exc,"tool","upgrade","ComicGUISpider"]
            cmd.extend(["--index-url", PYPI_SOURCE[conf.pypi_source]])
            self.print("[uv cmd]" + " ".join(cmd))
            process = subprocess.Popen(
                cmd, cwd=exc_p, env=env,
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
                self.print(line)
            remaining = process.stdout.read()
            if remaining:
                for line in remaining.splitlines():
                    cleaned_line = line.strip()
                    full_output.append(cleaned_line)
                    self.print(cleaned_line)
            exit_code = process.wait()
            if exit_code == 0:
                self.print("[!uv upgrade done!]")
        except Exception as e:
            raise e
        else:
            self.update_end()

    def update_end(self):
        with open(self.local_ver_file, 'w', encoding='utf-8') as f:
            json.dump({"current": self.ver}, f, ensure_ascii=False, indent=4)
