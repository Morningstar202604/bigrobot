# Channel events

English · [中文](zh/channel-events.md)

The gateway forwards OneBot v11 `notice` and `request` events to core at `POST /v1/event`. Core records them and performs only a small set of deterministic side effects.

## Supported events

| Kind | Event type | Behaviour |
|---|---|---|
| notice | `group_recall` | Find the message in the mapped session and soft-delete it; the model no longer sees it |
| notice | `friend_recall` | Same for direct messages |
| notice | `group_increase` / `group_decrease` | Audit record only |
| notice | `group_admin` / `group_card` / `friend_add` | Audit record only |
| request | `friend` / `group` | Audit record only; never auto-accept |

## Why requests are not auto-approved

Adding a friend, joining a group, kicking or muting changes external state. Core records the event; decisions belong to the `policy` / `approvals` path. The gateway does not decide on a person's behalf.

## Data

`channel_events` stores the event type, channel, group id, triggering user, message id, operator, bot account, diagnostic payload, result and timestamp.

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" \
  "http://127.0.0.1:8010/api/channel-events?limit=50&event_type=group_recall"
```

## Recall semantics

Only visitor messages that core actually stored carry an `external_id`. A matching recall calls `store.delete_message` for a soft delete: the row stays in audit history, but never enters model context.

Recalls resolve the session by `self_id`. Two bot accounts in one group have separate mappings, so a recall seen by account A cannot delete the copy seen by account B.
