"""历史落库：重复拉取不翻倍；缺 external_id 的行跳过并计数。"""
from core import history_ingest, store
from tests.conftest import create_web_session


def test_second_pull_is_idempotent(client):
    sid, _ = create_web_session(client)
    rows = [
        {"external_id": "g1", "sender": "小明", "content": "在吗"},
        {"external_id": "g2", "sender": "小红", "content": "明天开会"},
    ]
    first = history_ingest.ingest_history(sid, rows)
    second = history_ingest.ingest_history(sid, rows)
    assert first == {"added": 2, "skipped": 0, "total": 2}
    assert second["added"] == 0 and second["skipped"] == 2

    msgs = [m for m in store.get_messages(sid) if m["source"] == "platform"]
    assert len(msgs) == 2
    assert msgs[0]["content"].startswith("小明: ")


def test_rows_without_external_id_are_skipped(client):
    sid, _ = create_web_session(client)
    r = history_ingest.ingest_history(sid, [{"content": "无 id"}])
    assert r["added"] == 0 and r["skipped"] == 1
