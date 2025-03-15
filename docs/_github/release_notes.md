> [!Info]  
> `v2.0.0-beta`版本将维持一周左右收集错误信息，如发现任何问题请进群反馈  

> [!Warning]  
> 此次win老用户需覆盖更新，如需请备份配置文件 `scripts/conf.yml`与去重记录`scripts/record.db`  
> mac老用户`从v1.x至v2.0.0-beta`仅需使用`CGS-更新`更新库列表后用`CGS-初始化`更新环境库即可

## 🎁 Features

✅ CGS的`使用说明`与`更新`在 v2.0.0-beta 以后将设置在配置窗口的左下按钮，绿色包可执行程序只保留主程序（macOS加个初始化.app）  
✅ 优化更新流程，贴近主流软件体验  
✅ ✨使用`QFluentWidgets`优化界面与操作体验  
<span style="white-space:pre">&#9;</span>✅ 搜索框增加右键选项`展开预设`, 序号输入框也有  
<span style="white-space:pre">&#9;</span>✅ 展示已阅最新话使用表格视图  
<span style="white-space:pre">&#9;</span>✅ 预览窗口改造了右键菜单，已将翻页加进去（后续有机会扩展菜单功能），附带有`CGS`内的全局快捷键  
<span style="white-space:pre">&#9;</span>📣 优化ui后，目前在 `2560*1600分辨率 150%缩放` 上去掉`Qt同步系统缩放`也能有良好ui体验
（操作参考[更新历史`v1.6.3`删代码部分](https://github.com/jasoneri/ComicGUISpider/blob/GUI/docs/UPDATE_RECORD.md)，后续若有反响则做成开关提供切换）

## 🐞 Fix

✅ 修复`wnacg`剪贴板xpath解析错误问题
✅ 修复去重样式提示在翻页后没有生效
