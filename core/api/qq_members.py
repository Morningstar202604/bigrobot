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


@router.get("/groups/{group_id}/files", dependencies=[Depends(require_admin)])
async def group_files(group_id: str):
    """群文件列表。OneBot 的返回是 {files:[...]}，字段名各协议端略有差异，统一成固定形状。"""
    from gateway import bridge

    payload = await bridge.call_onebot("get_group_root_files", {"group_id": group_id})
    if payload is None:
        raise HTTPException(409, "没有可用的协议端连接（先在渠道页启动并登录）")
    files = (payload or {}).get("files") or []
    items = [
        {
            "file_id": str(f.get("file_id") or ""),
            "name": f.get("file_name") or f.get("name") or "",
            "size": int(f.get("file_size") or f.get("size") or 0),
            "uploader": str(f.get("uploader") or f.get("user_id") or ""),
            "uploaded_at": f.get("upload_time") or f.get("modify_time"),
            "busid": f.get("busid"),   # 下载时必须带回去，OneBot 用它定位目录
        }
        for f in files
        if isinstance(f, dict)
    ]
    return {"group_id": group_id, "count": len(items), "files": items}


@router.get("/groups/{group_id}/files/{file_id}/url", dependencies=[Depends(require_admin)])
async def group_file_url(group_id: str, file_id: str, busid: int = 0):
    """取下载直链。OneBot 的 get_group_file_url 需要 group_id + file_id + busid 三件套。"""
    from gateway import bridge

    payload = await bridge.call_onebot(
        "get_group_file_url",
        {"group_id": group_id, "file_id": file_id, "busid": busid},
    )
    if payload is None:
        raise HTTPException(409, "没有可用的协议端连接（先在渠道页启动并登录）")
    url = (payload or {}).get("url") if isinstance(payload, dict) else None
    if not url:
        raise HTTPException(404, "协议端没有返回下载地址（文件可能已过期）")
    return {"url": url}
