# 🔎聚合搜索

## 使用

从下文输入方式获取一组搜索词，然后将多个搜索列表一次性在预览窗口中列出，  
后面就是常规选择下载流程  

<table><tbody>
  <tr>
    <td><img src="https://img-cgs.101114105.xyz/file/1764957291429_ags.gif"></td>
  </tr>  
</tbody></table>

### 输入

#### 1. 任务文本文件

:::tip 格式: 每一行是一个搜索词  
:::
任务文件自带状态管理，选择下载后会把文件中对应已选择的行删除，可以用 Langbot 机器人等方式持续集成搜索词到该文件  
👉点击 `from 文件` 按钮

#### 2. 剪贴板

::: warning 惯例需要 `Ditto` / `Maccy`
下载安装（[参考前置](/feat/clip)）并[设置db_path](/config/#%E5%89%AA%E8%B4%B4%E6%9D%BFdb-clip-db)，否则不会出现此按钮
:::

从剪贴板读取N条  
👉调整读取数，点击 `from 剪贴板` 按钮

#### 3. qq-消息复制

在 qq 聊天窗口按住左键区域选择，然后点复制，回 CGS 的 aggrSearch  
👉点击 `from qq` 按钮  

#### 4. 待扩展

详见 [utils/ags/extractor.py](
https://github.com/jasoneri/ComicGUISpider/blob/2.6-dev/utils/ags/extractor.py) 参照 qq 实现即可

### 搜索词列表

从输入获取搜索词列表后，

- 可以自行取消部分勾选
- 或文本框修改单个搜索词
- 或点右侧恢复按钮恢复（未被内部程序解析处理的）初始文本

👉最后点击 `运行` 按钮，即进入预览窗口的常规选择下载流程

## 其他

### 功能相关

- 目前仅支持 `搜索接口` 的聚合
- 不支持翻页

### [🔗适用的网站](/feat/#%E9%80%82%E7%94%A8%E6%80%A7)
