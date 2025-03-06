**| [English](docs/README_en.md) | 简体中文 |**

<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="assets/icon.png" alt="logo">
  </a>
  <h1 id="koishi">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/-3.12%2B-brightgreen.svg?logo=python" alt="tag">
  <img src="https://img.shields.io/badge/By-Qt5_&_Scrapy-blue.svg?colorA=abcdef" alt="tag">
  <a href="https://github.com/jasoneri/ComicGUISpider/releases" target="_blank">
    <img src="https://img.shields.io/github/downloads/jasoneri/ComicGUISpider/total?style=social&logo=github" alt="tag">
  </a>

  <p><a href="https://github.com/jasoneri/ComicGUISpider"><img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=32&duration=2500&pause=2500&color=13C8C3&center=true&vCenter=true&width=800&lines=CGS%EF%BC%8C%E4%B8%80%E4%B8%AA%E8%83%BD%E9%A2%84%E8%A7%88%2F%E7%BF%BB%E9%A1%B5%2F%E8%AF%BB%E5%89%AA%E8%B4%B4%E6%9D%BF%E7%AD%89%E5%8A%9F%E8%83%BD%E7%9A%84%E6%BC%AB%E7%94%BB%E4%B8%8B%E8%BD%BD%E8%BD%AF%E4%BB%B6" alt="Typing SVG" /></a></p>

</div>

▼ 操作演示 ▼

|  预览、多选（[国内备链](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/preview-usage.gif)）  | 翻页、保留选择（[国内备链](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/turn-page.gif)） |
|:--------------------------------------------------------------------------------:|:----------------------------------------------------------------------------:|
| ![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/preview-usage.gif) | ![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/turn-page.gif) |

## 📑介绍

### 支持网站/功能

| 网站                                    |  预览<br/>(点击多选) |    翻页     | 读剪贴板 |    补充说明    |
|:--------------------------------------|:-------------:|:---------:|:----:|:----------:|
| [拷贝漫画](https://www.mangacopy.com/)    |       ❌       |     ✅     |  ❌   |   已解锁隐藏    |
| [Māngabz](https://mangabz.com)        |       ❌       |     ✅     |  ❌   | 代理 |
| [禁漫天堂](https://18comic.vip/)          |       ✅       |     ✅     |  ✅   |     🔞     |
| [绅士漫画(wnacg)](https://www.wnacg.com/) |       ✅       |     ✅     |  ✅   |     🔞<br>不fan墙需求看[QA第三条](#-q--a-问答)     |
| [ExHentai](https://exhentai.org/)     |       ✅       | ✅<br/>禁跳转 |  ✅   |     🔞/代理     |

使用请适度，以免加重对方服务器负担，也减少被封ip风险

<table><tbody>  
  <tr>
    <td>CGS导航</td>
    <td><a href="https://github.com/jasoneri/ComicGUISpider/releases/latest">🔗开箱即用绿色包下载</a></td>
    <td><a href="https://www.veed.io/view/zh-CN/688ae765-2bfb-4deb-9495-32b24a273373?panel=comments">🔗GUI使用指南(视频，注意评论跳链)</a></td>  
    <td><a href="deploy/launcher/mac/EXTRA.md">🔗macOS必读的补充说明</a></td> 
  </tr>  
</tbody></table>

<hr>

**☝️😋收藏夹吃灰？不如点⭐Star给作者加赛博功德(*￣∇￣*) 你的⭐Star会让CGS升级更快！**
![](https://img.shields.io/github/stars/jasoneri/ComicGUISpider)

<hr>

## 📢更新

> 现遵从`语义版本控制`，到下一稳定版之间至少会有一个[`Pre-release`的
`beta`开发版](https://github.com/jasoneri/ComicGUISpider/releases)

### v1.7.6 | ~ 2025-03-06

#### 🐞 Fix

+ 修复输入框常规输入无法正常使用
+ 命令行工具相关
  + 修复细化任务后带来的只停留在下载第一页问题
  + 修复参数使用负数无法正常使用的问题

> [点击查看更新历史](https://github.com/jasoneri/ComicGUISpider/wiki/%E6%9B%B4%E6%96%B0%E8%AE%B0%E5%BD%95-update-record)

## 📚功能

1. 搜索框的联想功能（ 按 <kbd>空格</kbd> 弹出对应预设 ）
2. 预览功能：内置的小型浏览器，封面点击多选，条目链接浏览器体验，浏览器功能按键等。详情使用看`视频3`
3. 翻页：当有列表结果出来后开启使用，使用如上面动图所示

| 4.工具箱  | 仅用于.. | 说明                                                                                                                                                                                                                                 |
|:-------|:-----:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 读剪贴板.. |  🔞网  | 读剪贴板匹配生成任务，需配合剪贴板软件使用（自行下载安装），win为 [Ditto](https://github.com/sabrogden/Ditto)、macOS为 [Maccy](https://github.com/p0deje/Maccy)。<br>该功能流程使用看`视频3`相关部分，此功能的使用说明以及后续的更新细则等将放在任务页面右上的`额外说明`<br>｛不下载剪贴板软件仅会影响`读剪贴板`这一功能而已，不影响软件常规流程的使用｝ |
| 显示记录.. | 常规漫画网 | 需配合 [comic_viewer项目](https://github.com/jasoneri/comic_viewer) 使用，用其阅读后产生的记录文件能知道从哪一话开始下起                                                                                                                                          |
| 整合章节.. | 常规漫画网 | 批量整合，例如将`D:\Comic\蓝箱\165\第1页`整合转至`D:\Comic\web\蓝箱_165\第1页`（使用comic_viewer项目需要此目录结构）                                                                                                                                                |

## 🚀使用

### 常规GUI运行

`python CGS.py`

### 命令行工具 <a id="命令行cli"></a>

`python crawl_only.py --help`  
或使用绿色包的环境，在解压目录打开终端执行`.\runtime\python.exe .\scripts\crawl_only.py --help`

> 当前版本能进行简单下载/调试功能，使用方法进help看说明  
> 后续将逐步扩展命令行工具/参数  
> 命令行工具的配置可用GUI方式修改 或 直接修改`scripts/conf.yml`文件

## 🔨配置

> 有关生效时间节点请查阅 [Q&A 第二点](#2-配置生效相关)

![](assets/conf_usage.jpg)
<details>
<summary>配置详细说明(点击展开)</summary>

|            |     yml字段     |    默认值    | 说明                                                                                                                                                                                                                                                      |
|:-----------|:-------------:|:---------:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 存储路径       |    sv_path    | D:\comic  | 下载目录（内容目录结构里还有个`web`文件夹的情况是因为默认关联[`comic_viewer`项目](https://github.com/jasoneri/comic_viewer)所以这样设置的）                                                                                                                                                   |
| 日志等级       |   log_level   | `WARNING` | 后台运行过后会有log目录，GUI 与 后台 同级，报错时GUI会进行操作指引                                                                                                                                                                                                                 |
| 去重         | isDeduplicate |   false   | <a id="配置"></a>勾选状态下，点预览时会额外花点时间查记录并做出相应样式提示，同时下载也会自动过滤已存在的记录<br>当前仅🔞网适用                                                                                                                                                                               |
| 增加标识       |    addUuid    |   false   | 存储时目录最后增加标识，用以处理同一命名的不同作品等                                                                                                                                                                                                                              |
| 代理         |    proxies    |           | 翻墙用，（已设置`jm`无论用全局还是怎样都只走本地原生ip）<br/>（建议使用代理模式在此配置代理，而非全局代理模式，不然访问图源会吃走大量代理的流量）                                                                                                                                                                          |
| 映射         |  custom_map   |           | 搜索输入映射 当搜索与预设不满足使用时，先在此加入键值对，重开gui在搜索框输入自定义键就会将对应网址结果输出，视频3有介绍用法<br/>1. 映射无需理会域名，前提是用在当前网站，只要满足 `不用映射时能访问` 和 `填入的不是无效的url`，<br/>程序会内置替换成可用的域名，如非代理下映射的`wnacg.com`会自动被替换掉<br/>2. 注意自制的映射有可能超出翻页规则范围，此时可通知开发者进行扩展                                         |
| 预设         |   completer   |           | 搜索框按<kbd>空格</kbd>弹出的内容，鼠标悬停在输入框会有`序号对应网站`的提示(其实就是选择框的序号)，视频3有介绍用法                                                                                                                                                                                       |
| eh_cookies |  eh_cookies   |           | 使用`exhentai`时必需，[🔗点击查看获取方法](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/ehentai_get_cookies_new.gif)  ([ 国内备链 ](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/ehentai_get_cookies_new.gif))<br/> [🔗动图中的curl转换网站](https://tool.lu/curl/) |
| 剪贴板db      |    clip_db    |           | 默认读取剪贴板软件的数据库初设路径<br>如相关功能无法使用时可自行查看路径是否一致，并在此更改<br>1. ditto(win): 打开选项 → 数据库路径 <br>2.maccy(macOS): [issue搜索相关得知](https://github.com/p0deje/Maccy/issues/271)                                                                                           |
| 读取条数       | clip_read_num |    20     | 读取剪贴板软件条目数量，需少于剪贴板软件设置的最大数量 (建议少量多次)                                                                                                                                                                                                                    |
| cv项目路径     | cv_proj_path  |           | 没用到`comic_viewer`项目的不用管。若用到, 会联动将存储路径更新进去（若不想联动更新，随便写个无关路径）                                                                                                                                                                                             |

</details>

> 除 `存储路径` 其他均非必须，使用默认即可 或置空  
> 配置文件为 `scripts/conf.yml`

## ❓ Q & A 问答

### 1. 预览窗口选择页面有时一行只有一列/显示有问题/页面空白

JavaScript 没加载出来，刷新一下页面

### 2. 配置生效相关 <a id="2-配置生效相关"></a>

除少部分条目例如预设(只影响gui)，能当即保存时立即生效(保存配置的操作与gui同一进程);  
其余影响后台进程的配置条目在选择网站后定型(点选网站后`后台进程`即开始)，如果选网站后才反应过来改配置，需retry重启方可生效

### 3. 域名相关说明

各网站的 `发布页`/`永久链接` 能在 `scripts/utils/website/__init__.py` 里找到  
（国内域名专用）域名缓存文件为`scripts/__temp/xxx_domain.txt`，再开程序会检测修改时间大于24小时则失效重新获取，处于24小时内则可对此文件删改即时生效
> `发布页`/`永久链接`失效的情况下鼓励用户向开发者提供新可用网址，让软件能够持续使用  

> [20250306]`wnacg`相关1: 对发布页做了访问限制，要想全程墙内访问的临时解决手段是手动改域名缓存文件，参考[🔗讨论](https://github.com/jasoneri/ComicGUISpider/discussions/22)  
> 2. 图片似乎变得要开全局代理手段解决，好像edge又能访问... 先静观其变

### 4. 拷贝漫画部分无法出列表

拷贝有些漫画卷和话是分开的，api结构转换的当前是有结果的，但是没做解析，如需前往群里反馈

### 5. 拷贝/Māngabz多选书情况

多选了书时，在章节序号输入环节中可以直接点击`开始爬取`跳过当前书的章节选择，只要直到出进度条即可

### 6. <win系统独占>弹出消息框报错而且一堆英文不是中文(非开发者预设报错)的时候

前往查阅 [🔗Qt报错集合](https://github.com/jasoneri/ComicGUISpider/wiki/Qt%E6%8A%A5%E9%94%99%E9%9B%86%E5%90%88)

### 7. 使用遇到问题想寻求帮助或报错，但没有github账号

看下方交流群，但提问格式请参考 [issue的样式](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/issue-format.png)
，一句连标点符号都不带没有上下文的话并不是一个好问题/反馈

## 🔰其他
### 漫画观看方式自荐

[![点击前往comic_viewer](https://github-readme-stats.vercel.app/api/pin/?username=jasoneri&repo=comic_viewer)](https://github.com/jasoneri/comic_viewer)

### 额外的脚本集

`utils.script.image` 内含 `kemono`, `saucenao` 等脚本，详情到 [script.md](docs/script.md) 查阅

### 扩展支持网站的讨论

前往[🔗Discussions](https://github.com/jasoneri/ComicGUISpider/discussions/16)

> 开发力紧张，需5票以上启动计划，避免费力开发没人用  
> 可自行发起投票，并在置顶贴里留下对应指向

### 使用建议

终端显示优化，
前往[🔗window终端](https://apps.microsoft.com/detail/9N0DX20HK701?launch=true&mode=full&hl=zh-cn&gl=cn&ocid=bingwebsearch)
并自行安装 ~~建议升级win11~~

## 💬交流

![](https://img.shields.io/badge/QQ群-437774506-blue.svg?colorA=abcopq)

## 🔇免责声明

详见[License](LICENSE) 当你下载或使用本项目，将默许

本项目仅供交流和学习使用，请勿用此从事 违法/商业盈利 等，开发者团队拥有本项目的最终解释权

---
![CGS](https://count.getloli.com/get/@CGS?theme=gelbooru)
