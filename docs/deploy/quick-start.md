# 🚀 快速开始

::: warning ⚠️ CGS 代码/解压的路径不能含有中文/中标
:::

## 1. 下载 / 部署

+ 直接下载 [📦绿色包](https://github.com/jasoneri/ComicGUISpider/releases/latest)，并解压，初次打开应用时会进入自动部署流程

::: warning macOS用户
须阅读 [macOS 部署](./mac-required-reading.md) 文档
:::

::: danger ⚠️ 自动部署流程异常处理方法 (基本仅`win`)
::: details 点击展开

+ 参考解压包内的图例或使用脚本，图例视群友反馈对策效果后续可能增加
+ 自动部署之后的`解压目录/bin/cgs.exe`仍然不存在时尝试换源，查看 [换源指引](/faq/#pypi%E6%8D%A2%E6%BA%90%E6%8C%87%E5%BC%95)
+ 开终端参考`./CGS.exe --help`，使用参数重新部署，例子：下方[更新第三种方法](#_4-更新)

:::

::: warning release 上的 `CGS_win_full.7z`为免部署懒人包，出问题解决是以`CGS.7z`包即上述异常处理去解决的  
不要以`full`包无法运行去提问题，否则会获得套餐 < ❗️💢👊💥💫🚑💀 >
:::

+ 或使用`uv tool`  

::: info 仅使用时不建议用克隆源码方式，否则需要自行管理环境 `uv sync`，  
同样需要用到 uv，那还是不如直接用 `uv tool`
:::
::: details `uv tool` 流程（点击展开）：  
1. 安装 [uv](https://github.com/astral-sh/uv)，使用 brew 安装最简单，或者使用官方的 [远程安装脚本](https://docs.astral.sh/uv/#installation)  
2. （可选）设置 uv tool 的环境变量，否则 win 会默认装在C盘上  
    win: 新建用户级的环境变量，设置后需开新终端窗口生效  
    &emsp;`UV_TOOL_DIR`(uv tool安装项目的位置),  
    &emsp;`UV_TOOL_BIN_DIR`(uv编译执行程序的放置位置)  
    mac(示例zsh): `echo "export UV_TOOL_DIR=放置tool的位置" >> ~/.zshrc`,  
    &emsp;`UV_TOOL_BIN_DIR`同理操作，`source ~/.zshrc`后生效  
    最后执行 `uv tool update-shell` 更新进 PATH，之后新终端窗口可直接运行 cgs / cgs-cli
3. uv tool 安装 CGS  
``` bash
uv tool install ComicGUISpider --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```
:::
::: warning v2.4.0 之后的绿色包均转为套壳操作 `uv tool`
:::

## 2. 运行

::: tip 以下非绿色包命令均基于已执行 `uv tool update-shell`
否则为 `uv tool run --from comicguispider cgs`
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

+ CGS 内置了更新模块，能在配置窗口中点击 `检查更新` 按钮进行更新  
::: info 当 `本地版本` < `最新稳定版` < `最新开发版` 时  
需更新到`最新稳定版`后，才能更新到`最新开发版`
:::

+ 或 uv tool 管理的指定版本，例如 `2.4.4`

```zsh
uv tool install ComicGUISpider==2.4.4 --force --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

+ 或 win-绿色包 安装指定版本，例如 `2.4.4`  
需 `解压目录/_pystand_static.int` 首行含 version 且大于等于 `v1`，否则从最新版绿色包获取

```cmd
.\CGS.exe -v 2.4.4 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 5. 搭配阅读器

欢迎尝试使用 redViewer ，最适 CGS ！也希望能提供有创意的功能想法给 rV ！💑

[![点击前往redViewer](https://github-readme-stats.vercel.app/api/pin/?username=jasoneri&repo=redViewer&show_icons=true&bg_color=60,ef4057,cf4057,c44490&title_color=4df5b4&hide_border=true&icon_color=e9ede1&text_color=e9ede1)](https://github.com/jasoneri/redViewer)
