<div align="center">
  <a href="https://github.com/jasoneri/ComicSpider" target="_blank">
    <img src="assets/icon.png" alt="logo">
  </a>
  <h1 id="koishi">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg?style=social" alt="tag">
  <img src="https://img.shields.io/badge/Mode-GUI+Scrapy-blue.svg?colorA=abcdef" alt="tag">
</div>

交互式下载漫画项目，支持预览多选

▼ 操作展示 ▼ (国内如果无法看到动图 [点这里](https://jsd.cdn.zzko.cn/gh/jasoneri/imgur@main/CGS/preview-usage.gif))

![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/preview-usage.gif)

## 项目介绍

### 支持网站

| 网站          | 支持<br>(数字输入) | 预览 | 翻页 |
|:------------|:------------:|:--:|:--:|
| 拷贝漫画        |      ✅       | ❌  | 📃 |
| 禁漫天堂        |      ✅       | ✅  | 📃 |
| 绅士漫画(wnacg) |      ✅       | ✅  | 📃 |
| E-Hentai    |    开发中📃     | 📃 | 📃 |

使用请适度，以免加重对方服务器负担

> 打包好的开箱即用版，[点击前往下载页面](https://github.com/jasoneri/ComicGUISpider/releases)，包名 `CGS.7z`
> ，解压后目录树如下 <br>
> `每次解压绿色包` 后，建议先更新一次保证代码最新 <br>
> 注意: 如解压后文件缺少可能是被杀软当病毒清了，可从杀软恢复 or 联系开发者 or 临时解决：将`scripts/deploy/launcher`
> 的所有`bat`文件放到解压根目录运行

```shell
  CGS
   ├── runtime
   ├── scripts
   ├── site-packages
   ├── CGS.exe              # 对应 CGS.bat  主程序
   ├── CGS-使用说明.exe      # 对应 desc.bat
   ├── CGS-更新.exe         # 对应 update.bat
   └── _pystand_static.int
```

> [点击前往GUI使用指南](https://www.veed.io/view/zh-CN/688ae765-2bfb-4deb-9495-32b24a273373?panel=comments)
> 注意看评论有补充链接（防挂），新增`v1.6 新增功能演示 视频3`

## 更新

### V1.6 | # 2024-08-20

新增预览功能：内置小型浏览器，无需打开电脑浏览器，视频3有介绍各种用法 <br>

1. 使用预览时，增加全新的多选方式
2. 能点击其一的链接进入该本的对应页面，与浏览器体验一样
3. 功能按键 [ 窗口置顶，主页，后退，前进，刷新 ]，使用 `主页` 时能直接返回到选择页面
4. 右上`确认选择`启动后台下载

## 功能

1. 搜索框的联想功能（按空格弹出对应预设）
2. 常规漫画工具箱功能
   > 工具箱功能配合另一个项目用 -> [点击前往项目](https://github.com/jasoneri/comic_viewer)
3. 多开,设限20

## 使用

> 使用打包的，需要看下面配置说明

`python CGS.py` 正常GUI运行

`python crawl_only.py` 则是无GUI纯脚本，可用于调试等

### 配置

![](assets/conf_usage.jpg)

|        |    yml字段     |    默认值    | 说明                                                                                                                                                                                                        |
|:-------|:------------:|:---------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 存储路径   |   sv_path    | D:\comic  | 下载目录                                                                                                                                                                                                      |
| 日志等级   |  log_level   | `WARNING` | 后台运行过后会有log目录，GUI 与 后台 同级，后台未知错误GUI会进行操作指引                                                                                                                                                                |
| 代理     |   proxies    |           | 翻墙用，使用`wnacg`时可以用到，`jmcomic`用的内地域名此项对其无效                                                                                                                                                                  |
| 映射     |  custom_map  |           | 搜索输入映射 当搜索与预设不满足使用时，先在此加入键值对，重开gui在搜索框输入自定义键就会将对应网址结果输出<br/>1. 例如内置的 `更新4`, 对应的是 `wnacg` 的 更新-第4页<br/>2. 映射无需理会域名，前提是用在当前网站，只要满足 `不用映射时能访问` 和 `填入的不是无效的url`，<br/>程序会内置替换成可用的域名，如非代理下映射的`wnacg.com`会自动被替换掉 |
| 预设     |  completer   |           | 搜索框按<kbd>空格</kbd>弹出的内容，鼠标悬停在输入框会有`序号对应网站`的提示(其实就是选择框的序号)，视频3有介绍用法                                                                                                                                         |
| cv项目路径 | cv_proj_path |           | 没用到`comic_viewer`项目的不用管。若用到, 会联动将存储路径更新进去。若不想联动更新，此处置空                                                                                                                                                    |

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

## 免责声明

详见[License](LICENSE)，切勿进行盈利，所造成的后果与本人无关。
