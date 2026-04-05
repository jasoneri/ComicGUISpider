
# 🚧 ScriptTool

kemono / danbooru / saucenao

## ⚠️ 通用前置须知

::: danger (🔔必装)脚本集通用前置安装
任务模块：[Redis-windows](https://github.com/redis-windows/redis-windows/releases) | mac:`brew install redis`  
下载引擎：[Motrix](https://github.com/agalwood/Motrix/releases)
:::
::: tip 源码使用 `uv` 安装脚本集依赖（GUI下的程序内站点切到 script 时已自动化处理了）
> [!info] 仅 2.10.0-beta 前需要，后续强制统一安装所有依赖
```bash
uv tool install ComicGUISpider[script] --force --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```
⚠️ win绿色包自动安装依赖失败时则用以下命令  
（基于`_pystand_static.int` 的 `version` 大于等于 `v2`）
```cmd
.\CGS.exe -v 2.9.0 -s -i https://pypi.tuna.tsinghua.edu.cn/simple
```
:::

::: details 脚本目录树: `script`目录 (非 GUI 相关)
```shell
utils
  ├── script
        ├── __init__.py
        ├── extra.py                  # 作为单个简单类爬虫使用
        ├── image  
             ├── __init__.py  
             ├── kemono.py            # 网站有如右相关资源 patreon/fanbox/fantia 等
             ├── expander.py          # 基于每个作者对作品集取名习惯(标题是颜文字表情之类的见怪不怪了)进行筛选（类kemono网站共用）
             ├── nekohouse.py         # 大概就是 kemono 的克隆网站
             ├── saucenao.py          # saucenao 著名的二次元以图搜图网站
```
:::

## 1. [kemono](/script/kemono/)

## 2. Danbooru

doh 可免代理，空词进首页过 cf 盾即可

<div align="left">
<a href="https://img-cgs.101114105.xyz/file/cgs/1774207508440_danbooru.mkv" target="_blank">
  <img src="https://img-cgs.101114105.xyz/file/cgs/1774207883543_danbooruPlay.png" alt="logo">
</a></div>

## 3. saucenao 二次元的以图搜图 (仅脚本)

`Danbooru`无需代理，`Yande`（这个指`yande.re`）需要代理，其他图源没做，感觉也没比`Yande`更全更高清的了，
没代理就去掉`imgur_module`的`Yande`<br>
有时也会搜出kemono的，知道作者名之后就用上面的kemono脚本吧

saucenao限制30秒搜3张图，有它的账号也才30秒4张没什么好说的

相似度阈值可自行各个图源分别调整，搜索`similarity_threshold`更改。 匹配的图源是`imgur_module`的值(列表) 从左到右

---

#### 运行/操作

1. 随意创建个目录例如 `D:\pic`，丢几张图进去，脚本的`get_hd_img`的位置实参改成该目录，然后跑脚本`python saucenao.py`
2. 成功后会保存在`D:\pic\hd`里，对照下文件大小之类的，合适就回去把原文件删了（不然下次跑会重复做前面的任务）

// # TODO[9]: 重复任务用pathlib.exists()查一下hd文件夹内的，并用saucenao.json记录数据

::: tip 进阶：
可以在很多图像的目录上运行脚本，只要在`get_hd_img`加上参数`first='a.png'`，就会以`文件大小`的`顺序`从`a.png`开始进行搜图  
不过同样要对比和手动删源文件，顺序可以自己调代码在`get_tasks`的`__ = sorted(...`的`key`
:::
