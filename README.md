<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="docs/public/CGS-girl.png" alt="logo">
  </a>
  <h1 id="koishi" style="margin: 0.1em 0;">ComicGUISpider(CGS)</h1>
  <img src="https://img.shields.io/github/license/jasoneri/ComicGUISpider" alt="tag">
  <img src="https://img.shields.io/badge/Platform-All-blue?color=#4ec820" alt="tag">
  <img src="https://img.shields.io/badge/-%3E3.8%20%3C3.14-brightgreen.svg?logo=python" alt="tag">
  <a href="https://github.com/jasoneri/ComicGUISpider/releases" target="_blank">
    <img src="https://img.shields.io/github/downloads/jasoneri/ComicGUISpider/total?style=social&logo=github" alt="tag">
  </a>

  <p align="center">
  <a href="docs/_github/README_en.md">English</a> | 
  <a href="https://jasoneri.github.io/ComicGUISpider">🌐官方网站</a> | 
  <a href="https://jasoneri.github.io/ComicGUISpider/deploy/quick-start">🚀快速开始</a> | 
  <a href="https://jasoneri.github.io/ComicGUISpider/faq">📖FAQ</a> | 
  <a href="https://github.com/jasoneri/ComicGUISpider/releases/latest">📦绿色包下载</a>
  </p>
</div>

▼ 操作演示 ▼

|       预览/多选/翻页（[备链](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/common-usage.gif)）       |       读剪贴板（[备链](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/load_clip.gif)）       |
|:--------------------------------------------------------------------------------------------:|:-------------------------------------------------------------------------------------:|
| ![turn-page-new](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/common-usage.gif) | ![load_clip](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/load_clip.gif) |
| **聚合搜索**（[备链](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/ags.gif)） | |
| ![聚合搜索动图预留位](https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/ags.gif) | |

## 📑介绍

👉 点下 ⭐star [![stars](https://img.shields.io/github/stars/jasoneri/ComicGUISpider
)](https://github.com/jasoneri/ComicGUISpider/stargazers) &emsp;推广 `CGS` 吧 👾  

| 网站                                    | 适用区域 |    补充说明    | 状态<br>(UTC+8) |
|:--------------------------------------|:----:|:----------:|:----:|
| [拷贝漫画](https://www.2025copy.com/)    | :cn: | | ![status_kaobei](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_kaobei.json) |
| [Māngabz](https://mangabz.com)        | :cn: | | ![status_mangabz](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_mangabz.json) |
| [禁漫天堂](https://18comic.vip/)          | :cn: |     🔞     | ![status_jm](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_jm.json) |
| [绅士漫画(wnacg)](https://www.wnacg.com/) | :cn: |     🔞     | ![status_wnacg](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_wnacg.json) |
| [ExHentai](https://exhentai.org/)     | 🌏 |     🔞/代理     | ![status_ehentai](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_ehentai.json)  |
| [Hitomi](https://hitomi.la/)     | 🌏 |     🔞     | ![status_hitomi](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_hitomi.json) |
| [Kemono](https://kemono.cr)     | 🌏 |     🔞     |  |

使用请适度，以免加重对方服务器负担，也减少被封ip风险

---

**🔉提 bug 前提是 查过[文档](
https://jasoneri.github.io/ComicGUISpider/faq) 和搜过 [issue](
https://github.com/jasoneri/ComicGUISpider/issues?q=is%3Aissue%20state%3Aclosed) 等都没处理方法的，否则会被 [这样回复](
https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way/blob/main/README-zh_CN.md#%E5%A5%BD%E9%97%AE%E9%A2%98%E4%B8%8E%E8%A0%A2%E9%97%AE%E9%A2%98)**

---

## 📢更新

### [![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/jasoneri/ComicGUISpider?color=blue&label=Ver&sort=semver)](https://github.com/jasoneri/ComicGUISpider/releases/latest)  [![release build-status](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml/badge.svg)](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml)

#### 🎁 Features

✅ 新增`聚合搜索`功能，具体看 [适用性](
https://jasoneri.github.io/ComicGUISpider/feat/#%E9%80%82%E7%94%A8%E6%80%A7) 和 [功能介绍](
https://jasoneri.github.io/ComicGUISpider/feat/ags)

#### 🐞 Fix

✅ 较多任务时自动降并发  
✅ 修复 wnacg 发布页域名解析  
✅ wnacg 已设代理下跳过域名缓存处理  
✅ 排除 jm 的猜你喜欢的12本，空搜索时即空  
✅ 优化 jm 剪贴板正则格式匹配  
☑️【长驻提示】`avif依赖` 与 `python3.14` 不兼容，针对初始安装脚本/说明等做了版本限制  

> 可参考 [更新方法](https://jasoneri.github.io//ComicGUISpider/deploy/quick-start.html#_4-%E6%9B%B4%E6%96%B0) 进行更新  

> [🕑更新历史](docs/changelog/history.md) / [📝开发板](https://github.com/jasoneri/ComicGUISpider/projects?query=is%3Aopen)

## 🍮食用搭配(阅读器)

完全适配 CGS ， `rV (redViewer)`  
已内置显眼按钮以及小窗管理，后续会基于 rV 展开  

[![点击前往redViewer](https://github-readme-stats.vercel.app/api/pin/?username=jasoneri&repo=redViewer&show_icons=true&bg_color=60,ef4057,cf4057,c44490&title_color=4df5b4&hide_border=true&icon_color=e9ede1&text_color=e9ede1)](https://github.com/jasoneri/redViewer)

## 💝感谢以下开源项目

<table><tbody>  
  <tr>
    <td><div align="center"><a href="https://github.com/skywind3000/PyStand" target="_blank">
      PyStand
    </a></div></td>
    <td><div align="center"><a href="https://github.com/sveinbjornt/Platypus" target="_blank">
      <img src="https://jsd.vxo.im/gh/sveinbjornt/Platypus/Documentation/images/platypus.png" alt="logo" height="50">
      <br>Platypus</a></div></td>
    <td><div align="center"><a href="https://github.com/sabrogden/Ditto" target="_blank">
      <img src="https://avatars.githubusercontent.com/u/16867884?v=4" alt="logo" height="50">
      <br>Ditto</a></div></td>
    <td><div align="center"><a href="https://github.com/p0deje/Maccy" target="_blank">
      <img src="https://maccy.app/img/maccy/Logo.png" alt="logo" height="50">
      <br>Maccy</a></div></td>
    <td><div align="center"><a href="https://github.com/astral-sh/uv" target="_blank">
      <img src="https://docs.astral.sh/uv/assets/logo-letter.svg" alt="logo" height="50">
      <br>uv</a></div></td>
    <td><div align="center">etc..</div></td>
  </tr>  
</tbody></table>

由 [Weblate](https://hosted.weblate.org/engage/comicguispider/) 托管实现多语言的翻译  

<a href="https://hosted.weblate.org/engage/comicguispider/">
<img src="https://hosted.weblate.org/widget/comicguispider/287x66-grey.png" alt="翻译状态" />
</a>

<a href="https://afdian.com/a/jsoneri">
  <img src="https://raw.githubusercontent.com/jasoneri/imgur/main/CGS/CGS-aifadian.png" alt="在爱发电支持我">
</a>

## 🔇免责声明

详见[License](LICENSE) 当你下载或使用本项目，将默许

本项目仅供交流和学习使用，请勿用此从事 违法/商业盈利 等，开发者团队拥有本项目的最终解释权

---
![CGS](https://count.getloli.com/get/@CGS?theme=gelbooru)
