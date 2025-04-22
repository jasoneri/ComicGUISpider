# 🚀 快速开始

## 1. 下载 / 部署

+ 直接下载 [📦绿色包](https://github.com/jasoneri/ComicGUISpider/releases/latest)，并解压

::: warning 解压路径不能含有中文/中标
:::
::: warning macOS用户
须阅读 [macOS部署](./mac-required-reading.md) 文档
:::

+ 或克隆此项目 `git clone https://github.com/jasoneri/ComicGUISpider.git`  
需安装 `python3.12+`，环境包在根目录的 `requirements` 里，pip 安装对应的架构即可

::: tip 使用 git 克隆的话请忽视全篇文档中的 scripts/xxx 的 `scripts`，文档是基于绿色包进行的说明
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
命令行工具的配置可用GUI方式修改 或 直接修改`scripts/conf.yml`文件
:::

## 3. 配置

有自定义需求的，参考 [🔨配置文档](../config/index.md) 进行设置

## 4. 更新

+ CGS 内置了更新模块，能在配置窗口中点击 `检查更新` 按钮进行更新  
::: info 当 `本地版本` < `最新稳定版` < `最新开发版` 时
需更新到`最新稳定版`后，才能更新到`最新开发版`
:::

+ 也可以选择到 releases 手动下载最新版，但需要注意配置等文件不被覆盖丢失
::: tip 分别是 配置文件 `scripts/conf.yml` 与去重记录 `scripts/record.db`
:::
