"""动作客户端把账号带到网关，避免 A 号看到的消息用 B 号发。"""
import asyncio


def test_call_action_payload_carries_account(monkeypatch):
    from core.actions import client as action_client

    seen = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True, "data": {"message_id": 1}}

    class FakeClient:
        async def post(self, url, json=None, headers=None):
            seen.update(json or {})
            return FakeResp()

    monkeypatch.setattr(action_client, "get_client", lambda timeout: FakeClient())
    result = asyncio.run(action_client.call_action(
        "send_group_msg", {"group_id": 1, "message": "hi"},
        timeout_s=3, account_id="qq:10001"))
    assert result["data"]["message_id"] == 1
    assert seen["account_id"] == "qq:10001"
    assert seen["action"] == "send_group_msg"
