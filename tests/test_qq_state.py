"""部署状态卡要把进程与守护的实况带出来，否则看门狗工作了用户也看不见。"""


def test_deploy_status_exposes_process_and_watchdog(client):
    r = client.get("/api/channel/qq/deploy-status")
    assert r.status_code == 200
    body = r.json()
    assert "alive" in body and "pid" in body
    wd = body["watchdog"]
    for key in ("running", "restarts", "failed", "last_exit"):
        assert key in wd
