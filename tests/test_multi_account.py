"""多账号隔离：同群两个机器人各自一条会话，撤回/投递不串号。"""
from core import sessions, store


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGROBOT_DB", str(tmp_path / "multi.db"))
    store._SCHEMA_READY.clear()
    store.init_db()


def test_same_group_two_accounts_have_separate_sessions(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    channel = "qq_group:777"
    a = sessions.resolve_session(channel, "qq_group:777", account_id="10001")
    b = sessions.resolve_session(channel, "qq_group:777", account_id="20002")
    assert a != b
    assert store.get_session(a)["account_id"] == "qq:10001"
    assert store.get_session(b)["account_id"] == "qq:20002"
    assert store.get_channel_session(channel, "qq:10001")["session_id"] == a
    assert store.get_channel_session(channel, "qq:20002")["session_id"] == b

    # 同一个号再进来必须复用，不能每次新建
    assert sessions.resolve_session(channel, "qq_group:777", account_id="10001") == a


def test_legacy_mapping_is_adopted_by_first_account(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    channel = "qq_group:legacy"
    store.create_session("legacy-sid", "v", account_id="qq:10001")
    store.set_channel_session(channel, "legacy-sid", "")

    sid = sessions.resolve_session(channel, "v", account_id="10001")
    assert sid == "legacy-sid"
    assert store.get_channel_session(channel, "qq:10001")["session_id"] == sid
    assert store.get_channel_session(channel, "") is None


def test_visitor_key_is_account_scoped():
    assert sessions.scoped_visitor("qq_group:42", "qq_group:g", "10001") == "qq_group:42#qq:10001"
    assert sessions.scoped_visitor("qq_group:42", "qq_group:g", None) == "qq_group:42"


def test_recall_from_one_account_does_not_touch_other(client):
    channel = "qq_group:88"
    store.create_session("s-a", "v", account_id="qq:10001")
    store.create_session("s-b", "v", account_id="qq:20002")
    store.set_channel_session(channel, "s-a", "qq:10001")
    store.set_channel_session(channel, "s-b", "qq:20002")
    store.add_message("s-a", "visitor", "A 的消息", external_id="m-a")
    store.add_message("s-b", "visitor", "B 的消息", external_id="m-b")

    r = client.post("/v1/event", json={
        "kind": "notice", "event_type": "group_recall",
        "channel_type": "qq_group", "channel_user_id": "42",
        "group_id": "88", "message_id": "m-a", "self_id": "10001",
    })
    assert r.status_code == 200
    assert r.json()["action"] == "deleted"
    assert store.get_messages("s-a", include_deleted=False) == []
    assert len(store.get_messages("s-b", include_deleted=False)) == 1


def test_ingest_same_group_from_two_self_ids(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "t1")
    monkeypatch.setenv("CHANNEL_TOKEN", "t1")
    from core import config as cfg
    monkeypatch.setattr(cfg, "get_config", lambda: {"channels": {"allowlist_enabled": False}})
    body = {"channel_type": "qq_group", "channel_user_id": "u1", "group_id": "g1",
            "text": "hi"}
    r1 = client.post("/v1/ingest", headers={"X-Channel-Token": "t1"}, json={**body, "self_id": "10001"})
    r2 = client.post("/v1/ingest", headers={"X-Channel-Token": "t1"}, json={**body, "self_id": "20002"})
    assert r1.status_code == 200 and r2.status_code == 200
    sid1, sid2 = r1.json()["session_id"], r2.json()["session_id"]
    assert sid1 != sid2
    assert store.get_session(sid1)["account_id"] == "qq:10001"
    assert store.get_session(sid2)["account_id"] == "qq:20002"
    assert store.get_session(sid1)["visitor_id"].endswith("#qq:10001")
    assert store.get_session(sid2)["visitor_id"].endswith("#qq:20002")
    assert store.get_messages(sid1, include_deleted=False)[0]["account_id"] == "qq:10001"
    assert store.get_messages(sid2, include_deleted=False)[0]["account_id"] == "qq:20002"
    # 用户档案也分桶：同一人在两个号上是两段关系
    from core import profiles
    assert profiles.get_profile("qq:u1#qq:10001") is not None
    assert profiles.get_profile("qq:u1#qq:20002") is not None
