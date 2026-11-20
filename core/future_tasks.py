"""未来任务调度器：到点唤醒 Agent 执行一条指令，再把结果投回原渠道。

和提醒的区别：
- 提醒只投递固定文本；
- 未来任务会把当时保存的指令重新交给 Agent，允许它查库、读文件、发消息，
  执行结果落库后再投递，失败可重试。

并发语义沿用提醒的「原子认领」：多 worker 只有一个能抢到任务。
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from core import future_task_store, store

logger = logging.getLogger("core.future_tasks")

TICK_S = float(os.environ.get("FUTURE_TASK_TICK_SECONDS", "30"))
MAX_ATTEMPTS = int(os.environ.get("FUTURE_TASK_MAX_ATTEMPTS", "3"))


def _history(rec: dict) -> list[dict]:
    sid = (rec.get("session_id") or "").strip()
    if not sid:
        return []
    try:
        return store.get_messages(sid, limit=10, include_deleted=False)
    except Exception:
        return []


async def execute(rec: dict) -> str:
    """执行保存的指令，返回 Agent 最终文本。"""
    from core import pipeline
    from core.pipeline import ChannelMessage

    sid = (rec.get("session_id") or "").strip()
    msg = ChannelMessage(
        text=str(rec.get("instruction") or ""),
        channel_type=str(rec.get("channel_type") or "webchat"),
        channel_user_id=str(rec.get("channel_user_id") or rec.get("visitor_id") or "anonymous"),
        group_id=rec.get("group_id"),
        display_name="未来任务",
        session_id=sid,
    )
    reply = await pipeline.run(msg, _history(rec), str(rec.get("visitor_id") or ""))
    text = (reply.text or "").strip()
    if not text:
        raise RuntimeError(f"Agent 没有返回内容（mode={reply.mode}）")
    return text


async def deliver(rec: dict, text: str) -> tuple[bool, str]:
    from core import reminders

    prefix = f"⏳ 未来任务：{rec.get('instruction') or ''}\n\n"
    return await reminders.deliver_raw(rec, prefix + text)


async def tick() -> int:
    """扫描一次到期任务，返回成功完成数。"""
    now = datetime.now(timezone.utc).isoformat()
    rows = future_task_store.future_task_due(now)
    done = 0
    for rec in rows:
        tid = int(rec["id"])
        if not future_task_store.future_task_claim(tid):
            continue
        try:
            # 上次执行成功但投递失败：结果已落库，直接重投，避免重复执行副作用。
            text = str(rec.get("result") or "").strip()
            if not text:
                text = await execute(rec)
                future_task_store.future_task_set_result(tid, text)
            ok, err = await deliver(rec, text)
            if ok:
                future_task_store.future_task_mark(tid, "done")
                done += 1
                logger.info("future task %s done", tid)
            else:
                attempts = int(rec.get("attempts") or 0) + 1
                status = "failed" if attempts >= MAX_ATTEMPTS else "pending"
                future_task_store.future_task_mark(tid, status, err)
                logger.warning("future task %s delivery failed (%s/%s): %s",
                               tid, attempts, MAX_ATTEMPTS, err)
        except asyncio.CancelledError:
            future_task_store.future_task_release(tid)
            raise
        except Exception as e:
            attempts = int(rec.get("attempts") or 0) + 1
            status = "failed" if attempts >= MAX_ATTEMPTS else "pending"
            future_task_store.future_task_mark(tid, status, f"{type(e).__name__}: {str(e)[:200]}")
            logger.warning("future task %s execution failed (%s/%s): %s",
                           tid, attempts, MAX_ATTEMPTS, type(e).__name__)
    return done


async def run_forever(stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    logger.info("future task scheduler started (tick=%ss)", TICK_S)
    while not stop.is_set():
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("future task tick failed: %s: %s", type(e).__name__, str(e)[:150])
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_S)
        except asyncio.TimeoutError:
            pass
    logger.info("future task scheduler stopped")
