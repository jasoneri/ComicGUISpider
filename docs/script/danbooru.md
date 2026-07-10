# Danbooru

::: warning **需已读 [⚠️ 通用前置须知](/script/)**
:::

## 视频演示常规操作

<div align="left">
<a href="{{URL_IMG}}/file/cgs/1777322414802_danbooru.webm" target="_blank">
  <img src="{{URL_IMG}}/file/cgs/1774207883543_danbooruPlay.png" alt="logo">
</a></div>

## 补充视频没提及的操作/配置

### 配置

进 scriptWin 前 / 进 scriptWin 后搜索之前，设置 doh 即可免代理访问，空词进首页过 cf 盾即可

### 主界面

![img]({{URL_IMG}}/file/cgs/1783623690797_danbooruTopicRowBtnGroup.png)

#### 标签管理

自定义区点击目标组激活 `target group` 后，在默认区利用 ctrl/shift 选中一个/多个没分类 tags ,  
点击界面中间的 `右移按钮` 移动，保存，即可在输入框右键收藏组看到对应效果

::: warning 注意自定义区`组的删除`会连带删除组内 tags
可提前利用 ctrl/shift 将已分组 tags 批量 `左移` 回默认区
:::

#### 功能集

+ 整合目录：将附有「额外输入」的目录转移回无印，  
  例如 `beatrice_(re-zero) score--100` 转移回 `beatrice_(re-zero)`
  > 目录储存问题，`score--100` 即为 `score:>100`

#### 额外输入

输入框文字触发显示左侧 `+` 号按钮  
作用：为输入追加条件筛选 tag , 例如 `score:>50`(得分大于50) `-rating:e` (排除nsfw)  
[内有同样的指引](https://www.yuque.com/baimusheng/programer/wl9c6nxxdvecm1tg)

#### 瀑布流网格区域操作

| 操作 | 说明 |
|------|------|
| 鼠标中键 | 关闭当前 tab 页 |
| 右键菜单-清除此页前图片 | 有利于浏览长页数 tag，释放缓存 |
| 小键盘 Num4 | 追加第一个「额外输入」条件并搜索 |
| 小键盘 Num5 | 收藏/取消收藏当前搜索词 |
| 小键盘 Num6 | 切换为「评分逆序」 |

::: warning 键盘快捷键需要在输入框非激活状态才有效
:::

### 预览页 viewer

| 按键 | 功能 |
|------|------|
| ↑ | 关闭 viewer |
| ← | 上一图 |
| ↓ | 下载当前资源 |
| → | 下一图 |
| 鼠标滚轮向上 | 上一图 |
| 鼠标滚轮向下 | 下一图 |
| 鼠标中键 | 关闭 viewer |
| 小键盘 Num1 | 直接打开 Character 的第一个 tag |
| 小键盘 Num2 | 直接打开 Artist 的第一个 tag |
| 小键盘 Num3 | 直接打开 Copyright 的第一个 tag |
