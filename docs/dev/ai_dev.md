# ✒️ ai开发指南

## ai 爬虫开发

### 前期准备

1. 目标网站搜索url(search_url), 搜索页面html(search.html)，书页url(book_url)书页html(book.html)
2. 根据 ai 模型定方向
    - 通用代码模型（例如 claude）：git 克隆本项目到本地
    - 能指定 github 仓库模型（例如 豆包）：在网站上进行 prompt 对话
    - deepseek 等纯对话模型不推荐，除非人工截断 html 并适当更改 prompt，否则读 html 长上下文被截断就没效果
3. 将第一步的两个 url 值加进下面的 prompt 上，上传/指定两个 html 文件，将 prompt 发给 ai

### prompt 参考

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

**二、解析部分（Utils类开发）**

1. 在 `utils/website/` 目录下实现对应的Utils解析类，驼峰命名 abcdefgUtils
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
- 代码需符合PEP 8规范
- XPath选择器需准确可靠
- 添加必要的注释说明
- 确保错误处理机制完善

## 线上开发相关
开发分支命名格式为`x.x-dev`，根据项目中最新dev分支，提醒用户PR时合并需指向哪个分支
```

## 注意

ai 作为手段并不一定可靠，ai 开发流程中出现预期偏差时，先尝试以自身代码/文档阅读能力解决  
[原开发文档](/dev/dev_spider)
