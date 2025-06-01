
# 🚧 其他脚本集

saucenao / kemono / nekohouse  

<2025-05-11> [Motrix](https://github.com/agalwood/Motrix) yyds!!  
`kemono` 下载改用 Motrix-PRC ，太稳了！有兴趣看下方 kemono 等相关说明  

## ⚠️ 通用前置须知

::: tip 脚本集通用前置安装
任务模块：[Redis-windows](https://github.com/redis-windows/redis-windows/releases) | mac:`brew install redis`  
下载引擎：[Motrix](https://github.com/agalwood/Motrix/releases)
 
---
使用 `uv` 安装脚本集依赖 `requirements/script/*.txt`
```bash
python -m uv pip install -r "requirements/script/win.txt" --index-url http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```
绿色包使用的命令为 👇
```bash
./runtime/python.exe -m uv pip install -r "./scripts/requirements/script/win.txt" --index-url http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```
:::

::: details 脚本目录树: `script`目录
```shell
utils
  ├── script
        ├── __init__.py
        ├── conf.yml                  # 此目录下的所有脚本配置引用，没上传至git，需要自创建
        ├── extra.py                  # 作为单个简单类爬虫使用
        ├── image  
             ├── __init__.py  
             ├── kemono.py            # 网站有如右相关资源 patreon/fanbox/fantia 等
             ├── expander.py          # 基于每个作者对作品集取名习惯(标题是颜文字表情之类的见怪不怪了)进行筛选（类kemono网站共用）
             ├── nekohouse.py         # 大概就是 kemono 的克隆网站
             ├── saucenao.py          # saucenao 著名的二次元以图搜图网站
```
:::

::: details 配置文件 `./scripts/utils/script/conf.yml` （必要❗️自行创建）
```yaml
kemono:
  sv_path: D:\pic\kemono
  cookie: eyJfcGVybWaabbbW50Ijxxxxxxxxxxxxxxxxxxxxx   # 需要登录的账号 https://kemono.su/api/schema, F12打开控制台查看cookies, 字段名为 `session`
  redis_key: kemono
  
nekohouse:
  sv_path: D:\pic\nekohouse
  cookie: eyJfcGVybWaabbbW50Ijxxxxxxxxxxxxxxxxxxxxx   # 需要登录的账号 https://nekohouse.su, F12打开控制台查看cookies, 字段名为 `session`
  redis_key: nekohouse

redis:
  host: 127.0.0.1
  port: 6379
  db: 0
  password:
```
:::

暂无开发GUI界面打算

---
::: warning 以下内容 均基于通用前置须知
:::

## 1. kemono

### 🚀 快速开始

1. 启动 `redis` 服务，打开 `Motrix`
::: details 2. (可选)增加配置
```yaml
kemono:
  ...
  filter:                     # 正则过滤
    Artists:                  # 作品标题过滤
      normal: "PSD|支援者"     # normal一旦设置则会作为通用的兜底过滤
      DaikiKase: "支援者様】"   # 单独指定作者过滤规则，作者非纯英文名时需要配合 ArtistsEnum
    file: "(mp4|zip)$"        # 文件类型过滤

proxies:                      # 设代理访问才算通畅，此处代理设置不影响 Motrix 的下载相关
  - 127.0.0.1:10809
```
:::
3. 命令行工具参考

::: tip 绿色包使用的命令为 `./runtime/python.exe ./scripts/utils/script/image/kemono.py --help`  
:::

```bash
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
