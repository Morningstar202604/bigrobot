"""守护线程：掉线会自动重启，连续失败会停手。"""
import time

from core import qq_watchdog


class FakeDeploy:
    def __init__(self):
        self.alive = True
        self.started = 0
        self.fail = False

    def proc_alive(self):
        return self.alive

    def protocol_start(self, qq):
        if self.fail:
            raise RuntimeError("boom")
        self.started += 1
        self.alive = True


def test_watchdog_restarts_dead_process(monkeypatch):
    monkeypatch.setattr(qq_watchdog, "POLL", 0.05)
    monkeypatch.setattr(qq_watchdog, "DELAYS", (0.05,))
    fake = FakeDeploy()
    fake.alive = False
    qq_watchdog.start("10001", _deploy=fake)
    time.sleep(0.4)
    qq_watchdog.stop()
    assert fake.started >= 1
    assert qq_watchdog.status()["restarts"] >= 1


def test_watchdog_gives_up_after_max(monkeypatch):
    monkeypatch.setattr(qq_watchdog, "POLL", 0.05)
    monkeypatch.setattr(qq_watchdog, "DELAYS", (0.01,))
    monkeypatch.setattr(qq_watchdog, "MAX_RESTARTS", 1)
    fake = FakeDeploy()
    fake.alive = False
    fake.fail = True
    qq_watchdog.start("10002", _deploy=fake)
    time.sleep(0.6)
    qq_watchdog.stop()
    assert qq_watchdog.status()["failed"] is True
