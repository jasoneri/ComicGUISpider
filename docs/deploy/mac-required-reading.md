# 💻 macOS( mac 操作系统) 部署

## 📑 说明

::: tip v2.4.0-beta 之后的绿色包均转为套壳的 `uv tool`

---

也推荐干脆直接使用 [uv tool方式部署安装](/deploy/quick-start#1-下载--部署)
:::

## ⛵️ 绿色包操作

::: warning 以下初始化步骤严格按序执行
:::

|   初次化步骤    | 解析说明                                                                                                                                                                                                                                                                           |
|:------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1   | 每次解压后，将`CGS.app`移至应用程序<br/> ![图示](../assets/img/deploy/mac-app-move.jpg)|
| 2   | 运行`CGS.app`（点击app前阅读下方签名收费的提示），初始会自动启动 `uv tool` 处理 |

::: warning mac 由于认证签名收费，个人开发的 app 初次打开可能会有限制，正确操作如下

1. 对 app 右键打开，报错不要丢垃圾篓，直接取消
2. 再对 app 右键打开，此时弹出窗口有打开选项，能打开了
3. 后续就能双击打开，不用右键打开了
:::

::: tip 单独 初始化/环境更新/CGS更新等 执行命令：
```bash
curl -fsSL https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/launcher/mac/init.bash | bash -s 1
```
_**根据终端提示操作**_  
:::
::: danger 换源相关
CGS.app 初始化中非 brew 失败的话尝试进行换源，执行上方的命令  
命令中 `...-s 1` 最后的数字序号对应 pypi 国内源，序号参考 [序号映射](/config/#pypi%E6%BA%90-pypi-source)  
:::

::: warning _**源码根目录**_ (执行以下命令获取)
```bash
echo "$(uv tool dir)/comicguispider/Lib/site-packages"
```

所有文档中由`site-packages`开始的目录的  
包括此mac部署说明，主说明README，release页面，issue的等等等等，  
`site-packages`目录就是命令得出的源码根目录
:::

## 🔰 其他

### CGS.app 无法运行就直接用 uv 编译的

```bash
cgs
# 或
uv tool run --from comicguispider cgs
```

### bug report / 提交报错 issue

macOS上运行软件出错需要提issue时，除系统选`macOS`外，还需描述加上系统版本与架构  
（开发者测试开发环境为`macOS Sonoma(14) / x86_64`）

::: tip 获取架构命令
```bash
python -c "import platform; print(platform.machine())"
```
:::
