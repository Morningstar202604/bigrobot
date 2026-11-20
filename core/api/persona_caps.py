"""角色能力边界 API：查看预设角色可用的工具/技能/MCP/扩展，并按角色收缩。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import config, extensions, mcp_client, persona_caps, skills, store, tools
from core.api.deps import require_admin, require_id

router = APIRouter(prefix="/api/persona-caps", tags=["persona-caps"])


class CapsIn(BaseModel):
    items: dict


def _options(cfg: dict) -> dict:
    personas = []
    try:
        from core import personas as personas_mod

        personas = personas_mod.list_public(with_persona=False)["presets"]
    except Exception:
        pass
    tool_items = [{"id": t["name"], "name": t["name"], "desc": t.get("desc") or ""}
                  for t in tools.tool_schema_block(cfg)]
    skill_items = []
    try:
        for s in skills.normalize_items((cfg.get("skills") or {}).get("items")):
            skill_items.append({"id": s["id"], "name": s["name"], "desc": s.get("description") or "",
                                "builtin": bool(s.get("builtin"))})
        for s in extensions.skill_items():
            skill_items.append({"id": s["id"], "name": s["name"], "desc": s.get("description") or "",
                                "builtin": False})
    except Exception:
        pass
    return {
        "personas": [{"id": p["id"], "name": p["name"], "category": p["category"]} for p in personas],
        "tools": tool_items,
        "skills": skill_items,
        "mcp": [{"id": s["id"], "name": s.get("name") or s["id"], "enabled": bool(s.get("enabled", True))}
                for s in mcp_client.list_servers()],
        "extensions": [{"id": i["id"], "name": i.get("name") or i["id"], "enabled": bool(i.get("enabled", True)),
                        "error": i.get("error") or ""} for i in extensions.list_items()],
    }


@router.get("", dependencies=[Depends(require_admin)])
def get_caps():
    cfg = config.get_config()
    return {"items": persona_caps.items(cfg), "options": _options(cfg)}


@router.put("", dependencies=[Depends(require_admin)])
def put_caps(body: CapsIn):
    cfg = config.get_config()
    options = _options(cfg)
    known = {
        "tools": {i["id"] for i in options["tools"]},
        "skills": {i["id"] for i in options["skills"]},
        "mcp": {i["id"] for i in options["mcp"]},
        "extensions": {i["id"] for i in options["extensions"]},
    }
    items = persona_caps.normalize_items(body.items)
    persona_ids = {p["id"] for p in options["personas"]}
    for pid, groups in items.items():
        if persona_ids and pid not in persona_ids:
            raise HTTPException(400, f"未知角色：{pid}")
        for kind, group in groups.items():
            if group.get("mode") == "allow":
                unknown = [x for x in group.get("ids") or [] if x not in known[kind]]
                if unknown:
                    raise HTTPException(400, f"{pid}.{kind} 含未知项：{', '.join(unknown[:5])}")
    config.update_config({"persona_caps": {"items": items}})
    try:
        store.append_audit("admin", "config.updated", {"group": "persona_caps", "personas": list(items)})
    except Exception:
        pass
    return {"items": items}


@router.delete("/{persona_id}", dependencies=[Depends(require_admin)])
def delete_caps(persona_id: str):
    pid = require_id(persona_id, "persona_id")
    cfg = config.get_config()
    items = persona_caps.items(cfg)
    if pid not in items:
        raise HTTPException(404, "这个角色没有单独配置能力边界")
    items.pop(pid, None)
    config.update_config({"persona_caps": {"items": items}})
    return {"items": items}
