# Multi-account isolation

English · [中文](zh/multi-account.md)

Two bot accounts can watch the same QQ group at once. A session keyed only by `channel` would share one conversation and one context, and a message received by account A could be sent by account B. Sessions are now keyed by `(channel, account_id)`.

## Session mapping

`channel_sessions` uses `(channel, account_id)` as its primary key:

```text
qq_group:12345  qq:10001  -> session A
qq_group:12345  qq:20002  -> session B
```

Accounts are canonicalised to `qq:10001`. A bare gateway `self_id=10001` or an old `qq_group:10001` is normalised.

### Legacy databases

Migration rebuilds the table and puts old rows in the `account_id=''` bucket. When a concrete account first enters the same channel, an unowned legacy session, or one already owned by that account, is claimed so context is not lost. A differently owned session is left alone and a new one is created; another account's history is never adopted.

## Visitor identity

QQ visitor keys carry an account suffix:

```text
qq_group:42#qq:10001
qq_group:42#qq:20002
```

Memory, reminders and future tasks use this key. User profiles append the same suffix after `qq:<user id>`, so one person on two bot accounts does not mix state. Web visitors have no account and keep their old keys.

## Action routing

- Tools that send a group or private message, or query the protocol side, carry `ToolContext.account_id` to the gateway.
- `POST /internal/action` resolves the bot by `account_id`. If that account is offline it returns 503 instead of silently using the first online bot.
- Normal replies also select the bot by the source `self_id`; each account has its own adapter binding.
- A console action uses the request's `account_id` first, then the account of the session named by `session_id`, then the first online bot.

## Reminders and future tasks

`reminders` and `future_tasks` store `account_id`. Delivery goes through the original account. Rows created before the upgrade have an empty account and keep the old first-online-bot behaviour.

## Reset

`POST /v1/channel/reset` accepts `self_id`; it removes only that account's mapping and closes that session. Another account in the same group is untouched.

## Current boundaries

- `tickets` has no separate account column; it joins an already isolated session by `session_id`.
- Group-level profiles and slang remain shared per group. The language environment of a group is shared by design; if a future feature needs a per-bot persona inside one group, add an `account_id` dimension there.
- Multiple accounts online depend on NapCat actually running those accounts; the gateway can only route to bots visible in `get_bots()`.
