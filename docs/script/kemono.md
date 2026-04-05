# Kemono

## [⚠️ 通用前置须知](/script/)

## 🚀 快速上手

1. 启动 `redis` 服务，打开 `Motrix`

2. GUI 方式运行 (网站选择 Script，预检测通过即进入)

![run_png]({{URL_IMG}}/file/screenshots/1771751999788_scriptTool.png)

### 相关操作说明

- 作者表格按钮左侧的 `橡皮擦按钮` 作用是清除输入框和重置初始化文本框
- 表格点击首行列名能进行排序
- 表格内右键是命令菜单，分别是对该行作者：
    1. 发送至输入框
    2. 浏览器查看其作品
    3. 收藏至本地

### 📏过滤规则示例

> 最好在其他地方编辑完再复制进 GUI 里

```yaml
TitleRe:
  _normal: "PSD|支援者"
  加瀬大輝: "様】"
keep: false
file: "(mp4|zip)$"
RuleFEnum:
  mdasdaro: "3316400"
```

1. TitleRe：使用的是正则过滤 post 标题；其中特殊的 _normal 是兜底的通用过滤规则
2. file：正则对 post 内的附件文件名过滤
3. RuleFEnum：复杂规则系过滤一般人用不上，需要自己编代码，可以参考 [keihh函数](https://github.com/jasoneri/ComicGUISpider/blob/GUI/utils/script/image/expander.py)  
RuleFEnum则是因函数命名而无法处理非纯英作者名，故而使用id映射函数名这种动态方式

#### 4. keep 逻辑讲解 (不设默认 false, 下文 post 指代一个作品)

> true: `保留`匹配的_normal`或`作者正则匹配的 post，并仅`保留` post 中 `file正则` 匹配文件  
> false: `排除`匹配的_normal`后再排除`作者正则匹配的 post，并`排除` post 中 `file正则` 匹配文件

> [!Warning] ⚠️ 过滤规则偏向高阶操作，最简单还是不设过滤手动删除


### 命令行工具参考

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

## 📒 说明

在 GUI 形式下，任务生成全基于作者id的 posts，受配置的 过滤规则 所设限制任务的量  
kemono 资源重复多，文件大，最好或多或少意识到过滤的重要性  

::: tip 复杂规则系扩展:  
处于 `expander.py` ，例如`keihh`
，其作品通常有无印/v2/v3，而v3会包括无印/v2，这情况就要过滤掉无印/v2  
复杂规则系过滤需要 python 编码能力
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
