# 💻 macOS( mac 操作系统) 部署

> [!Info] WantHelp!
> 寻找 `mac—arm64` 开发者维护 `mac` 应用（本渣配台式开始跑不动 `mac` 虚拟机了） [查看详情](
  https://github.com/jasoneri/ComicGUISpider/issues/35)

## 🚩 前置架构相关

通过以下命令查看架构

```bash
python -c "import platform; print(platform.machine())"
```

1. 英特尔i系，`x86_64` 架构（开发者虚拟机架构）  
2. 苹果m系，`arm64` 架构

`v2.2.3` 以后优化了脚本命令，理论上兼容两种芯片了，  
作为保留，下文中列出一些[应对`CGS.app`无法打开](#针对弹窗报错的尝试)的处理方案  

## 📑 绿色包说明

macOS 仅需下载 `CGS-macOS`压缩包

::: details 解压后目录树(点击展开)

```text
  CGS-macOS
   └── CGS.app                     # 既是 *主程序*，也可以当成代码目录文件夹打开，执行脚本 `scripts/deploy/launcher/mac/CGS.bash`  
        └── Contents
             ├── Resources
                  ├── scripts      # 真实项目代码目录
```

:::
::: warning macOS 由于认证签名收费，app 初次打开可能会有限制，正确操作如下

1. 对 app 右键打开，报错不要丢垃圾篓，直接取消
2. 再对 app 右键打开，此时弹出窗口有打开选项，能打开了
3. 后续就能双击打开，不用右键打开了
:::

## ⛵️ 操作

::: warning 所有文档中包含`scripts`目录的  
包括此mac部署说明，主说明README，release页面，issue的等等等等，  
在app移至应用程序后的绝对路径皆指为`/Applications/CGS.app/Contents/Resources/scripts`
:::

::: warning 以下初始化步骤严格按序执行
:::

|   初次化步骤    | 解析说明                                                                                                                                                                                                                                                                           |
|:------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1   | 每次解压后，将`CGS.app`移至应用程序<br/> ![图示](../assets/img/deploy/mac-app-move.jpg)|
| 1.5   | （可选，需要在第2步前进行）由于macOS没微软雅黑字体，默认替换成`冬青黑体简体中文`<br/>不清楚是否每种macOS必有，留了后门替换，在 `scripts/deploy/launcher/mac/__init__.py` 的`font`值，有注释说明 |
| 2   | 打开终端执行 初始化/环境更新 命令，（牢记此页面有这条命令，经常用）<br>`bash /Applications/CGS.app/Contents/Resources/scripts/deploy/launcher/mac/init.bash`<br/>⚠️ _**根据提示操作**_ （对应第1.5步改字体可以反复执行第2步） |

## 🔰 其他

### 针对弹窗报错的尝试

```bash
# CGS.app显示损坏无法打开时，尝试绕过签名 
sudo xattr -d com.apple.quarantine /Applications/CGS.app
# 或
sudo xattr -r -d com.apple.quarantine /Applications/CGS.app

# 或直接运行
bash /Applications/CGS.app/Contents/Resources/scripts/deploy/launcher/mac/CGS.bash
```

::: tip 还是失败无果的情况下可先自行deepseek等寻找方法或群内反馈  
除命令以外能成功`解决CGS.app显示损坏`的示例请在下方评论区留言，造福后人  
格式：1.报错信息;2.解决方案;3.结果
:::

### bug report / 提交报错 issue

macOS上运行软件出错需要提issue时，除系统选`macOS`外，还需描述加上系统版本与架构  
（开发者测试开发环境为`macOS Sonoma(14) / x86_64`）
