"""多知识库集合、按库导入与角色绑定过滤的回归测试。"""
from __future__ import annotations

from core import config, personas, retrieval
from core import pipeline


def _create_collection(client, cid: str, name: str, persona_ids: list[str] | None = None) -> None:
    r = client.post("/api/kb/collections", json={
        "id": cid,
        "name": name,
        "description": "测试库",
        "persona_ids": persona_ids or [],
        "enabled": True,
    })
    assert r.status_code == 200, r.text


def test_collection_crud_and_persona_scope(client):
    _create_collection(client, "char_lore", "砚的资料", ["researcher"])
    r = client.post("/api/kb", json={
        "id": "KB900",
        "title": "资料编号体系",
        "text": "资料 编号 体系 来源",
        "answer": "来源、日期、原文页码，缺一项标未核实。",
        "tags": ["资料"],
        "collection": "char_lore",
        "source": "manual",
    })
    assert r.status_code == 200, r.text
    assert r.json()["entry"]["collection"] == "char_lore"

    r = client.get("/api/kb?collection=char_lore")
    assert r.status_code == 200, r.text
    items = r.json()["kb"]
    assert [e["id"] for e in items] == ["KB900"]
    assert next(c for c in r.json()["collections"] if c["id"] == "char_lore")["entry_count"] == 1

    # 公共库始终可见；角色专属库只对绑定的预设可见。
    assert "char_lore" in retrieval.active_collections("researcher")
    assert "char_lore" not in retrieval.active_collections("zero")

    # 删除集合不丢条目：迁移到默认库。
    r = client.delete("/api/kb/collections/char_lore?move_to=default")
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 1
    assert retrieval.load_kb()[-1]["collection"] == "default"


def test_import_is_scoped_to_one_collection(client):
    _create_collection(client, "faq2", "第二 FAQ")
    before = len(retrieval.load_kb())

    r = client.post("/api/kb/import", json={
        "text": "## 新退货政策\n拆封后不支持无理由退货。\n\n## 新发票\n电子发票 24 小时内开出。",
        "replace": True,
        "collection": "faq2",
    })
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 2
    # replace 只清空 faq2；默认库的 5 条种子必须还在。
    assert len(retrieval.load_kb()) == before + 2
    assert all((e.get("collection") == "default") for e in retrieval.load_kb()[:before])

    r = client.get("/api/kb?collection=faq2")
    assert r.status_code == 200, r.text
    assert {e["title"] for e in r.json()["kb"]} == {"新退货政策", "新发票"}

    r = client.post(
        "/api/kb/import/document",
        files={"file": ("notes.txt", "角色历史资料\n\n零在城南旧货市场被捡回。", "text/plain")},
        data={"collection": "faq2"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] >= 1
    r = client.get("/api/kb?collection=faq2")
    assert any(e["source"] == "notes.txt" for e in r.json()["kb"])


def test_pipeline_applies_persona_collection_scope(client, monkeypatch):
    _create_collection(client, "char_lore", "砚的资料", ["researcher"])
    r = client.post("/api/kb", json={
        "id": "KB901",
        "title": "资料出处规则",
        "text": "资料 出处 来源 编号",
        "answer": "一手文件优先，转述只能当线索。",
        "collection": "char_lore",
    })
    assert r.status_code == 200, r.text

    cfg = config.get_config()
    cfg["retrieval"] = {"kb_top_k": 2, "min_overlap": 0.0, "embedding": "off"}
    cfg["context"] = {**(cfg.get("context") or {}), "persona": personas.get("researcher").persona,
                      "modules": {"kb": True}}
    monkeypatch.setattr(pipeline, "_self_fix_hint", lambda: "")
    ctx = pipeline.build_context("资料出处规则", [], cfg, "kb-scope-visitor")
    assert ctx["used"]["kb"]["persona_id"] == "researcher"
    assert "char_lore" in (ctx["used"]["kb"]["collections"] or [])
    assert any(e["id"] == "KB901" for _, e in ctx["hits"])

    cfg["context"]["persona"] = personas.get("zero").persona
    ctx0 = pipeline.build_context("资料出处规则", [], cfg, "kb-scope-visitor")
    assert "char_lore" not in (ctx0["used"]["kb"]["collections"] or [])
    assert not any(e["id"] == "KB901" for _, e in ctx0["hits"])
