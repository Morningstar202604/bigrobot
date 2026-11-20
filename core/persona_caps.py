"""角色能力边界：按预设角色收缩工具/技能/MCP/扩展的可见范围。

设计约束：
- **默认继承全部**。没有配置的角色行为与现状完全一致，升级不会悄悄少能力。
- **只收缩、不扩张**：白名单只能拿全局已启用的子集，不能绕过工具注册表、
  扩展安装、MCP 停用这些更上层的开关。
- **四类能力分治**：工具是模型能调的函数；技能是提示词里的用法说明；
  MCP 服务器与声明式扩展是工具来源。它们可以分别限制，不搞一个大杂烩开关。

config.persona_caps.items 结构：
{
  "<persona_id>": {
    "tools":      {"mode": "all" | "allow", "ids": ["web_search", ...]},
    "skills":     {"mode": "all" | "allow", "ids": ["builtin-web-research", ...]},
    "mcp":        {"mode": "all" | "allow", "ids": ["echo", ...]},
    "extensions": {"mode": "all" | "allow", "ids": ["weather-http", ...]}
  }
}

兼容旧写法：某一类直接写成数组时，按 allow 白名单处理。
"""
from __future__ import annotations

import re

KINDS = ("tools", "skills", "mcp", "extensions")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")


def _normalize_group(raw) -> dict:
    if raw is None:
        return {"mode": "all", "ids": []}
    if isinstance(raw, list):
        raw = {"mode": "allow", "ids": raw}
    if not isinstance(raw, dict):
        return {"mode": "all", "ids": []}
    mode = "allow" if str(raw.get("mode") or "").strip().lower() == "allow" else "all"
    ids: list[str] = []
    for item in raw.get("ids") or []:
        sid = str(item or "").strip()
        if sid and sid not in ids:
            ids.append(sid[:80])
    return {"mode": mode, "ids": ids[:200]}


def normalize_items(raw) -> dict:
    """清洗整张角色能力表；非法角色 id 丢弃，四类分组补默认。"""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for pid, caps in raw.items():
        key = str(pid or "").strip()
        if not _ID_RE.match(key):
            continue
        groups = caps if isinstance(caps, dict) else {}
        out[key] = {kind: _normalize_group(groups.get(kind)) for kind in KINDS}
    return out


def items(cfg: dict) -> dict:
    return normalize_items((cfg.get("persona_caps") or {}).get("items"))


def get(cfg: dict, persona_id: str) -> dict:
    return items(cfg).get((persona_id or "").strip()) or {
        kind: {"mode": "all", "ids": []} for kind in KINDS
    }


def allowed(cfg: dict, persona_id: str, kind: str) -> set[str] | None:
    """返回 None 表示不限制；返回集合表示只允许这些 id。"""
    if kind not in KINDS:
        return None
    pid = (persona_id or "").strip()
    if not pid:
        return None
    group = get(cfg, pid).get(kind) or {}
    if group.get("mode") != "allow":
        return None
    return set(group.get("ids") or [])


def tool_allowed(cfg: dict, persona_id: str, name: str) -> bool:
    allowed_tools = allowed(cfg, persona_id, "tools")
    return allowed_tools is None or name in allowed_tools


def skill_allowed(cfg: dict, persona_id: str, skill_id: str) -> bool:
    allowed_skills = allowed(cfg, persona_id, "skills")
    return allowed_skills is None or skill_id in allowed_skills


def mcp_allowed(cfg: dict, persona_id: str, server_id: str) -> bool:
    allowed_mcp = allowed(cfg, persona_id, "mcp")
    return allowed_mcp is None or server_id in allowed_mcp


def extension_allowed(cfg: dict, persona_id: str, ext_id: str) -> bool:
    allowed_ext = allowed(cfg, persona_id, "extensions")
    return allowed_ext is None or ext_id in allowed_ext


def source_allowed(cfg: dict, persona_id: str, spec: dict) -> bool:
    """动态工具 spec 的来源过滤：扩展/MCP 各自的白名单都要通过。"""
    ext = str(spec.get("extension") or "").strip()
    if ext and not extension_allowed(cfg, persona_id, ext):
        return False
    server = str(spec.get("server") or "").strip()
    if server and not mcp_allowed(cfg, persona_id, server):
        return False
    return True
