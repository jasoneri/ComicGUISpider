
# 🚧 其他脚本集

saucenao / kemono / nekohouse  

[Motrix](https://github.com/agalwood/Motrix) yyds!!  

`v2.3.0` 之后支持 GUI 使用 kemono  

## ⚠️ 通用前置须知

::: warning (🔔必装)脚本集通用前置安装
任务模块：[Redis-windows](https://github.com/redis-windows/redis-windows/releases) | mac:`brew install redis`  
下载引擎：[Motrix](https://github.com/agalwood/Motrix/releases)
:::
::: tip 分界线，以下是针对用源码操作的说明

使用 `uv` 安装脚本集依赖（GUI下的程序内切到 kemono 时已自动化处理了）
```bash
uv tool install ComicGUISpider[script] --force --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```
:::

::: warning 配置相关：改存储目录/cookies等请使用GUI方式修改
:::

::: details 脚本目录树: `script`目录
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

---
::: warning 以下内容 均基于通用前置须知
:::

## 1. kemono

### 🚀 快速开始

1. 启动 `redis` 服务，打开 `Motrix`
> [!TIP] 2. 额外过滤示例，在 GUI 里设置
> ::: details 点击展开  
> ```yaml
> Artists:
>   normal: "PSD|支援者"
>   DaikiKase: "支援者様】"
> file: "(mp4|zip)$"
> ```
> :::
> 注: 使用的是正则过滤 post 标题；Artists-normal 是兜底的通用过滤规则

3. GUI 方式运行 (`v2.3.0`以及之后版本)

![run_png](../assets/img/feat/scriptTool.png)

::: tip 一些使用心得说明:

- 作者表格按钮左侧的 `橡皮擦按钮` 作用是清除输入框
- 表格点击首行列名能进行排序
- 表格内右键是命令菜单，分别是对该行作者 Ⅰ发送至输入框 Ⅱ浏览器查看其作品 Ⅲ收藏至本地
- `加瀬大輝`这种非纯英的作者名，因为过滤方案问题，需要把额外过滤示例粘贴进过滤规则中，目前仅他一人

:::

3.2 命令行工具参考

::: tip 脚本相对位置 `utils/script/image/kemono.py`  
:::

```bash
# 先用 --help 测试/查看参数说明
python kemono.py --help
python kemono.py -c 'fav=[["keihh","fanbox"],"サインこす"]' -sd "2025-03-01"  -ed "2025-05-01"
python kemono.py -c 'creatorid=[16015726,1145144444444]' -sd "2025-03-01"

# 部分失败任务的补漏命令 👇
python kemono.py -p run
```

### 📒 说明

基于账号收藏 或 作者id，受配置的 filter 所设限制一定量的任务  
kemono 性质，资源重复多，文件大，基本设置条件过滤才正常  

::: tip 过滤扩展:  
`expander.py` 内置部分作者命名习惯的过滤，例如`keihh_patreon`
，其作品通常有无印/v2/v3，而v3会包括无印/v2，这情况就要过滤掉无印/v2  
鉴于作品集命名杂七杂八的，除通用过滤外可对每一位作者单独增加过滤规则
:::

---

::: details 运行过后所得目录树 (目录结构基于 [redViewer](https://github.com/jasoneri/redViewer))
```shell
  kemono_path
    ├── __handle                  # 爬资源本身没有，redViewer 项目生成的，处理save/remove
    ├── __sorted_record           # 文件/图片下载时无序也不再是第n页这种命名，此时生成任务时记录列表顺序，用于 redViewer 人类顺序阅读使用
          └── a5p74od3_fanbox
               ├── [2023-01-01]今年もよろしくお願いします。.json    # 作品集顺序记录
    
    ├── MだSたろう_fanbox          # 分隔开的这部分均为作者_平台\作品集\图片or文件，命名格式：作者_平台
    ├── a5p74od3_fanbox
    ├── keihh_fanbox
    ├── keihh_patreon
    ├── サインこす_fanbox
    ├── ラマンダ_fantia
           ├── [2020-07-30]アカリちゃんとクエスト
           ├── [2021-01-29]白血球さんお願いします！
           └── [2022-07-30]ノノ水着                                  # 作品集，命名格式：[作品创建时间]kemono的标题名
                    ├── 85fe7ae7-dfea-4ef2-816d-46f378ee2f80.png    # 该作品集的一个文件/图片
                    ├── c57e9b35-608f-471f-8a34-2e56ead4dc70.png
    
    ├── blacklist.json            # 下载过滤名单，避免重复下载用（redViewer阅读过后操作会加进去 或 手动添加）
    └── record.txt                # redViewer 阅读后操作记录
```
:::

---

## 2. saucenao 二次元的以图搜图

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

---

## 3. nekohouse 类似kemono的补充

::: info 除了一些配置等从`kemono`变为`nekohouse`之外，使用方面与`kemono`用法别无二致，参照`kemono`即可
:::

nekohouse 看数据到25年3月已停很久，哪天它死者苏生的话会考虑重新维护此脚本
