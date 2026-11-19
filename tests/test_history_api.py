"""拉取路由：没有协议端要 409，有协议端要幂等落库。"""
from core import store
from tests.conftest import create_web_session

PAYLOAD = {"messages": [
    {"message_id": 21, "sender": {"nickname": "小明"},
     "message": [{"type": "text", "data": {"text": "早"}}]},
]}


def test_no_protocol_connection_returns_409(client, monkeypatch):
    from gateway import bridge

    async def none(*a, **kw):
        return None

    monkeypatch.setattr(bridge, "call_onebot", none)
    sid, _ = create_web_session(client)
    r = client.post(f"/api/sessions/{sid}/history/pull", json={"group_id": "410001"})
    assert r.status_code == 409


def test_pull_is_idempotent(client, monkeypatch):
    from gateway import bridge

    async def fake(action, params):
        assert action == "get_group_msg_history"
        return PAYLOAD

    monkeypatch.setattr(bridge, "call_onebot", fake)
    sid, _ = create_web_session(client)
    r1 = client.post(f"/api/sessions/{sid}/history/pull", json={"group_id": "410001"})
    r2 = client.post(f"/api/sessions/{sid}/history/pull", json={"group_id": "410001"})
    assert r1.status_code == 200 and r1.json()["added"] == 1
    assert r2.json()["added"] == 0
    assert any(m["source"] == "platform" for m in store.get_messages(sid))
