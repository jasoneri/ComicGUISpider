# ✒️ 开发指南

后续会基于 ai 规则 / 工作流 / skills，方便统一规范测试

::: tip 当前说明适用于当前仓库的 provider / gateway / runtime 架构
`2.10-dev` 以后的分支新增或迁移站点请以下文为准。
:::

## 爬虫开发

#### 前期准备

目标网站搜索 url (`search_url`)、搜索页面 html (`search.html`)，  
书页 url (`book_url`)、书页 html (`book.html`)

如已知，也建议一并准备：

- 是否需要代理 / cookies
- 网站属于普通漫画还是 🔞
- 是否支持 aggr / clip
- 是否存在动态 domain / 发布页 / 特殊 referer / `verify=False`

#### 实际开发

1. `git` 克隆本项目到本地，使用主流模型 / CLI（`claudecode` / `codex`）
2. 将第一步的 url、html 和已知站点特征补进下面的 prompt，发给 ai 执行

::: details prompt ⇩

```text
search_url=
book_url=
site_name=
need_proxy=
need_cookies=
site_kind=普通漫画 / R18
supports_preview=
supports_aggr=
supports_clip=

作为熟悉 Python、Scrapy、httpx 与本仓库架构的开发者，现在你需要在 ComicGUISpider 当前分支上扩展新网站。

先阅读仓库现状再编码，禁止按旧文档直接假设路径和职责。若发现当前结构与旧结构不一致，以当前代码为准。

## 本地开发相关
请按以下六个部分完成开发：

**一、先做基线检索（必须先检索，后生成）**

1. 先在仓库中找 1 到 2 个最像的现有站点做基线，至少同时阅读：
   - `utils/website/providers/_template.py`
   - `utils/website/providers/<baseline>.py`
   - `ComicSpider/spiders/<baseline>.py`
   - `ComicSpider/spiders/basecomicspider.py`
   - `utils/website/ins.py`
   - `variables/__init__.py`
   - `GUI/mainwindow.py`
   - `GUI/manager/preprocess.py`
2. 先判断新站点属于“常规接入”还是“扩展接入”：
   - 常规接入：主要是节点抽取、常规搜索 URL 组织
   - 扩展接入：还需要请求层扩展、响应适配、资源定位规则、middleware 组合、动态 domain / cookies / 发布页等能力
3. 命名时先统一以下标识：
   - provider / spider `name`
   - `variables.Spider` 枚举名
   - `utils.website.ins.py` 的注册 key
   - GUI 下拉展示名
4. 若当前代码里已有同类站点实现，不要跳过对照，先抽能力矩阵再开发

**二、provider 部分（站点能力主体）**

1. 在 `utils/website/providers/` 下创建新 provider 文件，优先以 `_template.py` 为起点
2. 视站点能力组合正确的 mixin / 结构：
   - 常规站点通常围绕 `Utils` / `Req` / `Previewer`
   - `R18` 站点通常围绕 `EroUtils`
   - 需要动态 domain 时使用 `DomainUtils`
   - 需要 cookies 时补 `Cookies`
3. provider 里至少明确这些能力：
   - `name`
   - `domain` / `index`
   - `headers` / `book_hea`
   - `uuid_regex` 或 `get_uuid`
   - `parse_search_item`
   - `parse_search`
   - `parse_book`
4. 当前架构优先使用 request / parser 分层；复杂站点不要把所有逻辑都堆进一个大类里
5. 按站点需要补充这些扩展点：
   - `reqer_cls`
   - `build_search_url()`
   - `preview_search()`
   - `preview_fetch_episodes()`
   - `preview_fetch_pages()`
   - `preview_client_config()`
   - `preview_transport_config()`
   - `test_index()`
   - `parse_publish_()`
   - 资源定位 / 响应适配辅助函数
   - 站点专用异常类型
6. 保持异常直接暴露根因，不要吞异常、静默返回空值或做无说明的兼容补丁

**三、spider 部分（下载装配）**

1. 在 `ComicSpider/spiders/` 下创建站点 spider 文件
2. 根据真实流程选择合适基类：
   - `BaseComicSpider`
   - `BaseComicSpider2`
   - `BaseComicSpider3`
   - `FormReqBaseComicSpider`
3. spider 至少要明确这些契约：
   - `name`
   - `domain`
   - `search_url_head`
   - `book_id_url` / `transfer_url`（需要时）
   - `mappings`
   - `turn_page_search` / `turn_page_info`
4. 按站点需要实现：
   - `preready()`
   - `frame_book()`
   - `frame_section()`
   - `parse_fin_page()`
   - `custom_settings`（最小且正确的 middleware / pipeline 组合）
5. spider 侧不要重复写解析规则；优先通过 `self.site` / adapter 消费 provider 能力
6. 需要代理时再决定是否装配：
   - `ComicDlProxyMiddleware`
   - `ComicDlAllProxyMiddleware`
   - `RefererMiddleware`
   - `UAMiddleware`
   - 其他站点专用 middleware

**四、注册、GUI 与运行时接线**

1. 在 `utils/website/providers/__init__.py` 导出新 provider
2. 在 `utils/website/ins.py` 的 `provider_map` 注册站点；运行时会同步生成 `site_gateway_map` 与 `spider_adapter_map`
3. 在 `variables/__init__.py` 中同步：
   - `Spider` 枚举
   - `SPIDERS`
   - `DEFAULT_COMPLETER`
   - `STATUS_TIP`
   - `COOKIES_SUPPORT`（需要 cookies 时）
   - 能力集合：`specials()` / `mangas()` / `cn_proxy()` / `aggr()` / `clip()`
4. 在 `GUI/mainwindow.py` 的 `apply_translations()` 中补 `chooseBox` 下拉文案，不是旧的 `setupUi()`
5. 只有站点确实需要专门预处理时，才修改 `GUI/manager/preprocess.py`
6. 明确 `specials()` 与 `preview_fetch_episodes()` 的契约：
   - 属于 `specials()` 的站点通常不需要 CLI `-i2`
   - 非 `specials()` 站点需要保证章节选择链路正常

**五、测试与回归**

1. 如需自动验证，使用 `unittest`，并由 agent 根据本次接入内容自行在 `test/` 下创建测试脚本
2. 这些测试脚本默认用于本地验证，此 repo 的管理者已明确要求禁止 git 跟踪 unittest 相关资产
3. 夹具统一放 `test/analyze/` 或测试脚本配套目录，不要内联大段 HTML
4. 先跑 CLI 链路：
   - `uv run crawl_only.py -w 序号 -k 关键词 -i 1`
   - 非 `specials()` 站点再补 `-i2 1`
5. 再跑 GUI 链路：
   - `uv run CGS.py`
6. 需要时由 agent 自行执行对应的 `uv run python -m unittest ...`
7. 检查搜索、预览、章节选择、下载、任务面板、`log/scrapy.log` 是否都正常
8. 若发现兼容节点或职责边界冲突，先把冲突点明确列出并说明影响，再决定如何实现

**六、输出要求**

- 提供完整可运行的代码
- 仅修改与目标站点接入直接相关的文件
- 默认使用 `uv`
- 测试使用 `unittest`；若需补自动验证，由 agent 在 `test/` 下自行创建脚本
- 注释非必要不添加
- 禁止隐藏报错堆栈，异常直接暴露根因
- 代码完成后使用 `$style-refactor` 对本轮改动做一次结构清洗
- 提醒用户 PR 应合并到当前最新的 `*-dev` 分支
```

:::

> [实例 PR 参考](https://github.com/jasoneri/ComicGUISpider/issues?q=state%3Aclosed%20label%3A%22dev%20spider%22)

## 注意

ai 作为手段并不一定可靠，ai 开发流程中出现预期偏差时，先尝试以自身代码 / 文档阅读能力解决

::: details ✒️当前架构下的网站开发说明

### 1. provider 代码

建议同时看两个样板：

[scrapy 下载装配: `WnacgSpider`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/ComicSpider/spiders/wnacg.py)  
[provider 样板: `HComicUtils / HComicReqer / HComicParser`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/website/providers/hcomic.py)  
[provider 模板: `TemplateUtils`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/website/providers/_template.py)

#### Provider 文件落点

&emsp;✅ 新站点主体放在 `utils/website/providers/<site>.py`  
&emsp;✅ 导出放在 `utils/website/providers/__init__.py`  
&emsp;✅ 注册放在 `utils/website/ins.py` 的 `provider_map`

#### Provider 常见职责

&emsp;✅ `name` / `domain` / `index`  
&emsp;✅ `headers` / `book_hea`  
&emsp;✅ `uuid_regex` 或 `get_uuid()`  
&emsp;✅ `parse_search_item` / `parse_search` / `parse_book`  
&emsp;🔳 `reqer_cls`（复杂站点建议拆请求层）  
&emsp;🔳 `preview_search` / `preview_fetch_episodes` / `preview_fetch_pages`  
&emsp;🔳 `preview_client_config` / `preview_transport_config`  
&emsp;🔳 `test_index`  
&emsp;🔳 `parse_publish_` / 动态 domain / cookies / 资源定位规则  
&emsp;🔳 站点专用异常类型

> [!tip] 当前运行时通过 `utils/website/ins.py` 的 `provider_map` 生成 `site_gateway_map` 与 `spider_adapter_map`。新增站点时不要只改 provider 文件本身。

### 2. spider 代码

#### [`ComicSpider/spiders/basecomicspider.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/ComicSpider/spiders/basecomicspider.py)

先判断最接近的新站点样板再选基类：

&emsp;✅ `BaseComicSpider`：通用入口  
&emsp;✅ `BaseComicSpider2`：章节页可直接产出最终图片 URL  
&emsp;✅ `BaseComicSpider3`：多跳分页流程  
&emsp;✅ `FormReqBaseComicSpider`：表单请求型站点

#### spider 常见职责

&emsp;✅ `name` / `domain` / `search_url_head`  
&emsp;🔳 `book_id_url` / `transfer_url`  
&emsp;🔳 `mappings` / `turn_page_search` / `turn_page_info`  
&emsp;🔳 `preready`  
&emsp;✅ `frame_book`  
&emsp;✅ `frame_section`  
&emsp;🔳 `parse_fin_page`  
&emsp;🔳 `custom_settings`（middleware / pipeline 组合）

> [!tip] spider 负责下载装配，不应重复堆解析规则。当前代码通常通过 `self.site` 消费 provider 的 request / parser 能力。

### 3. 其他代码

#### [`variables/__init__.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/variables/__init__.py)

1. `Spider` - 新站点先补枚举成员，能力分组通过类方法维护：
   - `specials()`
   - `mangas()`
   - `cn_proxy()`
   - `aggr()`
   - `clip()`
2. `SPIDERS` - 由 `Spider` 枚举自动生成
3. `DEFAULT_COMPLETER` - 新序号的默认预设
4. `STATUS_TIP` - 新序号的状态栏提示
5. `COOKIES_SUPPORT` - 需要 cookies 的站点补支持字段

> [!TIP] `specials()` 不只是分类文案，它会直接影响 GUI / CLI 下载契约；非 `specials()` 站点的 CLI 需要 `-i2/--indexes2`。

### 4. UI 代码

#### [`GUI/mainwindow.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/GUI/mainwindow.py)

在 `apply_translations()` 里加入如下类似代码

```python
self.chooseBox.addItem("")
self.chooseBox.setItemText(8, _translate("MainWindow", "8、h-comic🔞"))
```

只有站点需要额外预处理时，再看 [`GUI/manager/preprocess.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/GUI/manager/preprocess.py) 是否需要专门分支。  
仅有 `test_index()` 的站点通常可以走通用预处理路径。

### 5. 测试

若需要自动验证，建议让 agent 按本次接入内容自行在 `test/` 下创建 `unittest` 脚本；只能用于本地验证，禁止纳入 git。

#### CLI 链路

```bash
uv run crawl_only.py -w 8 -k test -i 1
```

非 `specials()` 站点需要补 `-i2`：

```bash
uv run crawl_only.py -w 5 -k 更新 -i 1 -i2 1
```

#### GUI 链路

```bash
uv run CGS.py
```

> 注意：GUI / Scrapy 异常仍以日志为准，排查时优先看 `log/scrapy.log`，不要用吞异常掩盖根因。

:::
