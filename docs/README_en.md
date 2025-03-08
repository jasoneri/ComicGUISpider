<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="../assets/icon.png" alt="logo">
  </a>
  <h1 id="koishi">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/-3.12%2B-brightgreen.svg?logo=python" alt="tag">
  <img src="https://img.shields.io/badge/By-Qt5_&_Scrapy-blue.svg?colorA=abcdef" alt="tag">
  <img src="https://img.shields.io/badge/Platform-Win%20|%20macOS-blue?color=#4ec820" alt="tag">
  <a href="https://github.com/jasoneri/ComicGUISpider/releases" target="_blank">
    <img src="https://img.shields.io/github/downloads/jasoneri/ComicGUISpider/total?style=social&logo=github" alt="tag">
  </a>

  <p><a href="https://git.io/typing-svg"><img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=28&duration=2500&pause=1800&color=13C8C3&center=true&vCenter=true&multiline=true&width=950&height=100&lines=CGS%2C++A+comic%2Fmanga+download+software;which+support+preview+and+turn-page+and+read+Clipboard" alt="Typing SVG" /></a></p>

</div>

▼ Demo ▼

|  Preview & Multi-select  | Paging & Selection Retention |
|:--------------------------------------------------------------------------------:|:----------------------------------------------------------------------------:|
| ![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/preview-usage.gif) | ![](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/turn-page.gif) |

## 📑 Introduction

### Supported Websites

| Website  | Preview<br/>(Multi-select) | Paging  | Clipboard | Notes         |
|:--------------------------------------|:-------------:|:---------:|:----:|:----------:|
| [MangaCopy](https://www.mangacopy.com/) | ❌ | ✅ | ❌ | Hidden content unlocked |
| [Māngabz](https://mangabz.com)        | ❌ | ✅ | ❌ |  |
| [18comic](https://18comic.vip/)       | ✅ | ✅ | ✅ | 🔞         |
| [wnacg](https://www.wnacg.com/)       | ✅ | ✅ | ✅ | 🔞         |
| [ExHentai](https://exhentai.org/)     | ✅ | ✅<br/>(No redirect) | ✅ | 🔞         |

<table><tbody>  
  <tr>
    <td>CGS Navigation</td>
    <td><a href="https://github.com/jasoneri/ComicGUISpider/releases/latest">🔗 Portable Package</a></td>
    <td><a href="https://www.veed.io/view/zh-CN/688ae765-2bfb-4deb-9495-32b24a273373?panel=comments">🔗 GUI Guide (Video)</a></td>  
    <td><a href="deploy/launcher/mac/EXTRA.md">🔗 macOS Notes</a></td> 
  </tr>  
</tbody></table>

<hr>

**☝️😋 Star this repo to boost development karma! Your ⭐ makes CGS better!**
![](https://img.shields.io/github/stars/jasoneri/ComicGUISpider)

<hr>

## 🌏I18N / Localization Support

If you find this project valuable and would like to help translate it into your native language, we warmly welcome your contribution!

Some step like:

+ Submit translation PRs for existing languages
+ Propose support for new languages
+ Improve existing translations

📮 Contact maintainer on [Discussions](https://github.com/jasoneri/ComicGUISpider/discussions/24) for assistance.

## 📢 Changelog

> Following semantic versioning. Check [beta releases](https://github.com/jasoneri/ComicGUISpider/releases) between stable versions.

### v1.7.5 | ~ 2025-03-01

#### 🐞 Fixes

+ Serial number input extension: supports a single negative number, e.g. '-3' indicates selecting the last three
+ compatibility with clipboard-preview-window releated
+ fixes error prompt, e.g. [WinError 10054]

> [Full History](https://github.com/jasoneri/ComicGUISpider/wiki/%E6%9B%B4%E6%96%B0%E8%AE%B0%E5%BD%95-update-record)

## 📚 Features

1. Search suggestions (<kbd>Space</kbd> trigger)
2. Preview window with browser-like features
3. Paging functionality (see demo)
4. Toolbox:
   - Clipboard reading (🔞 sites)
   - Reading records integration
   - Chapter consolidation

## 🚀 Usage

### GUI
`python CGS.py`

### CLI <a id="cli"></a>
`python crawl_only.py --help`  
Or using env of portable package:  
`.\runtime\python.exe .\scripts\crawl_only.py --help`

## 🔨 Configuration

![](../assets/conf_usage.jpg)
<details>
<summary>Config Details</summary>

| Yaml-Field         | Default      | Description                          |
|:--------------|:------------|:-------------------------------------|
| sv_path  | D:\comic    | Download directory                  |
| log_level     | WARNING     | Log verbosity                       |
| isDeduplicate | false       | Auto-skip downloaded content (🔞)   |
| addUuid       |    false   | Add uuid set end of the title durning folder naming |
| proxies         | -           | Proxy settings                     |
| custom_map         | -           | -                     |
| completer         | -           | Completer of search-input |
| eh_cookies    | -           | Required for ExHentai, [🔗view how to gei it](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/ehentai_get_cookies_new.gif)              |
| clip_db    | -           |  [Ditto](https://github.com/sabrogden/Ditto) or [Maccy](https://github.com/p0deje/Maccy) 's local db path |
| clip_read_num    | 20           | - |
| cv_proj_path    | -           | - |

</details>

## ❓ FAQ

### 1. Preview layout issues

Refresh page if JavaScript fails to load

### 2. Configuration effective releated

Most settings require restart after website selection  
Except completer

### 3. Somethins wrong with Qt5

> [Check Qt error collection](https://github.com/jasoneri/ComicGUISpider/wiki/Qt%E6%8A%A5%E9%94%99%E9%9B%86%E5%90%88)

## 🔰 Extras

### Scripts Extras
About `kemono`/`saucenao` utilities

## 🔇 Disclaimer
See [License](LICENSE). By using this project you agree to:
- Non-commercial use only
- Developer's final interpretation


---
![CGS_en](https://count.getloli.com/get/@CGS_en?theme=rule34)
