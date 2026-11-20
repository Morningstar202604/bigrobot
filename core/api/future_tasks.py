"""未来任务 API：控制台查看、创建、取消，以及手动触发扫描。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import future_task_store
from core.api.deps import require_admin

router = APIRouter(prefix="/api/future-tasks", tags=["future-tasks"])


class FutureTaskIn(BaseModel):
    instruction: str
    when: str = ""
    due_at: str = ""
    visitor_id: str = "admin"
    chat_key: str = ""
    channel_type: str = "webchat"
    group_id: str | None = None
    channel_user_id: str | None = None
    session_id: str = ""
    persona_id: str = ""


@router.get("", dependencies=[Depends(require_admin)])
def future_tasks_list(status: str = "open", visitor_id: str = "", limit: int = 50):
    return {"tasks": future_task_store.future_task_list(
        visitor_id=visitor_id, status=status, limit=min(max(limit, 1), 200))}


@router.post("", dependencies=[Depends(require_admin)])
def future_tasks_create(body: FutureTaskIn):
    from core import tools as tools_mod

    instruction = (body.instruction or "").strip()
    if not instruction:
        raise HTTPException(400, "任务指令不能为空")
    due_iso = (body.due_at or "").strip()
    if not due_iso:
        due = tools_mod._parse_due((body.when or "").strip())
        if due is None:
            raise HTTPException(400, f"看不懂时间表达：{body.when or '(空)'}")
        due_iso = due.isoformat()
    rec = future_task_store.future_task_add(
        visitor_id=(body.visitor_id or "admin").strip(),
        chat_key=(body.chat_key or f"{body.channel_type}:{body.visitor_id or 'admin'}").strip(),
        instruction=instruction[:500],
        due_at=due_iso,
        channel_type=body.channel_type,
        group_id=body.group_id,
        channel_user_id=body.channel_user_id,
        session_id=body.session_id,
        persona_id=body.persona_id,
    )
    return rec


@router.delete("/{tid}", dependencies=[Depends(require_admin)])
def future_tasks_cancel(tid: int):
    if not future_task_store.future_task_cancel(tid):
        raise HTTPException(404, "任务不存在或已开始执行")
    return {"cancelled": tid}


@router.post("/tick", dependencies=[Depends(require_admin)])
async def future_tasks_tick():
    from core import future_tasks

    return {"done": await future_tasks.tick()}
