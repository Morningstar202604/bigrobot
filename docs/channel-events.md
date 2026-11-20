# 渠道事件

网关把 OneBot v11 的 `notice` / `request` 事件送到核心 `/v1/event`，核心落库并执行有限的确定性副作用。

## 支持的事件

| kind | event_type | 行为 |
|---|---|---|
| notice | `group_recall` | 找到对应会话里的消息并软删除，模型不再引用被撤回内容 |
| notice | `friend_recall` | 同上（私聊） |
| notice | `group_increase` / `group_decrease` | 仅审计留档 |
| notice | `group_admin` / `group_card` / `friend_add` | 仅审计留档 |
| request | `friend` / `group` | 仅审计留档，不自动同意 |

## 为什么不做自动审批

加好友、加群、踢人、禁言这类动作会改变外部状态。核心只记录事件，审批由 `policy` / `approvals` 链路处理；网关不替人做决定。

## 数据

`channel_events` 表记录：事件类型、渠道、群号、触发用户、消息 id、操作者、机器人账号、原始诊断字段、处理结果、时间。

查询：

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" \
  "http://127.0.0.1:8010/api/channel-events?limit=50&event_type=group_recall"
```

## 撤回语义

只有核心实际落过库的访客消息才带 `external_id`。撤回事件命中时走 `store.delete_message` 软删除，历史仍保留在审计里，但不会进入模型上下文。
