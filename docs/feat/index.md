# 🎸 常规功能

::: tip 欢迎提供功能建议，提交issue / PR / 此页下方评论区留言 等  
:::

## 适用性

::: info 没列出的功能全网适用，一眼独占的工具如 hitomiTool 也不会列出  
表漫站点没以下矩阵功能
:::

|  | 📋读剪贴板 | 🔎聚合搜索 | 以图搜索 |
|:---|:---:|:---:|:---:|
| [禁漫](https://18comic.vip/) | ✔️ | ✔️ | ✔️ |
| [wnacg](https://www.wnacg.com/) | ✔️ | ✔️ | ✔️ |
| [ExHentai](https://exhentai.org/) | ✔️ | ✔️ | ✔️ |
| [hitomi](https://hitomi.la/) | 🚧 | 🚧 | 🚧 |
| [hcomic](https://h-comic.com) | ❌ | ✔️ | ✔️ |
| [nhentai](https://nhentai.net) | ❌ | ✔️ | ✔️ |

---

![mainBtnGroup]({{URL_IMG}}/file/cgs/1783624759721_mainBtnGroup.png)

## 1. 主界面

| 功能项 | 说明 |
|:-------------:|:---------|
| 搜索框预设 | 搜索框区域按 `空格` 或右键点`展开预设`即可弹出预设项 （序号输入框同理）<br>主界面选中文本右键可快速加进预设 |
| 搜索框历史 | 搜索框区右键点 `历史` 即可弹出，全站点共用，上限 50 |
| 翻页按钮组 | 当列表结果出来后开启使用 |
| 读剪贴板 | 如图，参阅 [📋跳转阅读 > 使用](/feat/clip) |
| 重置搜索 | 如图，选择站点后开启使用 |
| 域名管理 | 仅 jm 和 wnacg 在无代理状态下出现，用于换域名 |

## 2. 预览/内置浏览器

| 功能项 | 说明 |
|:-------------:|:---------|
| 顶栏按钮组 | 左上窗口置顶，其他常规浏览器的按钮自行摸索<br>可鼠标 **按住顶栏空白处** 移动内置浏览器窗口 |
| 右上复制按钮 | 复制未完成任务链接，[📋跳转阅读 > 复制未完成任务链接](/feat/clip.md#复制未完成任务链接)   |
| 其他常规 | 多选/翻页等如动图所示。详情使用看 `🎥视频使用指南3` |

### 2.1 常规漫的预览

::: tip 点卡片右上角 ★ 后可加为本地收藏
随便收藏一本即自动设置 `本地收藏` 进预设，并自动加进订阅清单  
之后搜索框用预设的 `本地收藏` 就会仅列出对应的书本卡片列表
:::

## 3. 工具工作台

主界面点 工具按钮 打开，默认 `rvTool`  
部分标签按条件出现：`aggrSearch` 随站点、`hitomiTool` 随 hitomi 数据

![toolWorkspace]({{URL_IMG}}/file/cgs/1792438002237_toolWorkspace.png)

<table>
  <thead>
    <tr>
      <th style="text-align: center;">标签</th>
      <th style="text-align: left;">说明</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align: center; vertical-align: middle;">rvTool</td>
      <td style="text-align: left;">常驻表列出已阅最新话、下载最新话，可删除选中行或把书名发去主界面搜索；<br>右上刷新键重扫本地存至<code>储存目录/rV.db</code>，与 rV 共用<br><code>已阅最新话</code>需用 <a href="https://github.com/jasoneri/redViewer" target="_blank" rel="noopener noreferrer">rV</a> 操作过才有记录</td>
    </tr>
    <tr>
      <td style="text-align: center;">aggrSearch</td>
      <td style="text-align: left;"><a href="/feat/ags">🔎跳转阅读 > 使用</a></td>
    </tr>
    <tr>
      <td style="text-align: center;">hitomiTool</td>
      <td style="text-align: left;"><a href="{{URL_IMG}}/file/1764957586207_hitomi-tools-usage.gif" target="_blank" rel="noopener noreferrer">📹参考用法</a>, 其中表格能点击进行数量倒序等</td>
    </tr>
    <tr>
      <td style="text-align: center;">midTool</td>
      <td style="text-align: left;"><a href="/feat/mid">🀄️跳转阅读 > 使用</a></td>
    </tr>
    <tr>
      <td style="text-align: center;">订阅</td>
      <td style="text-align: left;">订阅管理见 <a href="#_4-%E8%AE%A2%E9%98%85%E7%AE%A1%E7%90%86%E9%9D%A2%E6%9D%BF-%E8%AF%95%E8%A1%8C%E4%B8%AD">§4</a></td>
    </tr>
    <tr>
      <td style="text-align: center;">webdav</td>
      <td style="text-align: left;">把本地库通过树选择上传到 WebDAV</td>
    </tr>
    <tr>
      <td style="text-align: center; vertical-align: middle;" rowspan="4">addons<br><small>格子页</small></td>
      <td style="text-align: left;"><strong>rV</strong>: 下载/清除<code>锚点</code>/<code>锚点</code>定位&运行<br>新增格都是以这种模式出现</td>
    </tr>
    <tr><td style="text-align: left;"><strong>acggr</strong>: 进 scriptWin（danbooru / pawchive / Cbg）</td></tr>
    <tr><td style="text-align: left;"><strong>以图搜索</strong>: 借用 saucenao，按 CGS 内指示操作即可，仅 R18 站点出现</td></tr>
    <tr><td style="text-align: left;"><strong>+ / 🗑</strong>: 新增自定义格（执行文件 / 命令行）；<br>🗑 进入清理模式，无法清除前三项内置格子</td></tr>
  </tbody>
</table>

## 4. 订阅管理面板（试行中）

工作台 `订阅` 标签页

![subscribeWin]({{URL_IMG}}/file/cgs/1792436087646_subscribeWin.png)
