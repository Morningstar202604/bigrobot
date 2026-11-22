"""手机远控：一次性配对、单手机、刷新失效、停止失效。"""
import re
import time

import pytest

from core import remote


@pytest.fixture(autouse=True)
def clean_remote(monkeypatch):
    monkeypatch.setattr(remote, "_audit", lambda *a, **k: None)
    remote.stop()
    yield
    remote.stop()


def _pair(mode="direct"):
    r = remote.start("http://127.0.0.1:8014", "127.0.0.1:8014", 8014, mode)
    raw = re.search(r"#t=([^&]+)", r["url"]).group(1)
    return r, raw


def test_pair_link_is_fragment_and_has_qr():
    r, raw = _pair()
    assert "/remote#t=" in r["url"]
    assert raw not in r["url"].split("#")[0]
    assert r["qr"].startswith("data:image/png;base64,")
    assert r["mode"] == "direct"


def test_pair_is_one_time_and_token_works():
    _, raw = _pair()
    token, base = remote.pair(raw, "iPhone", "1.2.3.4")
    assert token and base
    assert remote.validate(token)
    assert remote.status()["connected"] == 1
    # 同一个二维码不能再用
    assert remote.pair(raw, "第二台", "1.2.3.4")[0] is None


def test_new_pair_kicks_old_phone_and_stop_revokes():
    _, raw = _pair()
    token, _ = remote.pair(raw, "旧手机", "1.1.1.1")
    assert remote.validate(token)
    _, raw2 = _pair()
    assert not remote.validate(token), "刷新二维码后旧手机必须掉线"
    token2, _ = remote.pair(raw2, "新手机", "2.2.2.2")
    assert remote.validate(token2)
    remote.stop()
    assert not remote.validate(token2)
    assert remote.status()["active"] is False


def test_expired_pair_and_token_are_rejected():
    _, raw = _pair()
    remote._pair["expires"] = time.time() - 1
    assert remote.pair(raw, "迟到手机", "")[0] is None
    _, raw2 = _pair()
    token, _ = remote.pair(raw2, "手机", "")
    key = next(iter(remote._sessions))
    remote._sessions[key]["expires"] = time.time() - 1
    assert not remote.validate(token)
