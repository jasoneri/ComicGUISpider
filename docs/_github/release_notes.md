> [!TIP]  
> `v2.0.0-beta.2`此版完善更新流程机制

> [!Warning]  
> win: `v2.0.0-beta.2`为绿色包环境增设更新必须的工具（pip），如无意外此版内置更新能升级到往后任意版本,
> `v2.0.0-beta`需覆盖更新至此版才能正常使用内置更新，如需请备份配置文件 `scripts/conf.yml`与去重记录`scripts/record.db`  

## 🎁 Features

✅ CGS的`使用说明`与`更新`在 v2.0.0-beta 以后将设置在配置窗口的左下按钮，绿色包可执行程序只保留主程序（macOS加个初始化.app）  
✅ ✨优化更新流程，贴近主流软件体验  
✅ ✨使用`QFluentWidgets`优化界面与操作体验  
&emsp;✅ 搜索框增加右键选项`展开预设`, 序号输入框也有  
&emsp;✅ 展示已阅最新话使用表格视图  
&emsp;✅ 预览窗口改造了右键菜单，已将翻页加进去（后续有机会扩展菜单功能），附带有`CGS`内的全局快捷键  
&emsp;📣 优化ui后，目前在 `2560*1600分辨率 150%缩放` 上去掉`Qt同步系统缩放`也能有良好ui体验
（操作参考[更新历史`v1.6.3`删代码部分](https://github.com/jasoneri/ComicGUISpider/blob/GUI/docs/UPDATE_RECORD.md)，后续若有反响则做成开关提供切换）

## 🐞 Fix

✅ 修复`wnacg`剪贴板xpath解析错误问题
✅ 修复去重样式提示在翻页后没有生效
