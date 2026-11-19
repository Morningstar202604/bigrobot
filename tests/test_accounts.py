"""账号维度：同一渠道下 platform_uid 唯一，重复登记只更新展示名。"""
from core import store


def test_first_register_creates_row():
    acc = store.upsert_account("qq", "10001", "小号")
    assert acc["id"] == "qq:10001"
    assert len(store.list_accounts()) == 1


def test_same_uid_updates_not_duplicates():
    store.upsert_account("qq", "10001", "小号")
    store.upsert_account("qq", "10001", "改名后")
    rows = store.list_accounts()
    assert len(rows) == 1 and rows[0]["display_name"] == "改名后"


def test_different_channel_is_separate_account():
    store.upsert_account("qq", "10001", "A")
    store.upsert_account("webchat", "10001", "B")
    assert len(store.list_accounts()) == 2


def test_api_rejects_empty_fields(client):
    r = client.post("/api/accounts", json={"channel": "", "platform_uid": "1"})
    assert r.status_code == 400
