# 文档索引

## 现行（改代码时要同步更新）

| 文档 | 用途 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层与进程模型：core / gateway / executor 各自职责 |
| [DEPLOY.md](DEPLOY.md) | 部署与启动（含 QQ 协议端） |
| [RELEASING.md](RELEASING.md) | 版本号与发布流程 |
| [route-audit.md](route-audit.md) | 路由消费者审计口径与结论 |
| [PERSONA-EVAL.md](PERSONA-EVAL.md) | 角色评测怎么跑、看什么指标 |
| [extensions.md](extensions.md) | 声明式 HTTP 扩展包与 MCP 客户端 |
| [knowledge-base.md](knowledge-base.md) | 多知识库集合、角色绑定与资料摄入 |
| [future-tasks.md](future-tasks.md) | 未来任务：到点让 Agent 执行并回推结果 |
| [channel-events.md](channel-events.md) | 渠道事件：入群/退群/撤回/请求落库，撤回软删除 |
| [multi-account.md](multi-account.md) | 多账号隔离：会话、记忆、动作、提醒按机器人账号分开 |
| [persona-capabilities.md](persona-capabilities.md) | 角色能力边界：工具/技能/MCP/扩展白名单 |

## 存档（保留历史，不再维护）

`docs/archive/` 下是 `*-v1.md` 与早期竞品调研。它们记录了当时的判断，**不要按里面的命令操作**——入口和脚本已经变过。

## 资产

| 路径 | 内容 |
|---|---|
| `docs/screenshots/` | 控制台截图，由 `scripts/take_screenshots.py` 生成 |
| `docs/media/` | README 用的演示视频 |
| `docs/logo*.svg` `og-1200x630.png` | 品牌资产 |
| `docs/index.html` | 项目落地页 |
| `docs/napcat-compose.yaml` | 协议端 compose 示例 |

## 维护约定

1. **新增文档先问归属**：现行就放根，历史就放 `archive/`，别在根上堆。
2. 涉及命令的文档，改脚本时必须同步改文档（`scripts/qq_login`、`persona_eval` 等都被文档直接引用）。
3. 截图由脚本生成，不手工替换。
