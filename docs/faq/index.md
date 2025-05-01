# ❓ 常见问题

## 1. GUI

### 预览窗口选择页面有时一行只有一列/显示有问题/页面空白

JavaScript 没加载出来，刷新一下页面

## 2. 爬虫

### 拷贝漫画部分无法出列表

拷贝有些漫画卷和话是分开的，api结构转换的当前是有结果的，但没做解析，如需前往群里反馈

### 拷贝/Māngabz多选书情况

多选书时，在章节序号输入时可以直接点击`开始爬取`跳过当前书的章节选择，只要出进度条即可

## 3. 其他

### ModuleNotFoundError: No module named 'xxx'

win: 利用脚本安装依赖 `./scripts/deploy/launcher/init.bat`  (脚本执行的 pip)  

macOS: 用`CGS-init`更新环境依赖

### 更新失败后程序无法打开

::: tip 最简单 > 备份配置文件和去重记录后到最新 release 下载绿色包（覆盖更新）  
:::

更新的报错日志已整合进 log/GUI.log 文件里，建议提 issue 并附上 log，帮助 CGS 进行优化  

1. 回退到上一个正常版本: 找到对应版本的 `Source code (zip)` 源码包，解压后将全部源码覆盖到 scripts 目录下  
删除文件 `scripts/deploy/version.json`，恢复正常使用

2. 安全使用最新版本: 将最新版本的 `Source code (zip)` 源码包，解压后将全部源码覆盖到 scripts 目录下  

2.1 按上面 ModuleNotFoundError 的方法用 pip 安装依赖

::: info macOS用户自行切换 python 与 requirements/xxx.txt 文件  
:::

### 【win】弹出消息框报错而且一堆英文不是中文(非开发者预设报错)的时候

例如`Qxxx:xxxx`, `OpenGL`等，此前已优化过，如还有弹出框警告，  
尝试在解压目录使用cmd运行`./CGS.bat > CGS-err.log 2>&1`，然后把`CGS-err.log`发群里反馈

---

> [!Info] 如果存在上述没有覆盖的问题
> **请带上 `log` 到 [issue](
  https://github.com/jasoneri/ComicGUISpider/issues/new?template=bug-report.yml
) 反馈 或 进群反馈。**
