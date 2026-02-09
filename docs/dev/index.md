# ✒️ 开发指南

后续会基于ai规则/工作流/skills, 方便统一规范测试

## 爬虫开发

#### 前期准备

目标网站搜索url(search_url), 搜索页面html(search.html)，  
书页url(book_url)，书页html(book.html)

#### 实际开发

1. git 克隆本项目到本地，使用主流的模型/Cli (claudecode/codex)
2. 将第一步的两个 url 值加进下面的 prompt 上，上传/指定两个 html 文件，将 prompt 发给 ai

::: details prompt 参考

```text
search_url=
book_url=

作为熟悉python与scrapy，优良代码规范的爬虫工程师，现在你需要在此项目上扩展新网站，

## 本地开发相关
请按照以下四个部分完成开发：

**一、爬虫部分（Spider类开发）**

1. 假如用户没有给目标网站定名，则从 search_url 的域名中提取定名，下文说明使用 `abcdefg` 作为代替
2. 在 `ComicSpider/spiders/` 目录下创建新的爬虫文件（例如：`abcdefg.py`）
3. 实现Spider类，需包含以下必需属性和方法：
   - name：爬虫名称（使用目标网站域名或标题）
   - domain：目标网站完整域名
   - search_url_head：搜索页URL前缀（不含关键词部分）
4. 参考已有的 [WnacgSpider](ComicSpider/spiders/wnacg.py) 实现方式
5. 与用户讨论目标网站是否需要代理才能访问，以此决定 custom_settings 属性是否增加 ComicDlProxyMiddleware / ComicDlAllProxyMiddleware

**二、解析部分（Utils类开发）**

1. 在 `utils/website/` 目录下实现对应的Utils解析类，驼峰命名 AbcdefgUtils
2. 根据网站类型继承正确的基类（常规漫画网站与18+网站基类不同）
3. 实现以下必需属性和方法：
   - name：abcdefg
   - uuid_regex：从预览URL能提取作品ID的正则表达式
   - parse_search：解析 search.html 定位要素，调用 parse_search_item 得到 BookInfo 列表的方法
   - parse_search_item：传参定位要素为单个条目，返回 BookInfo 对象
   - parse_book：能将 book.html 解析为 BookInfo 对象的方法
4. 完成后在 spider_utils_map 中注册该Utils类

**三、UI部分（界面配置）**

1. 在 `variables/__init__.py` 中添加配置：
   - SPIDERS：添加新序号和爬虫名称
   - DEFAULT_COMPLETER：添加序号和默认预设映射（可为空列表）
   - STATUS_TIP：添加序号和状态栏提示文字（可为空字符串）
   - 若为18+网站：在 SPECIAL_WEBSITES 添加爬虫名，在 SPECIAL_WEBSITES_IDXES 添加序号
   - 如预览图需代理访问：在 CN_PREVIEW_NEED_PROXIES_IDXES 添加序号

2. 在 `GUI/mainwindow.py` 的 setupUi 方法中添加下拉选项：
self.chooseBox.addItem("")
self.chooseBox.setItemText(序号, _translate("MainWindow", "序号、网站名"))

**四、测试部分（验证功能）**

1. 无GUI测试：运行 `python crawl_only.py -w 序号 -k 关键词 -i 1` 验证爬虫基本功能
2. GUI测试：运行 `python CGS.py` 完整测试：
- 测试新网站的完整流程（搜索、下载等）
3. 注意日志配置：`ComicSpider/settings.py` 中的 LOG_FILE

**输出要求：**
- 提供完整可运行的代码
- 代码需符合 PEP 8 规范
- XPath 选择器需准确可靠
- 添加必要的注释说明
- 确保错误处理机制完善

## 线上开发相关
开发分支命名格式为`x.x-dev`，根据项目中最新dev分支，提醒用户PR时合并需指向哪个分支
```

:::

## 注意

ai 作为手段并不一定可靠，ai 开发流程中出现预期偏差时，先尝试以自身代码/文档阅读能力解决  

::: details ✒️原网站开发指南

### 1. 爬虫代码

以 wnacg 为例

[scrapy爬虫类: `WnacgSpider`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/ComicSpider/spiders/wnacg.py)  
[xpath解析类: `WnacgUtils`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/website/ins.py)

#### WnacgSpider

&emsp;✅ name: 爬虫名字，取目标网站域名的部分或标题，与分支名相同  
&emsp;✅ domain: 目标网站域名  
&emsp;✅ search_url_head: 搜索页url(去掉关键词)，大部分网站都是以get形式直出的  

##### 类方法

&emsp;🔳 @property search: 生成第一个请求的连接，可结合`mappings`进行复杂输入的转换  
&emsp;🔳 start_requests: 发出第一个请求，可在此进行`search`实现不了 或 不合其逻辑的操作  
&emsp;🔳 parse_fin_page: (一跳页面不需要，二跳页面必须) 章节页面 > 直接获取该章节的全页  

##### 常用方法

+ self.say: 能将字符串(可使用部分html标签格式)打印在gui上  

#### WnacgUtils

常规漫与🔞继承基类不同

##### 类属性(Utils)

&emsp;✅ name: 同爬虫名字  
&emsp;✅ uuid_regex: 将 作品id 从作品 预览url 中抽取的正则表达式  
&emsp;🔳 headers: 通用请求头  
&emsp;🔳 book_hea: 读剪贴板功能使用的请求头  
&emsp;🔳 book_url_regex: 读剪贴板功能使用所对应当前网站抽取 作品id 的正则表达式  

##### 类方法(Utils)

&emsp;✅ parse_search_item: 解析搜索页 xpath -> BookInfo  
&emsp;🔳 parse_book: 读剪贴板功能 xpath 等解析作品页 -> BookInfo  
&emsp;🔳 parse_search: 聚合搜索 xpath 等解析搜索页 -> List[BookInfo]  
&emsp;🔳 parse_publish_: 解析发布页  
&emsp;🔳 test_index: 测试网络环境能否访问当前网站  

> [!tip] 最后需要在 spider_utils_map 加上对应的 Utils

### 2. 其他代码

#### [`variables/__init__.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/variables/__init__.py) 

1. `SPIDERS` - 爬虫名字：加入新序号(方面下面理解设为序号`3`²)，值为爬虫名字`wnacg`
2. `DEFAULT_COMPLETER` - 默认预设：序号必须，值可空列表。用户配置会覆盖，但是可以先把做了开发的映射放进去
3. `STATUS_TIP` - 状态栏输入提示：序号必须，值可空字符串。鼠标悬停在搜索框时，最下状态栏会出现的文字

> [!TIP] 如目标网站为🔞的  
> 还需在`SPECIAL_WEBSITES`加进 爬虫名字`wnacg` （此处影响存储位置）  
> 在`SPECIAL_WEBSITES_IDXES`加进 序号`3`² （此处影响gui逻辑）

### 3. ui 代码

#### [`GUI/mainwindow.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/GUI/mainwindow.py)

在 setupUi 里加入如下类似代码（需参考 `variables/__init__.py` 的 `SPIDERS` 避免使用重复序号导致覆盖）

```python
self.chooseBox.addItem("")
self.chooseBox.setItemText(3, _translate("MainWindow", "3、wnacg🔞"))  # 🔞标识符不影响任何代码
```

---

### 4. 无GUI测试

```python
python crawl_only.py -w 3 -k 首页 -i 1
```

### 5. GUI测试

`python CGS.py`，对进行开发的网站测试流程是否正常，然后测试其他网站有没受影响

> 注意: 当`ComicSpider/settings.py`里的`LOG_FILE`不为空时，控制台不会打印任何信息，只会在日志`log/scrapy.log`中输出，无论什么日志等级  
> 反之想让控制台输出时将其值置为空，在commit时需要改回来

:::