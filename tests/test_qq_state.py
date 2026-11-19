"""状态卡要带出进程与守护的实况，否则看门狗工作了用户也看不见。

断言同步函数而不是 async handler：整套用例里 event loop 可能已被别的异步用例占用，
在测试里再起一个 asyncio.run 会变成"看顺序"的假失败。
"""
from core import qq_deploy


def test_deploy_status_exposes_process_and_watchdog():
    body = qq_deploy.status_card()
    assert "alive" in body and "pid" in body
    for key in ("running", "restarts", "failed", "last_exit"):
        assert key in body["watchdog"]
