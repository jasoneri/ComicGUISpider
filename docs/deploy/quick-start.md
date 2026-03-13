# 🚀 快速上手

::: warning ⚠️ CGS 代码/解压的路径不能含有中文/中标
:::

## 1. 下载 / 部署

+ 直接下载 [📦绿色包](https://github.com/jasoneri/ComicGUISpider/releases/latest)，并解压，初次打开应用时会进入自动部署流程

::: warning macOS用户须阅读 [macOS 部署](./mac-required-reading.md) 文档
:::

::: danger ⚠️ 初始自动部署流程异常处理方法
::: details 点击展开

+ 过一遍 [faq](/faq/)
+ 参考解压包内的 `异常处理提示.txt` (仅`win`绿色包)
+ 开终端参考`./CGS.exe --help`，使用参数重新部署，例子：下方[更新第三种方法](#_4-更新)

:::

+ 或使用 `uv tool`  

::: details `uv tool` 细节部署流程：⇩  
1. 安装 [uv](https://github.com/astral-sh/uv)，使用 brew 安装最简单，或者使用官方的 [远程安装脚本](https://docs.astral.sh/uv/#installation)  
2. 安装 python，（如没安装）  
```
uv python install 3.13 --mirror https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone
```
3. （可选）C盘洁癖~~飘红~~：将以下 `D:\uv` 改为你想要放的位置，创建子目录`cache`,`tools`,`bin`,  
然后控制台开 powershell 执行以下命令，重启控制台生效
```powershell
[System.Environment]::SetEnvironmentVariable("UV_CACHE_DIR", "D:\uv\cache", "User")
[System.Environment]::SetEnvironmentVariable("UV_TOOL_DIR", "D:\uv\tools", "User")
[System.Environment]::SetEnvironmentVariable("UV_TOOL_BIN_DIR", "D:\uv\bin", "User")
uv tool update-shell
```

4. uv 安装 CGS  
``` bash
uvx ComicGUISpider --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```
:::
::: info 若需要用 `git` 克隆源码方式，需要自行管理环境 `uv sync`  
:::

## 2. 运行

::: tip 以下非绿色包命令均基于已执行 `uv tool update-shell`
否则为 `uvx --from comicguispider cgs`
:::

### 常规 GUI 运行

```cmd
cgs
```

或直接使用📦绿色包程序

### 命令行工具

```cmd
cgs-cli --help
```
或使用绿色包的环境，在解压目录打开终端执行  
```cmd
.\bin\cgs-cli.exe --help
```

::: info 使用方法进help看说明  
当前版本能进行简单下载/调试功能（后续将逐步扩展）  
命令行工具的配置可用GUI方式修改 或 直接修改`conf.yml`文件（[📒3-配置系文件路径](/faq/extra.html#_3-%E9%85%8D%E7%BD%AE%E7%B3%BB%E6%96%87%E4%BB%B6%E8%B7%AF%E5%BE%84)）
:::

## 3. 配置

有自定义需求的，参考 [🔨主配置文档](/config/index.md) 进行设置

## 4. 更新

+ CGS 内置了 更新模块 和 每日检测  
::: info 当 `本地版本` < `最新稳定版` < `最新开发版` 时  
需更新到`最新稳定版`后，才能更新到`最新开发版`
:::

+ 或 uv tool 管理的指定版本，例如 `2.9.0`

```zsh
uv tool install ComicGUISpider==2.9.0 --force --reinstall --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

+ 或 win-绿色包 安装指定版本，例如 `2.9.0`  

```cmd
.\CGS.exe -v 2.9.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 5. 搭配阅读器

欢迎尝试使用 redViewer ，最适 CGS ！也希望能提供有创意的功能想法给 rV ！💑

[![点击前往redViewer]({{URL_GHSTAT}}/api/pin/?username=jasoneri&repo=redViewer&show_icons=true&bg_color=60,ef4057,cf4057,c44490&title_color=4df5b4&hide_border=true&icon_color=e9ede1&text_color=e9ede1)](https://github.com/jasoneri/redViewer)
