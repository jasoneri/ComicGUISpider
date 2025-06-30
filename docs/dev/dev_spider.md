# ✒️ 其他网站的扩展开发指南

Website crawler develope guide

基于 `Scrapy`  
需切换到 **下一个版本** Minor 开发分支，PR 时提交到此分支

## 开发步骤

### 1. 爬虫代码

以 wnacg 为例

### WnacgSpider

[`代码位置`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/ComicSpider/spiders/wnacg.py)

#### 类属性

&emsp;✅ name: 爬虫名字，取目标网站域名的部分或标题，与分支名相同  
&emsp;✅ domain: 目标网站域名  
&emsp;✅ search_url_head: 搜索页url(去掉关键词)，大部分网站都是以get形式直出的  
&emsp;🔳 custom_settings: `scrapy`客制设定。举例两个应用  
&emsp;&emsp; `wnacg`里的`ComicDlProxyMiddleware`, 配置里设了代理时 & 走目标网站域名情况下，会通过代理进行访问  
&emsp;&emsp; `jm`里的`JmComicPipeline`，禁漫的图片直接访问链接时是切割加密过的(可自行浏览器右键新建标签打开图像)，这里做了解密还原了  
&emsp;🔳 ua: 若`custom_settings`设了 `UAMiddleware` 才会生效  
&emsp;🔳 mappings: 默认映射，与`更改配置`里的`映射`相叠加  
&emsp;🔳 frame_book_format: 影响传递给`self.parse_section`的`meta`组成  
&emsp;🔳 turn_page_search/turn_page_info: 翻页时需要，使用为`utils.processed_class.Url`， 参照已有案例即可  (注意`Url.set_next`，受传参个数影响)

#### 类方法

&emsp;🔳 @property search: 生成第一个请求的连接，可结合`mappings`进行复杂输入的转换  
&emsp;🔳 start_requests: 发出第一个请求，可在此进行`search`实现不了 或 不合其逻辑的操作  
&emsp;✅ frame_book: "搜索 > 书列表" 之间的清洗  
&emsp;✅ frame_section:  
&emsp;&emsp; 一跳页面：书页面 > 能直接获取该书的全页  
&emsp;&emsp; 二跳页面：书页面 > 章节列表 之间的清洗  
&emsp;🔳 parse_fin_page: (一跳页面不需要，二跳页面必须) 章节页面 > 直接获取该章节的全页  
&emsp;🔳 mk_page_tasks: 跟三跳页面相关，可以用巧妙方法绕过，初始先不管，二跳页面情况下参考`kaobei.py`

#### 常用方法

+ self.say: 能将字符串(可使用部分html标签格式)打印在gui上  
+ utils.processed_class.PreviewHtml: 通过`add`喂预览图链接，结束后用`created_temp_html`  
  生成临时html文件。实例详见`WnacgSpider.frame_book`

### WnacgUtils

[`代码位置`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/website/__init__.py)  
常规漫与🔞继承基类不同

#### 类属性(Utils)

&emsp;✅ name: 同爬虫名字  
&emsp;✅ uuid_regex: 将 作品id 从作品 预览url 中抽取的正则表达式  
&emsp;🔳 headers: 通用请求头  
&emsp;🔳 book_hea: 读剪贴板功能使用的请求头  
&emsp;🔳 book_url_regex: 读剪贴板功能使用所对应当前网站抽取 作品id 的正则表达式  

#### 类方法(Utils)

&emsp;🔳 parse_publish_: 清洗发布页  
&emsp;🔳 parse_book: 清洗出读剪贴板功能的信息  
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

在最下方加入代码（需参考 `variables/__init__.py` 的 `SPIDERS` 避免使用重复序号导致覆盖）

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
