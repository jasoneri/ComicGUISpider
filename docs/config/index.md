# 🔨 主配置

![conf](../assets/img/config/conf_usage.png)

::: info 配置文件为初始使用后产生的 `conf.yml` （[📒3-配置系文件路径](/faq/extra.html#_3-%E9%85%8D%E7%BD%AE%E7%B3%BB%E6%96%87%E4%BB%B6%E8%B7%AF%E5%BE%84)）  
有关生效时间节点请查阅 [📒2-配置生效相关](../faq/extra.md#_2-配置生效相关)  
:::
::: warning 多行的编辑框输入为 `yaml` 格式（除了 cookies ），冒号后要加一个⚠️ `空格` ⚠️  
:::

## 配置项 / 对应 `yml` 字段

### 存储路径 / `sv_path`

::: warning 良好的习惯是创建一个空目录，并设于此处  
因为默认值，⚠️ win 没D盘的必须改  
同时设置防呆警告，所列情况设置无效：①设在盘符根；②设在 CGS 相关目录内
:::

默认值：&emsp;`win: D:\Comic`&emsp;`macOS: ~/Downloads/Comic`  
目录结构里还有个 `web` 文件夹的情况是因为默认关联 [`redViewer`](https://github.com/jasoneri/redViewer) 项目而设的

### 日志等级 / `log_level`

后台运行过后会有 log 目录，GUI 与 后台 同级，报错时 GUI 会进行操作指引

### 并发数 / `concurr_num`

影响后台下载速度  

### 去重 / `isDeduplicate`

勾选状态下，预览窗口会有已下载的样式提示  
同时下载也会自动过滤已存在的记录  
> [!Info] 当前仅🔞网适用

### 增加标识 / `addUuid`

存储时目录最后增加标识，用以处理同一命名的不同作品等（[对应逻辑](../faq/other.md#_1-去重，增加标识相关说明)）

### 代理 / `proxies`

翻墙用  
> [!Warning] ⚠️ 已设置 jm 无论用全局还是怎样都只走本地原生ip  

> [!Info] 建议使用代理模式在此配置代理，而非全局代理模式，不然访问图源会吃走大量代理的流量

### pypi源 / `pypi_source`

「代理输入框」右侧的选择框  
涉及到 CGS更新、脚本集额外依赖安装等，其序号映射如下

```yaml
0: pypi
1: 清华源
2: 阿里源
3: 华为源
```

### 夜间模式 / `darkTheme`

「pypi源选择框」右侧的「月亮图标」按钮  
形式为开关布尔值，根据值切换日间/夜间模式

### 映射 / `custom_map`

搜索输入映射  
当搜索与预设不满足使用时，先在此加入键值对，重启后在搜索框输入自定义键就会将对应网址结果输出，`🎥视频使用指南3`有介绍用法  

1. 映射无需理会域名，前提是用在当前网站，只要满足 `不用映射时能访问` 和 `填入的不是无效的url`，
程序会内置替换成可用的域名，如非代理下映射的`wnacg.com`会自动被替换掉  
2. 注意自制的映射有可能超出翻页规则范围，此时可通知开发者进行扩展

### 预设 / `completer`

自定义预设  
鼠标悬停在输入框会有`序号对应网站`的提示(其实就是选择框的序号)  
`🎥视频使用指南3`有介绍用法  

### cookies / `cookies`

目前选择编辑支持 `ehentai`, `jm`

[🎬获取方法](https://jsd.vxo.im/gh/jasoneri/imgur@main/CGS/ehentai_get_cookies_new.gif) | [🔗动图中的curl转换网站](https://tool.lu/curl/)  
任意网站同理，登录状态下开 F12 控制台然后点首页，筛选出 html/文档 类型请求复制其 curl (POSIX/bash)  
`v2.2.6-beta` 之后版本支持直接将 curl 文本粘贴到编辑框内，程序已内置转换处理  

:::warning 使用 exhentai 时必需设值
设值后，大量下载导致被服务器对账号实施处理的后果自行负责  
:::

### 剪贴板db / `clip_db`

::: tip 前提：已阅 [`🎸5-读剪贴板`](/feat/index#_5-读剪贴板) 功能说明
:::

读取剪贴板功能无法使用时可查看路径是否存在，通过以下查得正确路径后在此更改  

1. ditto(win): 打开选项 → 数据库路径  
2. maccy(macOS): [issue 搜索相关得知](https://github.com/p0deje/Maccy/issues/271)

### 读取条数 / `clip_read_num`

读取剪贴板软件条目数量

## 其他 `yml` 字段

::: info 此类字段没提供配置窗口便捷修改（或以后支持），不设时使用默认值
:::

### `img_sv_type`

默认值： `jpg`  
图片文件命名后缀  

### `rv_script`

默认值：  
rV(redViewer) 绑定的启动脚本，用于启动 rV 等  

### `bg_path`

默认值：  
会递归搜索该目录下所有png格式图片，然后随机抽一张设成文本输出框的背景  
