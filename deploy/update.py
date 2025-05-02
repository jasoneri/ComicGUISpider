#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code update
base on client, env-python: embed"""
import argparse
import os
import sys
import time
import subprocess
import importlib
import json
import shutil
import stat
import pathlib
import zipfile
import traceback
import platform
import base64

import httpx
from tqdm import tqdm
from colorama import init, Fore
from packaging.version import parse

from assets import res as ori_res
from utils import conf
from utils.docs import MarkdownConverter, MdHtml


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
    gitee_t_url = "https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/t.json"
    gitee_t_file = existed_proj_p.joinpath('deploy/gitee_t.json')

    def __init__(self):
        self.token = self.check_token()

    @property
    def headers(self):
        return {**headers, 'Authorization': self.token} if self.token else headers

    def check_token(self):
        try:
            if not self.gitee_t_file.exists():
                self.download_t_file()
            with open(self.gitee_t_file, 'r', encoding='utf-8') as f:
                tokens = json.load(f)
        except json.decoder.JSONDecodeError:
            tokens = []
        for _token in tokens:
            token = f"Bearer {base64.b64decode(_token).decode()}"
            with httpx.Client(headers={**headers, 'Authorization': token}) as client:
                resp = client.head(f"https://api.github.com")
                if str(resp.status_code).startswith('2'):
                    return token
        updater_logger.warning(res.token_invalid_notification)
        os.remove(self.gitee_t_file)

    def download_t_file(self):
        with open(self.gitee_t_file, 'w', encoding='utf-8') as f:
            resp = httpx.get(self.gitee_t_url)
            resp_json = resp.json()
            json.dump(resp_json, f, ensure_ascii=False)


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
    local_ver_file = existed_proj_p.joinpath('deploy/version.json')
    changed_files = []
    update_flag = "local"
    update_info = {}
    updated_success_flag = True

    def __init__(self):
        self.git_handler = GitHandler(self.github_author, self.name, self.branch)

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
        def delete(func, _path, execinfo):
            os.chmod(_path, stat.S_IWUSR)
            func(_path)

        def move(src, dst):
            if src.is_dir() and dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
                if dst.exists():  # fix
                    os.rmdir(dst)
            dst.parent.mkdir(exist_ok=True)
            if src.exists():
                shutil.move(src, dst)

        self.ver = ver or self.update_info.get('tag_name') or self.local_ver
        backuper = BackupManager()
        backuper.create_backup()
        try:
            proj_zip = self.git_handler.download_src_code(
                f"{self.git_handler.zipball_url}/{ver}" if ver else self.update_info.get('zipball_url'))
            with zipfile.ZipFile(proj_zip, 'r') as zip_f:
                zip_f.extractall(temp_p)
            temp_proj_p = next(temp_p.glob(f"*{self.name}*"))
            # REMARK(2024-08-08):      # f"{self.name}-{self.branch}"  this naming by src_url-"github.com/owner/repo/...zip"
            _, folders, files = next(os.walk(temp_proj_p))
            all_files = (*folders, *files)
            for file in all_files:
                if file != "conf.yml" or file != "record.db":
                    move(temp_proj_p.joinpath(file), existed_proj_p.joinpath(file))
            self.env_check_and_replenish()
            if not self.updated_success_flag:
                raise RuntimeError("update failed")
        except Exception as e:
            try:
                if existed_proj_p.exists():
                    shutil.rmtree(existed_proj_p, ignore_errors=True)
                backuper.restore_backup()
                raise e
            except Exception as _e:
                raise _e
        else:
            shutil.rmtree(temp_p, onexc=delete, ignore_errors=True)
            self.update_end()

    def update_end(self):
        with open(self.local_ver_file, 'w', encoding='utf-8') as f:
            json.dump({"current": self.ver}, f, ensure_ascii=False, indent=4)

    @updater_logger.catch
    def env_check_and_replenish(self):
        def check_import():
            for site_package in env_supplements:
                try:
                    importlib.import_module(site_package)
                except ImportError:
                    updater_logger.info(f"pkg-missing: {site_package}")
                    return True

        record_file = existed_proj_p.joinpath("deploy/env_record.json")
        if not record_file.exists():
            return
        with open(record_file, 'r', encoding='utf-8') as f:
            env_supplements = json.load(f)

        pip_flag = check_import()   
        updater_logger.debug(f"{pip_flag=}")     
        if pip_flag:
            if curr_os == "macOS":
                bash_path = existed_proj_p.joinpath("deploy/launcher/mac/init.bash")
                os.chmod(bash_path, stat.S_IRWXU)
                cmd = ["/bin/bash", str(bash_path)]
            else:
                bat_path = existed_proj_p.joinpath("deploy/launcher/init.bat")
                cmd = [str(bat_path)]
                print(f"{ori_res.lang=}")
                if ori_res.lang == "zh-CN":
                    cmd.extend([
                        "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", 
                        "--trusted-host", "pypi.tuna.tsinghua.edu.cn"])
            updater_logger.debug(f"[ pip-command ]: {' '.join(cmd)}")
            try:
                result = subprocess.run(cmd, check=False, capture_output=True, text=True)
                if result.returncode == 0:
                    updater_logger.debug(result.stdout)  # todo[1] 必须将result.stdout发出去给看
                else:
                    updater_logger.warning(f"[ pip-returncode <{result.returncode}> ]: {result.stderr}")
                    self.updated_success_flag = False
            except Exception as e:
                self.updated_success_flag = False
                updater_logger.exception(f"[ pip-exception ]: {e}")
        else:
            time.sleep(2)


def regular_update(ver):
    retry_times = 1
    __ = None
    update_result = ""
    while retry_times < 4:
        try:
            proj.local_update(ver)
            break
        except Exception as e:
            __ = traceback.format_exc()
            print(Fore.RED + f"[ {res.refresh_fail_retry}-{retry_times} ]\n{type(e)} {e} ")
            retry_times += 1
    if retry_times > 3:
        print(__)
        print(Fore.RED + f"[Errno 11001] {res.refresh_fail_retry_over_limit}")
        update_result = "exception: over_limit"
    return update_result


def create_desc(proj_path=None):
    """deprecated, use github-page instead"""
    _p = proj_path or existed_proj_p
    with open(_p.joinpath('README.md'), 'r', encoding='utf-8') as f:
        md_content = f.read().replace(
            'deploy/launcher/mac/EXTRA.md', 'deploy/launcher/mac/desc_macOS.html').replace(
            'docs/FAQ_and_EXTRA.md', 'docs/FAQ_and_EXTRA.html').replace(
            'docs/UPDATE_RECORD.md', 'docs/UPDATE_RECORD.html'
        )
    full_html = MarkdownConverter.convert_html(
        MdHtml(md_content).cdn_replace(Proj.github_author, "imgur", "main").details_formatter)
    with open(_p.joinpath('desc.html'), 'w', encoding='utf-8') as f:
        f.write(full_html)

    def transfer_markdown(_in, _out):
        MarkdownConverter.transfer_markdown(_p.joinpath(_in), _p.joinpath(_out))
    transfer_markdown('deploy/launcher/mac/EXTRA.md', 'deploy/launcher/mac/desc_macOS.html')
    transfer_markdown('docs/FAQ_and_EXTRA.md', 'docs/FAQ_and_EXTRA.html')
    transfer_markdown('docs/UPDATE_RECORD.md', 'docs/UPDATE_RECORD.html')
    return _p.joinpath('desc.html')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        add_help=False,
        description="CGS updater",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    args = parser.add_argument_group("Arguments")
    args.add_argument('-d', '--desc', action=argparse.BooleanOptionalAction, required=False)
    args.add_argument('-c', '--check', action=argparse.BooleanOptionalAction, required=False)
    args.add_argument('-v', '--version', required=False, help='指定版本号, 需要先搭配-c/--check查询')
    parsed = parser.parse_args()

    proj = Proj()
    if parsed.desc:
        create_desc()
    elif parsed.check:
        proj.check()
    elif parsed.version:
        regular_update(parsed.version)
