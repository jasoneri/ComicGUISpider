
# 🚧 ScriptTool

kemono / danbooru / cbg / saucenao

## ⚠️ 通用前置须知

::: warning 🔔 脚本集通用前置安装( v2.11.0 改为 `按需` )
任务模块：[Redis-windows](https://github.com/redis-windows/redis-windows/releases) | mac:`brew install redis`  
下载引擎：[Motrix](https://github.com/agalwood/Motrix/releases)
> [!tip] 指引
> Redis-windows: 下载 *-cygwin-with-Service.zip  
> 查看 [文档](https://github.com/redis-windows/redis-windows/blob/main/README.zh_CN.md) 安装为 Windows 服务

Motrix 在进入 Script 前保持启动即可
:::

| 前置矩阵 | redis-service | Motrix |
| --- |  :---: | :---: |
| Kemono | ⭕️ | ⭕️ |
| Danbooru | ➖ | ⭕️ |
| Cbg | ➖ | ➖ |
| Jsoneri-Services | ➖ | ➖ |

::: tip 参考 `前置矩阵` 例如只装 Motrix 并进 Script 前启动就能使用 Danbooru
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

## 1. [kemono](/script/kemono)

## 2. [Danbooru](/script/danbooru)

## 3. Cbg (CornerBackground)

快捷入口为 rvTool 橙色按钮 Cbg

::: details 功能为油猴脚本，让立绘资源在浏览器右下角常驻展示（当前仅本地资源，火狐暂不支持 ¹）  
> [!Tip] 需要进扩展管理油猴权限设 `允许访问文件网址` (火狐没有所以不支持)

![cbgShow]({{URL_IMG}}/file/cgs/1777293262706_cbgShow.png)
:::
技术开源，资源自备  
或前往[引力圈](https://app.unifans.io/c/jsoneri)赞助获取资源  
如展示图立绘还可用于 cgs-bg_path , [楓の美化工具箱](https://winmoes.com/tools/12948.html)资源管理器背景, 
[rainmeter 的 Dock](https://tieba.baidu.com/p/3119085879) 等

::: info 后续视赞助人数置换为图床api ¹
:::

## 4. saucenao 二次元的以图搜图 (仅脚本)

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
