"""未来任务持久化层：到点让 Agent 执行的指令，而不是一条固定提醒。

与 reminders 分开存：提醒的产物是一段文本，未来任务的产物是一次 Agent 运行，
需要保存会话、角色、执行结果与重试状态。两者共享同一套「原子认领」并发语义。
"""
from __future__ import annotations

import sqlite3

from core.store import _now, get_conn

__all__ = [
    "future_task_add", "future_task_get", "future_task_list", "future_task_due",
    "future_task_claim", "future_task_release", "future_task_set_result",
    "future_task_mark", "future_task_cancel",
]


def future_task_add(visitor_id: str, chat_key: str, instruction: str, due_at: str,
                    channel_type: str = "webchat", group_id: str | None = None,
                    channel_user_id: str | None = None, session_id: str = "",
                    persona_id: str = "") -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO future_tasks (visitor_id, chat_key, channel_type, group_id, "
            "channel_user_id, session_id, persona_id, instruction, due_at, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (visitor_id, chat_key, channel_type, group_id, channel_user_id,
             session_id, persona_id, instruction, due_at, _now()),
        )
        tid = cur.lastrowid
    return future_task_get(int(tid)) or {}


def future_task_get(tid: int) -> dict | None:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT * FROM future_tasks WHERE id = ?", (tid,)).fetchone()
    return dict(r) if r else None


def future_task_list(visitor_id: str = "", status: str = "pending", limit: int = 50) -> list[dict]:
    sql = "SELECT * FROM future_tasks WHERE 1=1"
    args: list = []
    if visitor_id:
        sql += " AND visitor_id = ?"
        args.append(visitor_id)
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY due_at LIMIT ?"
    args.append(limit)
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def future_task_due(now: str, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM future_tasks WHERE status = 'pending' "
            "AND julianday(due_at) <= julianday(?) "
            "ORDER BY julianday(due_at) LIMIT ?", (now, limit)).fetchall()
    return [dict(r) for r in rows]


def future_task_claim(tid: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE future_tasks SET status = 'running', started_at = ? "
            "WHERE id = ? AND status = 'pending'", (_now(), tid))
    return cur.rowcount > 0


def future_task_release(tid: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE future_tasks SET status = 'pending' WHERE id = ? AND status = 'running'", (tid,))


def future_task_set_result(tid: int, result: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE future_tasks SET result = ?, executed_at = ? WHERE id = ?",
            (result[:4000], _now(), tid),
        )


def future_task_mark(tid: int, status: str, error: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE future_tasks SET status = ?, finished_at = ?, attempts = attempts + 1, "
            "last_error = ? WHERE id = ?",
            (status, _now(), error[:300], tid),
        )


def future_task_cancel(tid: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE future_tasks SET status = 'cancelled' WHERE id = ? AND status = 'pending'", (tid,))
    return cur.rowcount > 0
