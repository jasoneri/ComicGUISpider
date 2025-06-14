# 🎸 常规功能

::: tip 欢迎提供功能建议，提交issue / PR / 此页下方评论区留言 等  
例如打包 epub 格式 zip（需描述过程结果）
:::

## 适用性

> [!Info] 没列出的功能全网适用，一眼独占的工具如 hitomiTool 也不会列出  

|  |  [拷贝](https://www.copy20.com/) |    [Māngabz](https://mangabz.com)     | [禁漫](https://18comic.vip/) |    [wnacg](https://www.wnacg.com/)    | [ExHentai](https://exhentai.org/) | [hitomi](https://hitomi.la/) |
|:--------------------------------------|:-------------:|:---------:|:----:|:----------:|:----------:|:----------:|
| 预览 | ❌ |     ❌ | ✔️ | ✔️ | ✔️ | ✔️ |
| 翻页 | ✔️ |     ✔️ | ✔️ | ✔️ | ✔️<br>禁跳页 | ✔️ |
| rV-显示记录 | ✔️ | ✔️ | ❌ | ❌ | ❌ | ❌ |
| rV-整合章节 | ✔️ | ✔️ | ❌ | ❌ | ❌ | ❌ |
| 域名工具 | ❌ | ❌ | ✔️ | ✔️ | ❌ | ❌ |
| 读剪贴板 | ❌ | ❌ | ✔️ | ✔️ | ✔️ | 🚧 |

## 功能项

### 1. 搜索框预设

搜索框区域按 `空格` 或右键点`展开预设`即可弹出预设项 （序号输入框同理）  

### 2. 预览功能

内置的浏览器，多选/翻页等如动图所示。其他详情使用看 `🎥视频使用指南3`
  
### 3. 翻页

当列表结果出来后开启使用

---

### 4. 工具视窗

![toolsWin](../assets/img/feat/toolsWin.png)

点击 rV 按钮触发显示，点击对应标签切换工具，常驻 rV工具，状态工具  
 
- 域名工具( domainTool )仅选择 jm/wnacg 触发  
- hitomiTool 仅选择 hitomi 触发  

### 4.1 rV工具 / rvTool

#### 4.1.1 显示记录

配合 [rV(redViewer)](https://github.com/jasoneri/redViewer) 使用，用 rV 阅读产生看到哪最新话，然后配合下载  
Maybe: 后续能扩展做订阅

#### 4.1.2 整合章节

批量整合，例如将`D:\Comic\蓝箱\165\第1页`整合转至`D:\Comic\web\蓝箱_165\第1页`  
> [!Info] 匹配 rV 目录结构

### 4.2 状态工具 / statusTool

比网页列出的状态更全 ~~（没错，就是对策那个网站）~~  
功能不单是显示状态，内有使用指引  

### 4.3 域名工具 / domainTool

其实本来每次启动 jm/wnacg 就会处理域名，内有使用指引  
~~这工具纯粹安心了解自己所处的网络情况~~  

::: warning 发布页登不上的情况有两种  
1. 自身网络问题：自行用手机测、切代理尝试
2. 发布页崩了（参考 wnacg 之前换过域名）：先参考 [📒域名相关](/faq/extra) 排查，未果则上报  
:::

### 4.4 hitomiTool

仅 hitomi 用，[📹参考用法](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/hitomi-tools-usage.gif)

### 5 读剪贴板

::: tip 从`v2.2.3`起该功能单独分配一键，选择 符合适用性 的网站即可开启使用  
![clipBtn](../assets/img/feat/clipBtn.png)
:::

读剪贴板匹配生成任务，需配合剪贴板软件使用（自行下载安装）  
win: [🌐Ditto](https://github.com/sabrogden/Ditto)  
macOS: [🌐Maccy](https://github.com/p0deje/Maccy)  
流程使用看`🎥视频使用指南3`相关部分，此功能说明须知放在任务页面右上的`额外说明`  
::: info 不下载剪贴板软件仅影响 `读剪贴板` 功能，不影响常规流程使用
:::

### 6. 重启CGS

![rebootBtn](../assets/img/feat/reboot.png)
选择网站后开启使用  

### 7. 预览窗口功能项

#### 7.1. 复制未完成任务链接

![browser_copyBtn](../assets/img/feat/browser_copyBtn.png)

> [!Tip] 前置设置  
> 需参考 [🔧其他配置 > 复制按钮相关](../config/other.md) 对剪贴板软件更改设置

将当前未完成链接复制到剪贴板。  
先`复制`后用`工具箱-读剪贴板`的流程，常用于进度卡死不动重下或补漏页
