# 🔐 Hitomi 加解密更新

Hitomi 的图片路由由远端脚本动态控制，`gg.js` 中 `b`（时间戳目录）与 `m`（分流 case 列表）高频变化，`common.js` 定义 URL 组装行为作为逻辑真值来源

当图片下载失败时，将以下 prompt 发给 ai，指导其对比最新 JS 与本地 Python 实现并同步更新

#### 前置准备

live gg.js(`https://ltn.gold-usergeneratedcontent.net/gg.js`)，
live common.js(`https://ltn.gold-usergeneratedcontent.net/common.js`)，
测试参考：`test/analyze/hitomi/`（gg.js / common.js 历史快照与样本数据）

::: details prompt

```text
你是熟悉 Python / JS 逆向映射的后端工程师。请在本项目中自动更新 Hitomi 图片 URL 加解密逻辑，目标文件为 `utils/website/hitomi/__init__.py`。

严格执行以下六阶段流程，每个阶段输出简短结论。

## JS → Python 映射表

| JS (common.js / gg.js) | Python | Location |
|---|---|---|
| `gg.m(g)` | `gg.m(g)` | `__init__.py` gg 类 |
| `gg.s(h)` | `gg.s(h)` | `__init__.py` gg 类 |
| `gg.b` | `gg.b` | `__init__.py` gg 类 |
| `subdomain_from_url(url,base,dir)` | `Decrypt.subdomain_from_url(base,img_type,gg_s)` | `__init__.py` Decrypt 内部类 |
| `full_path_from_hash(hash)` | `Decrypt.full_path_from_hash(img_hash,gg_s)` | `__init__.py` Decrypt 内部类 |
| `real_full_path_from_hash(hash)` | `Decrypt.real_full_path_from_hash(img_hash,img_type,preview)` | `__init__.py` Decrypt 内部类 |
| `url_from_hash(...)` | `HitomiUtils.get_img_url(...)` | `__init__.py` HitomiUtils |

====================
【阶段 1：拉取 live 脚本】
====================
1. 拉取以下两个最新脚本：
   - https://ltn.gold-usergeneratedcontent.net/gg.js
   - https://ltn.gold-usergeneratedcontent.net/common.js
2. 记录拉取时间（UTC）与脚本来源 URL
3. 若拉取失败，重试；仍失败则停止并输出"网络获取失败诊断"

============================
【阶段 2：结构契约检测（必须）】
============================
检查 gg.js 与 common.js 是否仍满足可自动更新的结构契约：

A. gg.js 契约
- 存在 `gg = { ... }` 对象
- 存在 `m(g)`、`s(h)`、`b` 三个核心成员
- `m(g)` 仍可识别其语义（典型为 switch-case + default；若变为 if/else 或混淆则视为不可识别）
- `s(h)` 仍可识别末尾 3 位 hash 变换逻辑（典型 `/(..)(.)$/`）
- `b` 仍可识别时间戳路径（典型 `'##########/'`）

B. common.js 契约
- 可定位函数：`subdomain_from_url`、`full_path_from_hash`、`real_full_path_from_hash`、`url_from_hash` / `url_from_url_from_hash`
- 可提取 URL 构造关键规则（子域、路径拼接、扩展名处理）

**若任一契约不可识别（显著混淆、结构重写、语义无法确定），立即停止代码修改，输出"结构不可识别诊断报告"，不要提交代码变更。**

======================================
【阶段 3：Python 逻辑对齐更新（gg + Decrypt）】
======================================
基于 live JS 真值，逐项对齐 `utils/website/hitomi/__init__.py`：

1. `gg` 类
   - `m_cases` 提取逻辑是否仍正确
   - `b` 提取逻辑是否精准（避免误匹配任意 10 位数字）
   - `s(h)` 变换规则是否与 JS 完全一致
   - 异常处理是否清晰（匹配失败应抛出可诊断错误）

2. `Decrypt` + `get_img_url`
   - `subdomain_from_url` 的子域计算是否与 JS 一致
   - `full_path_from_hash` 是否与 JS 路径规则一致
   - `real_full_path_from_hash` 是否与 JS 正则替换一致
   - `get_img_url` 是否正确映射 `url_from_hash` / `url_from_url_from_hash` 行为

只修改必要代码，不进行无关重构。

======================================
【阶段 4：m() 语义一致性核验（重点）】
======================================
必须明确验证 Python `m()` 与 JS `gg.m()` 语义一致，尤其检查"反转问题"：

- JS 典型语义：default=1，命中 case => 0
- 验证 Python 是否与此一致
- 至少使用两组 g 值做真值对拍：一组命中 case，一组不命中 case
- 必须验证子域分流未被对调（w1/w2 或 a1/a2）

若发现语义反转（in-case/out-case 对调），视为必须修复项。

======================================
【阶段 5：端到端回归测试（必须通过）】
======================================
执行：`python test/analyze/hitomi/test_flow.py`

test_flow.py 覆盖了完整链路：Init → Fetch nozomi → Fetch gallery → Build URL → Download image → PIL Verify

要求：
- 必须 6/6 全通过，才允许声明完成
- 若失败，输出失败步骤、根因、修复动作，然后重测直到通过
- 禁止"未测完成"或"理论通过"式结论

======================================
【阶段 6：输出变更报告】
======================================
最终报告必须包含：
1. 修改文件列表（通常仅 `utils/website/hitomi/__init__.py`）
2. 每一处修改对应的 JS 依据（来自 gg.js 或 common.js 的哪条规则）
3. `m()` 语义核验结果（含 in-case/out-case 对拍结论）
4. 回归测试结果（贴 `[1/6]...[6/6]` 输出摘要）
5. 风险与后续建议

====================
【硬性约束】
====================
- 仅修改必要代码，不破坏既有功能
- 注释语言保持中文，代码风格保持与现有文件一致
- 每个改动必须解释"对应了哪条 JS 变化"
- 在 `python test/analyze/hitomi/test_flow.py` 未达到 6/6 前，不得输出"已完成"
- 若触发停止条件，只输出诊断报告，不做代码改动
```

:::
