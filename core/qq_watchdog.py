"""协议端守护：进程退出后按指数退避自动重启，超限停手并置 failed。

为什么要独立模块而不是塞进 qq_deploy：
deploy 负责"装和起"，watchdog 负责"活着"。混在一起后，部署失败和运行崩溃
会共用同一份 state，状态卡就分不清"没装好"还是"装好了但掉线"。

约束：
- 只依赖 qq_deploy 的 proc_alive / protocol_start 两个函数，便于测试替身
- 连续失败 max_restarts 次后停止重启（避免无限重拉打爆 CPU 与 QQ 风控）
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("cs.events")

POLL = 5.0                    # 轮询间隔
DELAYS = (1, 5, 30)          # 第 1/2/3 次及以后的重启等待
MAX_RESTARTS = 5

_state: dict[str, Any] = {
    "running": False,
    "restarts": 0,
    "last_exit": None,       # 最近一次检测到进程退出的时间
    "failed": False,
    "qq": "",
}
_thread: threading.Thread | None = None
_deploy_override: object | None = None
_stop = threading.Event()


def status() -> dict:
    return dict(_state)


def start(qq: str, *, _deploy=None) -> dict:
    """开启守护。重复调用是幂等的（不会起第二个线程）。"""
    global _thread
    if _state["running"]:
        return status()
    _state.update(running=True, qq=qq, restarts=0, failed=False, last_exit=None)
    global _deploy_override
    _deploy_override = _deploy
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="qq-watchdog")
    _thread.start()
    logger.info("qq watchdog started qq=%s", qq)
    return status()


def stop() -> dict:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=2)
        _thread = None
    _state["running"] = False
    logger.info("qq watchdog stopped")
    return status()


def _loop() -> None:
    deploy: Any = _deploy_override
    if deploy is None:
        from core import qq_deploy as deploy  # 延迟导入，避免与 qq_deploy 循环
    start_fn = deploy.protocol_start   # 测试替身只需这两个方法
    alive_fn = deploy.proc_alive

    while not _stop.is_set():
        if _stop.wait(POLL):
            break
        if alive_fn():
            continue
        _state["last_exit"] = time.time()
        if _state["restarts"] >= MAX_RESTARTS:
            _state["failed"] = True
            _state["running"] = False
            logger.warning("qq watchdog gave up after %s restarts", MAX_RESTARTS)
            return
        delay = DELAYS[min(_state["restarts"], len(DELAYS) - 1)]
        if _stop.wait(delay):
            break
        _state["restarts"] += 1
        logger.info("qq watchdog restarting (%s/%s)", _state["restarts"], MAX_RESTARTS)
        try:
            start_fn(_state["qq"])
        except Exception:  # noqa: BLE001 重启失败也要继续计数，不能把线程炸掉
            logger.exception("qq watchdog restart failed")
