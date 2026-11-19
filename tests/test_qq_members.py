"""群成员整表：没有协议端 409，有数据要规范化字段。"""


def test_members_requires_protocol(client, monkeypatch):
    from gateway import bridge

    async def none(*a, **kw):
        return None

    monkeypatch.setattr(bridge, "call_onebot", none)
    assert client.get("/api/channel/qq/groups/410001/members").status_code == 409


def test_members_normalized(client, monkeypatch):
    from gateway import bridge

    async def fake(action, params):
        assert action == "get_group_member_list" and params["group_id"] == "410001"
        return [
            {"user_id": 10001, "nickname": "小明", "role": "owner"},
            {"user_id": 10002, "card": "客服小号", "role": "admin"},
            "bad-row",
        ]

    monkeypatch.setattr(bridge, "call_onebot", fake)
    r = client.get("/api/channel/qq/groups/410001/members")
    body = r.json()
    assert r.status_code == 200 and body["count"] == 2
    assert body["members"][0]["role"] == "owner"
    assert body["members"][1]["nickname"] == "客服小号"   # card 优先


def test_group_files_normalized(client, monkeypatch):
    from gateway import bridge

    async def fake(action, params):
        assert action == "get_group_root_files"
        return {"files": [
            {"file_id": "f1", "file_name": "周报.docx", "file_size": 10240, "upload_time": 1700000000},
            {"name": "照片.zip", "size": 2048},
            "bad",
        ]}

    monkeypatch.setattr(bridge, "call_onebot", fake)
    r = client.get("/api/channel/qq/groups/410001/files")
    body = r.json()
    assert r.status_code == 200 and body["count"] == 2
    assert body["files"][0]["name"] == "周报.docx" and body["files"][0]["size"] == 10240


def test_group_files_without_protocol(client, monkeypatch):
    from gateway import bridge

    async def none(*a, **kw):
        return None

    monkeypatch.setattr(bridge, "call_onebot", none)
    assert client.get("/api/channel/qq/groups/410001/files").status_code == 409
