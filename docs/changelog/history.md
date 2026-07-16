# 🕑 更新历史

## `v2.11.1`

### 🎁 Features

+ danbooru tag 管理面板新增 ai 后台翻译 tag 功能，使用时会结合展示，需到设置面板事前配置 ai provider，或自定义区底部手动改展示名，详情看[文档](https://cgs.101114105.xyz/script/danbooru#%E6%A0%87%E7%AD%BE%E7%AE%A1%E7%90%86)
+ jm：扩展正确区分出带章节的漫画卡片，下半区补齐收藏/订阅勾选，并修复下半区域漫画卡片的章节下载
+ 搜索输入栏右键菜单增设历史记录，共用不分站点

### 🐞 Fix/Upd

+ 加入 搜索/翻页 Loader ，优化内置浏览器的等待体感
+ 修复托盘模式的日夜模式
+ 修复 mangabz 章节下载时的终端闪烁问题
+ 修复 wnacg 的图源代理下载，代理时提高完下率
+ 修复 无限动漫 的首页 章节无法加载问题
+ 修复 dm5 更新接口时间节点处理
+ 修复 jcomic 封面无法加载问题
+ 修复章节框选，fix模式的工具组，toast等优化交互行为
+ danbooru tag 管理面板删除操作更改，减少渲染优化加载

<details>
<summary> v2.11.0 ⇩</summary>

### 🎁 Features

+ ✨CGS server/mcp ，由配置窗口点击 `CGS server` 触发托盘，配合 [rv-app](https://rv.101114105.xyz/guide/mobile.html) 使用
+ 🌐支持 `jcomic`
+ 🌐支持 `mh1234`
+ 自定义站点选择框支持显示/隐藏
+ 🌐支持 `无限动漫` （comicabc，暂定用这英文映射啊嗯..）
+ 🌐支持 `dm5`
+ discord 分享模块
+ 🌐支持 `nhentai`
+ 🌐支持 `manhuagui` （漫画柜）
+ 🌐支持 `rumanhua` （如漫画）
+ Danbooru 支持 视频播放下载，zip下载，扩展按键绑定

### 🐞 Fix/Upd

+ 补漏页:重新提交任务优化为细化只补漏掉的页
+ 优化 scriptWin 的进入条件，[详情看文档](https://cgs.101114105.xyz/script/)
+ 日夜模式 icon 优化
+ Danbooru 优化流畅度性能，多个细节体验优化(分页标识,视频标识,已收藏标识等)
+ scriptWin 新增自制的一些服务占位
+ ⚠️ 关于订阅模块目前没想好业务形态，均视为占位
+ 修复 win 的储存目录变更失效硬绑定 C盘 的问题
+ 基于`dm5`章节提交至下载时长不定，增加提交反馈
+ 站点状态增加三大宽带运营商维度
+ 重新描述被忽视的`映射`能力，[详见文档](https://cgs.101114105.xyz/config/#%E6%98%A0%E5%B0%84-custom-map)
+ jestful 序号调整为 9 , 关注预设, jestful 预设词 `更新` 失效需要改为 `首页`
+ hitomi/Script(此前卡点在 Kemono)/nhentai 预处理改为 ci raleases/preset生成，使用时下载（带进度反馈）

</details>

::: tip 备用更新方法  
win绿色包(exe): 先去 [对应版本的tag下载zip](https://github.com/jasoneri/ComicGUISpider/tags)  
&emsp;&emsp;然后解压覆盖在`解压目录\comicguispider\Lib\site-packages`里  
mac/终端uv：如上下载 {tag}.zip，解压目录直接跑 `uv run CGS.py`  
:::

---

> [!Info] 下方记录会忽略修复动作相关的记录，含引导意义的条目除外

::: details v2.10.0
+ 🌐支持 `jestful`
+ ✨新增 Danbooru
+ ✨新增 Cbg(CornerBackground)
+ CGS-docs 增设 站点状态 交互
+ 架构改变，交互与下载分离，重置搜索
+ doh 相关
+ html/卡片样式改变(bootstrap转tailwind)，新增 fixHtml
+ 发布页域名管理主动触发
+ 一键补漏页
:::

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
