<div align="center">
  <a href="https://github.com/jasoneri/ComicSpider" target="_blank">
    <img src="assets/icon.png" alt="logo">
  </a>
  <h1 id="koishi">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg?style=social" alt="tag">
  <img src="https://img.shields.io/badge/Mode-GUI+Scrapy-blue.svg?colorA=abcdef" alt="tag">
</div>

交互式下载漫画项目，支持预览多选，翻页等

▼ 操作展示 ▼ (国内如果无法看到动图 [点这里](https://cdn.jsdmirror.com/gh/jasoneri/imgur@main/CGS/preview-usage.gif))

![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/preview-usage.gif)

## 项目介绍

### 支持网站

| 网站          | 支持<br>(数字输入) | 预览 |  翻页   |
|:------------|:------------:|:--:|:-----:|
| 拷贝漫画        |      ✅       | ❌  |   ✅   |
| 禁漫天堂        |      ✅       | ✅  |   ✅   |
| 绅士漫画(wnacg) |      ✅       | ✅  |   ✅   |
| ExHentai    |      ✅       | ✅  | 开发中📃 |

使用请适度，以免加重对方服务器负担

> 打包好的开箱即用版，[点击前往下载页面](https://github.com/jasoneri/ComicGUISpider/releases)，包名 `CGS.7z`
> ，解压后目录树如下 <br>
> `每次解压绿色包` 后，建议先更新一次保证代码最新 <br>

```shell
  CGS
   ├── runtime
   ├── scripts
   ├── site-packages
   ├── CGS.bat              # 等价于 CGS.exe *主程序* 防被杀毒软件隔离 备用
   ├── CGS.exe              # 对应 deploy/launcher/CGS.bat  *主程序*
   ├── CGS-使用说明.exe      # 对应 deploy/launcher/desc.bat
   └── CGS-更新.exe         # 对应 deploy/launcher/update.bat
```

> [点击前往GUI使用指南](https://www.veed.io/view/zh-CN/688ae765-2bfb-4deb-9495-32b24a273373?panel=comments)
> 注意看评论有补充链接（防挂），新增`v1.6 新增功能演示 视频3`

## 更新

### V1.6 | # 2024-08-27

支持 `ehentai`（准确来说是`exhentai`），程序已内置使用说明

### V1.6 | # 2024-08-26

新增翻页功能，已考虑使用场景以及做了使用的引导限制等，不再详述；<br>
需要注意的是`拷贝漫画`的翻页数使用的是`序号`而不是`页数`，对应状态栏处已做详细说明

## 功能

1. 搜索框的联想功能（按空格弹出对应预设）
2. 常规漫画工具箱功能
   > 工具箱功能配合另一个项目用 -> [点击前往项目](https://github.com/jasoneri/comic_viewer)
3. 预览功能：内置的小型浏览器，封面点击多选，条目链接浏览器体验，浏览器功能按键等。详情使用看`视频3`

## 使用

> 使用打包的，需要看下面配置说明

`python CGS.py` 正常GUI运行

`python crawl_only.py` 则是无GUI纯脚本，可用于调试等

### 配置

![](assets/conf_usage.jpg)

|            |    yml字段     |    默认值    | 说明                                                                                                                                                                                                                  |
|:-----------|:------------:|:---------:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 存储路径       |   sv_path    | D:\comic  | 下载目录                                                                                                                                                                                                                |
| 日志等级       |  log_level   | `WARNING` | 后台运行过后会有log目录，GUI 与 后台 同级，后台未知错误GUI会进行操作指引                                                                                                                                                                          |
| 代理         |   proxies    |           | 翻墙用，使用`wnacg`时可以用到，`jmcomic`用的内地域名此项对其无效                                                                                                                                                                            |
| 映射         |  custom_map  |           | 搜索输入映射 当搜索与预设不满足使用时，先在此加入键值对，重开gui在搜索框输入自定义键就会将对应网址结果输出<br/>1. 映射无需理会域名，前提是用在当前网站，只要满足 `不用映射时能访问` 和 `填入的不是无效的url`，<br/>程序会内置替换成可用的域名，如非代理下映射的`wnacg.com`会自动被替换掉<br/>2. 已无需使用映射做翻页，但注意的是自制映射有可能超出翻页规则范围，此时可通知开发者进行扩展 |
| 预设         |  completer   |           | 搜索框按<kbd>空格</kbd>弹出的内容，鼠标悬停在输入框会有`序号对应网站`的提示(其实就是选择框的序号)，视频3有介绍用法                                                                                                                                                   |
| eh_cookies |  eh_cookies  |           | 使用`ehentai`时需要，[点击查看获取方法](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/ehentai_get_cookies.gif)  ([ 国内备用查看 ](https://cdn.jsdmirror.com/gh/jasoneri/imgur@main/CGS/ehentai_get_cookies.gif))            |
| cv项目路径     | cv_proj_path |           | 没用到`comic_viewer`项目的不用管。若用到, 会联动将存储路径更新进去。若不想联动更新，此处置空                                                                                                                                                              |

> 除 `存储路径` 其他均非必须，使用默认即可 或置空 <br>
> 如熟悉yaml或其他需求，可至 `conf.yml`或`scripts/conf.yml` 修改

> [2024-08-16 未开发 开发完后会在此处更新说明]<br>
> 保留字段: `wnacg_publish_domain`, `jm_forever_url`, `jm_publish_url`<br>
> 不会进配置窗口，用作对应程序内设的 `发布页`/`永久链接` 均失效了时用户可以自设的情况

## bug记录

+ 拷贝有些漫画卷和话是分开的，只做了粗糙处理 -> ComicSpider/spiders/kaobei.py `frame_book`的注释`url`进行互换

## 其他

### 额外的脚本

`utils.script` 内含 `kemono`, `saucenao` 等脚本，详情到 [script.md](utils/script/script.md) 查阅

### 使用建议

[点击前往window终端](https://apps.microsoft.com/detail/9N0DX20HK701?launch=true&mode=full&hl=zh-cn&gl=cn&ocid=bingwebsearch)
并自行安装

开始菜单搜`终端`并打开，打开设置（快捷键 <kbd>Ctrl/Command</kbd> + <kbd>,</kbd>）<br>

1. 启动 > 默认终端应用程序 > 选择 `windows终端`<br>
2. 启动 > 新建实例行为 > 选择 `附加到最近使用的窗口`

## 交流

![](https://img.shields.io/badge/QQ群-437774506-blue.svg?colorA=abcopq)

如果感觉用着还行，希望能点亮此项目的 🌟，你的🌟将会成为开发者的开发动力

## 免责声明

详见[License](LICENSE)，切勿进行盈利，所造成的后果与本人无关。
