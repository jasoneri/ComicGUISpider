# ❓ 常见问题

## 1. GUI

### 预览窗口页面显示异常/页面空白/图片加载等

刷新一下页面  
有些是 JavaScript 没加载，有些是对方服务器问题  

## 2. 爬虫

### 拷贝漫画部分无法出列表

拷贝有些漫画卷和话是分开的，api结构转换的当前是有结果的，但没做解析，如需前往群里反馈

### 拷贝/Māngabz多选书情况

多选书时，在章节序号输入时可以直接点击`开始爬取`跳过当前书的章节选择，只要出进度条即可

## 3. 其他

### ModuleNotFoundError: No module named 'xxx'

win:

1. 在绿色包解压的目录打开 (powershell) 终端执行命令  

``` bash
irm https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/online_scripts/win.ps1 | iex
```

::: info 非绿色包的用户参考 [🚀 快速开始 > 部署](../deploy/quick-start#1-下载--部署) 的安装依赖命令示例
:::

macOS: （与 mac部署 初始化步骤命令一样的）  

```bash
bash /Applications/CGS.app/Contents/Resources/scripts/deploy/launcher/mac/init.bash
```

### 更新失败后程序无法打开

::: tip 最简单有效❗️  
下载📦绿色包 覆盖更新  
:::

更新的报错日志已整合进 log/GUI.log 文件里，建议提 issue 并附上 log，帮助 CGS 进行优化  

1. 回退到上一个正常版本: 找到对应版本的 `Source code (zip)` 源码包，解压后将全部源码覆盖到 scripts 目录下  
删除 `scripts/deploy/version.json`，恢复正常使用

2. 安全使用最新版本: 将最新版本的 `Source code (zip)` 源码包，解压后将全部源码覆盖到 scripts 目录下  

2.1 按上面 ModuleNotFoundError 的方法安装依赖

### 【win】弹出消息框报错而且一堆英文不是中文(非开发者预设报错)的时候

例如`Qxxx:xxxx`, `OpenGL`等，此前已优化过，如还有弹出框警告，  
尝试在解压目录使用cmd运行`./CGS.bat > CGS-err.log 2>&1`，然后把`CGS-err.log`发群里反馈

---

::: warning 如果存在上述没有覆盖的问题
请带上 `log` 到 [issue](
  https://github.com/jasoneri/ComicGUISpider/issues/new?template=bug-report.yml
) 反馈 或 进群(右上角qq/discord)反馈。
:::

<iframe src="https://discord.com/widget?id=1373740034536112138&theme=dark" width="350" height="500" allowtransparency="true" frameborder="0" sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"></iframe>
