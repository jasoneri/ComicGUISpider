<div align="center">
  <a href="https://github.com/jasoneri/ComicGUISpider" target="_blank">
    <img src="docs/public/CGS-girl.png" alt="logo">
  </a>
  <h1 id="koishi" style="margin: 0.1em 0;">ComicGUISpider(CGS)</h1>
  <img src="https://img.shields.io/github/license/jasoneri/ComicGUISpider" alt="tag">
  <img src="https://img.shields.io/badge/Platform-Win%20|%20macOS-blue?color=#4ec820" alt="tag">
  <img src="https://img.shields.io/badge/-3.12%2B-brightgreen.svg?logo=python" alt="tag">
  <a href="https://github.com/jasoneri/ComicGUISpider/releases" target="_blank">
    <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fcgs-downloaded-cn.jsoneri.workers.dev%2F&style=social&logo=github" alt="tag">
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

是否有过看漫加载慢，频跳广告而烦躁过😫，用 `CGS` 先下后看就行了啊嗯☝️  

| 网站                                    | 适用区域 |    补充说明    | 状态<br>(UTC+8) |
|:--------------------------------------|:----:|:----------:|:----:|
| [拷贝漫画](https://www.copy20.com/)    | :cn: |   已解锁隐藏    | ![status_kaobei](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_kaobei.json) |
| [Māngabz](https://mangabz.com)        | :cn: | 代理 | ![status_mangabz](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_mangabz.json) |
| [禁漫天堂](https://18comic.vip/)          | :cn: |     🔞     | ![status_jm](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_jm.json) |
| [绅士漫画(wnacg)](https://www.wnacg.com/) | :cn: |     🔞     | ![status_wnacg](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_wnacg.json) |
| [ExHentai](https://exhentai.org/)     | 🌏 |     🔞/代理     | ![status_ehentai](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_ehentai.json)  |
| [Hitomi](https://hitomi.la/)     | 🌏 |     🔞     | ![status_hitomi](https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_hitomi.json) |
| [Kemono](https://kemono.su)     | 🌏 |     🔞/[📒使用指引](https://jasoneri.github.io/ComicGUISpider/feature/script)     |  |

使用请适度，以免加重对方服务器负担，也减少被封ip风险

---

**[![stars](https://img.shields.io/github/stars/jasoneri/ComicGUISpider
)](https://github.com/jasoneri/ComicGUISpider/stargazers)&nbsp;&nbsp;若觉得体验还不错的话，要不回头点个⭐️star吧👻**

---

## 📢更新

### [![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/jasoneri/ComicGUISpider?color=blue&label=Ver&sort=semver)](https://github.com/jasoneri/ComicGUISpider/releases/latest)  [![release build-status](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml/badge.svg)](https://github.com/jasoneri/ComicGUISpider/actions/workflows/release.yml)

#### 🎁 Features

🔳 hitomi  
&emsp;🔳 数据集下载自动化/更新等，方式待定  
&emsp;🔳 读剪贴板功能开发中  
&emsp;🔳 优化速度，翻页等  
✅ 增设 rV 按钮（很显眼）及其管理窗口，选脚本然后取消有指示可快捷部署 rV，`显示记录`和`整合章节`移至其窗口内  
✅ ✨ 将配置系记录系的文件转移位置，后续更新等都不用再手动备份（ 参考[📒配置系文件路径](https://jasoneri.github.io/ComicGUISpider/faq/extra) ）  
✅ ✨ 增加工具视窗，内有`jm`等简化设置域名的工具，受影响的有`hotomi-tools`,`读剪贴板` （ 参考[🎸常规功能](https://jasoneri.github.io/ComicGUISpider/feature)里的图示）  

#### 🐞 Fix

✅ ✨ 设置 rV 后，更改存储目录会联动更改 rV 的配置  
✅ ✨ 修复 hitomi 图源  
✅ ✨ macOS: 修复locale环境中文识别; 打包程序的初始化/使用等问题  
✅ 修复多开端口重复绑定导致的错误  
✅ 设置储存目录防呆  

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
