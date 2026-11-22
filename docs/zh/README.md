# 文档索引

[English](../README.md) · 中文

## 现行（改代码时要同步更新）

| 文档 | 用途 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 进程模型与分层：core / gateway / executor |
| [DEPLOY.md](DEPLOY.md) | 安装、启动、QQ 协议端、验收、运维、排障 |
| [RELEASING.md](RELEASING.md) | 版本号与发布流程 |
| [route-audit.md](route-audit.md) | 路由消费者审计口径 |
| [PERSONA-EVAL.md](PERSONA-EVAL.md) | 人设评测方法与结果 |
| [COMPARISON.md](COMPARISON.md) | 产品边界：是什么、不是什么 |
| [extensions.md](extensions.md) | 声明式 HTTP 扩展与 MCP 客户端 |
| [knowledge-base.md](knowledge-base.md) | 多集合、角色绑定与资料摄入 |
| [future-tasks.md](future-tasks.md) | 到点让 Agent 执行并回推结果 |
| [channel-events.md](channel-events.md) | 通知、请求与撤回软删除 |
| [multi-account.md](multi-account.md) | 按机器人账号隔离会话、记忆与动作 |
| [persona-capabilities.md](persona-capabilities.md) | 角色工具/技能/MCP/扩展边界 |
| [remote-control.md](remote-control.md) | 手机扫码接管控制台：配对、安全模型与限制 |

## 存档

`docs/archive/` 保留早期 `*-v1.md` 与竞品调研。它记录当时的判断，命令和入口可能已经过期；不要按里面的步骤操作。

## 资产

| 路径 | 内容 |
|---|---|
| `docs/screenshots/` | 控制台截图，由 `scripts/take_screenshots.py` 生成 |
| `docs/media/` | 演示素材 |
| `docs/logo*.svg`、`docs/og-1200x630.png` | 品牌资产 |
| `docs/index.html` | 项目落地页 |
| `docs/napcat-compose.yaml` | 协议端 compose 示例 |

## 维护约定

1. 现行文档放 `docs/` 根，历史放 `archive/`，不要在根上堆。
2. 文档引用脚本时，改脚本必须同步改文档。
3. 截图由脚本生成，不手工替换。
4. 英文是主版本，中文翻译放 `docs/zh/` 并链接回英文页。
