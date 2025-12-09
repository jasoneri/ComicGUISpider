# ✒️ 其他网站的扩展原开发指南

Website crawler develope guide

基于 `Scrapy`  
需切换到 **下一个版本** Minor 开发分支，PR 时提交到此分支

## 开发步骤

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

::: tip 最后需要在 spider_utils_map 加上对应的 Utils
:::

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
