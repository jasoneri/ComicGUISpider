# 🚀 快速开始

## 1. 下载 / 部署

+ 直接下载 [📦绿色包](https://github.com/jasoneri/ComicGUISpider/releases/latest)，并解压

::: warning 解压路径不能含有中文/中标
:::
::: warning macOS用户
须阅读 [macOS 部署](./mac-required-reading.md) 文档
:::

+ 或克隆此项目 `git clone https://github.com/jasoneri/ComicGUISpider.git`  
::: tip 需安装  
+ `python3.12+`
+ 安装 [astral-sh/uv](https://github.com/astral-sh/uv)（然后抛弃 pip ，让 uv 管理依赖）
``` bash
python -m pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
```
**安装依赖命令示例** （CGS的 `requirements/*.txt` 都是用uv编译的，原生 pip 装你会发现各种麻烦）  
``` bash
python -m uv pip install -r "requirements/win.txt" --index-url https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host https://pypi.tuna.tsinghua.edu.cn/simple
```
:::
::: warning 使用 git 克隆的话请忽视全篇文档中的 scripts/xxx 的 `scripts`，文档是基于绿色包的说明
:::

## 2. 运行

### 常规 GUI 运行

`python CGS.py`  
或使用绿色包程序

### 命令行工具

`python crawl_only.py --help`  
或使用绿色包的环境，在解压目录打开终端执行  
`.\runtime\python.exe .\scripts\crawl_only.py --help`

::: info 使用方法进help看说明  
当前版本能进行简单下载/调试功能（后续将逐步扩展）  
命令行工具的配置可用GUI方式修改 或 直接修改`conf.yml`文件（[📒配置系文件路径](/faq/extra.html#_3-%E9%85%8D%E7%BD%AE%E7%B3%BB%E6%96%87%E4%BB%B6%E8%B7%AF%E5%BE%84)）
:::

## 3. 配置

有自定义需求的，参考 [🔨主配置文档](../config/index.md) 进行设置

## 4. 更新

+ CGS 内置了更新模块，能在配置窗口中点击 `检查更新` 按钮进行更新  
::: info 当 `本地版本` < `最新稳定版` < `最新开发版` 时  
需更新到`最新稳定版`后，才能更新到`最新开发版`
:::

+ 也可以选择到 releases 手动下载最新版

## 5. 搭配阅读器

欢迎尝试使用 redViewer ，最适 CGS ！也希望能提供有创意的功能想法给 rV ！💑

[![点击前往redViewer](https://github-readme-stats.vercel.app/api/pin/?username=jasoneri&repo=redViewer&show_icons=true&bg_color=60,ef4057,cf4057,c44490&title_color=4df5b4&hide_border=true&icon_color=e9ede1&text_color=e9ede1)](https://github.com/jasoneri/redViewer)
