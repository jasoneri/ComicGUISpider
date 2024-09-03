## 须知

### 脚本目录树
```shell
script
  ├── __init__.py
  ├── conf.yml                  # 此目录下的所有脚本配置引用，没上传至git，需要自创建
  ├── extra.py                  # 作为单个简单类爬虫使用
  ├── image  
       ├── __init__.py  
       ├── kemono.py            # 网站有如右相关资源 patreon/fanbox/fantia 等
       ├── kemono_expander.py   # 基于每个作者对作品集取名习惯(可能是kemono本身爬作品时取标题的恶习)进行筛选
       └── saucenao.py          # saucenao 著名的二次元以图搜图网站
  └── script.md
```

### 配置字段 `script/conf.yml` （别把绿色安装包的`scripts`目录搞混）

```yaml
kemono:
  sv_path: D:\pic\kemono
  cookie: eyJfcGVybWaabbbW50Ijxxxxxxxxxxxxxxxxxxxxx   # 需要登录的账号 https://kemono.su/api/schema, F12打开控制台查看cookies, 字段名为 `cookie`
  redis_key: kemono

redis:
  host: 127.0.0.1
  port: 6379
  db: 0
  password:
```

### 注意

运行此目录下脚本的部分第三方依赖并不列在`requirements.txt`, 即绿色安装包的python运行环境不足以运行<br>
因为设计当初没考虑进GUI主界面功能，是作为能单独运行的脚本集合 (除了 `from utils import Conf, ori_path`)

此脚本目录下的脚本需要具备些少后端技能如 `redis`

暂无开发GUI界面打算

---

> 以下内容 基于以上须知

## 内容

### kemono

无需代理，基于账号对作者的收藏，运行时指定`作者_平台`，`作品创建时间`
，来限制一定量的任务（kemono一个png能几十M，不过滤任务几个T都不够用）<br>
> 过滤补充: `kemono_expander.py` 内置部分作者命名习惯的过滤，例如`keihh_patreon`
> ，其作品通常有无印/v2/v3，而v3会包括无印/v2，这情况就要过滤掉无印/v2 <br>
> 鉴于作者命名杂七杂八的，基本需要应对每一位作者做过滤，引用的在`kemono.py Kemono.step1_tasks_create_by_favorites._filter`
> 里
>
> 目录结构及其使用是基于 [comic_viewer](https://github.com/jasoneri/comic_viewer) 项目而调整成这样的
>
> 限制文件大小 100Mb 以下，在 `Kemono.file_size_limit`

#### 运行

启动 `redis` 服务；设置配置如上`conf.yml`内容；

环境：pycharm打开这个仓库，直接运行以下。 或把`from utils.script import conf, AioRClient, BlackList`
的类剪切复制到`kemono.py`补环境

`python kemono.py` 需要结合注释拆分使用

1. 获取任务
    ```python
    loop.run_until_complete(obj.step1_tasks_create_by_favorites(
        '2024-01-01', ListArtistsInfo(['Gsusart2222'])))
    loop.run_until_complete(obj.temp_copy_vals(restore=False))
    ```
2. 处理任务
    ```python
        tasks = loop.run_until_complete(obj.step2_get_tasks())
        sem = asyncio.Semaphore(7)
        loop.run_until_complete(obj.step2_run_task(sem, tasks))
    ```

#### 运行过后所得目录树

```shell
  kemono_path
    ├── __handle                  # 爬资源本身没有，comic_viewer 项目生成的，处理save/remove
    ├── __sorted_record           # 文件/图片下载时无序也不再是第n页这种命名，此时生成任务时记录列表顺序，用于 comic_viewer 人类顺序阅读使用
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
           └── [2022-07-30]ノノ水着                                       # 作品集
                    ├── 85fe7ae7-dfea-4ef2-816d-46f378ee2f80.png         # 该作品集的一个文件/图片
                    ├── c57e9b35-608f-471f-8a34-2e56ead4dc70.png
    
    ├── blacklist.json            # 下载过滤名单，避免重复下载用（comic_viewer阅读过后操作会加进去 或 手动添加）
    └── record.txt                # comic_viewer 阅读后操作记录
```
