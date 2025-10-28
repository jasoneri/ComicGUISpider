# 💻 macOS( mac 操作系统) 部署

## 📑 说明

::: tip v2.4.0 之后的绿色包均转为套壳的 `uv tool`

---

绿色包使用gitee源，墙外的建议直接使用 [uv tool方式部署安装](/deploy/quick-start#1-下载--部署)
:::

## ⛵️ 绿色包操作

::: warning mac 由于认证签名收费，打包派发的 app 初次打开会有限制，正确操作如下

1. 对 app 右键打开，报错不要丢垃圾篓，直接取消
2. 再对 app 右键打开，此时弹出窗口有打开选项，能打开了
3. 后续就能双击打开，不用右键打开了
:::

|   步骤    | 解析说明 |
|:------:|:-----------------------------------|
| 1. 初始化   | 解压后初次运行`CGS.app`时（点击app前阅读上方签名收费的提示）<br>检测没 `brew`、`uv` 环境的话，会在终端指引安装此两，然后安装`CGS` |
| 2. 常规运行   | 以后打开会检测`uv tool dir --bin`里有没`cgs`可执行，有则直接打开 |

::: danger 换源相关
初始化中带 pypi 字眼相关等网络失败的话可尝试进行换源，执行下方的命令  
命令中 `...-s 1` 最后的数字序号对应 pypi 国内源，序号参考 [序号映射](/config/#pypi%E6%BA%90-pypi-source)  
:::

::: tip `CGS.app`实际执行的命令  
**单独 初始化/环境更新/CGS更新等 执行命令：**
```bash
curl -fsSL https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/launcher/mac/init.bash | bash -s 1
```
_**根据终端提示操作**_  
:::


::: warning _**源码根目录**_  
`uv tool dir` 命令输出拼接 `/comicguispider/Lib/site-packages`，  
`/com.../site-packages`路径之中有个 python3.x.x 的目录  

::: tip 所有文档中由`site-packages`开始的目录的  
包括此mac部署说明，主说明README，release页面，issue的等等等等，  
`site-packages`目录就是命令得出的源码根目录
:::

## 🔰 其他

### 经过部署后的绿色包 `CGS.app` 与终端使用 `uv tool` 是共通的  

全部文档提及到的 `uv tool` 命名均可直接用，例如

```bash
# 1. 终端运行
cgs
# 或
uv tool run --from comicguispider cgs
# 2. 更新到指定版本2.5.0
uv tool install ComicGUISpider==2.5.0 --force --index-url https://pypi.tuna.tsinghua.edu.cn/simple --python "<3.14"
```

### bug report / 提交报错 issue

macOS上运行软件出错需要提issue时，除系统选`macOS`外，还需描述加上系统版本与架构  
（开发者测试开发环境为`macOS Sonoma(14) / x86_64`）

::: tip 获取架构命令
```bash
uv run python -c "import platform; print(platform.machine())"
```
:::
