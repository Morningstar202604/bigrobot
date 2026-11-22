# BigRobot

[English](README.md) · **中文**

BigRobot 把你自己已有的聊天账号接管成一个自托管 AI 工作台。账号仍然是你的：真实的群、成员、文件和聊天记录都在这里，助手只在你设定的权限范围内行动。

## 为什么从账号开始

大多数机器人等着回复消息。BigRobot 先把一个现成账号接过来，让你看清里面真实存在的东西。第一个渠道是 QQ——QQ 没有可用的后台，登录之后什么都看不见。这里能看到群、成员、文件和历史，再在上面放一个 Agent。

## 下载

Windows 免安装单文件：`releases/2.0.1/bigrobot-2.0.1-win64.exe`（不需要装 Python）。GitHub Releases 提供同一个包与 `SHA256SUMS.txt`；Gitee、GitCode 没有 Release 区，安装包直接放在仓库的 `releases/2.0.1/` 目录里。

包没有代码签名，Windows 可能弹 SmartScreen；首次运行会在用户数据目录创建 `bigrobot-data/`。校验值在 `releases/2.0.1/SHA256SUMS.txt`。

## 能做什么

- **接管账号**：启动协议端、扫码登录，用看门狗和退避重启维持在线。
- **看得见**：群聊与私聊历史落本地库，成员整表含角色，群文件、群公告、好友。
- **能操作**：发文本、图片、语音、文件；撤回、禁言、踢人、改名片、发公告。
- **语音**：音频随消息保留，转码、转写，再回填到聊天记录。
- **Agent**：工具调用带风险分级、审批和审计留痕；提醒与未来任务。
- **知识库**：多集合检索、文档摄入、按角色绑定资料包。
- **本地模型**：下载 2B 级本地模型，离线运行，一键切换；提示词不出本机，选哪个由用户自己定。
- **扩展**：声明式 HTTP 扩展包与 MCP stdio 客户端，安装后的工具进入同一套 Agent 工具注册表。
- **控制台**：一个账号弹窗、一个会话抽屉；界面按渠道能力渲染，不按平台名写死。

## 设计取舍

**按能力声明，不按平台名写死。** `core/adapters_registry.py` 声明一个渠道能做什么。接新平台是加一条声明，不是改界面。

**不假装成功。** 没有协议连接返回 409，转写未配置返回 503，音频格式不支持返回 422。失败就如实报失败。

**只做加法迁移。** 表结构先加可空列，只回填确定能知道的值。旧行保留空账号，不拿猜测去填。

## 快速开始

```bash
pip install -r requirements.txt
ADMIN_TOKEN=change-me python -m uvicorn core.main:app --port 8010
```

打开 `http://127.0.0.1:8010`。QQ 需要本地协议端（NapCat），账号弹窗会引导你部署 → 启动 → 扫码，细节见 [部署文档](docs/zh/DEPLOY.md)。

## 验证

```bash
python scripts/full_check.py        # 全部，几分钟
python scripts/full_check.py --fast # 跳过测试套件
```

后端测试、ruff、mypy、前端 lint/测试/构建、路由统计与 harness 一次跑完；中途失败也会打印完整报告。

## 目录

```
core/      API、存储、Agent 循环、渠道适配器
gateway/   与聊天协议之间的桥
executor/  动作执行沙箱
frontend/  控制台（React）
docs/      现行文档，中文翻译在 docs/zh
```

## 文档

[部署](docs/zh/DEPLOY.md) · [架构](docs/zh/ARCHITECTURE.md) · [发布](docs/zh/RELEASING.md) · [路由审计](docs/zh/route-audit.md) · [角色评测](docs/zh/PERSONA-EVAL.md) · [扩展与 MCP](docs/zh/extensions.md) · [知识库](docs/zh/knowledge-base.md) · [未来任务](docs/zh/future-tasks.md) · [渠道事件](docs/zh/channel-events.md) · [多账号](docs/zh/multi-account.md) · [角色能力](docs/zh/persona-capabilities.md) · [本地模型](docs/zh/LOCAL-MODELS.md) · [全部文档](docs/zh/README.md)

## 现状

已完成：QQ 账号接管、历史、成员、文件、语音转写、带审批的工具调用。

还没做：第二个渠道的完整实现；在 CI 里对真实账号跑一次端到端。

## 许可

MIT，见 [LICENSE](LICENSE)。
