"""会话历史拉取：把协议端的历史消息拉进本地 messages。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import history_ingest, store
from core.api.deps import require_admin

router = APIRouter(prefix="/api/sessions", tags=["history"])


class PullIn(BaseModel):
    group_id: str
    limit: int = 50


@router.post("/{sid}/history/pull", dependencies=[Depends(require_admin)])
async def pull_history(sid: str, body: PullIn):
    if not store.get_session(sid):
        raise HTTPException(404, "会话不存在")
    limit = max(1, min(body.limit, 200))   # 协议端一次最多给多少，不放大请求

    from gateway import bridge

    payload = await bridge.call_onebot(
        "get_group_msg_history", {"group_id": body.group_id, "count": limit})
    if payload is None:
        # 没有在线协议端是"当前不可用"，不是服务端错误：让前端提示去扫码/启动
        raise HTTPException(409, "没有可用的协议端连接（先在渠道页启动并登录）")
    rows = history_ingest.onebot_history_rows(payload)
    return history_ingest.ingest_history(sid, rows)
