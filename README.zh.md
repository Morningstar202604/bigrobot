# BigRobot

**中文** · [English](README.md)

接管你已经有的聊天账号，而不是再做一个机器人框架。

大多数机器人是等着回复消息。BigRobot 从另一头开始：先把一个现成账号接过来，把里面真实存在的东西看清楚，再在上面放一个 AI 助手。第一个渠道是 QQ——因为 QQ 本身没有可用的后台，登录之后什么都看不见。这里能看到群、成员、文件和历史，并且能直接操作。

## 能做什么

| 方面 | 内容 |
|---|---|
| 接管账号 | 启动协议端、扫码登录、看门狗守护与退避重启 |
| 看得见 | 群聊与私聊历史落本地库、成员整表含角色、群文件、群公告、好友 |
| 能操作 | 发文本/图片/语音/文件、撤回、禁言、踢人、改名片、发公告 |
| 语音 | 音频随消息保留，转码成 wav 后转写，结果回填到聊天记录 |
| AI 助手 | 工具调用带分级风险、审批、审计留痕、知识库、提醒 |
| 控制台 | 一个账号弹窗、一个会话抽屉，按能力渲染而不是按平台写死 |

## 设计取舍

**按能力声明，不按平台名写死。** `core/adapters_registry.py` 里声明一个渠道能做什么（`group.member_list`、`voice.transcribe`……），界面按能力渲染。接新平台是加一条声明，不是改界面。

**不假装成功。** 没有协议连接返回 409，转写未配置返回 503，音频格式不支持返回 422。失败就如实报失败，不生成一段看起来合理的假结果。

**只做加法迁移。** 表结构先加可空列，只有确定能知道的值才回填。老会话的 `account_id` 保持 `NULL`，不拿猜测去填。

## 快速开始

```bash
pip install -r requirements.txt
ADMIN_TOKEN=change-me python -m uvicorn core.main:app --port 8010
```

打开 `http://127.0.0.1:8010`。QQ 需要本地协议端（NapCat），账号弹窗会引导你部署 → 启动 → 扫码，细节见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 验证

```bash
python scripts/full_check.py        # 全部，约 4 分钟
python scripts/full_check.py --fast # 跳过测试套件
```

后端测试、ruff、mypy、前端 lint/测试/构建、路由统计与 harness 一次跑完——中途失败也会继续跑到底并给出完整报告。

## 目录

```
core/      API、存储、Agent 循环、渠道适配器
gateway/   与聊天协议之间的桥
executor/  动作执行沙箱
frontend/  控制台（React）
docs/      现行文档与存档，见 docs/README.md
```

## 文档

[部署](docs/DEPLOY.md) · [架构](docs/ARCHITECTURE.md) · [发布](docs/RELEASING.md) · [路由审计](docs/route-audit.md) · [角色评测](docs/PERSONA-EVAL.md)

## 现状

已完成：QQ 账号接管、历史、成员、文件、语音转写、带审批的工具调用。
还没做：第二个渠道的完整实现；在 CI 里对真实账号跑一次端到端。

## 许可

MIT，见 [LICENSE](LICENSE)。
