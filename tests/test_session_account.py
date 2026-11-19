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
