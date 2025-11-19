# 🔎聚合搜索

## 使用

从下文输入方式获取一组搜索词，然后将多个搜索列表一次性在预览窗口中列出，后面就是常规选择下载流程  

<table><tbody>
  <tr>
    <td><img src="https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/ags.gif"></td>
  </tr>  
</tbody></table>

### 输入

#### 1. qq-消息复制

在 qq 聊天窗口按住左键区域选择，然后点复制，回 CGS 的 aggrSearch  
👉点击 `from qq` 按钮  

#### 2. 任务文本文件

:::tip 格式: 每一行是一个搜索词  
:::
任务文件自带状态管理，选择下载后会把文件中对应已选择的行删除，可以用 Langbot 机器人等方式持续集成搜索词到该文件  
👉点击 `from 文件` 按钮

#### 3. 待扩展

集思广益，可以起草 issue（需要提供输入输出），  
或自发 PR 到 2.6-dev 分支，详见 [utils/ags/extractor.py](
https://github.com/jasoneri/ComicGUISpider/blob/2.6-dev/utils/ags/extractor.py) 参照 qq 实现即可

### 搜索词列表

从输入获取搜索词列表后，

- 可以自行取消部分勾选
- 或文本框修改单个搜索词
- 或点右侧恢复按钮恢复（未被内部程序解析处理的）初始文本

👉最后点击 `运行` 按钮，即进入预览窗口的常规选择下载流程

## 题外话（脑洞）

后续把聚合搜索写进 cgs-cli （命令行工具）后  
用 Langbot 之类持续集成到文件，定时跑 cgs-cli，实现 QQ等 向小号持续发词就能全自动下载了  
~~👮开门！查水表~~
