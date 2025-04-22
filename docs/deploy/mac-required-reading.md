# 💻 macOS( mac 操作系统) 部署

> [!Info] WantHelp!
> 寻找一位 `mac—arm64` 开发者维护 `mac` 应用程序（本人渣配置台式开始跑不动 `mac` 虚拟机了）

## 🚩 前置架构相关

通过以下命令查看架构（一般英特尔芯片i系的即为`x86_64`, 苹果芯片m系的为`arm64`）  

```bash
python -c "import platform; print(platform.machine())"
```

1. `x86_64` 架构: 开发者虚拟机就是该架构，一般按下面流程走即可  
2. `arm64` 架构: CGS-init.app 会自动安装`Rosetta 2`，下文中有列出一些[应对`CGS.app`无法打开](#针对弹窗报错的尝试)的处理方案  

## 📑 绿色包说明

macOS 仅需下载 `CGS-macOS`压缩包

::: details 解压后目录树(点击展开)

```
  CGS-macOS
   ├── CGS.app                     # 既是 *主程序*，也可以当成代码目录文件夹打开，执行脚本 `scripts/deploy/launcher/mac/CGS.bash`  
   |    ├── Contents
   |         ├── Resources
   |              ├── scripts      # 真实项目代码目录
   ├── CGS-init.app                # 执行脚本 `scripts/deploy/launcher/mac/init.bash`
   └── CGS_macOS_first_guide.html  # 用作刚解压时提供指引的一次性使用说明
```

:::

## ⛵️ 操作

::: warning 所有文档中包含`scripts`目录的  
包括此额外说明，主说明README，release页面，issue的等等等等，  
在app移至应用程序后的绝对路径皆指为`/Applications/CGS.app/Contents/Resources/scripts`
:::

::: warning 先执行下面的初始化步骤  
**全部 `.app` 第一次右键打开时点取消，第二次右键打开有选项能打开，再以后就能双击打开**  
:::

|       | 解析说明                                                                                                                                                                                                                                                                           |
|:------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 初始化   | ⚠️以下步骤严格按序执行<br/>1. 每次解压后，将`CGS.app`移至应用程序（下有图示）<br/>1.5 （可选，需要在第2步前进行）由于macOS没微软雅黑字体，默认替换成`冬青黑体简体中文`<br/>（不清楚是否每种macOS必有，留了后门替换，在 `scripts/deploy/launcher/mac/__init__.py` 的`font`值，有注释说明）<br/>2. 每次解压后，必须运行`CGS-init.app`检测/安装环境，<br/>⚠️ _**注意新打开的终端窗口并根据提示操作**_ ⚠️（对应第1.5步改字体可以反复执行第2步） |
| app应用 | 目前用的`Platypus`将代码封装成`app`，处理方式与win的随意位置有所不同                                                                                                                                                                                                                                    |

<table><tbody>  
    <!-- 此EXTRA.md会生成guide.html与自身位置的html，静态资源禁止使用路径，需使用url（然后切cdn） -->
    <tr><td>app移至应用程序</td><td><img alt="" src="../assets/img/deploy/mac-app-move.jpg"></td></tr>  
</tbody></table>

## 🔰 其他

### 针对弹窗报错的尝试

```bash
# arm64 CGS.app显示损坏无法打开时
/opt/homebrew/bin/python3.12 /Applications/CGS.app/Contents/Resources/scripts/CGS.py
# 或
/usr/local/bin/python3.12 /Applications/CGS.app/Contents/Resources/scripts/CGS.py
```

::: info 都失败的话可先自行deepseek等寻找方法 / 群内反馈
:::

### 更新相关

⚠️ 配置文件/去重记录均存放在`scripts`上，注意避免下包直接覆盖导致丢失  
版本如若涉及到 UI/界面变动 相关的，最好运行 `CGS-init.app` 一下以保证字体等设置

### bug report / 提交报错 issue

macOS上运行软件出错需要提issue时，除了选择系统选`macOS`以外，还需要在描述上说明系统版本与架构  
（开发者测试开发环境为`macOS Sonoma(14) / x86_64`）
