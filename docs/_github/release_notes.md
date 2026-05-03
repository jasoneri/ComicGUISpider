## 🎁 Features

+ ✨新增 jestful 站点支持，表漫生肉
+ 新增 Cbg(CornerBackground) 功能，入口为 rvTool 新增按钮，与 CGS 里常见的各种立绘资源相关，[详情看文档](https://cgs.101114105.xyz/script/#_3-cbg-cornerbackground)
+ Danbooru(Script): 入口为站点选 Script , 同样需要[前置准备](https://cgs.101114105.xyz/script/)
  - 功能：收藏 tag 管理，输入菜单/额外输入，预览viewer键盘按键 等等，前往[danbooru 文档页](https://cgs.101114105.xyz/script/danbooru)查看
+ CGS-docs 增设 站点状态 页面，上报入口在 配置窗口 的 状态 按钮
+ 交互与下载分离，优化交互：
  - 翻页保留拆解为翻页前自动提交
  - 内置重启语义改为重置搜索, 重置前可以一直提交任务, 已提交任务也与重置无关继续进行
+ doh: 当前 GUI (例如danbooru+motrix) 都能用，scrapy(下载侧)不能用还在研究。 doh 是有效改善网络的功能，具体可以自行 github 找资源
+ html/卡片样式改变 (bootstrap转tailwind)
  - 新增fix模式，可尝试jm搜"非H"，能同页区分上下卡片区域，下区域卡片点击会进入章节选择面板（当前仅处理`青年漫`）
+ 两个网站的发布页管理可主动触发，非代理选择网站后会有明显按钮
+ 补漏页一键重试，有漏页声明后右下会出现按钮
+ 内置浏览器可输入网址点访问直达，特殊字段`dev`能开控制台 (利于前端渲染抓虫)
+ 代理记录缓存

## 🐞 Fix/Upd

+ win更新相关：_pystand_static.int 与 runtime/installer.exe 的策略更新，版本回退最低定格于 `v2.9.11`
+ 日志相关：配置窗口增设直达按钮，GUI初始化会 DEBUG 级别记录配置值，上报日志到公共网络注意保留使用痕迹告知之余脱敏
+ win 默认存储路径改为 `C:\Users\<UserName>\Downloads\Comic`
+ kaobei 封ip暂时没辙了，可以选择下一个章节重置换一个节点的打法
+ hitomi 已更新图片解密算法
+ wnacg 设置代理被视为图源也走代理，仅 miss 不删域名缓存
+ hcomic 补回首页入口，已设预设的加关键词`更新`
+ 预览相关：修复封面加载完成前下载、翻页等操作被锁定的情况，恢复漫画卡片加载态动画
+ 修复空结果提示，内置浏览器空页问题
+ 任务面板滚动区域高度被裁修复
+ 站点选择的 kemono 改为 Script
+ 2.10.0-beta 后续强制统一安装包括 script 的所有依赖 (redis/pandas etc.)
+ git 瘦身至十多 mb (偏开发)

> CGSMid 暂时关闭
