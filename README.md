<div align="center">
  <a href="https://github.com/jasoneri/ComicSpider" target="_blank">
    <img src="assets/icon.png" alt="logo">
  </a>
  <h1 id="koishi">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg?style=social" alt="tag">
  <img src="https://img.shields.io/badge/Mode-GUI+Scrapy-blue.svg?colorA=abcdef" alt="tag">
</div>

交互式下载漫画项目

## 项目介绍

支持拷贝漫画，禁漫天堂，wnacg

使用请适度，以免加重对方服务器负担

> 打包好的开箱即用版，[点击前往下载页面](https://github.com/jasoneri/ComicGUISpider/releases)，包名 `CGS.7z` <br>
> 内置更新程序 `CGS-更新.exe` 直接更新代码，一般情况下更新代码不必重新下载包<br>
> `第一次使用` 或 `每次解压绿色包` 后，建议先更新一次保证代码最新

> [点击前往GUI使用指南](https://www.veed.io/view/zh-CN/688ae765-2bfb-4deb-9495-32b24a273373?panel=comments)
> 注意看评论有补充链接（防挂）

> `wnacg` 补充说明: 没设置代理的情况下，程序会使用发布页获取国内可访问的域名。<br>
> 但实测响应有点慢，自动使用国内源时还请留意，属于正常现象

## 更新

### V1.6 | # 2024-08-xx

1. （尚未完成）追加预览：内置小型浏览器，可进行预览（无需打开电脑浏览器）

### V1.5 | # 2024-07-16

1. 新增jm-comic(禁漫天堂)
   > 注意点：gui显示的顺序是没错的，但pc网站缓存做得有点。。如序号对应的标题跟肉眼所示对不上可尝试清除浏览器上该网的cookies(
   用搜索时一般没事)
   ，确保gui顺序跟浏览器顺序一致再选
2. 增加搜索输入框的联想功能（按空格弹出来预设），增加常规漫画工具箱功能
   > 工具箱功能配合另一个项目用 -> [点击前往项目](https://github.com/jasoneri/comic_viewer)
3. 常规漫画网站下（拷贝漫画）避免选择多书，长链路下不稳定，若想同时下多本则开多个脚本分别搜索即可（可多开20进程）

## 使用

> 使用打包的，需要看下面配置说明

`python CGS.py` 正常GUI运行

`python crawl_only.py` 则是无GUI纯脚本，可用于调试等

### 配置

> 程序内已内置了 `配置更改` 按键<br>
> （如熟悉yaml或其他需求，可至 `conf.yml`或`scripts/conf.yml` 修改）

![](assets/conf_usage.jpg)

#### 说明

+ 存储路径(`sv_path`)：下载目录 默认为 `D:\comic`
+ 日志等级(`log_level`)：后台有运行过会有log目录，GUI记录界面操作记录默认为INFO，scrapy默认为WARNING，未知错误使用DEBUG进行记录吧
+ 代理(`proxies`)：翻墙用，使用`wnacg`时可以用到，`jmcomic`用的内地域名此项对其无效
+ 映射(`custom_map`)： 搜索输入映射 当搜索与预设不满足使用时，先在此加入键值对，重开gui在搜索框输入自定义键就会将对应网址结果输出
    1. 例如内置的 `更新4`, 对应的是 `wnacg` 的 更新-第4页
    2. 映射无需理会域名，只要满足 `不用映射时能访问` 和 `填入的不是无效的url`
       ，程序会内置替换成可用的域名，如非代理下映射的`wnacg.com`会自动替换掉
+ cv项目路径(`cv_proj_path`)：没用到`comic_viewer`项目的不用管。若用到, 会联动将存储路径更新进去。若不想联动更新，此处置空

> 括号内对应`conf.yml`的字段<br>
> 除 `存储路径` 其他均非必须，使用默认即可 或置空

> [2024-08-16 未开发 开发完后会在此处更新说明]<br>
> 保留字段: `wnacg_publish_domain`, `jm_forever_url`, `jm_publish_url`<br>
> 不会进配置窗口，用作对应程序内设的 `发布页`/`永久链接` 均失效了时用户可以自设的情况

## bug记录

+ 拷贝有些漫画卷和话是分开的，只做了粗糙处理 -> ComicSpider/spiders/kaobei.py 97与98行注释互换

## 其他

### 额外的脚本

`utils.script` 内含 `kemono`, `saucenao` 等脚本，详情到 [script.md](utils/script/script.md) 查阅

### 使用建议

[点击前往window终端](https://apps.microsoft.com/detail/9N0DX20HK701?launch=true&mode=full&hl=zh-cn&gl=cn&ocid=bingwebsearch)
并自行安装

开始菜单搜`终端`并打开，打开设置（标题栏空白处右键 / `ctrl+逗号` 等方法）<br>

1. 启动 > 默认终端应用程序 > 选择 `windows终端`<br>
2. 启动 > 新建实例行为 > 选择 `附加到最近使用的窗口`

## 交流

群 437774506

## 免责声明

详见[License](LICENSE)，切勿进行盈利，所造成的后果与本人无关。
