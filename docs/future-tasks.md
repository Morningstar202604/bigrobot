# 未来任务（Future Task）

> 到点不是「发一句话提醒你」，而是「把当时那句话重新交给 Agent 去做」，做完再把结果发回原渠道。

## 它和提醒的区别

| | 提醒（reminder） | 未来任务（future task） |
|---|---|---|
| 到点做什么 | 投递一段固定文本 | 重新运行 Agent，可查知识库、读文件、调工具 |
| 结果 | 用户自己看 | Agent 执行结果落库后再投递 |
| 失败处理 | 投递失败重试 3 次 | 执行/投递失败都重试 3 次，已成功的结果不会重复执行 |
| 适合 | 「9 点叫我吃药」 | 「9 点帮我汇总昨晚群聊并列出待办」 |

两者共用同一套渠道投递（QQ 群/私聊、网页会话），区别只在到点之后。

## 在聊天里用

直接说人话即可，模型会通过「提醒管理」工具的 `op=future` 入口安排：

- 「明天早上 9 点帮我汇总群里的未读消息」
- 「3 天后提醒我跟进这个客户，并把他上次的报价找出来」
- 「今晚 9 点把知识库里关于退款政策的条目整理成三条发我」

查看和取消：

- 「我有哪些未来任务？」→ `reminders(op=tasks)`
- 「取消 3 号未来任务」→ `reminders(op=cancel_task)`

如果只想到点收到一句话，用原来的「提醒」即可，不必占用 Agent 执行。

## 控制台

「提醒」页新增「未来任务」区块，可直接填写指令和时间（支持「1 小时后 / 今晚 9 点 / 明天 9 点 / 3 天后」快捷选项），并查看、取消待执行任务。

## API

所有接口都需要 `X-Admin-Token`。

```http
GET    /api/future-tasks?status=pending&visitor_id=&limit=50
POST   /api/future-tasks
DELETE /api/future-tasks/{id}
POST   /api/future-tasks/tick
```

创建：

```json
{
  "instruction": "汇总昨晚群聊并列出待办",
  "when": "明天9点",
  "visitor_id": "admin",
  "channel_type": "webchat",
  "session_id": "可选的网页会话 id"
}
```

也可以直接传 `due_at`（ISO 8601，带时区），优先级高于 `when`。`session_id` 用于执行时加载原会话最近 10 条消息，让任务知道「上次聊到哪」；不传也能执行，只是没有上下文。

## 执行模型

1. 调度器每 30 秒扫描一次到期任务（`FUTURE_TASK_TICK_SECONDS`）。
2. 用 SQLite 原子认领，多个 worker 只有一个能执行。
3. 构造 `ChannelMessage`，复用 `pipeline.run()`，与原聊天同一条 Agent 链路（角色、知识库、工具权限都生效）。
4. 结果先落库，再投递；投递失败只重投，不重复执行可能有副作用的任务。
5. 执行或投递失败累计 3 次后标记 `failed`（`FUTURE_TASK_MAX_ATTEMPTS`）。
6. 服务启动时回收超过 1 小时的 `running` 僵尸任务（`FUTURE_TASK_STALE_SECONDS`），
   连续中断 3 次直接判 `failed`，避免必然崩溃的任务无限重跑。

状态：`pending → running → done / failed / cancelled`。控制台用 `status=open`
同时展示待执行与失败任务，失败任务可以直接取消。

## 边界与已知限制

- 未来任务不是定时 cron：只执行一次，不做周期调度；周期需求用提醒的 `repeat_rule`。
- 执行时优先恢复任务创建时的预设角色与知识库范围；预设已被删除时才回落到当前聊天角色。
- 网页会话若已过期，任务仍会执行，但历史为空；结果会尝试投回原会话，失败则落 `last_error`。
- QQ 侧投递依赖机器人仍在目标群/好友关系内；退群后任务会失败并重试。
- 未来任务允许调用写工具，因此创建者必须是可信主体；控制台 API 需要管理员 token，聊天侧走现有工具权限闸门。
