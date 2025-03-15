#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code update
base on client, env-python: embed"""
import argparse
import os
import json
import shutil
import stat
import pathlib
import zipfile
import traceback
import platform
import base64

import markdown
import httpx
from tqdm import tqdm
from colorama import init, Fore
from packaging.version import parse

from assets import res as ori_res

curr_os = platform.system()
if curr_os.startswith("Darwin"):
    curr_os = "macOS"
init(autoreset=True)
path = pathlib.Path(__file__).parent.parent.parent
existed_proj_p = path.joinpath('scripts')
if not existed_proj_p.exists():
    existed_proj_p = path.joinpath('ComicGUISpider')
temp_p = path.joinpath('temp')
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
}


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
        if not self.gitee_t_file.exists():
            self.download_t_file()
        try:
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
        print(Fore.RED + res.token_invalid_notification)
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
        self.src_url = f"{self.api_prefix}/repos/{owner}/{proj_name}/zipball/{branch}"
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
        latest_resp_json = self.normal_req(self.releases_api)
        latest_stable_resp_json = self.normal_req(f"{self.releases_api}/latest")
        return latest_resp_json[0], latest_stable_resp_json

    def check_changed_files(self, commit):
        print(Fore.BLUE + f"[ {res.ver_check}.. ]")
        resp_json = self.normal_req(self.branch_commit_api)
        commits = list(map(lambda _: _["sha"], resp_json))
        if not commit:
            print(Fore.RED + f"[ {res.ver_file_not_exist}.. ]")
            return commits[0], []
        commit_index = commits.index(commit) if commit in commits else None
        valid_commits = commits[:commit_index]
        if len(valid_commits) > 10:
            print(Fore.YELLOW + f"[ {res.too_much_waiting_update}... ]")
            return commits[0], ["*"]
        files = []
        print(Fore.BLUE + f"[ {res.check_refresh_code}.. ]")
        for _commit in valid_commits:
            resp_json = self.get_commit_info(_commit)
            files.extend(list(map(lambda _: _["filename"], resp_json["files"])))
            print(Fore.GREEN + f"[ {_commit[:8]} ] {resp_json['commit']['message']}")
        out_files = list(set(files))
        if "deploy/update.py" in out_files:  # make sure update.py must be local-updated
            out_files.remove("deploy/update.py")
            out_files.insert(0, "deploy/update.py")
        return commits[0], out_files

    def download_src_code(self, _url=None, zip_name="src.zip"):
        """proj less than 1Mb, actually just take little second"""
        temp_p.mkdir(exist_ok=True)
        zip_file = temp_p.joinpath(zip_name)
        with self.sess.stream("GET", _url or self.src_url, follow_redirects=True) as resp:
            with open(zip_file, 'wb') as f:
                size = 50 * 1024
                for chunk in tqdm(resp.iter_bytes(size), ncols=80,
                                  ascii=True, desc=Fore.BLUE + f"[ {res.code_downloading}.. ]"):
                    f.write(chunk)
        return zip_file


class Proj:
    proj = "CGS"
    github_author = "jasoneri"
    name = "ComicGUISpider"
    branch = "GUI"

    ver = ""
    first_flag = False
    local_ver = None
    local_ver_file = existed_proj_p.joinpath('deploy/version.json')
    changed_files = []
    update_flag = "local"
    update_info = None

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

    def local_update(self):
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

        if not self.first_flag and not self.changed_files:
            print(Fore.CYAN + f"[ {res.code_is_latest} ]")
            return

        proj_zip = self.git_handler.download_src_code()
        with zipfile.ZipFile(proj_zip, 'r') as zip_f:
            zip_f.extractall(temp_p)
        temp_proj_p = next(temp_p.glob(f"{self.github_author}-{self.name}*"))
        # REMARK(2024-08-08):      # f"{self.name}-{self.branch}"  this naming by src_url-"github.com/owner/repo/...zip"
        if self.first_flag or self.changed_files[0] == "*":
            # first_flag: when the first-time use this update(no version-file)
            print(Fore.YELLOW + f"[ {res.latest_code_overwriting}.. ]")
            _, folders, files = next(os.walk(temp_proj_p))
            all_files = (*folders, *files)
            for file in tqdm(all_files, total=len(all_files), ncols=80, ascii=True,
                             desc=Fore.BLUE + f"[ {res.refreshing_code}.. ]"):
                move(temp_proj_p.joinpath(file), existed_proj_p.joinpath(file))
        else:
            for changed_file in tqdm(self.changed_files, total=len(self.changed_files),
                                     ncols=80, ascii=True, desc=Fore.BLUE + f"[ {res.refreshing_code}.. ]"):
                move(temp_proj_p.joinpath(changed_file), existed_proj_p.joinpath(changed_file))
        shutil.rmtree(temp_p, onerror=delete)

    def end(self):
        # with open(existed_proj_p.joinpath('version'), 'w', encoding='utf-8') as f:
        #     f.write(self.ver)
        # print(Fore.GREEN + "=" * 40 + f"[ {res.finish} ]" + "=" * 40)
        with open(self.local_ver_file, 'w', encoding='utf-8') as f:
            json.dump({"current": self.ver}, f, ensure_ascii=False, indent=4)

    def env_check_and_replenish(self):
        record_file = path.joinpath("scripts/deploy/env_record.json")
        if not record_file.exists() or not self.local_ver:
            return
        with open(record_file, 'r', encoding='utf-8') as f:
            env_supplements = json.load(f)
        site_packages_p = path.joinpath("site-packages")
        for site_package in env_supplements:
            if site_packages_p.joinpath(site_package).exists():
                continue
            print(Fore.RED + f"[ {res.env_check_fail % site_package} ]")
            return
        print(Fore.CYAN + f"[ {res.env_is_latest} ]")


def regular_update(version):
    retry_times = 1
    __ = None
    update_result = ""
    while retry_times < 4:
        try:
            proj.local_update()
            if curr_os != 'macOS':
                proj.env_check_and_replenish()
            proj.end()
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

    
with open(existed_proj_p.joinpath('assets/github_format.html'), 'r', encoding='utf-8') as f:
    github_markdown_format = f.read()


class MarkdownConverter:
    github_markdown_format = github_markdown_format
    md = markdown.Markdown(extensions=['markdown.extensions.md_in_html', 
        'markdown.extensions.tables', 'markdown.extensions.fenced_code', 'markdown.extensions.nl2br'],
        output_format='html5')

    @classmethod
    def convert_html(cls, md_content):
        html_body = cls.md.convert(md_content)
        full_html = cls.github_markdown_format.replace('{content}', html_body)
        return full_html


def create_desc(proj_path=None):
    def cdn_replace(md_str, author, repo, branch):
        return (md_str.replace("raw.githubusercontent.com", "jsd.vxo.im/gh")
                .replace(f"{author}/{repo}/{branch}", f"{author}/{repo}@{branch}"))
    
    _p = proj_path or existed_proj_p
    with open(_p.joinpath('README.md'), 'r', encoding='utf-8') as f:
        md_content = f.read().replace(
            'deploy/launcher/mac/EXTRA.md', 'deploy/launcher/mac/desc_macOS.html').replace(
            'docs/FAQ_and_EXTRA.md', 'docs/FAQ_and_EXTRA.html').replace(
            'docs/UPDATE_RECORD.md', 'docs/UPDATE_RECORD.html'
        )
    md_content = cdn_replace(md_content, Proj.github_author, "imgur", "main").replace(
        "<details>", '<details markdown="1">')
    full_html = MarkdownConverter.convert_html(md_content)
    with open(_p.joinpath('desc.html'), 'w', encoding='utf-8') as f:
        f.write(full_html)

    def transfer_markdown(_in, _out):
        with open(_p.joinpath(_in), 'r', encoding='utf-8') as f:
            _md_content = f.read()
        _html = MarkdownConverter.convert_html(_md_content)
        with open(_p.joinpath(_out), 'w', encoding='utf-8') as f:
            f.write(_html)
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
    args.add_argument('-u', '--update', required=False)
    parsed = parser.parse_args()

    proj = Proj()
    if parsed.desc:
        create_desc()
    elif parsed.check:
        proj.check()
    elif parsed.update:
        regular_update(parsed.update)
