[![License](https://img.shields.io/github/license/rails/rails)](https://github.com/rails/rails)

# 欢迎扩展其他网站支持

## 开发说明

需要 `python`,`抓包`,`xpath` 基础知识即可，仓库已封装了大量方法，以下说明

## 开发步骤

### 1. 克隆仓库，创建新分支，命名以目标网站域名即可

### 2. 代码编写

#### 2.1 爬虫代码

> 首先说明:<br>
>   + 三级跳转 表示 "搜索 > 书列表 > 书章节（例如第1卷/第1话）> 该章节的每一页"<br>
>   + 二级跳转 表示 "搜索 > 书列表 > 没有章节，直接给全书的页数"<br>
      > 从搜索页url得出书url，称为一步跳转。。(压缩/技巧等)直到能拿到图片访问的url，需要几步就称为几级跳转

[爬虫代码存放位置在此](../ComicSpider/spiders)，创建`py脚本`，命名同分支 <br>
二级跳转模版参照`jm.py`,`wnacg.py`，继承类`BaseComicSpider2` <br>
三级跳转模板参照`kaobei.py`，继承类`BaseComicSpider` <br>

下面展开`类属性`与`类方法`等说明，其中选中(打钩)的部分为 开发必须部分

##### 类属性

- [x] name: 爬虫名字，取印象易记的如目标网站域名的部分，与分支名相同亦可 (方面下面理解设为`ehentai¹`)
- [x] domain: 目标网站域名，初始取固定即可 (`jm`,`wnacg`的域名采用 发布页/永久链接 间接动态更新的，可以先不用理解)
- [x] search_url_head: 搜索页url(去掉关键词)，大部分网站都是以get形式直出的
- [ ] custom_settings: `scrapy`客制设定，不了解可以忽略。举例两个应用
    + `wnacg`里的`ComicDlProxyMiddleware`, 配置里设了代理时 & 走目标网站域名情况下，会通过代理进行访问
    + `jm`里的`JmComicPipeline`，禁漫的图片直接访问链接时是切割加密过的(可自行浏览器右键新建标签打开图像)，这里做了解密还原了
- [ ] ua: 若`custom_settings`设了 `UAMiddleware` 才会生效
- [ ] mappings: 默认映射，与`更改配置`里的`映射`相叠加
- [ ] frame_book_format: 影响传递给`self.parse_section`的`meta`组成
- [ ] turn_page_search/turn_page_info: 翻页时需要，使用为`utils.processed_class.Url`， 参照已有案例即可
  (注意`Url.set_next`，受传参个数影响)

##### 类方法

- [ ] @property search: 生成第一个请求的连接，可结合`mappings`进行复杂输入的转换
- [ ] start_requests: 发出第一个请求，可在此进行`search`实现不了 或 不合其逻辑的操作
- [x] frame_book: "搜索 > 书列表" 之间的清洗
- [x] frame_section:
    + 二级跳转：书页面 > 能直接获取该书的全页
    + 三级跳转：书页面 > 章节列表 之间的清洗
- [ ] parse_fin_page: (二级跳转不需要，三级跳转必须) 章节页面 > 直接获取该章节的全页
- [ ] mk_page_tasks: 跟四级跳转相关，可以用巧妙方法绕过，初始先不管，三级跳转情况下参考`kaobei.py`

##### 常用方法

+ self.say: 能将字符串(可使用部分html标签格式)打印在gui上
+ utils.font_color: 自定义\<font>标签，跟self.say配合使用
+ utils.processed_class.PreviewHtml: 通过`add`喂预览图链接，结束后用`created_temp_html`
  生成临时html文件。实例详见`JmSpider.frame_book`

#### 2.2 通设代码

[前往`variables` ](../variables/__init__.py) 更新以下值

1. `SPIDERS` - 爬虫名字：加入新序号(方面下面理解设为序号`4`²)，值为爬虫名字`ehentai¹`
2. `DEFAULT_COMPLETER` - 默认预设：序号必须，值可空列表。用户配置会覆盖，但是可以先把做了开发的映射放进去
3. `STATUS_TIP` - 状态栏输入提示：序号必须，值可空字符串。鼠标悬停在搜索框时，最下状态栏会出现的文字

> 如目标网站为禁漫这类的，还需在`SPECIAL_WEBSITES`加进 爬虫名字`ehentai¹` （此处影响存储位置）<br>
> 在`SPECIAL_WEBSITES_IDXES`加进 序号`4`² （此处影响gui逻辑）

#### 2.3 gui代码

1. [前往`GUI/uic/ui_mainwindow.py` ](../GUI/uic/ui_mainwindow.py) 搜索`self.chooseBox.setItemText`，在`wnacg`条目下方加入代码
    ```python
    self.chooseBox.addItem("")
    self.chooseBox.setItemText(4, _translate("MainWindow", "4、ehentai**"))  # ** 是作为禁漫这类网站的标识，不影响任何代码
    ```

至此代码开发完毕

---

### 3. 测试

#### 纯后台测试 无GUI

根目录的`crawl_only.py`，修改`spider_choice`为序号`4`²，运行测试，根据报错等调整跑通后，进入GUI集成测试

#### GUI测试

> 注意: 当`ComicSpider/settings.py`里的`LOG_FILE`不为空时，控制台不会打印任何信息，只会在日志`log/scrapy.log`
> 中输出，无论什么日志等级 <br>
> 反之想让控制台输出时将其值置为空，在commit时需要改回来

根目录运行`python CGS.py`，进GUI后先进行开发的网站流程是否正常，然后测试其他网站有没受影响

如一切正常，恭喜，之后可以提 `PR`，我会认真阅读每一条代码

### 额外

如开发遇到问题，或想获取建议，欢迎在 `Discussions` 或 Q群 进行讨论，初学者一视同仁
