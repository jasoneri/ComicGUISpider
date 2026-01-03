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
- 丰富多样的输入规则，方便指定选择
- 无感翻页保留选择，已下载记录等提示
- 预设，去重，加标识符等各种自定义设置

**更多移步查阅 [🎸功能文档](https://doc.comicguispider.nyc.mn/feat/)**

## 📑介绍

👍 什么玩意啊，最好再召集多点人把消星当减速带使吧 👍 还搞集体无口迷惑呢，真谢谢用这方法把我恶心了 👍  
ok的，懒得服务无口消星大爷，筛用户，`v2.7.2` 以后不发布，不发版，也不更新README  
正常用户麻烦到 `PR` 或软件内配置窗口更新按钮里看更新修复情况  

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

图链/项目主页/文档都已转用 Cloudflare 加速优化，卡的话可以用 [Steamcommunity 302](https://www.dogfight360.com/blog/18682/)  
【🔉长驻提示】`avif依赖` 与 `python3.14` 不兼容，针对初始安装脚本/说明等做了版本限制  

### [![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/jasoneri/ComicGUISpider?color=blue&label=Ver&sort=semver)](https://github.com/jasoneri/ComicGUISpider/releases/latest)  [![release build-status](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml/badge.svg)](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml)

#### 🎁 Features

✅ 简化处理发布页域名相关流程  
✅ `rvTool > 显示记录` 记录窗口新增 `搜索选中行` 按钮  
✅ 匹配记录提示，菜单操作增强 > [📷screenshot](https://img.comicguispider.nyc.mn/file/1765701939059_feat-2.7.1-beta.2.png)
✨ `元数据记录` 改成 `后处理`，下载完成的后处理，具体看 [`配置 > 后处理`](https://doc.comicguispider.nyc.mn/config/#%E4%BB%A3%E7%90%86-proxies)  
✨ `kemono` 过滤规则 修复&增强 > [看📏过滤规则示例](https://doc.comicguispider.nyc.mn/feat/script.html#%F0%9F%9A%80-%E5%BF%AB%E9%80%9F%E4%B8%8A%E6%89%8B) （注意字段更改及时更新本地过滤规则）  

#### 🐞 Fix

✅ 修复代理状态时拷贝流程仍然出错，具体看 [`faq > 拷贝访问相关`](https://doc.comicguispider.nyc.mn/faq/#_2-%E7%88%AC%E8%99%AB)  
✅ 修复 jm 域名获取（保底简化处理流程保留）, 子进度条修复  
✨ 修复 kb 缓存失败重启卡死；报错 'tasks_progress_panel_flag'; 章节的 `.cbz`;  

> 可参考 [更新方法](https://jasoneri.github.io//ComicGUISpider/deploy/quick-start.html#_4-%E6%9B%B4%E6%96%B0) 进行更新  

> [🕑更新历史](docs/changelog/history.md) / [📝开发板](https://github.com/jasoneri/ComicGUISpider/projects?query=is%3Aopen)

## 🍮食用搭配(阅读器)

<table><tbody>  
  <tr>
    <td><div align="center"><a href="https://github.com/jasoneri/redViewer" target="_blank">
      <img src="https://img.comicguispider.nyc.mn/file/1766904566021_rv.png" alt="logo" height="60">
      </a></div></td>
    <td><div align="center"><a href="https://github.com/gotson/komga" target="_blank">
      <img src="https://raw.githubusercontent.com/gotson/komga/master/.github/readme-images/app-icon.png" alt="komga" height="60">
      </a></div></td>
    <td><div align="center"><a href="https://github.com/Ruben2776/PicView" target="_blank">
      <img src="https://avatars.githubusercontent.com/u/4200419?s=48&v=4" alt="PicView" height="60">
      </a></div></td>
  </tr>
  <tr>
    <td>rV, 自用<br>全面无感适配 CGS<br><s>CGS 为它服务</s></td>
    <td>komga/ComicRack系<br>需后处理设<code>.cbz</code></td>
    <td>PicView<br>图片管理器, 但用来操作子目录图片<br>或是<code>.cbz</code>都是不错选择</td>
  </tr>
</tbody></table>

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
<img src="https://hosted.weblate.org/widget/comicguispider/287x66-grey.png" alt="翻译状态" height="66" style="vertical-align: middle;" />
</a>
<a href="https://ko-fi.com/jsoneri">
  <img src="https://img.comicguispider.nyc.mn/file/1766128193347_sponsor_kofi.gif" alt="ko-fi" height="66" style="vertical-align: middle;">
</a>

## 🔇免责声明

详见[License](LICENSE) 当你下载或使用本项目，将默许

本项目仅供交流和学习使用，请勿用此从事 违法/商业盈利 等，开发者团队拥有本项目的最终解释权

---
![CGS](https://count.getloli.com/get/@CGS?theme=gelbooru)
