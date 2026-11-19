"""守护线程：掉线会自动重启，连续失败会停手。

用条件等待而不是 sleep 固定时长：整套用例并行跑时线程调度会漂，
定长 sleep 会出现"单跑过、全量挂"的假失败。
"""
import time

import pytest

from core import qq_watchdog


@pytest.fixture(autouse=True)
def _reset_watchdog():
    qq_watchdog.stop()
    qq_watchdog._state.update(running=False, restarts=0, failed=False, last_exit=None)
    yield
    qq_watchdog.stop()


def wait_until(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return False


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
    monkeypatch.setattr(qq_watchdog, "POLL", 0.02)
    monkeypatch.setattr(qq_watchdog, "DELAYS", (0.02,))
    fake = FakeDeploy()
    fake.alive = False
    qq_watchdog.start("10001", _deploy=fake)
    assert wait_until(lambda: fake.started >= 1)
    assert qq_watchdog.status()["restarts"] >= 1


def test_watchdog_gives_up_after_max(monkeypatch):
    monkeypatch.setattr(qq_watchdog, "POLL", 0.02)
    monkeypatch.setattr(qq_watchdog, "DELAYS", (0.01,))
    monkeypatch.setattr(qq_watchdog, "MAX_RESTARTS", 1)
    fake = FakeDeploy()
    fake.alive = False
    fake.fail = True
    qq_watchdog.start("10002", _deploy=fake)
    assert wait_until(lambda: qq_watchdog.status()["failed"] is True)
