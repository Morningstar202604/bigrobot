"""角色能力边界：默认全继承，显式白名单才收缩；清单与执行层双重生效。"""
from __future__ import annotations

import asyncio

from core import config, persona_caps, personas, pipeline, skills, tools
from core.tool_context import ToolContext


ALL = {"mode": "all", "ids": []}


def test_default_is_inherit_all():
    cfg = config.get_config()
    assert persona_caps.get(cfg, "zero") == {
        "tools": ALL, "skills": ALL, "mcp": ALL, "extensions": ALL,
    }
    assert persona_caps.allowed(cfg, "zero", "tools") is None
    assert persona_caps.tool_allowed(cfg, "zero", "anything") is True


def test_api_caps_roundtrip_filters_tools_and_skills(client):
    r = client.get("/api/persona-caps")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"] == {}
    assert data["options"]["personas"]
    tool_id = next(t["id"] for t in data["options"]["tools"] if t["id"] == "web_search")
    pid = data["options"]["personas"][0]["id"]
    items = {pid: {
        "tools": {"mode": "allow", "ids": [tool_id]},
        "skills": {"mode": "allow", "ids": ["builtin-web-research"]},
        "mcp": ALL,
        "extensions": ALL,
    }}
    r = client.put("/api/persona-caps", json={"items": items})
    assert r.status_code == 200, r.text
    cfg = config.get_config()
    active = set(tools.active_tools(cfg, pid))
    assert tool_id in active
    assert "read_file" not in active
    block = skills.render(cfg, {"builtin-web-research"})
    assert "联网查证" in block and "文件操作" not in block
    denied = asyncio.run(tools.invoke("read_file", {}, ToolContext(persona_id=pid)))
    assert denied["found"] is False
    assert "权限" in denied["note"]
    assert client.delete(f"/api/persona-caps/{pid}").status_code == 200
    assert persona_caps.get(config.get_config(), pid)["tools"]["mode"] == "all"


def test_api_rejects_unknown_allowlist_item(client):
    pid = client.get("/api/persona-caps").json()["options"]["personas"][0]["id"]
    items = {pid: {
        "tools": {"mode": "allow", "ids": ["not_a_real_tool"]},
        "skills": ALL, "mcp": ALL, "extensions": ALL,
    }}
    r = client.put("/api/persona-caps", json={"items": items})
    assert r.status_code == 400
    assert "未知项" in r.text


def test_build_context_filters_by_actual_preset():
    cfg = config.get_config()
    preset = personas.get("minimal")
    cfg["context"]["persona"] = preset.persona
    cfg["persona_caps"] = {"items": {"minimal": {
        "tools": {"mode": "allow", "ids": ["calc"]},
        "skills": ALL, "mcp": ALL, "extensions": ALL,
    }}}
    ctx = pipeline.build_context("1+1", [], cfg, "u")
    assert ctx["persona_id"] == "minimal"
    assert set(ctx["tools"]) == {"calc"}
    assert {t["name"] for t in ctx["tools_schema"]} == {"calc"}


def test_source_caps_filter_dynamic_specs():
    cfg = config.get_config()
    spec = {"name": "demo_echo", "extension": "demo", "args": [], "desc": "x"}
    assert persona_caps.source_allowed(cfg, "zero", spec) is True
    cfg = {"persona_caps": {"items": {"zero": {
        "tools": ALL, "skills": ALL, "mcp": ALL,
        "extensions": {"mode": "allow", "ids": ["other"]},
    }}}}
    assert persona_caps.source_allowed(cfg, "zero", spec) is False
