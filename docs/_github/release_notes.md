## 🎁 Features

+ danbooru tag 管理面板新增 ai 后台翻译 tag 功能，使用时会结合展示，需到设置面板事前配置 ai provider，或自定义区底部手动改展示名，详情看[文档](https://cgs.101114105.xyz/script/danbooru#%E6%A0%87%E7%AD%BE%E7%AE%A1%E7%90%86)
+ jm：扩展正确区分出带章节的漫画卡片，下半区补齐收藏/订阅勾选，并修复下半区域漫画卡片的章节下载
+ 搜索输入栏右键菜单增设历史记录，共用不分站点

## 🐞 Fix/Upd

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

## 🎁 Features

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

## 🐞 Fix/Upd

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
