"""渠道事件：落库、查询、撤回软删除。"""


def test_event_is_recorded_and_listed(client):
    r = client.post("/v1/event", json={
        "kind": "notice", "event_type": "group_increase",
        "channel_type": "qq_group", "channel_user_id": "42",
        "group_id": "100", "self_id": "10001",
        "payload": {"sub_type": "increase"},
    })
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "recorded"

    rows = client.get("/api/channel-events").json()["events"]
    assert rows and rows[0]["event_type"] == "group_increase"
    assert rows[0]["payload"]["sub_type"] == "increase"
    assert rows[0]["handled"] is True


def test_recall_soft_deletes_the_message(client):
    from core import store

    sid = "sid-recall"
    store.create_session(sid, "qq:42", account_id="qq:10001")
    store.add_message(sid, "visitor", "这句会被撤回", external_id="9001")
    store.set_channel_session("qq_group:100", sid)

    r = client.post("/v1/event", json={
        "kind": "notice", "event_type": "group_recall",
        "channel_type": "qq_group", "channel_user_id": "42",
        "group_id": "100", "message_id": "9001", "self_id": "10001",
    })
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "deleted"

    assert store.get_messages(sid, include_deleted=False) == []
    assert store.get_messages(sid, include_deleted=True)[0]["deleted"] == 1
    events = client.get("/api/channel-events?event_type=group_recall").json()["events"]
    assert events[0]["result"].startswith("deleted")


def test_recall_unknown_message_is_ignored(client):
    r = client.post("/v1/event", json={
        "kind": "notice", "event_type": "friend_recall",
        "channel_type": "qq_private", "channel_user_id": "42",
        "message_id": "404", "self_id": "10001",
    })
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "ignored"


def test_event_requires_known_kind(client):
    r = client.post("/v1/event", json={"kind": "message", "event_type": "x"})
    assert r.status_code == 400
