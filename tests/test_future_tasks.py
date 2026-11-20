"""未来任务：持久化、API、调度执行与失败重试。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


from core import future_task_store, future_tasks
from core.tool_context import ToolContext
from core import tools


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


def test_store_add_list_cancel():
    rec = future_task_store.future_task_add(
        visitor_id="u1", chat_key="webchat:u1", instruction="整理群消息",
        due_at=_past(), channel_type="webchat", channel_user_id="u1",
    )
    assert rec["status"] == "pending"
    assert future_task_store.future_task_due(datetime.now(timezone.utc).isoformat())
    assert [r["id"] for r in future_task_store.future_task_list("u1")] == [rec["id"]]
    assert future_task_store.future_task_cancel(rec["id"]) is True
    assert future_task_store.future_task_list("u1", status="pending") == []


def test_api_create_list_cancel(client):
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = client.post("/api/future-tasks", json={
        "instruction": "汇总今天的群聊", "due_at": due, "visitor_id": "admin",
    })
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    rows = client.get("/api/future-tasks?status=pending").json()["tasks"]
    assert any(x["id"] == tid for x in rows)
    assert client.delete(f"/api/future-tasks/{tid}").status_code == 200
    assert client.delete(f"/api/future-tasks/{tid}").status_code == 404


def test_api_rejects_unparsable_when(client):
    r = client.post("/api/future-tasks", json={"instruction": "做事", "when": "某个时候"})
    assert r.status_code == 400


def test_tick_executes_and_marks_done(monkeypatch):
    rec = future_task_store.future_task_add(
        visitor_id="u1", chat_key="webchat:u1", instruction="查一下明天天气",
        due_at=_past(), channel_type="webchat", channel_user_id="u1",
    )
    calls = {"exec": 0, "deliver": 0}

    async def fake_execute(row):
        calls["exec"] += 1
        return "明天晴，20-28 度。"

    async def fake_deliver(row, text):
        calls["deliver"] += 1
        assert "明天晴" in text
        return True, ""

    monkeypatch.setattr(future_tasks, "execute", fake_execute)
    monkeypatch.setattr(future_tasks, "deliver", fake_deliver)
    assert asyncio.run(future_tasks.tick()) == 1
    assert calls == {"exec": 1, "deliver": 1}
    got = future_task_store.future_task_get(rec["id"])
    assert got["status"] == "done"
    assert got["result"] == "明天晴，20-28 度。"


def test_tick_retries_delivery_without_reexecuting(monkeypatch):
    rec = future_task_store.future_task_add(
        visitor_id="u1", chat_key="webchat:u1", instruction="汇总",
        due_at=_past(), channel_type="webchat", channel_user_id="u1",
    )
    calls = {"exec": 0}

    async def fake_execute(row):
        calls["exec"] += 1
        return "结果"

    async def always_fail(row, text):
        return False, "network down"

    monkeypatch.setattr(future_tasks, "execute", fake_execute)
    monkeypatch.setattr(future_tasks, "deliver", always_fail)
    assert asyncio.run(future_tasks.tick()) == 0
    got = future_task_store.future_task_get(rec["id"])
    assert got["status"] == "pending"  # 还有重试机会
    assert got["attempts"] == 1
    assert "network down" in got["last_error"]
    # 第二轮：结果已落库，不应再次执行
    assert asyncio.run(future_tasks.tick()) == 0
    assert calls["exec"] == 1
    assert future_task_store.future_task_get(rec["id"])["attempts"] == 2


def test_tick_releases_on_execute_exception(monkeypatch):
    rec = future_task_store.future_task_add(
        visitor_id="u1", chat_key="webchat:u1", instruction="会炸",
        due_at=_past(), channel_type="webchat", channel_user_id="u1",
    )

    async def boom(row):
        raise RuntimeError("boom")

    async def ok(row, text):
        return True, ""

    monkeypatch.setattr(future_tasks, "execute", boom)
    monkeypatch.setattr(future_tasks, "deliver", ok)
    asyncio.run(future_tasks.tick())
    got = future_task_store.future_task_get(rec["id"])
    assert got["status"] == "pending"
    assert got["attempts"] == 1
    assert "RuntimeError" in got["last_error"]


def test_tool_future_task_and_cancel():
    ctx = ToolContext(visitor_id="u2", session_id="s2", channel_type="webchat",
                      channel_user_id="u2", persona_id="")
    out = tools.tool_future_task(ctx, instruction="帮我盯一下订单", when="10分钟后")
    assert out["found"] is True
    tid = out["task_id"]
    listed = tools.tool_list_future_tasks(ctx)
    assert listed["found"] is True and str(tid) in listed["note"]
    assert tools.tool_cancel_future_task(ctx, str(tid))["found"] is True
    # 别人的任务不能取消
    other = ToolContext(visitor_id="u3")
    assert tools.tool_cancel_future_task(other, str(tid))["found"] is False


def test_reminders_merged_op_routes_future_task():
    ctx = ToolContext(visitor_id="u4", session_id="s4", channel_type="webchat",
                      channel_user_id="u4")
    import asyncio
    out = asyncio.run(tools.invoke("reminders", {"op": "future", "instruction": "整理资料",
                                               "when": "1小时后"}, ctx))
    assert out["found"] is True and out["task_id"]
    tasks = asyncio.run(tools.invoke("reminders", {"op": "tasks"}, ctx))
    assert str(out["task_id"]) in tasks["note"]
    cancel = asyncio.run(tools.invoke("reminders", {"op": "cancel_task",
                                                  "task_id": str(out["task_id"])}, ctx))
    assert cancel["found"] is True


def test_tool_future_task_requires_time():
    ctx = ToolContext(visitor_id="u2")
    out = tools.tool_future_task(ctx, instruction="帮我做事", when="未来某天")
    assert out["found"] is False
    assert out["status"] == "need_context"
