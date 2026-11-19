"""状态卡：把进程与守护的实况拼进部署态。

不依赖真实部署目录（整套用例里别的用例会把 DEPLOY_DIR 换到 tmp）：
这里只验证"拼接逻辑"，把 deploy_status 打桩掉。
"""
from core import qq_deploy


def test_status_card_merges_process_and_watchdog(monkeypatch):
    monkeypatch.setattr(qq_deploy, "deploy_status", lambda: {"stage": "idle", "pct": 0})
    body = qq_deploy.status_card()
    assert body["stage"] == "idle"
    assert "alive" in body and "pid" in body
    for key in ("running", "restarts", "failed", "last_exit"):
        assert key in body["watchdog"]
