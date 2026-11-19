"""协议端调用桥：让 HTTP 层能调到 nonebot 已连接的 OneBot bot。

为什么要桥：nonebot 的 bot 生命周期在 gateway 进程里，core 的 API 不该直接
import nonebot（缺依赖时会连带 core 起不来）。所以这里做一次软依赖：
没有 nonebot、或没有已连接的 bot，都返回 None，由调用方转成 409。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("cs.events")


async def call_onebot(action: str, params: dict) -> dict | None:
    """向任一已连接的 OneBot bot 发一次 API 调用；不可用时返回 None。"""
    try:
        import nonebot
    except Exception:  # noqa: BLE001 可选依赖
        return None
    bots = list(nonebot.get_bots().values())
    for bot in bots:
        try:
            return await bot.call_api(action, **params)
        except Exception as e:  # noqa: BLE001 换下一个 bot 试
            logger.warning("onebot call %s failed: %s", action, e)
    return None
