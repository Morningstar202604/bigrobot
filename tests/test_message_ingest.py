"""历史落库要幂等：同一批消息拉两次不能翻倍。"""
from tests.conftest import create_web_session


def test_external_id_dedupes(client):
    sid, _ = create_web_session(client)
    from core import store

    first = store.add_message(sid, "visitor", "你好", external_id="m-1", source="platform")
    second = store.add_message(sid, "visitor", "你好", external_id="m-1", source="platform")
    assert first == second
    rows = [m for m in store.get_messages(sid) if m.get("external_id") == "m-1"]
    assert len(rows) == 1


def test_no_external_id_still_appends(client):
    sid, _ = create_web_session(client)
    from core import store

    a = store.add_message(sid, "agent", "一")
    b = store.add_message(sid, "agent", "一")
    assert a != b
