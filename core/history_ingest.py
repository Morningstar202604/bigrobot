"""历史消息落库：把平台侧拉回来的消息写进本地 messages，幂等。

为什么单独一层：
- 平台 API 的分页/字段各不相同，但"每条消息变成什么"是所有渠道一样的
- 落库必须幂等：分页拉取会重叠，重复写入会让会话上下文和统计都失真
- 拉取失败的渠道要能明确报错，而不是静默少几条
"""
from __future__ import annotations

import logging
from typing import Iterable

from core import store

logger = logging.getLogger("cs.events")


def ingest_history(session_id: str, rows: Iterable[dict], *, account_id: str = "default") -> dict:
    """把一批平台消息写进会话。

    每行至少要有 `external_id` 与 `content`；`role` 缺省 visitor，
    `sender` 会拼在内容前缀里（QQ 历史里只有昵称，没有角色）。
    """
    added = skipped = 0
    for row in rows:
        ext = str(row.get("external_id") or "").strip()
        if not ext:
            skipped += 1
            continue
        if store.find_external_message(session_id, ext):
            skipped += 1
            continue
        role = row.get("role") or "visitor"
        content = str(row.get("content") or "").strip()
        sender = str(row.get("sender") or "").strip()
        if sender and role == "visitor":
            content = f"{sender}: {content}" if content else sender
        audio = str(row.get("audio_url") or "").strip()
        msg_id = store.add_message(
            session_id, role, content,
            refs=[audio] if audio else None,
            external_id=ext, source="platform",
        )
        if msg_id:
            added += 1
        else:
            skipped += 1
    logger.info("history ingest session=%s added=%s skipped=%s account=%s",
                session_id, added, skipped, account_id)
    return {"added": added, "skipped": skipped, "total": added + skipped}

def onebot_segments_to_text(message) -> tuple[str, str]:
    """OneBot 的 message 可能是字符串，也可能是 [{type,data}] 段数组。"""
    if isinstance(message, str):
        return message, ""
    parts = []
    audio = ""
    for seg in message or []:
        if not isinstance(seg, dict):
            continue
        data = seg.get("data") or {}
        if seg.get("type") == "text":
            parts.append(str(data.get("text") or ""))
        elif seg.get("type") == "image":
            parts.append("[图片]")
        elif seg.get("type") == "face":
            parts.append("[表情]")
        elif seg.get("type") == "record":
            parts.append("[语音]")
            audio = str(data.get("url") or data.get("file") or "")
    return "".join(parts), audio


def onebot_history_rows(payload: dict) -> list[dict]:
    """把 get_group_msg_history 的返回转成 ingest_history 认识的扁平行。"""
    rows = []
    for m in (payload or {}).get("messages") or []:
        ext = str(m.get("message_id") or "").strip()
        if not ext:
            continue
        sender = (m.get("sender") or {}).get("nickname") or ""
        text, audio = onebot_segments_to_text(m.get("message"))
        rows.append({
            "external_id": ext,
            "sender": sender,
            "content": text,
            "audio_url": audio,
        })
    return rows


def ingest_group_history(session_id: str, group_id: str, call_api, *, limit: int = 50) -> dict:
    """拉一页群历史并落库。`call_api` 注入，便于测试替身与不同协议端复用。"""
    payload = call_api("get_group_msg_history", {"group_id": group_id, "count": limit})
    return ingest_history(session_id, onebot_history_rows(payload or {}))
