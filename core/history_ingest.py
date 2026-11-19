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
        msg_id = store.add_message(
            session_id, role, content,
            external_id=ext, source="platform",
        )
        if msg_id:
            added += 1
        else:
            skipped += 1
    logger.info("history ingest session=%s added=%s skipped=%s account=%s",
                session_id, added, skipped, account_id)
    return {"added": added, "skipped": skipped, "total": added + skipped}
