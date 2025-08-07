
# 📒 额外使用说明

## 1. 域名相关

::: tip 简化流程的方法 > [🎸4.3-域名工具](/feat/#_4-3-%E5%9F%9F%E5%90%8D%E5%B7%A5%E5%85%B7-domaintool)
:::
各网站的 `发布页`/`永久链接` 能在 `site-packages/utils/website/__init__.py` 里找到  
（国内域名专用）域名缓存文件为 `site-packages/__temp/xxx_domain.txt`（xxx = `wnacg`或`jm`），  
缓存有效期为 48 小时  
程序每次启动会检测是否处于有效期内，过期或网络问题会删除缓存，下次启动重新获取  
处于有效期内则可对此文件删改换域名等或加个空格保存即时生效  

::: info `发布页`/`永久链接`失效的情况下鼓励用户向开发者提供新可用网址，让软件能够持续使用  
:::

## 2. 配置生效相关

除少部分条目例如预设(只影响gui)，能当即保存时立即生效(保存配置的操作与gui同一进程);  
其余影响后台进程的配置条目在选择网站后定型(点选网站后`后台进程`即开始)，  
如果选网站后才反应过来改配置，需重启CGS方可生效

## 3. 配置系文件路径

执行如下命令查看

```shell
python -c "from pathlib import Path;from PyQt5.QtCore import QStandardPaths;print(Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)).joinpath('CGS'))"
```

此路径设有文件如下:  

- `conf.yml`: 配置文件  
- `conf_img.yml`: scriptTool配置文件  
- `reccord.db`: 去重记录  
- `cookies.pkl`: cookies序列化文件  
