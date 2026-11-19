"""可观测性聚合接口：总览 / 日志。

合并的理由不是"路径好看"，而是原来同一份数据被拼了四遍：
`admin/overview`+`stats`+`report` 都在算统计，`admin/logs`+`injection-log`+`audit/entries`
都在翻日志。控制台首屏因此要打 3 个请求，日志页要打 2 个。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core import events_log, retrieval, store
from core.api.deps import require_admin

router = APIRouter(prefix="/api/observe", tags=["observe"])


@router.get("/overview", dependencies=[Depends(require_admin)])
def overview(days: int = 7):
    """一屏里的全部统计：计数、反馈汇总、近 N 天报表、漏斗。"""
    with store.get_conn() as conn:
        sessions = conn.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"]
        messages = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
        tickets = conn.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) c FROM sessions WHERE status='pending_agent'").fetchone()["c"]
    return {
        "sessions": sessions,
        "messages": messages,
        "tickets": tickets,
        "pending": pending,
        "feedback": store.feedback_summary(),
        "kb_count": len(retrieval.load_kb()),
        "injection": len(store.injection_log(50)),
        "stats": store.admin_stats(),
        "report": store.admin_report(days),
    }


@router.get("/logs", dependencies=[Depends(require_admin)])
def logs(source: str = "events", limit: int = 200, level: str | None = None):
    """一页日志三类来源：运行日志 / 注入日志 / 审计链。"""
    if source == "injection":
        return {"source": source, "entries": store.injection_log(limit)}
    if source == "audit":
        with store.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, actor, kind, payload, hash FROM audit_chain "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        return {"source": source, "entries": [dict(r) for r in rows]}
    return {"source": "events", "entries": events_log.entries(limit=limit, level=level)}
