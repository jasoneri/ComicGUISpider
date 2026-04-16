#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code update"""
import json
import pathlib
import platform
from datetime import date

import httpx
from tqdm import tqdm
from colorama import init, Fore
from packaging.version import parse

from assets import res as ori_res
from variables import VER
from utils import conf, get_httpx_verify
from utils.config import conf_dir


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
        self.sess = httpx.Client(verify=get_httpx_verify())
        self.tags_api = f"{self.api_prefix}/repos/{owner}/{proj_name}/tags"
        self.releases_api = f"{self.api_prefix}/repos/{owner}/{proj_name}/releases"
        self.branch_commit_api = f" {owner}/{proj_name}/commits?sha={branch}"
        self.commit_api = f"{self.api_prefix}/repos/{owner}/{proj_name}/commits"
        self.zipball_url = f"{self.api_prefix}/repos/{owner}/{proj_name}/zipball"
        self.src_url = f"{self.zipball_url}/{branch}"
        self.release_notes_url = lambda cs: f"https://raw.githubusercontent.com/{owner}/{proj_name}/{cs}/docs/_github/release_notes.md"
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

    def get_tags_info(self) -> dict:
        tags_resp_json = self.normal_req(self.tags_api)
        if not tags_resp_json:
            raise ValueError("No tags found")
        latest_tag = tags_resp_json[0]
        return {
            'tag_name': latest_tag['name'],
            'commit': latest_tag['commit'],
            'zipball_url': latest_tag['zipball_url'],
        }
    
    def get_release_notes(self, commit_sha: str) -> str:
        try:
            resp = self.sess.get(self.release_notes_url(commit_sha), timeout=10, headers=self.headers)
            if resp.status_code == 200:
                return resp.text
            return f"Failed to fetch release notes: {resp.status_code}"
        except Exception as e:
            return f"Error fetching release notes: {str(e)}"

    def download_src_code(self, _url=None, zip_name="src.zip"):
        """proj less than 1Mb, actually just take little second"""
        zip_file = temp_p.joinpath(zip_name)
        with self.sess.stream("GET", _url or self.src_url, follow_redirects=True) as resp:
            with open(zip_file, 'wb') as f:
                size = 50 * 1024
                for chunk in tqdm(resp.iter_bytes(size), ncols=80,
                                  ascii=True, desc=f"{Fore.BLUE}[ {res.code_downloading}.. ]"):
                    f.write(chunk)
        return zip_file


class UpdateState:
    _file = conf_dir / "update_state.json"

    def __init__(self):
        self.last_check_date = ""
        self.update_flag = "local"
        self.update_info = {}
        self.load()

    def load(self):
        if not self._file.exists():
            return
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        self.last_check_date = data.get("last_check_date", "")
        self.update_flag = data.get("update_flag", "local")
        self.update_info = data.get("update_info", {})

    def save(self):
        payload = {
            "last_check_date": self.last_check_date,
            "update_flag": self.update_flag,
            "update_info": self.update_info,
        }
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def needs_check_today(self) -> bool:
        return self.last_check_date != date.today().isoformat()

    def clear(self):
        self.last_check_date = ""
        self.update_flag = "local"
        self.update_info = {}
        self.save()


class Proj:
    proj = "CGS"
    github_author = "jasoneri"
    name = "ComicGUISpider"
    branch = "GUI"
    url = f"https://github.com/{github_author}/{name}"

    ver = ""
    first_flag = False
    local_ver = None
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
        return VER

    # def check(self): # by_tags
    #     self.local_ver = local_ver = self.check_existed_version()
    #     latest_tag_info = self.git_handler.get_tags_info()
    #     ver_local = parse(self.local_ver.lstrip('v'))
    #     ver_latest = parse(latest_tag_info.get('tag_name').lstrip('v'))
    #     if ver_local < ver_latest:
    #         self.update_flag = 'stable'
    #         self.update_info = latest_tag_info
    #         commit_sha = latest_tag_info.get('commit', {}).get('sha', '')
    #         if commit_sha:
    #             self.update_info['body'] = self.git_handler.get_release_notes(commit_sha)
    #     updater_logger.info(f"local_ver: {self.local_ver}")
    
    def check(self):
        self.local_ver = self.check_existed_version()
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
