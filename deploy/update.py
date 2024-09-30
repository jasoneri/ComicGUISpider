#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code update
base on client, env-python: embed"""
import argparse
import os
import sys
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

curr_os = platform.system()
if curr_os.startswith("Darwin"):
    curr_os = "macOS"
init(autoreset=True)
path = pathlib.Path(__file__).parent.parent.parent
existed_proj_p = path.joinpath('scripts')
temp_p = path.joinpath('temp')
sys.path.append(str(existed_proj_p))
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
}

from assets import res as ori_res  # must be below of sys.path.append

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
        with open(self.gitee_t_file, 'r', encoding='utf-8') as f:
            tokens = json.load(f)
        for _token in tokens:
            token = f"Bearer {base64.b64decode(_token).decode()}"
            with httpx.Client(headers={**headers, 'Authorization': token}) as client:
                resp = client.head(f"https://api.github.com")
                if str(resp.status_code).startswith('2'):
                    return token
        else:
            print(Fore.RED + res.token_invalid_notification)
            os.remove(self.gitee_t_file)

    def download_t_file(self):
        with open(self.gitee_t_file, 'w', encoding='utf-8') as f:
            resp = httpx.get(self.gitee_t_url)
            resp_json = resp.json()
            json.dump(resp_json, f, ensure_ascii=False)


class GitHandler:
    speedup_prefix = "https://gh.llkk.cc/"

    def __init__(self, owner, proj_name, branch):
        self.sess = httpx.Client()
        self.commit_api = f"https://api.github.com/repos/{owner}/{proj_name}/commits"
        self.src_url = f"https://api.github.com/repos/{owner}/{proj_name}/zipball/{branch}"
        t_handler = TokenHandler()
        self.headers = t_handler.headers

    # src_url = f"{self.speedup_prefix}https://github.com/{self.github_author}/{proj_name}/archive/refs/heads/{branch}.zip"

    def normal_req(self, *args, **kwargs):
        resp = self.sess.get(*args, headers=self.headers, **kwargs)
        if not str(resp.status_code).startswith("2"):
            raise ValueError(resp.text)
        return resp.json()

    def get_version_info(self, ver):
        resp_json = self.normal_req(f"{self.commit_api}/{ver}")
        return resp_json

    def check_changed_files(self, ver):
        print(Fore.BLUE + f"[ {res.ver_check}.. ]")
        resp_json = self.normal_req(self.commit_api)
        vers = list(map(lambda _: _["sha"], resp_json))
        if not ver:
            print(Fore.RED + f"[ {res.ver_file_not_exist}.. ]")
            return vers[0], []
        ver_index = vers.index(ver) if ver in vers else None
        valid_vers = vers[:ver_index]
        if len(valid_vers) > 10:
            print(Fore.YELLOW + f"[ {res.too_much_waiting_update}... ]")
            return vers[0], ["*"]
        files = []
        print(Fore.BLUE + f"[ {res.check_refresh_code}.. ]")
        for _ver in valid_vers:
            resp_json = self.get_version_info(_ver)
            files.extend(list(map(lambda _: _["filename"], resp_json["files"])))
            print(Fore.GREEN + f"[ {_ver[:8]} ] {resp_json['commit']['message']}")
        out_files = list(set(files))
        if "deploy/update.py" in out_files:  # make sure update.py must be local-updated
            out_files.remove("deploy/update.py")
            out_files.insert(0, "deploy/update.py")
        return vers[0], out_files

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
    changed_files = []

    def __init__(self):
        self.git_handler = GitHandler(self.github_author, self.name, self.branch)

    def check_existed_version(self):
        local_ver_file = existed_proj_p.joinpath('version')
        if not local_ver_file.exists():
            self.first_flag = True
        else:
            with open(local_ver_file, 'r', encoding='utf-8') as f:
                return f.read().strip()

    def check(self):
        self.local_ver = local_ver = self.check_existed_version()
        self.ver, self.changed_files = self.git_handler.check_changed_files(local_ver)

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
        with open(existed_proj_p.joinpath('version'), 'w', encoding='utf-8') as f:
            f.write(self.ver)
        print(Fore.GREEN + "=" * 40 + f"[ {res.finish} ]" + "=" * 40)

    def env_check_and_replenish(self):
        def delete(func, _path, execinfo):
            os.chmod(_path, stat.S_IWUSR)
            func(_path)

        record_file = path.joinpath("scripts/deploy/env_record.json")
        if not record_file.exists() or not self.local_ver:
            return
        with open(record_file, 'r', encoding='utf-8') as f:
            env_supplements = json.load(f)
        for env_pkg, env_files in env_supplements.items():
            if all(map(lambda _: path.joinpath(_).exists(), env_files)):
                continue
            proj_zip = self.git_handler.download_src_code(
                f"{self.git_handler.speedup_prefix}https://github.com/{self.github_author}/imgur/blob/main/CGS/{env_pkg}",
                zip_name=env_pkg)
            with zipfile.ZipFile(proj_zip, 'r') as zip_f:
                namelist = zip_f.namelist()
                zip_f.extractall(temp_p)
            for file in tqdm(namelist, total=len(namelist), ncols=80, ascii=True,
                             desc=Fore.BLUE + f"[ {res.env_covering}.. ]"):
                if not path.joinpath(file).exists():
                    path.joinpath(file).parent.mkdir(exist_ok=True, parents=True)
                    shutil.move(temp_p.joinpath(file), path.joinpath(file))
            shutil.rmtree(temp_p, onerror=delete)
        else:
            print(Fore.CYAN + f"[ {res.env_is_latest} ]")


def regular_update():
    retry_times = 1
    __ = None
    try:
        proj = Proj()
        proj.check()
    except Exception as e:
        __ = traceback.format_exc()
        print(__)
        print(Fore.RED + f"[Errno 11001] {res.refresh_fail_retry_over_limit}")
        return
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


def create_desc():
    def cdn_replace(md_str, author, repo, branch):
        return (md_str.replace("raw.githubusercontent.com", "jsd.onmicrosoft.cn/gh")
                .replace(f"{author}/{repo}/{branch}", f"{author}/{repo}@{branch}"))

    github_markdown_format = """<!DOCTYPE html><html><head><meta charset="UTF-8"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown.min.css"></head>
        <body><article class="markdown-body">
            %s
            </article></body></html>"""
    try:
        import markdown
    except ModuleNotFoundError:
        print(Fore.RED + f"[ {res.not_pkg_markdown} ]")
    else:
        with open(existed_proj_p.joinpath('README.md'), 'r', encoding='utf-8') as f:
            md_content = f.read()
            if curr_os == 'macOS':  # macOS desc also use markdown-html
                md_content = md_content.replace('deploy/launcher/mac/EXTRA.md',
                                                f'deploy/launcher/mac/desc_{curr_os}.html')
        md_content = cdn_replace(md_content, Proj.github_author, "imgur", "main")
        extensions = ['markdown.extensions.tables']
        html = markdown.markdown(md_content, extensions=extensions)
        html_style = github_markdown_format % html
        with open(existed_proj_p.joinpath('desc.html'), 'w', encoding='utf-8') as f:
            f.write(html_style)

        if curr_os == 'macOS':
            with open(existed_proj_p.joinpath('deploy/launcher/mac/EXTRA.md'), 'r', encoding='utf-8') as f:
                md_content = f.read()
            html = markdown.markdown(md_content, extensions=['markdown.extensions.tables'])
            html_style = github_markdown_format % html
            with open(existed_proj_p.joinpath(f'deploy/launcher/mac/desc_{curr_os}.html'), 'w', encoding='utf-8') as f:
                f.write(html_style)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        add_help=False,
        description="CGS updater",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    args = parser.add_argument_group("Arguments")
    args.add_argument('-d', '--desc', action=argparse.BooleanOptionalAction, required=False,
                      help=r'create scripts/desc.html from scripts/README.md')
    parsed = parser.parse_args()
    if parsed.desc:
        create_desc()
    else:
        regular_update()
