<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="docs/public/CGS-girl.png" alt="logo">
  </a>
  <h1 id="koishi" style="margin: 0.1em 0;">ComicGUISpider(CGS)</h1>
  <img src="https://img.shields.io/github/license/jasoneri/ComicGUISpider" alt="tag">
  <img src="https://img.shields.io/badge/Platform-Win%20|%20macOS-blue?color=#4ec820" alt="tag">
  <img src="https://img.shields.io/badge/-3.12%2B-brightgreen.svg?logo=python" alt="tag">
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

## 📑介绍

| 网站                                    | 适用区域 |    补充说明    | 状态<br>(UTC+8) |
|:--------------------------------------|:----:|:----------:|:----:|
| [拷贝漫画](https://www.2025copy.com/)    | :cn: | | ![status_kaobei](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_kaobei.json) |
| [Māngabz](https://mangabz.com)        | :cn: | 代理 | ![status_mangabz](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_mangabz.json) |
| [禁漫天堂](https://18comic.vip/)          | :cn: |     🔞     | ![status_jm](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_jm.json) |
| [绅士漫画(wnacg)](https://www.wnacg.com/) | :cn: |     🔞     | ![status_wnacg](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_wnacg.json) |
| [ExHentai](https://exhentai.org/)     | 🌏 |     🔞/代理     | ![status_ehentai](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_ehentai.json)  |
| [Hitomi](https://hitomi.la/)     | 🌏 |     🔞     | ![status_hitomi](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_hitomi.json) |
| [Kemono](https://kemono.cr)     | 🌏 |     🔞     |  |

使用请适度，以免加重对方服务器负担，也减少被封ip风险

---

**[![stars](https://img.shields.io/github/stars/jasoneri/ComicGUISpider
)](https://github.com/jasoneri/ComicGUISpider/stargazers)&nbsp;&nbsp;
关注/取消关注项目是你的自由，个人开发比较难做到一错不漏，  
提issue/群反映 → 项目改进修复，尤其对这种实时性强且多变的项目，才算得上开源社区形态...  
但无反馈/无效反馈/有效反馈比较难平衡，鉴于CGS目前还仅单人开发，反馈前三思，已阅文档已观issue而再起**

---

## 📢更新

### [![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/jasoneri/ComicGUISpider?color=blue&label=Ver&sort=semver)](https://github.com/jasoneri/ComicGUISpider/releases/latest)  [![release build-status](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml/badge.svg)](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml)

#### 🎁 Features

✅ 选网站可直接选kemono，单独窗口供后续脚本集扩展，详情看[📒使用指引](https://jasoneri.github.io/ComicGUISpider/feat/script)  
✅ 自定义背景，[配置key](https://jasoneri.github.io/ComicGUISpider/config/#bg-path)  

#### 🐞 Fix

✅ 修复包缺失导致的无法运行、kb缓存时间逻辑、内部重启的 division by zero 报错等

<details>
<summary> <code>v2.4.0-beta.3</code> 开发版特性👈看就点</summary>

#### 🎁 Features

✅ 已打包上传至 pypi ，可使用 uv tool 管理/运行 CGS [查看细则](https://jasoneri.github.io/ComicGUISpider/deploy/quick-start)  
✅ ✨支持日夜模式切换，已做字体颜色优化  

#### 🐞 Fix

✅ kemono域名更换  

🍗使用开发版遇到报错时请积极提 issue 等提供线索，谢谢
</details>

> 配置窗口左下设有`检查更新`按钮，请根据提示进行更新操作  

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
    <td><div align="center">etc..</div></td>
  </tr>  
</tbody></table>

由 [Weblate](https://hosted.weblate.org/engage/comicguispider/) 托管实现多语言的翻译  

<a href="https://hosted.weblate.org/engage/comicguispider/">
<img src="https://hosted.weblate.org/widget/comicguispider/287x66-grey.png" alt="翻译状态" />
</a>

## 🔇免责声明

详见[License](LICENSE) 当你下载或使用本项目，将默许

本项目仅供交流和学习使用，请勿用此从事 违法/商业盈利 等，开发者团队拥有本项目的最终解释权

---
![CGS](https://count.getloli.com/get/@CGS?theme=gelbooru)
