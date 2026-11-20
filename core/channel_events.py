"""渠道事件：OneBot notice/request → 核心落库 + 可执行的副作用。

第一版只做三件确定的事：
- 所有事件留档（谁、哪个群、哪个机器人账号、原始字段）；
- 撤回事件把对应消息软删除，避免模型继续引用已撤回内容；
- 其余事件只记录，不在网关/核心自动做审批或踢人——那些必须走策略与审批链。
"""
from __future__ import annotations

import json
import logging

from core import store

logger = logging.getLogger("core.channel_events")

RECALL_TYPES = {"group_recall", "friend_recall"}


def _channel_key(channel_type: str, group_id: str | None, channel_user_id: str | None) -> str:
    chat = (group_id or channel_user_id or "").strip()
    return f"{channel_type}:{chat}" if chat else ""


def handle(rec: dict) -> dict:
    """处理一条已落库事件，返回 {action, detail}。任何失败都不抛出。"""
    event_type = str(rec.get("event_type") or "")
    if event_type not in RECALL_TYPES:
        return {"action": "recorded", "detail": "仅记录"}
    channel = _channel_key(str(rec.get("channel_type") or "qq_group"),
                           rec.get("group_id"), rec.get("channel_user_id"))
    mid = str(rec.get("message_id") or "").strip()
    if not channel or not mid:
        return {"action": "ignored", "detail": "缺群/消息 id"}
    mapping = store.get_channel_session(channel)
    if not mapping:
        return {"action": "ignored", "detail": "会话不存在"}
    sid = str(mapping.get("session_id") or "")
    try:
        message_id = store.find_external_message(sid, mid)
    except Exception:
        message_id = None
    if not message_id:
        return {"action": "ignored", "detail": "消息未落库"}
    try:
        ok = store.delete_message(sid, int(message_id))
    except Exception as e:
        logger.warning("recall delete failed: %s", type(e).__name__)
        return {"action": "error", "detail": type(e).__name__}
    return {"action": "deleted" if ok else "ignored",
            "detail": f"message_id={message_id}"}


def parse_payload(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}
