# 💻 macOS( mac 操作系统) 部署

## 📑 说明

::: tip v2.4.0-beta 之后的绿色包均转为套壳的 `uv tool`
绿色包 `CGS-macOS.7z` 里 `CGS.app` 其执行内容为

```bash
if [ ! -x "cgs" ]; then
    curl -fsSL https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/launcher/mac/init.bash | bash && cgs
else
    cgs
fi
```

---

也推荐干脆直接使用 [uv tool方式部署安装](/deploy/quick-start#1-下载--部署)
:::

## ⛵️ 绿色包操作

::: warning 以下初始化步骤严格按序执行
:::

|   初次化步骤    | 解析说明                                                                                                                                                                                                                                                                           |
|:------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1   | 每次解压后，将`CGS.app`移至应用程序<br/> ![图示](../assets/img/deploy/mac-app-move.jpg)|
| 1.5   | （可选，需要在第2步前进行）由于macOS没微软雅黑字体，默认替换成`冬青黑体简体中文`<br/>不清楚是否每种macOS必有，留了后门替换，在 `scripts/deploy/launcher/mac/__init__.py` 的`font`值，有注释说明 |
| 2   | 运行`CGS.app`（点击app前阅读下方签名收费的提示），初始会自动启动 `uv tool` 处理 |

::: warning mac 由于认证签名收费，个人开发的 app 初次打开可能会有限制，正确操作如下

1. 对 app 右键打开，报错不要丢垃圾篓，直接取消
2. 再对 app 右键打开，此时弹出窗口有打开选项，能打开了
3. 后续就能双击打开，不用右键打开了
:::

::: tip 单独 初始化/环境更新/CGS更新 等命令：
```bash
curl -fsSL https://gitee.com/json_eri/ComicGUISpider/raw/GUI/deploy/launcher/mac/init.bash | bash
```
⚠️ _**根据终端提示操作**_ （对应第1.5步改字体可以反复执行此操作）
:::

::: warning _**源码根目录**_ (执行以下命令获取)
```bash
echo "$(uv tool dir)/comicguispider/Lib/site-packages"
```

所有文档中包含`scripts`目录的  
包括此mac部署说明，主说明README，release页面，issue的等等等等，  
`scripts`目录就是命令得出的源码根目录
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
