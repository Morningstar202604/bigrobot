"""适配器注册表：能力声明是控制台渲染依据，不能为空。"""
from core import adapters_registry


def test_catalog_has_webchat_and_qq():
    keys = [a["key"] for a in adapters_registry.catalog()]
    assert keys == ["webchat", "qq"]


def test_qq_declares_group_capabilities():
    caps = adapters_registry.capabilities_of("qq")
    assert "group.member_list" in caps and "group.files" in caps


def test_unknown_adapter_has_no_caps():
    assert adapters_registry.supports("telegram", "group.files") is False


def test_endpoint_returns_static_catalog(client):
    body = client.get("/api/channels/adapters").json()
    assert [a["key"] for a in body["adapters"]] == ["webchat", "qq"]
    qq = next(a for a in body["adapters"] if a["key"] == "qq")
    assert qq["status"] == "offline"          # 没登录协议端不假装在线
