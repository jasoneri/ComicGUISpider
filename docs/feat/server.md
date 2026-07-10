# 🖥️ CGS Server / MCP

<div class="cgs-server-overview">

<div class="cgs-server-overview__media">
  <a href="{{URL_IMG}}/file/rv/1783171021752_app.webm" target="_blank">
    <img src="{{URL_IMG}}/file/rv/1783000491990_app_cover.png" alt="rV app demo">
  </a>
</div>

<div class="cgs-server-overview__notes">

:::: tip 目前主要用于托盘化提供给 rv-app 通讯下载的能力，使用参考左侧视频 01:50 之后
::: warning 托盘启动入口在主界面进配置窗口点 `CGS Server` 按钮
:::
::::

::: tip 要点解析
+ 下载运行时互斥：主界面打开则 `托盘进程` 进 `被占用` ，  
  主界面退出则释放，避免交叉提交
+ 托盘管理窗口带一些基本的日志状态等信息，可以自行检察状态
:::

</div>

</div>

<style>
.cgs-server-overview {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  margin: 16px 0 24px;
}

.cgs-server-overview__media {
  display: flex;
  align-items: flex-start;
  justify-content: center;
}

.cgs-server-overview__media a {
  display: flex;
  align-items: flex-start;
  justify-content: center;
}

.cgs-server-overview__media img {
  width: 100%;
  max-width: 240px;
  height: auto;
  object-fit: cover;
  border-radius: 8px;
}

.cgs-server-overview__notes {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cgs-server-overview__notes > .custom-block {
  margin: 0;
}

@media (max-width: 719px) {
  .cgs-server-overview {
    grid-template-columns: 1fr;
  }

  .cgs-server-overview__media img {
    width: min(100%, 260px);
    height: auto;
  }
}
</style>

## 托盘管理窗口

`Schedule` / `Server` / `MCP` 三标签页

::: tip Schedule 已接入订阅后台运行
`Schedule` 面板负责订阅任务的后台观察和触发；订阅对象、follow bid、分享链发布等配置仍在主界面 `工具箱 > 追更 / 订阅源` 中维护。
:::

| 标签页 | 内容 |
|:---|:---|
| Schedule | 下次检查、自动化状态、立刻执行、运行阶段、pending、历史、缓存状态、Debug payload |
| Server | connect URL / bind / surfaces；错误列表仅收 Server 自身错误，点行看详情 |
| MCP | endpoint / bridge / Auth、tools / resources、调用记录、详情、Debug 抽屉 |

## 订阅 / Schedule  (并没实际想好业务形态，订阅功能均视为占位)

普通用户主路径是 `追更`：从预览页勾选作品加入追更，设置检查日和时间，CGS Server 后台按调度检查新章节并提交下载。`订阅源` 是高级路径：添加他人发布的 follow bid，按拉取间隔获取 metadata feed，并在开启自动下载时提交新内容。

`Schedule` 面板显示：

| 区域 | 说明 |
|:---|:---|
| Plan | 当前模式、状态、下次检查、检查时间、publish bid、对象数量、阻塞原因和下一步 |
| Sources | 已配置的作品、作者/标签、follow bid 列表 |
| Run | 当前/最近一次运行的 run id、trigger、阶段、扫描数、pending 数、提交数 |
| Pending Items | 待下载条目、来源、章节、阶段、打开来源入口 |
| History | 最近订阅运行事件和错误摘要 |
| Debug | 脱敏后的原始 Schedule payload，仅用于诊断 |

常见阻塞原因：

| 原因 | 下一步 |
|:---|:---|
| 没有启用的追更对象 | 从预览页勾选作品加入追更，或在主窗口启用已有对象 |
| 未选择自动检查日期 | 在追更配置里选择至少一个检查日 |
| 分享链尚未发布 | 本地追更检查和下载仍可运行；如需同步给订阅源，再发布分享链生成 publish bid |
| 订阅源自动下载已关闭 | 在订阅源配置里开启自动下载 |
| 没有订阅源 follow bid | 添加至少一个 follow bid |
| CGS Server runtime 不空闲 | 等待当前任务结束，或关闭占用中的前台任务 |

隐私和合规边界：metadata pkl 托管在 Discord attachment CDN，Cloudflare Worker 只保存 `{bid -> attachment_url}` 索引；订阅源运行不会轮询 Discord 频道消息。本地追更检查和下载不依赖 token；发布分享链、metadata 索引同步和订阅源拉取 follow feed 时需要本机配置中的 `discord_share_user_token`，界面 Debug 内容会做 token 脱敏。

## 接口

```text
GET  /health          # 唯一免 token
GET  /sites
POST /search
POST /submit-books
GET  /status
GET  /events
POST /foreground/enter
POST /foreground/leave
MCP  /mcp
```

```text
%LOCALAPPDATA%/CGS/runtime/cgs-server-*.json
```

## 状态对照

| 显示 | 原因 |
|:---|:---|
| 前台占用 | 主界面正开着 |
| 任务运行中 | 已有下载在跑 |
| 未找到 Server | 未启动或发现记录过期 |
| 未授权 | 没带 token |
