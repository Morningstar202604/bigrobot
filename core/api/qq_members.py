"""群成员整表：把 OneBot 的成员列表拉出来给控制台用。

历史消息是"发生过什么"，成员表是"现在有谁"——两者都属于 `group.member_list`
能力，控制台只有在渠道声明后才显示对应面板。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.api.deps import require_admin

router = APIRouter(prefix="/api/channel/qq", tags=["qq-members"])


@router.get("/groups/{group_id}/members", dependencies=[Depends(require_admin)])
async def group_members(group_id: str):
    from gateway import bridge

    payload = await bridge.call_onebot("get_group_member_list", {"group_id": group_id})
    if payload is None:
        raise HTTPException(409, "没有可用的协议端连接（先在渠道页启动并登录）")
    members = [
        {
            "user_id": str(m.get("user_id") or ""),
            "nickname": m.get("nickname") or m.get("card") or "",
            "card": m.get("card") or "",
            "role": m.get("role") or "member",   # owner / admin / member
            "join_time": m.get("join_time"),
            "last_active": m.get("last_sent_time"),
        }
        for m in (payload or [])
        if isinstance(m, dict)
    ]
    return {"group_id": group_id, "count": len(members), "members": members}
