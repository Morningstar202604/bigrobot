"""会话的账号维度：可空、写入即读回，老调用方不受影响。"""
from core import session_store, store


def _row(sid):
    with store.get_conn() as conn:
        return dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone())


def test_session_without_account_is_null():
    session_store.create_session("s-noacc", "v1", "sec")
    assert _row("s-noacc")["account_id"] is None


def test_session_with_account_roundtrips():
    session_store.create_session("s-acc", "v1", "sec", account_id="qq:10001")
    assert _row("s-acc")["account_id"] == "qq:10001"


def test_ingest_with_self_id_links_account(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "t1")
    monkeypatch.setenv("CHANNEL_TOKEN", "t1")
    from core import config as cfg
    monkeypatch.setattr(cfg, "get_config", lambda: {"channels": {"allowlist_enabled": False}})
    r = client.post("/v1/ingest", headers={"X-Channel-Token": "t1"},
                    json={"channel_type": "qq", "channel_user_id": "u1", "group_id": "g1",
                          "text": "hi", "self_id": "10001"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert _row(sid)["account_id"] == "qq:10001"


def test_ingest_without_self_id_keeps_null(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "t1")
    monkeypatch.setenv("CHANNEL_TOKEN", "t1")
    from core import config as cfg
    monkeypatch.setattr(cfg, "get_config", lambda: {"channels": {"allowlist_enabled": False}})
    r = client.post("/v1/ingest", headers={"X-Channel-Token": "t1"},
                    json={"channel_type": "qq", "channel_user_id": "u2", "text": "hi"})
    assert r.status_code == 200
    assert _row(r.json()["session_id"])["account_id"] is None


def test_resolve_session_canonicalizes_bare_account(tmp_path, monkeypatch):
    from core import sessions, store
    """网关给裸号 10001，落库必须变成 qq:10001，否则按账号筛不到。"""
    monkeypatch.setenv("BIGROBOT_DB", str(tmp_path / "canon.db"))
    store._SCHEMA_READY.clear()
    store.init_db()
    sid = sessions.resolve_session("qq_group:88123", "qq_group:88123", account_id="10001")
    assert store.get_session(sid)["account_id"] == "qq:10001"
    assert sessions.canonical_account("qq_private", "20002") == "qq:20002"
    assert sessions.canonical_account("wechat", "wx-1") == "wechat:wx-1"
    assert sessions.canonical_account("qq_group", "qq:30003") == "qq:30003"
