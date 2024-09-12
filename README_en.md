**| English | [简体中文](README.md) |**

<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="assets/icon.png" alt="logo">
  </a>
  <h1 id="koishi">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg?style=social" alt="tag">
  <img src="https://img.shields.io/badge/Mode-GUI+Scrapy-blue.svg?colorA=abcdef" alt="tag">

  <p><a href="https://git.io/typing-svg"><img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=28&duration=2500&pause=1800&color=13C8C3&center=true&vCenter=true&multiline=true&width=950&height=100&lines=CGS%2C++A+comic%2Fmanga+download+software;which+support+preview(multiple+choice)+and+turn-page" alt="Typing SVG" /></a></p>
</div>

▼ demo show ▼

|                             preview, multiple choice                             |                            turn page, keep choice                            |
|:--------------------------------------------------------------------------------:|:----------------------------------------------------------------------------:|
| ![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/preview-usage.gif) | ![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/turn-page.gif) |

## 🌏I18N

I'm not sure someone will interested in this project with English or other language,<br>
but some work were ongoing such as [inner-text-description](assets/res/__init__.py), as my current env is zh-cn, I put
the contents of my env file [zh_cn.py](assets/zh_cn.py) into it. <br>
It mean anyone can create `en.py` translated by chatgpt etc. , put contents into `assets/res/__init__.py`, then
software's inner-text-description will change into language of en.

As the beginning I said, if someone tell me needs of language is existed, I'm pleasure to promote translation work. <br>
or PR about translation is great !!

## 📑Introduce

### website

| website   | support<br>(digital inputs) | preview<br/>(multiple choice) |    pageTurn    |
|:----------|:---------------------------:|:-----------------------------:|:--------------:|
| mangacopy |              ✅              |               ❌               |       ✅        |
| jm-comic  |              ✅              |               ✅               |       ✅        |
| wnacg     |              ✅              |               ✅               |       ✅        |
| ExHentai  |              ✅              |               ✅               | ✅<br/>ban jump |

Please use it in moderation to avoid burdening the other party's server

> Portable Software，[click it go to the dl-page](https://github.com/jasoneri/ComicGUISpider/releases)，package
> name: `CGS.7z`
> ，below is the directory tree extracted out<br>
> recommend: use refresh-exe to keep code latest when each unzip time <br>

```shell
  CGS
   ├── runtime
   ├── scripts
   ├── site-packages
   ├── CGS.bat              # equal to CGS.exe *Main-Executor* Prevent isolation by anti-virus software 
   ├── CGS.exe              # equal to deploy/launcher/CGS.bat  *Main-Executor*
   ├── CGS-使用说明.exe      # equal to deploy/launcher/desc.bat
   └── CGS-更新.exe         # equal to deploy/launcher/update.bat
```

> [here is the GUI usage video (but chinese)](https://www.veed.io/view/zh-CN/688ae765-2bfb-4deb-9495-32b24a273373?panel=comments)

## 🚀Usage

> Portable Version: `CGS.exe` / `CGS.bat`

`python CGS.py` for GUI run

`python crawl_only.py` for backend only, or debug

## 🔨Config

![](assets/conf_usage.jpg)

|              |  yml field   |  default  | description                                                                                         |
|:-------------|:------------:|:---------:|:----------------------------------------------------------------------------------------------------|
| sv_path      |   sv_path    | D:\comic  |                                                                                                     |
| log_level    |  log_level   | `WARNING` |                                                                                                     |
| proxies      |   proxies    |           |                                                                                                     |
| custom_map   |  custom_map  |           |                                                                                                     |
| completer    |  completer   |           |                                                                                                     |
| eh_cookies   |  eh_cookies  |           | [demo to get it](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/ehentai_get_cookies.gif) |
| cv_proj_path | cv_proj_path |           |                                                                                                     |

## 🔰Else

### Suggestion

[using window terminal](https://apps.microsoft.com/detail/9N0DX20HK701?launch=true&mode=full&hl=zh-cn&gl=cn&ocid=bingwebsearch)
install bt self

## 🔇Disclaimer

see [License](LICENSE)，do not make profit by this project.

![CGS_en](https://count.getloli.com/get/@CGS_en?theme=rule34)
