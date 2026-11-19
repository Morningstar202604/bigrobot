"""部署状态卡要把进程与守护的实况带出来，否则看门狗工作了用户也看不见。

这里直接调 handler 而不是走 HTTP：状态聚合本身要断言的是"字段拼装"，
HTTP 层的 ADMIN_TOKEN 默认值在整套用例里会被别的用例临时摘掉，
用 HTTP 会让这个测试的成败取决于执行顺序。
"""
import asyncio

from core import qq_watchdog
from core.api import qq_deploy as api


def test_deploy_status_exposes_process_and_watchdog():
    body = asyncio.run(api.deploy_status(None))
    assert "alive" in body and "pid" in body
    for key in ("running", "restarts", "failed", "last_exit"):
        assert key in body["watchdog"]
    assert body["watchdog"] == qq_watchdog.status()
