# 🕑 更新历史

## `v2.10.0-beta.3`

### 🎁 Features

+ CBG (Comic Background Gallery)：新增浏览器背景定制系统
  - PNG 文件管理界面，可视化选择本地图片
  - 随机抽选模式，支持包含历史记录选项
  - 生成 Tampermonkey 脚本一键复制使用
  - 新主题样式 cbg.qss，QSS模板系统支持动态主题渲染
+ danbooru 收藏功能增强：
  - 新增收藏管理对话框，支持分组管理收藏标签
  - 可创建自定义收藏组，拖拽选择批量移动标签
  - 标签组织更灵活，支持重命名/删除收藏组
+ DoH (DNS over HTTPS) 配置说明新增至文档，可参考 cmliu/CF-Workers-DoH 部署

### ⚙️ Architecture

+ 重要重构：`site_gateway` 重命名为 `gui_site_runtime`，`spider_adapter` 重命名为 `provider_descriptor`
+ 引入 `site_runtime.py` 新架构：
  - `GuiSiteRuntime`: GUI 侧站点运行时管理
  - `ThreadSiteRuntime`: 线程级站点运行时（预览搜索）
  - `SpiderSiteRuntime`: Spider 侧站点运行时（下载）
+ Pipeline 简化逻辑优化

### 📦 Dependencies

+ Scrapy 升级至 >=2.15.1
+ 新增 py7zr>=1.1.0 依赖

### 📝 Documentation

+ 域名缓存有效期从 48 小时调整为一周
+ 拷贝漫画网址更新为 2026copy.com
+ 发布页管理可主动触发功能说明（v2.10.0-beta 已启用）

---

## `v2.10.0-beta.2`

### 🎁 Features

+ 增设 站点状态 页面，上报入口在 配置窗口 的 状态 按钮
+ 交互与下载分离，优化交互：
  - 翻页保留被拆解为翻页前自动提交
  - 内置重启语义改为重置搜索, 重置前可以一直提交任务, 已提交任务也与重置无关继续进行
+ [danbooru](https://img-cgs.101114105.xyz/file/cgs/1774207508440_danbooru.mkv) 入口为站点选 Script , 同样需要[前置准备](https://cgs.101114105.xyz/script/)
+ doh: 当前 GUI (例如danbooru+motrix) 都能用，scrapy(下载侧)不能用还在研究。 doh 是有效改善网络的功能，具体可以自行 github 找资源
+ html/卡片样式改变 (bootstrap转tailwind)
  - 新增fix模式，可尝试jm搜"非H"，能同页区分上下卡片区域，下区域卡片点击会进入章节选择面板（当前仅处理`青年漫`）
+ 两个网站的发布页管理可主动触发，选择网站后会有明显按钮
+ 补漏页一键重试，有漏页声明后右下会出现按钮
+ 内置浏览器可输入网址点访问直达，特殊字段`dev`能开控制台 (利于前端渲染抓虫)
+ 代理记录缓存

### 🐞 Fix

+ wnacg 设置代理被视为图源也走代理
+ 任务面板滚动区域高度被裁修复
+ 站点选择的 kemono 改为 Script
+ hcomic 补回首页入口，已设预设的加关键词`更新`
+ 2.10.0-beta 后续强制统一安装包括 script 的所有依赖 (redis/pandas etc.)
+ git 瘦身至十多 mb (偏开发)

> CGSMid 暂时关闭

::: tip 备用更新方法  
win绿色包(exe): 先去 [对应版本的tag下载zip](https://github.com/jasoneri/ComicGUISpider/tags)  
&emsp;&emsp;然后解压覆盖在`解压目录\comicguispider\Lib\site-packages`里  
mac/终端uv：如上下载 {tag}.zip，解压目录直接跑 `uv run CGS.py`  
:::

---

> [!Info] 下方记录会忽略修复动作相关的记录，含引导意义的条目除外

::: details v2.9.11
+ 任务板视觉操作增强
+ slot 兜底捕捉
+ _pystand_static.int 指定版本安装
+ bg_path 高度自动调节
:::

::: details v2.9.9
+ ui 大改，加入几个动画，去掉搜索键/序号输入框，统一预览键调度
+ 发布页交互优化，预览选择交互增强
:::

::: details v2.9.0
+ CGSMid
+ 常规漫预览，与 CGSMid 相斥
+ 版本更新提醒
:::

::: details v2.8.6
+ 新增 [h-comic](https://h-comic.com) 站点支持
+ rvTool 布局更改，并加入新功能 `以图搜索`
+ 聚合搜索增加 [from 剪贴板](/feat/ags.html#_2-%E5%89%AA%E8%B4%B4%E6%9D%BF) 方式
+ kemono 本地收藏增加作者头像缓存
:::

::: details v2.8.5
+ 更新内置浏览器样式
+ (内置浏览器发起的)发布页右键菜单支持手动输入域名
:::

::: details v2.8.0
+ 整改存储目录，区分后处理模式  
+ 补全元数据，并基于 `储存目录/rV.db` 本地储存信息  
+ rvTool 的显示记录增强，区分🔞  
:::

<details>
<summary> 古早记录 ⇩</summary>

::: details v2.2.5

+ ✨jm 支持章节，仅在读剪贴板可用；去重机制对于章节同样生效  
+ 配置栏 eh_cookies 改为 cookies  
+ 将耗时操作置于预处理后台线程；将诸多耗时 io 改为异步

:::
::: details v2.2.4

+ 工具视窗增设 statusTool

:::
::: details v2.2.3

+ 工具视窗增设 domainTool；hitomiTool 也转移至其中  
+ 配置系记录系的文件转移位置  
+ hitomi 用异步并发做归并了  
+ macOS-init.app 去除，改为 bash 命令自执行  
+ mac python 改为 uv

:::
::: details v2.2.2

+ 增设 rV 按钮，工具视窗  
+ 设置储存目录防呆  

:::
::: details v2.2.0 | ~ 2025-05-20

+ 🌐支持`hitomi` （部分）
+ Kemono 脚本集更新（下载引擎使用强大的 `Motrix-PRC`）  
+ 页数命名优化：更改为纯数字补零命名，附带可选 [文件命名后缀修改](/config/#其他-yml-字段)  
+ i18n 自动编译优化  
+ 使用 astral-sh/uv 管理依赖

:::
::: details v2.1.3 | ~ 2025-04-19

+ 支持 i18n  
+ 增加贡献指南等，文档优化，并建成 github-pages 做官网

:::
::: details v2.1.2 | ~ 2025-04-12

+ 更换看板娘  
+ 版面增设各网站运行状态

:::
::: details v2.1.0 | ~ 2025-03-29

+ 为预览窗口各封面右上增设badge
+ 将`requirements.txt`分别以`win`,`mac_x86_64`,`mac_arm64`编译

:::
::: details v2.0.0 | ~ 2025-03-21

+ `使用说明`与`更新`在`v2.0.0`后将设置在配置窗口的左下按钮，绿色包可执行程序只保留主程序（macOS加个初始化.app）  
+ 优化更新流程，贴近主流软件体验  
+ ✨使用`QFluentWidgets`优化界面与操作体验  
  + 搜索框右键选项`展开预设`, 序号输入框也有  
  + 预览窗口改造了右键菜单，增设翻页进去菜单项，附带有`CGS`内的全局快捷键  
  + 正确处理小数位级系统缩放，去掉`同步系统缩放`也有良好界面体验
（操作参考[`v1.6.3`删代码部分](#v1-6-3-2025-02-13)，后续若有反响则做成开关之类提供切换）

:::
::: details v1.8.2 | ~ 2025-03-08

+ ✨预览窗口新增`复制`未完成任务按钮，配合剪贴板功能功能的流程，常用于进度卡死不动重下或补漏页

:::
::: details v1.7.5 | ~ 2025-03-01

+ 序号输入扩展：输入框支持单个负数，例`-3`表示选择倒数三个

:::
::: details v1.7.2 | ~ 2025-02-24

+ ✨新增`增加标识`开关勾选，为储存目录最后加上网站url上的作品id  
+ ✨细化任务：预览窗口的`子任务进度`视图  
+ 处理拷贝的隐藏漫画  
+ 修正往后jm全程不走代理（如有jm需要走代理的场景请告知开发者） 

:::
::: details v1.6.3 | ~ 2025-02-13

+ ✨配置窗口新增`去重`勾选开关：分别有预览提示样式和自动过滤
+ ✨增加命令行工具(crawl_only.py)使用
+ 优化高分辨率(原开发环境为1080p)；若显示不理想可桌面右键显示设置缩放改为100%，或在[`CGS.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/CGS.py)中删除带`setAttribute(Qt.AA_` 的两行代码

:::
::: details v1.6.2 | ~ 2024-12-08

+ ✨增加域名缓存机制（针对jm/wnacg发布页访问错误），每12小时才刷新可用域名，缓存文件为`__temp/xxx_domain.txt`，可删可改
+ 处理部分用户环境无法显示ui图标相关资源问题（如对比动图/视频仍有ui图标没显示，请反馈）

:::
::: details v1.6.1 | ~ 2024-11-23 
+ ✨新增读剪切板匹配生成任务功能

:::
::: details v1.6.0 | ~ 2024-09-30
+ 🌐支持`Māngabz`
+ ✨支持`macOS`
+ 🌐支持`exhentai`
  + [`exhentai`]优化e绅士标题取名，优先使用副标题的中/日文作为目录名
+ ✨新增翻页功能
  + 翻页时保留选择状态
+ ✨新增预览功能
> [!Info] 内置小型浏览器，无需打开电脑浏览器，视频3有介绍各种用法

:::
::: details v1.5 | 上世纪 ~ 2024-08-05
+ ✨发布相关
> [!Info] 发布开箱即用版，GUI视频使用指南

+ ✨脚本集说明(kemono,saucenao)
  + 新增`nekohouse`
+ 🌐支持`jm(禁漫)`
  + 支持车号输入
+ 🌐支持`拷贝漫画`
  + 在配置设了代理后能解锁部分漫画章节
  + 处理章节数量大于300
+ 🌐支持`wnacg`

:::
</details>
