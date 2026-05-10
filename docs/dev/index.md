# ✒️ 开发指南

后续会基于 ai 规则 / 工作流 / skills，方便统一规范测试

::: tip 当前说明适用于当前仓库的 provider / runtime 架构
`2.10-dev` 以后的分支新增或迁移站点请以下文为准。
:::

## 爬虫开发

开始开发的准备：`git` 克隆本项目到本地  
使用主流模型 / CLI（`claudecode` / `codex` / `cursor`） 等等，纯对话模型不要参与

### 前期准备

目标网站

- 搜索接口 curl请求/响应
- 翻页接口 curl请求/响应
- 首页/更新接口 curl请求/响应
- (表漫)书详情 > 章节列表 curl请求/响应
- 书详情/章节详情 > 页数 curl请求/响应

如已知，也建议一并准备：

- 是否需要代理 / cookies
- 网站属于普通漫画还是 🔞
- 是否支持 aggr / clip
- 是否存在动态 domain / 发布页 / 特殊 referer

> 保存上述 curl 资料后，把资料路径交给主 agent，并要求它读取 docs\dev\index.md 的 prompt-prepare 和 prompt-dev
> 主 agent 作为调度与审核 owner，先串行派发 prepare agent：按 prompt-prepare 验证请求矩阵，并输出可供 prompt-dev 消费的素材摘要
> 主 agent 审核网络链路可行后，再串行派发 dev agent：基于素材摘要按 prompt-dev 实际开发
> 最后由主 agent 审核 diff、验证结果与是否需要回归处理

::: details prompt-prepare ⇩

```text
site_name=
site_url=

作为熟悉 Python、httpx 与本仓库架构的开发者，现在你需要为 ComicGUISpider 新站点准备请求响应夹具。

## 任务目标

基于开发者提供的 site_url 和已知站点特征，协助完成以下夹具捕获与验证工作。
所有夹具仅供本地验证，禁止 git 跟踪。

## 一、夹具捕获

1. 在浏览器中访问站点，使用 DevTools → Network 抓取各阶段的真实请求与响应
2. 对每个交互阶段保存一对文件：`<stage>_req.curl`（Copy as cURL）+ `<stage>_resp.<html|json>`（响应 Body）
3. 推荐目录：`test/analyze/<site>/`

### 最少必需阶段

| 阶段 | 文件前缀 | 说明 |
|------|----------|------|
| 搜索 | `search_*` | 搜索请求与结果列表 |
| 书页 | `book_*` | 书籍详情页，含章节引导 |
| 章节 | `chapter_*` | 章节列表（XHR 或内嵌） |
| 内页 | `section_*` | 章节内页图片数据 |

4. 复杂站点可能还有：首页(`index_*`)、搜索建议(`search_suggest_*`)、书元数据XHR(`book_pop_*`) 等，按实际交互补充

## 二、验证矩阵（可选）

1. 基于捕获的夹具编写解析验证脚本：`test/net/<site>/transport_matrix.py`
2. 对每个阶段用正则或解析器提取关键字段，输出 `[OK]` / `[ERR]` 报告
3. 确认 HTML/JSON 结构可被稳定解析

## 三、输出素材摘要

将验证结果整理为以下格式，供 prompt-dev 消费：

site_name: <站点英文标识>
site_url: <站点首页>
search_url: <搜索页 URL>
book_url: <书页 URL>

**已验证的交互阶段**
stages:
  search: <搜索方式：JSON XHR / HTML 分页 / ...>
  book: <书页结构：loader引导 / 直接章节列表 / ...>
  chapter: <章节来源：XHR / 内嵌HTML / ...>
  pages: <内页图片：XHR / 直接img / ...>

**站点特征**
need_proxy: 是/否
need_cookies: 是/否
site_kind: 普通漫画 / R18
supports_preview: 是/否
supports_aggr: 是/否
supports_clip: 是/否
dynamic_domain: 是/否

## 四、要求

- 夹具路径可自定义，不必与示例一致
- 不要伪造数据；无把握的阶段标注为"未验证"即可
- 异常直接暴露根因，不要静默跳过或吞错误
```

:::

#### 实际开发

将上一步的 curl资料 和已知站点特征/夹具准备等补进下面的 prompt，发给 ai 执行

::: details prompt-dev ⇩

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

先阅读仓库现状再编码，以当前代码结构为准。

当前站点接入遵循 provider-first contract：

- 请求、解析、preview、cookies/domain/proxy、章节与图片 URL 定位放在 `utils/website/providers/`
- spider 承担 Scrapy 下载装配
- provider 和 spider 各司其职，避免重复实现同一站点规则

## 本地开发相关
请按以下六个部分完成开发：

**一、先做基线检索（必须先检索，后生成）**

1. 先在仓库中找 1 到 2 个最像的现有站点做基线，至少同时阅读：
   - `utils/website/providers/_template.py`
   - `utils/website/providers/<baseline>.py`
   - `ComicSpider/spiders/<baseline>.py`（仅参考下载装配）
   - `ComicSpider/spiders/basecomicspider.py`
   - `utils/website/ins.py`
   - `utils/website/registry.py`
   - `utils/website/site_runtime.py`
   - `variables/__init__.py`
   - `GUI/mainwindow.py`
   - `GUI/manager/preprocess.py`
2. 先判断新站点属于“常规接入”还是“扩展接入”：
   - 常规接入：provider 完成节点抽取、搜索 URL、书页、章节、图片页解析
   - 扩展接入：provider 还需要请求层扩展、响应适配、资源定位、动态 domain / cookies / 发布页等能力
3. 命名时先统一以下标识：
   - provider `name`
   - 下载 spider `name`（确需 spider 时）
   - `variables.Spider` 枚举名
   - `utils.website.ins.py` 的 `_PROVIDER_BINDINGS` 键（挂到对应 `Spider.*`，不要手写数字 key）
   - `variables/__init__.py` 的站点展示名映射（`GUI/mainwindow.py` 会自动生成下拉文案）
4. 若当前代码里已有同类站点实现，不要跳过对照，先抽能力矩阵再开发

**二、provider 部分**

1. 在 `utils/website/providers/` 下创建新 provider 文件，优先以 `_template.py` 为起点
2. 视站点能力组合正确的 mixin / 结构：
   - 每个 provider 文件通常包含三个类：`XxxParser`（继承 `Previewer`，负责解析）、`XxxReqer`（继承 `Req`，负责请求与 preview 流程）、`XxxUtils`（继承 `Utils` + `Previewer`，组合 `parser` 与 `reqer_cls`）
   - `R18` 站点通常围绕 `EroUtils`
   - 需要动态 domain 时使用 `DomainUtils`
   - 需要 cookies 时补 `Cookies`
3. `XxxUtils` 里至少明确这些静态配置：
   - `name` / `domain` / `index`
   - `headers` / `book_hea`
   - `uuid_regex` 或 `get_uuid`
   - `parser` / `reqer_cls` / `__init__`（实例化 `self.reqer` 与 `self.parser`）
4. `XxxParser` 负责解析方法（`parse_search` / `parse_book` / `parse_search_item` / 章节列表 / reader 解码 / 图片 URL 构建等）
5. `XxxReqer` 负责请求与 preview 异步流程；复杂站点需要将逻辑拆分到合适的类中
6. 按站点需要补充这些扩展点：
   - `build_preview_search_request()`（Parser 类方法，构建搜索 `PreviewRequestSpec`）
   - `preview_search()` / `preview_fetch_episodes()` / `preview_fetch_pages()`（Reqer 异步方法）
   - `preview_client_config()` / `preview_transport_config()`（Utils 类方法）
   - `test_index()`
   - `parse_publish_()`
   - 资源定位 / 响应适配辅助函数
   - 站点专用异常类型
7. 已有全局捕获异常机制，业务代码不进行冗余捕获，静默返回空值或无说明的兼容补丁

**三、spider 部分**

1. 仅当站点需要进入 Scrapy 下载链路时，才新增或修改 `ComicSpider/spiders/<site>.py`
2. provider-first 站点的下载路线：下载入口消费已由 provider preview 填充的下载对象
   - `Spider.mangas()` 站点：提交 Scrapy 前，由 `preview_fetch_pages()` 填充 `Episode.page_urls`
   - spider 侧专注于下载装配，书页、章节页、图片页解析收口在 provider
   - 开发前确认章节与图片页解析已在 provider 内覆盖；spider 只消费 provider 的预览链路结果
3. 根据下载流程选择基类：
   - `BaseComicSpider`
   - `BaseComicSpider2`
   - `BaseComicSpider3`
   - `FormReqBaseComicSpider`
4. 只补基类要求的下载字段：
   - `name`
   - `domain`
   - `search_url_head`
   - `book_id_url` / `transfer_url`（基类或跳转流程需要时）
   - `mappings`（默认至少支持 `首页`或`更新`）
   - `turn_page_search` / `turn_page_info`（基类仍需要页码映射时）
5. 只按下载 fan-out 缺口实现：
   - `_process_episode()`：普通漫画站点消费 `Episode.page_urls` 并装配 item；未填充时抛出明确错误，作为 provider 预览链路的自检点
   - `process_item()`：仅用于 fake request 转交已构造 item
   - `image_request_meta()`（图片请求确实需要章节 referer 等元信息时）
   - `custom_settings`（最小且正确的 middleware / pipeline 组合）
6. 将 `frame_section()` / `parse_fin_page()` 等解析逻辑收口在 provider，spider 内只走单一下载路线
7. spider 通过下载对象消费 provider 预览结果；搜索、书页、章节、reader 与图片 URL 解析统一在 provider 完成
8. 需要代理、Referer 或 UA 时再装配：
   - `ComicDlProxyMiddleware`
   - `ComicDlAllProxyMiddleware`
   - `RefererMiddleware`
   - `UAMiddleware`
   - 其他站点专用 middleware

**四、注册、GUI 与运行时接线**

1. 在 `utils/website/providers/__init__.py` 导出新 provider
2. 在 `utils/website/ins.py` 的 `_PROVIDER_BINDINGS` 里把 provider 绑定到对应 `Spider` 成员；`provider_map` 会自动处理剩下的展开
3. 在 `variables/__init__.py` 中同步：
   - `Spider` 枚举
   - `DEFAULT_COMPLETER`
   - `STATUS_TIP`
   - `COOKIES_SUPPORT`（需要登录状态的 cookies 时，非登录的短效令牌不得写入）
   - 能力集合：`specials()` / `mangas()` / `cn_proxy()` / `aggr()` / `clip()`
4. 明确 `specials()` 与 `preview_fetch_episodes()` 的契约：
   - 属于 `specials()` 的站点通常不需要 CLI `-i2`
   - 非 `specials()` 站点需要保证章节选择链路正常
5. 只有站点确实需要专门预处理时，才修改 `GUI/manager/preprocess.py`

**五、测试与回归**

1. 如需自动验证，使用 `unittest`，并由 agent 根据本次接入内容自行在 `test/` 下创建测试脚本
2. 这些测试脚本默认用于本地验证，此 repo 的管理者已明确要求禁止 git 跟踪 unittest 相关资产
3. 夹具统一放 `test/analyze/` 或测试脚本配套目录，不要内联大段 HTML
4. 先跑 CLI 链路：
   - `uv run crawl_only.py -w 序号 -k 关键词 -i 1`
   - 非 `specials()` 站点再补 `-i2 1`
   - 普通漫画站点 CLI 在提交 Scrapy 前调用 `preview_fetch_pages()` 填充 `Episode.page_urls`
5. 再跑 GUI 链路：
   - `uv run CGS.py`
6. 需要时由 agent 自行执行对应的 `uv run python -m unittest ...`
7. 检查搜索、预览、章节选择、下载、任务面板、`log/scrapy.log` 是否都正常
8. 遇到兼容节点或职责边界冲突时，先把冲突点明确列出并说明影响，再决定实现方式

**六、输出要求**

- 提供完整可运行的代码
- 仅修改与目标站点接入直接相关的文件
- 默认使用 `uv`
- 测试使用 `unittest`；若需补自动验证，由 agent 在 `test/` 下自行创建脚本
- 注释非必要不添加
- 业务代码不进行冗余捕获，不隐藏报错堆栈
- 代码完成后使用 `$style-refactor` 对本轮改动做一次结构清洗
- 提醒用户 PR 应合并到当前最新的 `*-dev` 分支
```

:::

### 开发后的调整

开发完成首轮跑通是基础，但一般需要进行调整  
至少需要保证如下正常

1. 首页index/更新接口
2. 搜索接口
3. 翻页

需能达到正常的列表输出下载的流程使用

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

> [!tip] 当前运行时通过 `utils/website/ins.py` 的 `provider_map` 经 `registry.py` 生成 `provider_descriptor_map` 与 `provider_descriptor_spider_map`。新增站点时不要只改 provider 文件本身。

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
&emsp;✅ `_process_episode`（普通漫画站点只消费已填充 `page_urls` 的 Episode）  
&emsp;🔳 `process_item`  
&emsp;🔳 `image_request_meta`  
&emsp;🔳 `custom_settings`（middleware / pipeline 组合）

> [!tip] spider 负责下载装配，解析规则统一收口 provider。普通漫画站点的章节与图片页数据应在 provider preview 链路完成，`Episode.page_urls` 空值时抛出明确错误，无需在 spider 侧补另一条请求路线。

### 3. 其他代码

#### [`variables/__init__.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/variables/__init__.py)

1. `Spider` - 新站点先补枚举成员，能力分组通过类方法维护：
   - `specials()`
   - `mangas()`
   - `cn_proxy()`
   - `aggr()`
   - `clip()`
2. `SPIDERS` - 由 `Spider` 枚举自动生成
3. `SPIDERS_LABELS` / 站点展示名映射 - `chooseBox` 文案由此自动生成
4. `DEFAULT_COMPLETER` - 新序号的默认预设
5. `STATUS_TIP` - 新序号的状态栏提示
6. `COOKIES_SUPPORT` - 需要 cookies 的站点补支持字段

> [!TIP] `specials()` 不只是分类文案，它会直接影响 GUI / CLI 下载契约；非 `specials()` 站点的 CLI 需要 `-i2/--indexes2`。

### 4. UI 代码

#### [`GUI/mainwindow.py`](https://github.com/jasoneri/ComicGUISpider/blob/GUI/GUI/mainwindow.py)

`apply_translations()` 会按 `variables.__init__.py` 的 `SPIDERS_LABELS` 自动重建 `chooseBox`。新增站点时应维护变量侧展示名映射，而不是在这里手写 `setItemText()`。

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
