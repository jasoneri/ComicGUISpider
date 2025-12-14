<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="https://img.comicguispider.nyc.mn/file/1765128492268_cgs_eat.png" alt="logo">
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
  <a href="https://doc.comicguispider.nyc.mn">🏠项目主页</a> | 
  <a href="https://doc.comicguispider.nyc.mn/deploy/quick-start">🚀快速上手</a> | 
  <a href="https://doc.comicguispider.nyc.mn/faq">❓常见问题</a> | 
  <a href="https://github.com/jasoneri/ComicGUISpider/releases/latest">📦绿色包下载</a>
  </p>
</div>

|       预览/多选/翻页       |       [读剪贴板](https://doc.comicguispider.nyc.mn/feat/clip)       |
|:--------------------------------------------------------------------------------------------:|:-------------------------------------------------------------------------------------:|
| ![turn-page-new](https://img.comicguispider.nyc.mn/file/1764957470369_common-usage.gif) | ![load_clip](https://img.comicguispider.nyc.mn/file/1764957479778_load_clip.gif) |
| **[聚合搜索](https://doc.comicguispider.nyc.mn/feat/ags)** | |
| ![聚合搜索动图预留位](https://img.comicguispider.nyc.mn/file/1764957291429_ags.gif) | |

## ✨功能特性

- 如上动图演示的多种使用方式，方便的内置重启，多开同时操作不同网站等
- 开预览后随便点点就能下载，预览窗口充当于微型浏览器
- 通过加减号，`0 全选`，`-3 选倒数三个` 等输入规则，方便指定选择
- 基于翻页保留，体验如同塞进购物车
- 预设，去重，加标识符等自定义设置

**更多移步查阅 [🎸功能文档](https://doc.comicguispider.nyc.mn/feat/)**

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

## 📢更新

✨ 软件内外更新了 CGS 猫娘图（ ~~施法: 你是一只贫穷，只能捡路边法棍吃的猫娘~~ ）  
✨ 更换了 [🏠项目主页](https://doc.comicguispider.nyc.mn/) 域名/部署，图链/项目主页/文档都已转用 cloudflare 加速优化，  
假如 cf 都能卡的话可以考虑用 [Steamcommunity 302](https://www.dogfight360.com/blog/18682/)  
【🔉长驻提示】`avif依赖` 与 `python3.14` 不兼容，针对初始安装脚本/说明等做了版本限制  

### [![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/jasoneri/ComicGUISpider?color=blue&label=Ver&sort=semver)](https://github.com/jasoneri/ComicGUISpider/releases/latest)  [![release build-status](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml/badge.svg)](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml)

#### 🎁 Features

✅ 新增 `元数据记录` 功能，例如 `.czb` 的 `ComicInfo.xml`，具体看 [`配置 > 元数据类型`](https://doc.comicguispider.nyc.mn/config/#%E4%BB%A3%E7%90%86-proxies)  
✅ 简化处理发布页域名相关流程  
✅ `rvTool > 显示记录` 记录窗口新增 `搜索选中行` 按钮  

#### 🐞 Fix

✅ 配置窗口做了调整  
✅ 修复代理状态时拷贝流程仍然出错，具体看 [`faq > 拷贝访问相关`](https://doc.comicguispider.nyc.mn/faq/#_2-%E7%88%AC%E8%99%AB)  

<details>
<summary> <code>🧪v2.7.1-beta.2</code> 开发版特性👈看就点</summary>

#### 🎁 Features

✅ 匹配记录提示，菜单操作增强
![improve](https://img.comicguispider.nyc.mn/file/1765701939059_feat-2.7.1-beta.2.png)

#### 🐞 Fix

✅ 修复 jm 域名获取（保底简化处理流程保留）  
✅ 子进度条修复，大部分转用内置浏览器

</details>

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
      <img src="https://cdn.jsdmirror.com/gh/sveinbjornt/Platypus/Documentation/images/platypus.png" alt="logo" height="50">
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
  <img src="https://img.comicguispider.nyc.mn/file/1765002001925_CGS-aifadian.png" alt="在爱发电支持我">
</a>

## 🔇免责声明

详见[License](LICENSE) 当你下载或使用本项目，将默许

本项目仅供交流和学习使用，请勿用此从事 违法/商业盈利 等，开发者团队拥有本项目的最终解释权

---
![CGS](https://count.getloli.com/get/@CGS?theme=gelbooru)
