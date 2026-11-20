# Future tasks

English · [中文](zh/future-tasks.md)

A future task does not send a fixed sentence at a given time. It hands the original request back to the agent, lets it run, and delivers the result to the originating channel.

## Reminder vs future task

| | Reminder | Future task |
|---|---|---|
| At the due time | Deliver fixed text | Run the agent again with knowledge, files and tools |
| Result | User reads it | Agent result is stored, then delivered |
| Failure | Retry delivery | Retry execution or delivery; a successful result is not executed twice |
| Good for | "Remind me at nine" | "At nine, summarise last night's group chat and list the follow-ups" |

Both use the same channel delivery for QQ groups, QQ direct messages and web sessions.

## In chat

Plain language is enough. The model uses the `reminders` tool with `op=future`:

- "Tomorrow at 9, summarise the unread messages in this group."
- "In three days, remind me to follow up with this customer and find their last quote."
- "Tonight at 9, turn the refund policy entries into three bullets and send them to me."

List and cancel:

- "What future tasks do I have?" → `reminders(op=tasks)`
- "Cancel future task 3" → `reminders(op=cancel_task)`

If a fixed sentence is all you need, use a reminder and skip agent execution.

## Console

The Reminders page has a Future tasks section. Enter an instruction and a time (quick options include "in one hour", "tonight at nine", "tomorrow at nine", "in three days"), then list or cancel pending tasks.

## API

All endpoints require `X-Admin-Token`.

```http
GET    /api/future-tasks?status=pending&visitor_id=&limit=50
POST   /api/future-tasks
DELETE /api/future-tasks/{id}
POST   /api/future-tasks/tick
```

Create:

```json
{
  "instruction": "Summarise last night's group chat and list follow-ups",
  "when": "tomorrow 9am",
  "visitor_id": "admin",
  "channel_type": "webchat",
  "session_id": "optional web session id"
}
```

You can pass `due_at` (ISO 8601 with a timezone) instead of `when`; `due_at` wins. `session_id` loads the last ten messages from the original session so the task knows where the conversation stopped. It can run without one, with no context.

## Execution model

1. A scheduler scans due tasks every 30 seconds (`FUTURE_TASK_TICK_SECONDS`).
2. SQLite claims the task atomically; only one worker runs it.
3. A `ChannelMessage` is built and `pipeline.run()` is reused, so persona, knowledge scope and tool permissions are the same as a live turn.
4. The result is stored first, then delivered. A delivery failure retries delivery, not the side-effecting execution.
5. After three failed attempts the task becomes `failed` (`FUTURE_TASK_MAX_ATTEMPTS`).
6. On startup, `running` tasks older than an hour are reclaimed (`FUTURE_TASK_STALE_SECONDS`); three interruptions mark the task `failed` instead of retrying forever.

States: `pending → running → done / failed / cancelled`. The console shows pending and failed tasks with `status=open`; failed tasks can be cancelled.

## Limits

- A future task runs once, not on a cron. Use reminder `repeat_rule` for recurring work.
- Execution restores the preset persona and knowledge scope captured at creation. If that preset was deleted, it falls back to the current chat persona.
- An expired web session still runs the task, but with no history. Delivery tries the original session and records `last_error` on failure.
- QQ delivery needs the bot to remain in the group or friend list; leaving makes the task fail and retry.
- Future tasks may call write tools, so the creator must be a trusted subject. The console API needs the admin token; chat creation passes the normal tool permission gate.
