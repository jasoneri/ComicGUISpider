#!/usr/bin/python
# -*- coding: utf-8 -*-
"""code update
base on client, env-python: embed"""
import argparse
import os
import shutil
import stat
import pathlib
import zipfile

import httpx
from tqdm import tqdm
from colorama import init, Fore

from assets import res as ori_res

res = ori_res.Updater
init(autoreset=True)
path = pathlib.Path(__file__).parent.parent.parent
existed_proj_p = path.joinpath('scripts')
temp_p = path.joinpath('temp')
proxies = None
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
}


class GitHandler:
    speedup_prefix = "https://gh.llkk.cc/"

    def __init__(self, owner, proj_name, branch):
        self.sess = httpx.Client(proxies=proxies)
        self.commit_api = f"https://api.github.com/repos/{owner}/{proj_name}/commits"
        self.src_url = f"https://api.github.com/repos/{owner}/{proj_name}/zipball/{branch}"

    # src_url = f"{self.speedup_prefix}https://github.com/{self.github_author}/{proj_name}/archive/refs/heads/{branch}.zip"

    def check_changed_files(self, ver):
        print(Fore.BLUE + f"[ {res.ver_check}.. ]")
        resp = self.sess.get(self.commit_api, headers=headers)
        resp_json = resp.json()
        vers = list(map(lambda _: _["sha"], resp_json))
        if not ver:
            print(Fore.RED + f"[ {res.ver_file_not_exist}.. ]")
            return vers[0], []
        ver_index = vers.index(ver)
        valid_vers = vers[:ver_index]
        files = []
        print(Fore.BLUE + f"[ {res.check_refresh_code}.. ]")
        for _ver in valid_vers:
            resp = self.sess.get(f"{self.commit_api}/{_ver}", headers=headers)
            resp_json = resp.json()
            files.extend(list(map(lambda _: _["filename"], resp_json["files"])))
            print(Fore.GREEN + f"[ {_ver[:8]} ] {resp_json['commit']['message']}")
        return vers[0], list(set(files))

    def download_src_code(self):
        """proj less than 1Mb, actually just take little second"""
        temp_p.mkdir(exist_ok=True)
        zip_file = temp_p.joinpath("src.zip")
        with self.sess.stream("GET", self.src_url, follow_redirects=True) as resp:
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
    git_handler = GitHandler(github_author, name, branch)
    ver = ""
    first_flag = False
    changed_files = []

    def check_existed_version(self):
        local_ver_file = existed_proj_p.joinpath('version')
        if not local_ver_file.exists():
            self.first_flag = True
        else:
            with open(local_ver_file, 'r', encoding='utf-8') as f:
                return f.read().strip()

    def check(self):
        local_ver = self.check_existed_version()
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
            shutil.move(src, dst)

        if not self.first_flag and not self.changed_files:
            print(Fore.CYAN + "[ 代码已是最新.. 若有其他问题向群里反映 ]")
            return

        proj_zip = self.git_handler.download_src_code()
        with zipfile.ZipFile(proj_zip, 'r') as zip_f:
            zip_f.extractall(temp_p)
        temp_proj_p = next(temp_p.glob(f"{self.github_author}-{self.name}*"))
        # REMARK(2024-08-08):      # f"{self.name}-{self.branch}"  this naming by src_url-"github.com/owner/repo/...zip"
        if self.first_flag:  # when the first-time use this update(no version-file)
            print(Fore.YELLOW + "[ 首次使用更新，初始化覆盖中.. ]")
            _, folders, files = next(os.walk(temp_proj_p))
            all_files = (*folders, *files)
            for file in tqdm(all_files, total=len(all_files), ncols=80, ascii=True,
                             desc=Fore.BLUE + "[ 更新代码中.. ]"):
                move(temp_proj_p.joinpath(file), existed_proj_p.joinpath(file))
        else:
            for changed_file in tqdm(self.changed_files, total=len(self.changed_files),
                                     ncols=80, ascii=True, desc=Fore.BLUE + "[ 更新代码中.. ]"):
                move(temp_proj_p.joinpath(changed_file), existed_proj_p.joinpath(changed_file))
        shutil.rmtree(temp_p, onerror=delete)
        with open(existed_proj_p.joinpath('version'), 'w', encoding='utf-8') as f:
            f.write(self.ver)


def regular_update():
    proj = Proj()
    proj.check()
    proj.local_update()
    print(Fore.GREEN + "=" * 40 + f"[ {res.finish} ]" + "=" * 40)


def create_desc():
    def cdn_replace(md_str, author, repo, branch):
        return (md_str.replace("raw.githubusercontent.com", "jsd.cdn.zzko.cn/gh")
                .replace(f"{author}/{repo}/{branch}", f"{author}/{repo}@{branch}"))

    try:
        import markdown
    except ModuleNotFoundError:
        print(Fore.RED + f"[ {res.not_pkg_markdown} ]")
    else:
        file_path = 'scripts/README.md'
        out_name = 'scripts/desc.html'
        with open(path.joinpath(file_path), 'r', encoding='utf-8') as f:
            md_content = f.read()
        md_content = cdn_replace(md_content, Proj.github_author, "imgur", "main")
        extensions = ['markdown.extensions.tables']
        html = markdown.markdown(md_content, extensions=extensions)
        html_style = """<!DOCTYPE html><html><head><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown.min.css"></head>
        <body><article class="markdown-body">
            %s
            </article></body></html>""" % html
        with open(path.joinpath(out_name), 'w', encoding='utf-8') as f:
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
