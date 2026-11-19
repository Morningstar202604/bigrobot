"""OneBot 历史 --> 本地落库：段数组转文本、重复拉取幂等。"""
from core import history_ingest, store
from tests.conftest import create_web_session


PAYLOAD = {"messages": [
    {"message_id": 11, "sender": {"nickname": "小明"},
     "message": [{"type": "text", "data": {"text": "在吗"}}]},
    {"message_id": 12, "sender": {"nickname": "小红"},
     "message": [{"type": "image", "data": {"file": "x.jpg"}}]},
]}


def test_onebot_history_ingest_is_idempotent(client, monkeypatch):
    sid, _ = create_web_session(client)
    calls = []

    def fake_api(action, params):
        calls.append((action, params))
        return PAYLOAD

    first = history_ingest.ingest_group_history(sid, "410001", fake_api, limit=20)
    second = history_ingest.ingest_group_history(sid, "410001", fake_api, limit=20)
    assert first["added"] == 2
    assert second["added"] == 0
    assert calls[0][0] == "get_group_msg_history"
    assert calls[0][1]["group_id"] == "410001"

    texts = [m["content"] for m in store.get_messages(sid) if m["source"] == "platform"]
    assert "小明: 在吗" in texts
    assert any("[图片]" in t for t in texts)
