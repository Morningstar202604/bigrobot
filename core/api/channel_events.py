"""渠道事件查询 API：只读审计，不在控制台做审批动作。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core import channel_events as events_mod, store
from core.api.deps import require_admin

router = APIRouter(prefix="/api/channel-events", tags=["channel-events"])


@router.get("", dependencies=[Depends(require_admin)])
def channel_events_list(limit: int = 100, kind: str = "", event_type: str = ""):
    rows = store.list_channel_events(limit=limit, kind=kind, event_type=event_type)
    for r in rows:
        r["payload"] = events_mod.parse_payload(r.get("payload") or "")
        r["handled"] = bool(r.get("handled"))
        r["result"] = (r.get("result") or "").strip()
    return {"events": rows}
