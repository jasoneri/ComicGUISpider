---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "打开 CGS"
  text: "鼠标点几点轻松下漫画"
  tagline: 最自在
  image:
    src: /cgs_sleep.png
    alt: CGS
  actions:
    - theme: brand
      text: 快速上手
      link: /deploy/quick-start
    - theme: alt
      text: 配置
      link: /config
    - theme: brand
      text: 🎸功能
      link: /feat
    - theme: alt
      text: FAQ
      link: /faq
    - theme: brand
      text: 🕑看更新
      link: /changelog/history
    - theme: sponsor
      text: 🍖投喂
      link: https://ko-fi.com/jsoneri

---

<table><tbody>  
  <tr>
    <td><div align="center"><a href="https://www.2025copy.com/" target="_blank">
      <img src="/assets/img/icons/website/copy.png" alt="logo" style="max-height: 80px">
      </a></div></td>
    <td><div align="center"><a href="https://mangabz.com" target="_blank">
      <img src="/assets/img/icons/website/mangabz.png" alt="logo" style="max-height: 80px">
      </a></div></td>
    <td><div align="center"><a href="https://18comic.vip/" target="_blank">
      <img src="/assets/img/icons/website/jm.png" alt="logo" style="max-height: 80px">
      </a></div></td>
    <td><div align="center"><a href="https://www.wnacg.com/" target="_blank">
      <img src="/assets/img/icons/website/wnacg.png" alt="logo" style="max-height: 80px">
      </a></div></td>
    <td><div align="center"><a href="https://exhentai.org/" target="_blank">
      <img src="/assets/img/icons/website/ehentai.png" alt="logo" style="max-height: 80px">
      </a></div></td>
    <td><div align="center"><a href="https://hitomi.la/" target="_blank">
      <img src="/assets/img/icons/website/hitomi.png" alt="logo" style="max-height: 80px">
      </a></div></td>
    <td><div align="center"><a href="https://h-comic.com/" target="_blank">
      <img src="/assets/img/icons/website/hcomic.png" alt="logo" style="max-height: 80px">
      </a></div></td>
  </tr>
  <tr>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_kaobei.json"></td>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_mangabz.json"></td>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_jm.json"></td>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_wnacg.json"></td>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_ehentai.json"></td>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_hitomi.json"></td>
    <td><img src="https://img.shields.io/endpoint?url=https://cgs-status-badges.pages.dev/status_h_comic.json"></td>
  </tr>
</tbody></table>

<table><tbody>
  <tr>
    <td style="text-align: center; vertical-align: middle;" rowspan="4">
      <HomeDemoVideo src="{{URL_IMG}}/file/cgs/1772894706883_normal.mp4" title="AGS demo"></HomeDemoVideo>
    </td>
  </tr>
  <tr><td style="text-align: left;"><a href="/feat/clip/"><strong>📋读剪贴板</strong></a></td></tr>
  <tr><td style="text-align: left;"><a href="/feat/ags/"><strong>🔎聚合搜素</strong></a></td></tr>
  <tr><td style="text-align: left;"></td></tr>
</tbody></table>

## 功能特性

- 多种使用方式，多开同时操作不同网站等
- 多种输入规则
- 无感翻页保留选择，已下载记录等提示
- 预设，去重，加标识符等各种自定义设置

## 食用搭配(阅读器)

<table><tbody>  
  <tr>
    <td><div align="center"><a href="https://github.com/jasoneri/redViewer" target="_blank">
      <img src="{{URL_IMG}}/file/1766904566021_rv.png" alt="logo" height="60" style="max-height:60px;">
      </a></div></td>
    <td><div align="center"><a href="https://github.com/gotson/komga" target="_blank">
      <img src="https://raw.githubusercontent.com/gotson/komga/master/.github/readme-images/app-icon.png" alt="komga" style="min-height:60px;">
      </a></div></td>
    <td><div align="center"><a href="https://github.com/Ruben2776/PicView" target="_blank">
      <img src="https://avatars.githubusercontent.com/u/4200419?s=48&v=4" alt="PicView" style="min-height:60px;">
      </a></div></td>
  </tr>
  <tr>
    <td>rV, 自用<br>全面无感适配 CGS<br><s>CGS 为它服务</s></td>
    <td>komga/ComicRack系<br>需后处理设<code>.cbz</code></td>
    <td>PicView<br>图片管理器, 但用来操作子目录图片<br>或是<code>.cbz</code>都是不错选择</td>
  </tr>
</tbody></table>

## 致谢声明

### Credits

Thanks to

- [PyStand](https://github.com/skywind3000/PyStand) / [Platypus](https://github.com/sveinbjornt/Platypus) for providing win/macOS packaging.
- [Ditto](https://github.com/sabrogden/Ditto) / [Maccy](https://github.com/p0deje/Maccy) for providing great win/macOS Clipboard Soft.
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/) for providing elegant qfluent ui.
- [VitePress](https://vitepress.dev) for providing a great documentation framework.
- [astral-sh/uv](https://github.com/astral-sh/uv) for providing a great requirements manager.
- Every comic production team / translator team / fans.

## 贡献

欢迎提供 ISSUE 或者 PR

<a href="https://github.com/jasoneri/ComicGUISpider/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=jasoneri/ComicGUISpider" />
</a>

## 传播声明

- **请勿**将 ComicGUISpider 用于商业用途。
- **请勿**将 ComicGUISpider 制作为视频内容，于境内视频网站(版权利益方)传播。
- **请勿**将 ComicGUISpider 用于任何违反法律法规的行为。

ComicGUISpider 仅供学习交流使用。

## Licence

[MIT licence](https://github.com/jasoneri/ComicGUISpider/blob/GUI/LICENSE)

---

![CGS](https://count.getloli.com/get/@CGS?theme=asoul)
