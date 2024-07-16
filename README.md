# ComicSpider

![](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg?style=social) ![](https://img.shields.io/badge/Mode-GUI+Scrapy-blue.svg?colorA=abcdef)  
目前是一个交互式下漫画的项目  

## 更新

+ V1.5 | # 2024-07-16
    1. 新增jm-comic
       > 注意点：gui显示的顺序是没错的，但网站缓存做得稀烂，需要每次浏览器清除该网cookies(用搜索时不用清也行)
       ，确保gui顺序跟浏览器顺序一致再选
    2.
    增加搜索输入框的联想功能（按空格弹出来预设），增加常规漫画工具箱功能（配合另一个项目用 -> [手机看漫画](https://github.com/jasoneri/comic_viewer)）
    3. 常规漫画网站下（拷贝）避免选择多书，长链路下不稳定，若想同时下多本则开多个脚本分别搜索即可（可多开20进程）

## 一、简述  
![EXE简图](https://github.com/jasoneri/ComicSpider/blob/GUI/GUI/exe.jpg)

不打包了，有人看到issue我再说或者心血来潮搞github flow

> 入口是crawl_go.py 或 crawl_only.py

## 二、配置setting.yml

```yaml
## 配置文件，使用方法详情至readme.md了解

sv_path: D:\Comic
log_level: DEBUG  # DEBUG|INFO|ERROR 默认WARNING
proxies:
  - 127.0.0.1:10809
custom_map:
  更新4: https://wnacg.com/albums-index-page-4.html
  杂志: https://wnacg.com/albums-index-cate-10.html
  恥: https://wnacg.com/albums-index-tag-%E6%81%A5.html
```

### 字段说明

+ sv_path -> 下载目录 默认为 D:\comic
+ proxies -> ip代理 使用wnacg时需要用到，jmcomic用的内地域名此项对其无效
+ custom_map -> 搜索输入映射 当搜索与预设不满足使用时，先在此加入键值对，此时gui搜索框输入自定义键就会将对应网址结果输出
+ log_level -> 日志等级 后台有运行过会有log目录，GUI记录界面操作记录默认为INFO，scrapy默认为WARNING，未知错误使用DEBUG进行记录吧

> 除 `sv_path` 其他均非必须，行首#注释掉即可

------

## 【 bug记录 】

+ 拷贝有些漫画卷和话是分开的，只做了粗糙处理 -> ComicSpider/spiders/kaobei.py 98:13