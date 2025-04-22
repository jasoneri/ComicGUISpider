<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="../public/CGS-girl.png" alt="logo">
  </a>
  <h1 id="koishi"style="margin: 0.1em 0;">ComicGUISpider</h1>
  <img src="https://img.shields.io/badge/-3.12%2B-brightgreen.svg?logo=python" alt="tag">
  <img src="https://img.shields.io/badge/By-Qt5_&_Scrapy-blue.svg?colorA=abcdef" alt="tag">
  <img src="https://img.shields.io/badge/Platform-Win%20|%20macOS-blue?color=#4ec820" alt="tag">
  <a href="https://github.com/jasoneri/ComicGUISpider/releases" target="_blank">
    <img src="https://img.shields.io/github/downloads/jasoneri/ComicGUISpider/total?style=social&logo=github" alt="tag">
  </a>

  <p align="center">
  <a href="https://jasoneri.github.io/ComicGUISpider/locate/en/">🌐website</a> | 
  <a href="https://github.com/jasoneri/ComicGUISpider/releases/latest">📦portable-pkg</a>
  </p>

</div>

▼ Demo ▼

|                             Preview / Multi-select / Paging                              |                         Clipboard Tasks                         |
|:-------------------------------------------------------------------------------:|:----------------------------------------------------------------------------:|
| ![turn-page-new](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/common-usage.gif) | ![load_clip](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/load_clip.gif) |

## 📑 Introduction

### Supported Websites

| Website                                 | locale |          Notes          |                                               status<br>(UTC+8)                                                |
|:----------------------------------------|:------:|:-----------------------:|:--------------------------------------------------------------------------------------------------------------:|
| [MangaCopy](https://www.mangacopy.com/) |  :cn:  | Hidden content unlocked |  ![status_kaobei](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_kaobei.json)  |
| [Māngabz](https://mangabz.com)          |  :cn:  |                         | ![status_mangabz](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_mangabz.json) |
| [18comic](https://18comic.vip/)         |  :cn:  |           🔞            |      ![status_jm](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_jm.json)      |
| [wnacg](https://www.wnacg.com/)         |  :cn:  |           🔞            |   ![status_wnacg](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_wnacg.json)   |
| [ExHentai](https://exhentai.org/)       |   🌏   |           🔞            | ![status_ehentai](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_ehentai.json) |

<hr>

## 📜Contributing

now support simple `en-US` of Ui, but still need help for i18n of maintenance, such as Documentation  

Come here [🌏i18n Guide](../dev/i18n.md)

<hr>

## 📢 Changelog

Left-bottom of the config-dialog has `Check Update` button, please update according to the prompt

> [🕑Full History](docs/UPDATE_RECORD.md)

## 🚀 Usage

### GUI

`python CGS.py`

### CLI

`python crawl_only.py --help`  
Or using env of portable package:  
`.\runtime\python.exe .\scripts\crawl_only.py --help`

## 🔨 Configuration

![](../assets/img/config/conf_usage_en.png)

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
| eh_cookies    | -           | Required for ExHentai<br>[🔗view how to gei it](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/ehentai_get_cookies_new.gif)<br>[🔗Tool Website](https://tool.lu/en_US/curl/)             |
| clip_db    | -           |  [Ditto](https://github.com/sabrogden/Ditto) or [Maccy](https://github.com/p0deje/Maccy) 's local db path |
| clip_read_num    | 20           | - |

</details>

## 🔇 Disclaimer

See [License](LICENSE). By using this project you agree to:

- Non-commercial use only
- Developer's final interpretation

---
![CGS_en](https://count.getloli.com/get/@CGS_en?theme=rule34)
