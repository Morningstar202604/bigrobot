"""消息的账号维度：可空，能写能读，历史导入可指定。"""
from core import history_ingest, session_store, store


def _msg(sid, mid):
    with store.get_conn() as conn:
        return dict(conn.execute("SELECT * FROM messages WHERE session_id=? AND id=?", (sid, mid)).fetchone())


def test_message_without_account_is_null(client):
    sid = "s-msg-a"
    session_store.create_session(sid, "v1", "sec")
    mid = session_store.add_message(sid, "visitor", "hi")
    assert _msg(sid, mid)["account_id"] is None


def test_message_with_account_roundtrips(client):
    sid = "s-msg-b"
    session_store.create_session(sid, "v1", "sec")
    mid = session_store.add_message(sid, "visitor", "hi", account_id="qq:10001")
    assert _msg(sid, mid)["account_id"] == "qq:10001"


def test_ingest_history_stamps_account(client):
    sid = "s-msg-c"
    session_store.create_session(sid, "v1", "sec")
    history_ingest.ingest_history(sid, [{"external_id": "e1", "content": "从历史来"}], account_id="qq:10001")
    rows = store.get_messages(sid)
    assert rows[0]["account_id"] == "qq:10001"
