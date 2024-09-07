## macOS(mac操作系统) 额外说明

### 绿色包说明

> macOS 需要下载 `CGS-macOS.7z` (不需要下载`CGS.7z`)，解压后目录树如下

```shell
  CGS-macOS
   ├── scripts
   ├── extra
        ├── python-3.12.3.pkg 
   ├── init.sh
   ├── CGS.sh               # 等价于 CGS.app *主程序* 防被杀毒软件隔离 备用
   ├── CGS.app              # 对应 deploy/launcher/mac/CGS.sh  *主程序*
   ├── CGS-使用说明.app      # 对应 deploy/launcher/mac/desc.sh
   └── CGS-更新.app          # 对应 deploy/launcher/mac/update.sh
```

#### 解析

1. 每次解压后，运行`./init.sh`（安装程序运行环境）
    1. 由于macOS没微软雅黑字体，默认替换成`冬青黑体简体中文`
       （不清楚是否每种macOS必有，留了后门替换，在 [`scripts/deploy/launcher/mac/__init__.py`](./__init__.py) 的`font`
       值，有注释说明）
2. 默认储存路径：当前用户的(`下载`目录)`Downloads/Comic`
   ，更换的话到配置窗口更改即可（使用绝对路径，如 `/Users/xxxxxx/Downloads/Comic`）

### 其他

#### bug report / 提交报错issue

macOS上软件出错需要提issue时，除了选择系统选`macOS`
以外，还需要在描述上说明或截图使用的版本（开发者测试环境为`macOS Sonoma(14)`）
