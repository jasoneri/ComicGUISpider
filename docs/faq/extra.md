
# 📒 额外使用说明

## 1. 域名相关

::: tip 简化流程 > `v2.10.0-beta` 起能主动触发域名管理
:::
各网站的 `发布页`/`永久链接` 能在 `site-packages/utils/website/ins.py` 里找到  
（国内）域名缓存文件为 `site-packages/__temp/xxx_domain.txt`（xxx = `wnacg`或`jm`），  
缓存有效期为一周  

::: info `发布页`/`永久链接`失效的情况下鼓励用户向开发者提供新可用网址，让软件能够持续使用  
:::

## 2. 配置生效相关

::: tip **搜索生命周期** （CGS 的一个概念，牢记），自`选择站点`而起，至`重置搜索`而结束  
:::

| 保存生效时机 | 配置项 |
| :---: | :---: |
| 即时生效 | 预设/剪贴板配置/日夜模式 (等等 gui 相关) |
| 下一个搜索生命周期 | 绝大部分 |

::: tip 特殊：
1. 语言切换必须关掉重启 CGS 方可生效
2. 搜索生命周期更换仍不生效可尝试关掉 CGS 再启动  
:::

## 3. 配置系文件路径

win: `%USERPROFILE%\AppData\Local\CGS`  
mac: `~/Library/Application Support/CGS`

::: tip 如果没找到，执行如下命令查看

```shell
uv run python -c "from pathlib import Path;from PySide6.QtCore import QStandardPaths;print(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)).joinpath('CGS'))"
```

:::

## 4. 短更新

::: info 用于处理极小频繁的更改（非常规，参考拷贝频繁换域名的那段时期）  
:::

开发组：用`git tag`方式处理，格式: `hf26/02/10-2_9_0`  
用户：参考[备用更新方法](/changelog/history)（开发组打`tag`后会在最新的`release`上增加提示导向此处）  
