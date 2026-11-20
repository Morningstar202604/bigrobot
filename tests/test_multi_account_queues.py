"""提醒 / 未来任务记住来源账号，投递时按账号路由。"""
import asyncio
from datetime import datetime, timedelta, timezone

from core import future_task_store, reminders, store


def test_reminder_keeps_account():
    due = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    rec = store.reminder_add("v#qq:10001", "qq_group:1", "喝水", due,
                             "qq_group", "1", "2", account_id="qq:10001")
    assert rec["account_id"] == "qq:10001"


def test_future_task_keeps_account():
    due = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    rec = future_task_store.future_task_add(
        "v#qq:20002", "qq_group:1", "查天气", due, "qq_group", "1", "2",
        account_id="qq:20002")
    assert rec["account_id"] == "qq:20002"


def test_reminder_delivery_routes_to_account(monkeypatch):
    seen = []

    async def fake_call(action, params, timeout_s=15, **kw):
        seen.append(kw.get("account_id"))
        return {"data": {}}

    from core.actions import client as action_client
    monkeypatch.setattr(action_client, "call_action", fake_call)
    rec = {"channel_type": "qq_group", "group_id": "1", "account_id": "qq:10002"}
    ok, err = asyncio.run(reminders._deliver_qq(rec, "到点了"))
    assert ok and not err
    assert seen == ["qq:10002"]
