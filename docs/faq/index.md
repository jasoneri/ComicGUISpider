# ❓ 常见问题

## 1. GUI

::: warning 鉴于还是有人不看快速开始，再次声明启动出现各种异常的万恶之源！  
⚠️ 解压路径不能含有中文/中标 ⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️  
:::

### 预览窗口页面显示异常/页面空白/图片加载等

刷新一下页面  
有些是 JavaScript 没加载，有些是对方服务器问题  

### pypi换源指引

先选出当前网络环境能打开的（[清华源](https://pypi.tuna.tsinghua.edu.cn/simple/)
 / [阿里源](https://mirrors.aliyun.com/pypi/simple/)
 / [华为源](https://repo.huaweicloud.com/repository/pypi/simple/)，后缀加上 comicguispider 检测
）

::: warning 不限于以上三个常用国内源，可以网上搜索`pypi国内源`用你能连上的即可
除以下两种形式外，所有文档的所有涉及pypi源命令因网络问题出错的都是更换源网址这样去处理  
:::

#### Ⅰ. 绿色包部署换源

::: tip 默认是清华源，以下是切换至阿里源命令示例，在解压目录开终端

```cmd
.\CGS.exe -i https://mirrors.aliyun.com/pypi/simple
```
:::

#### Ⅱ. CGS更新/脚本集(kemono)额外依赖换源

默认使用清华源，换源通过 [配置窗口点选更换](/config/#pypi%E6%BA%90-pypi-source)  

## 2. 爬虫

### jm的章节下载

仅能在 [📋读剪贴板](/feat/clip.md) 流程中使用，点进去看相关教程

### 拷贝/Māngabz多选书情况

多选书时，在章节序号输入时可直接点击`开始爬取`跳过当前书的章节选择，只要出进度条即可

## 3. 其他

### ModuleNotFoundError: No module named 'xxx'

截图或带上 `log` 提交 [issue](
  https://github.com/jasoneri/ComicGUISpider/issues/new?template=bug-report.yml
)

### 更新失败后程序无法打开

::: tip 两种方式可选  

- 换一个解压目录 并重新解压📦绿色包，然后重新初始化部署/更新  
- 干脆直接使用 [uv tool方式部署安装](/deploy/quick-start#1-下载--部署)
:::

---

::: warning 如果存在上述没有覆盖的问题
请带上 `log` 到 [issue](
  https://github.com/jasoneri/ComicGUISpider/issues/new?template=bug-report.yml
) 反馈 或 进群(右上角qq/discord)反馈。  
:::

<iframe src="https://discord.com/widget?id=1373740034536112138&theme=dark" width="350" height="500" allowtransparency="true" frameborder="0" sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"></iframe>
