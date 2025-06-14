
## 🎁 Feat

✅ 将配置系记录系的文件转移位置，后续更新等都不用再手动备份（ 参考[📒配置系文件路径](https://jasoneri.github.io/ComicGUISpider/faq/extra) ）  
✅ 由 rV 按钮打开工具视窗，受影响的有`hotomi-tools`,`读剪贴板`（ 参考[🎸常规功能](https://jasoneri.github.io/ComicGUISpider/feat)里有各项图示 ）  
&emsp;✅ ✨ 工具视窗新增 statusTool，与上面的的状态栏一致，隐藏某站状态，内有某种功能  
&emsp;✅ rvTool: 选脚本然后取消有指示可快捷部署 rV，`显示记录`和`整合章节`移至其 rvTool 内  
&emsp;✅ 工具视窗内设`jm`等简化设置的域名工具  

## 🐞 Fix

🔳 hitomi  
&emsp;✅ ✨ 优化速度，翻页等  
&emsp;✅ 修复图源  
✅ macOS-init.app 去除，改为终端自执行 bash 命令；详情参考 [💻mac部署](https://jasoneri.github.io/ComicGUISpider/deploy/mac-required-reading)  
&emsp;✅ 另外 mac python 环境更改为 uv 的虚拟环境，参考 `CGS.bash` 与 `init.bash`  
&emsp;🔳 rV 部署/运行 会调用后台，但 mac 后台启动参数有误，cmd_kw 待更正  
