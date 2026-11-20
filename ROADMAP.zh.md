# 路线图

[English](ROADMAP.md) · 中文

> 这份是较详细的早期版本，当前摘要以英文页为准。

BigRobot 是**接管账号的机器人平台**：接模型 API、接协议端，把权限、审批、审计、记忆、检索
做在引擎里。所以路线图只有一条取舍标准：

> 这件事是否让「新增一个能力」「新增一个平台」「多一个账号」的成本更低？

不满足的排后面；与定位冲突的（见"明确不做"），不做。

`P0` 阻塞 · `P1` 下一步 · `P2` 之后 · `P3` 顺手

---

## 2.0 — 已发布

| 项 | 证据 |
|---|---|
| 品牌与配置统一 | `BigRobot` / `bigrobot` 全仓替换；环境变量统一 `BIGROBOT_*`，旧 `CS_AGENT_*` / `ZHIKE_*` 自动映射 |
| 改名不丢数据 | `core/paths.py` 发现旧目录 `zhike-data/` 时优先复用 |
| 前端存储键集中 | `frontend/src/lib/storage.ts` 一处定义，读旧键即迁移 |
| 文档去重 | 17 份 3556 行 → 门面 + 4 份专题，历史版本进 `docs/archive/` |

## 2.0.1 — 品牌收尾（M1，1 天）

| 项 | 为什么 | 验收 |
|---|---|---|
| ~~三个远端仓库改名~~（已核实完成：新地址 200 / 旧地址 301-302） | GitHub → GitCode → Gitee 均已生效 | `git ls-remote` 三端通；仓库内无旧地址残留 |
| 先把 2.0 的 120 个改动提交固化（远端已有 HEAD，工作区悬着） | 任何一次 pull 都可能冲掉工作区 | `git status` 干净；一次提交只含改名与文档去重 |
| 图形重做：logo / 单色标 / favicon / OG / 角色图 / 12 张截图 | 现有 logo 是「对话气泡」，属于客服语义，与"接管账号的平台"不符 | 16px 可辨、对比度 AA、截图与 2.x 界面零差异 |
| 截图脚本化（Playwright） | 手拍必然再次过期 | `npm run shots` 一条命令重出全部截图 |
| `demo.gif` 3.7MB → mp4/webp < 1MB | README 首图就是最大的一笔首屏开销 | 首屏少传 2.7MB |

## 2.1 — 通用化地基（P0）

| 项 | 为什么 | 验收 |
|---|---|---|
| 存储层加 `account_id` 维度（sessions / messages / memory / reminders / tickets） | 现有表没有账号维度，接第二个账号必然串数据 | 迁移脚本 + 全表带 `account_id`；双账号并发测试互不可见 |
| 网关补 notice / request / meta_event | 现在只有 `on_message`，入群、撤回、加好友全接不到 | 事件可注册；撤回/入群有单测 |
| 动作参数不再被 OneBot v11 声明限制 | `validate_params` 丢弃未声明参数，协议端原生 API 透不出去 | 未声明参数可透传；`ActionSpec` 改由 `get_supported_actions` 生成 |
| `_pick_bot()` 支持多账号路由 | 原实现注释写着"多账号时取第一个" | 按 `account_id` 路由；无匹配账号明确报错 |

## 2.2 — 生态出口（P0/P1）

**通用性靠协议，不靠代码。** 三条出口做完，接新平台不需要改 `core/`。

| Pri | 项 | 为什么 | 验收 |
|---|---|---|---|
| P0 | OpenAI 兼容 `/v1/chat/completions` | 让任何前端或编排平台把 BigRobot 当模型用 | 支持流式与 function calling；外部客户端直连可用 |
| P0 | MCP client | 接一个 MCP server 就多一批工具，不用改 `core/tools.py` | 配置即可挂载；工具名冲突有前缀隔离 |
| P1 | `PluginRegistry` 接进网关启动流程 | `PluginManifest`/`PluginRegistry` 目前只活在测试里，网关从未 import | 静态、签名、opt-in 加载；不联网安装 |
| P1 | `gateway/adapters/` 按需扩平台 | 平台数是主动短板，先补最常被问的 | 新适配器不改 core；OneBot 之外至少一路跑通 |

## 2.3 — 前端骨架重排（P1，依赖 2.1 的 `account_id`）

28 个界面 → 7 个：**实例 / 会话 / 能力 / 策略 / 观测 / 设置 / 提醒**。

| 项 | 为什么 | 验收 |
|---|---|---|
| 页面合并（Settings 15 tab 按域折叠；13 路由 → 7） | 现在的 IA 是客服 SaaS 骨架，不是机器人平台骨架 | 7 条一级路由；每个功能仍可达 |
| 页面合并 = 请求合并（`/api/observe/overview`、`/sessions?view=live\|history\|queue`） | 一个页面打 5 个接口就是重复 | 首屏请求数下降；分页统一走 `lib/paging` |
| 接回审批入口 | `ActionsCenter` 被 `/actions → /runs` 重定向吞掉，**全站没有地方能批 L2 动作** | `/actions` 可访问；待批数在导航可见 |
| 样式双轨收敛（1889 行手写 CSS + Tailwind → 一套） | 两套样式系统是纯维护税 | 新页面只用一套；旧页面按访问量迁移 |

## 2.4 — 性能、加载与拆分（P1/P2，2 周）

| Pri | 项 | 为什么 | 验收 |
|---|---|---|---|
| P1 | 7 条 `async def` 路由里的同步 SQLite / 文档解析改线程池 | 实测导入 291 段 docx 时全站 `/healthz` 峰值 2.2s | 同等负载下 p95 < 50ms |
| P1 | 拆 `core/main.py` 的 1917 行 `create_app`，路由按域进 `core/api/` | 95 条路由挤在一个闭包，依赖关系不可见 | `create_app` < 200 行；单文件 < 250 行；路由数不变；全量测试绿 |
| P1 | 接上预压缩：`core/spa.py:_precompressed()` 已写但从未调用，dist 里 `.br/.gz` 数为 0 | 每次请求都在 CPU 现压 | `Content-Encoding: br` 命中；CPU 下降 |
| P1 | 聚合接口 + 5s TTL：`/api/observe/overview` | 一个页面打 5 个接口 | 首屏请求 5 → 1；p95 < 80ms |
| P1 | 工具改装饰器注册（一处声明），可选依赖收进 `pyproject` | 现在加工具要改三处，文档数字才会漂移（42 vs 55） | 新增工具只改一个文件；`tool_count` 自动正确 |
| P1 | 前端按需加载：echarts 模块化注册、i18n 按命名空间拆 | EChart 188KB gzip 全量引入；`t` chunk 87KB 首屏也加载 | 访客首屏 < 120KB gzip；控制台 < 350KB |
| P2 | 审计链与审批队列批量写合并 | 每条事件一次事务，热点时 SQLite 锁等待 | 并发 20 写 p95 写延迟降 50% |
| P2 | 可选 Postgres 后端（同一存储接口） | SQLite 适合单机，多账号会成瓶颈 | 两套后端跑同一套测试 |

## 2.5 — 工程治理（持续）

| Pri | 项 | 为什么 | 验收 |
|---|---|---|---|
| P0 | 修 `mypy` 6 处（CI 锁 1.19 才报，本地 2.4.1 只报 4）并锁定单一版本 | 门禁现在是红的，本地绿 CI 红 | `mypy core executor gateway` 0 error，本地与 CI 同版本 |
| P0 | 修 `oxlint` 1 error（`SetupWizard.jsx:34` 的 spread fallback） | CI 要求 0 errors | `npx oxlint src` 0 error |
| P1 | 测试分层标记（unit / integration / e2e），CI 拆 job | 976 用例挤在一个池子跑 3.5 分钟 | PR 反馈 < 90s；e2e 只在 main 跑 |
| P1 | Conventional Commits + 从 commit 生成 CHANGELOG | 614 行手写必然与代码脱节 | 发布时 notes 自动生成 |
| P1 | 依赖单一源：8 份 `requirements*.txt` → `pyproject` optional-dependencies | 手工同步必然漏 | 无重复声明；安装脚本生成 |
| P2 | CI 加 `markdown-link-check` + 禁止指向 `docs/archive/` 的新链接 | 刚建立的"一份文档一个职责"需要机器守住 | 内链 0 404 |
| P2 | `import-linter` 契约（api → domain → infra 单向） | 拆分后防止回退成大泥球 | 0 violation |
| P2 | `docs/adr/` 补 5 篇关键决策记录 | 半年后没人记得"为什么不用 Postgres" | 5 篇一页式 ADR |

## 2.6 — 单元合并（最小代码、最小交互）

目标：能力不变，表面积减半。详见 `BigRobot-最小执行单元与合并方案.md`（工作稿，不入库）。

| 批 | 内容 | 验收 |
|---|---|---|
| B0 | 6 个正确性问题：审批主体顺序 / async 阻塞 / `/actions` 死路由 / 工具数三口径 / 门禁红 / 预压缩死代码 | 审批有单测；导入压力下 `/healthz` p95 < 50ms；oxlint+mypy 0 |
| B1 | `ActionSpec` 做唯一事实源，`qq_*` 工具由它生成；`TOOL_META` 增 `op_risk` | 新增能力只改一处；`ban/kick` 仍 L2 |
| B2 | 工具 51 → 26（QQ 20→6、编解码 9→6、时间 2→1、文件 2→1） | `tool_selection.py` 回归不掉点 |
| B3 | 路由 114 → ≤50；表 28 → 24（只合 4 处真重复） | 旧路由留一版别名，前端不动也能跑 |
| B4 | 页面 28 → 7；hooks 48 → 26；CSS 1916 → 约 720；脚本 31 → 10 | 7 条一级路由；审批可达；访客首屏 < 120KB gzip |

## 明确不做

- **可视化编排 / 画布** —— 编排在配置里，不在画布里。
- **插件市场 / 远程安装** —— 与"接管账号、权限内建"冲突，供应链风险换不来清晰收益。
- **堆 IM 适配器数量** —— 先把 QQ 这条链路做到长期活着。
- **声音克隆 / 合成人设影像** —— 滥用面远大于收益。

---

## 条目怎么进这张表

1. 真实使用中坏了，或真实部署被挡住 → 候选。
2. 写一句"为什么" + 一条**可度量**的验收标准。
3. 才排进版本。

没有验收标准的不是路线图条目，是愿望。
