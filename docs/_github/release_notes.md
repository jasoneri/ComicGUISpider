
## 🐞 Fix

✅ 拷贝换了域名  

#### ⚠️ (win)`v2.2.0-beta`之前的版本使用内置更新的话 ⚠️

（1） 先确保 CGS 已关闭（否则运行会出现占用导致报错）  
在解压的目录下开终端(powershell 最好是 pwsh )执行以下命令更新依赖 ，⚠️必须最后看到 `[!uv_install_pkgs done!]` 提示  

```powershell
irm https://gitproxy.click/https://raw.githubusercontent.com/jasoneri/ComicGUISpider/refs/heads/GUI/deploy/online_scripts/win.ps1 | iex
```

（2） 开 CGS 使用内置更新  
(非v2.2.0-beta)提示已是最新版本的话，肯定是上一步占用报错导致，
先确保第一步成功然后删掉 `scripts/deploy/version.json`  ，进 CGS 先更新到 v2.1.3 再更到这版 v2.2.0-beta

相关： [faq: 针对 ModuleNotFoundError 处理](
    https://jasoneri.github.io/ComicGUISpider/faq/#_3-%E5%85%B6%E4%BB%96)

---

<details>
<summary>📜上一稳定版截止至上一开发版更新细则 👈</summary>

## 🎁 Features

✅ hitomi 支持，有一丢丢黑科技 CGS 内有提示  
&emsp;✅ 内置 hitomi-tools  
&emsp;🔳 数据集下载自动化/更新等，方式待定  
&emsp;🔳 读剪贴板功能开发中  
&emsp;🔳 优化速度，翻页等  
✅ Kemono 脚本集更新，详阅[📒相关说明](https://jasoneri.github.io/ComicGUISpider/feature/script)

## 🐞 Fix

✅ 页数命名优化：更改为纯数字补零命名，附带可选 [文件命名后缀修改](https://jasoneri.github.io/ComicGUISpider/config/#其他-yml-字段)  
✅ i18n 自动编译优化  
✅ 使用 astral-sh/uv 管理依赖，优化更新模块  
✅ 修复 jm 读剪贴板部分解析错误  
✅ 优化命令行工具的发文等待，替换为循环检测信号，一旦触发即时发文  
✅ 其他小优化  
</details>
