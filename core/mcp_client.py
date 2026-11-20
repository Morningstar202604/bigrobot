"""MCP 客户端：把外部 MCP 服务器的工具接进 Agent。

与 core/mcp_server.py 的分工：
- mcp_server.py 把 BigRobot 的工具暴露给别的 Agent（我们是 server）；
- 本模块让 BigRobot 去消费别人的 MCP 工具（我们是 client）。

实现取舍：
- 先支持 stdio（覆盖 npx / uvx / python 脚本等绝大多数本地 MCP 服务器）；
- 每次调用起一个子进程，完成 initialize / call_tool 后退出。实现简单、进程隔离好，
  代价是冷启动慢一些；v1 先保证「能接、能调、能审计」，后续再加长连接池。
- 工具列表在「测试/刷新」时拉取并缓存到配置里，active_tools() 保持同步，
  不阻塞每轮对话构建。
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone

from core import config_store
from core.tool_result import miss_result, ok_result

try:  # mcp 是可选依赖；没装不影响主服务
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_IMPORT_ERROR = ""
except Exception as e:  # pragma: no cover - 只在上游缺依赖时触发
    ClientSession = None  # type: ignore[misc,assignment]
    StdioServerParameters = None  # type: ignore[misc,assignment]
    stdio_client = None  # type: ignore[misc,assignment]
    _MCP_IMPORT_ERROR = str(e)

MAX_TOOLS = 80
MAX_RESULT = 6000
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_TOOL_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def available() -> bool:
    return ClientSession is not None


def _slug(raw: str, fallback: str = "server") -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", (raw or "").lower()).strip("-_")
    return s[:40] or fallback


def _servers() -> list[dict]:
    cfg = config_store.get_config().get("mcp") or {}
    items = cfg.get("servers") or []
    return [s for s in items if isinstance(s, dict)]


def _save_servers(servers: list[dict]) -> None:
    config_store.set_config({"mcp": {"servers": servers}})


def _mask_server(server: dict) -> dict:
    out = {k: v for k, v in server.items() if k not in {"env"}}
    env = server.get("env") or {}
    out["env_keys"] = sorted(env.keys()) if isinstance(env, dict) else []
    out["tools_count"] = len(server.get("tools") or [])
    return out


def list_servers(mask: bool = True) -> list[dict]:
    servers = _servers()
    return [_mask_server(s) for s in servers] if mask else servers


def get_server(server_id: str, mask: bool = False) -> dict | None:
    for s in _servers():
        if s.get("id") == server_id:
            return _mask_server(s) if mask else s
    return None


def _validate_server(body: dict, existing: dict | None = None) -> dict:
    name = str(body.get("name") or "").strip()[:80]
    if not name:
        raise ValueError("MCP 服务器名称不能为空")
    server_id = str(body.get("id") or (existing or {}).get("id") or _slug(name)).strip().lower()
    if not _ID_RE.match(server_id):
        raise ValueError("MCP 服务器 id 只能是小写字母、数字、下划线或短横线（2–41 字符）")
    command = str(body.get("command") or (existing or {}).get("command") or "").strip()
    if not command:
        raise ValueError("启动命令不能为空（例如 npx / uvx / python3）")
    args = body.get("args")
    if args is None:
        args = (existing or {}).get("args") or []
    if isinstance(args, str):
        args = args.split()
    if not isinstance(args, list) or not all(isinstance(a, (str, int, float)) for a in args):
        raise ValueError("args 必须是字符串数组")
    args = [str(a) for a in args][:40]
    env = body.get("env")
    if env is None:
        env = (existing or {}).get("env") or {}
    if not isinstance(env, dict):
        raise ValueError("env 必须是对象")
    env = {str(k): str(v) for k, v in env.items() if str(k).strip()}
    enabled = bool(body.get("enabled", (existing or {}).get("enabled", True)))
    allow_untrusted = bool(body.get("allow_untrusted", (existing or {}).get("allow_untrusted", False)))
    risk = str(body.get("risk", (existing or {}).get("risk", "read"))).lower()
    if risk not in {"read", "write"}:
        risk = "read"
    try:
        timeout_s = max(5, min(120, int(body.get("timeout_s", (existing or {}).get("timeout_s", 20)))))
    except (TypeError, ValueError):
        timeout_s = 20
    cwd = str(body.get("cwd", (existing or {}).get("cwd", "")) or "").strip()
    return {
        "id": server_id,
        "name": name,
        "command": command,
        "args": args,
        "env": env,
        "cwd": cwd,
        "enabled": enabled,
        "allow_untrusted": allow_untrusted,
        "risk": risk,
        "timeout_s": timeout_s,
        "tools": (existing or {}).get("tools") or [],
        "last_error": "",
        "last_tested": (existing or {}).get("last_tested", ""),
        "created_at": (existing or {}).get("created_at") or _now(),
        "updated_at": _now(),
    }


def upsert_server(body: dict) -> dict:
    servers = _servers()
    server_id = str(body.get("id") or "").strip().lower()
    existing = next((s for s in servers if s.get("id") == server_id), None) if server_id else None
    item = _validate_server(body, existing)
    # 命令/参数变了，旧工具缓存作废，必须重新测试
    if existing and (
        existing.get("command") != item["command"]
        or existing.get("args") != item["args"]
        or existing.get("env") != item["env"]
        or existing.get("cwd") != item["cwd"]
    ):
        item["tools"] = []
    servers = [s for s in servers if s.get("id") != item["id"]]
    servers.append(item)
    _save_servers(servers)
    return _mask_server(item)


def delete_server(server_id: str) -> None:
    servers = _servers()
    if not any(s.get("id") == server_id for s in servers):
        raise KeyError(server_id)
    _save_servers([s for s in servers if s.get("id") != server_id])


def set_enabled(server_id: str, enabled: bool) -> dict:
    servers = _servers()
    for s in servers:
        if s.get("id") == server_id:
            s["enabled"] = bool(enabled)
            s["updated_at"] = _now()
            _save_servers(servers)
            return _mask_server(s)
    raise KeyError(server_id)


def _resolve_env(env: dict) -> dict:
    out = dict(os.environ)
    for k, v in (env or {}).items():
        val = str(v)
        if val.startswith("env:"):
            out[k] = os.environ.get(val[4:], "")
        else:
            out[k] = val
    return out


def _params(server: dict) -> "StdioServerParameters":
    if StdioServerParameters is None:
        raise RuntimeError(f"MCP 依赖未安装：{_MCP_IMPORT_ERROR}")
    return StdioServerParameters(
        command=server["command"],
        args=list(server.get("args") or []),
        env=_resolve_env(server.get("env") or {}),
        cwd=server.get("cwd") or None,
    )


def _normalize_tools(result) -> list[dict]:
    out: list[dict] = []
    for tool in getattr(result, "tools", []) or []:
        name = str(getattr(tool, "name", "") or "")
        if not name:
            continue
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
        if not isinstance(schema, dict):
            schema = {}
        props_raw = schema.get("properties")
        props: dict = props_raw if isinstance(props_raw, dict) else {}
        required_raw = schema.get("required")
        required = [r for r in required_raw if isinstance(r, str)] if isinstance(required_raw, list) else []
        out.append({
            "name": name,
            "description": str(getattr(tool, "description", "") or "")[:300],
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        })
        if len(out) >= MAX_TOOLS:
            break
    return out


async def _probe(server: dict) -> tuple[list[dict], str]:
    if not available():
        return [], f"MCP 依赖未安装：{_MCP_IMPORT_ERROR}"
    params = _params(server)
    timeout = float(server.get("timeout_s", 20))
    try:
        async def run():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return _normalize_tools(result)
        tools = await asyncio.wait_for(run(), timeout=timeout)
        return tools, ""
    except asyncio.TimeoutError:
        return [], "连接超时"
    except Exception as e:  # MCP 子进程可能各种失败，统一落 last_error
        return [], f"{type(e).__name__}: {str(e)[:200]}"


async def test_server(server_id: str) -> dict:
    servers = _servers()
    target = next((s for s in servers if s.get("id") == server_id), None)
    if target is None:
        raise KeyError(server_id)
    tools, error = await _probe(target)
    target["tools"] = tools
    target["last_error"] = error
    target["last_tested"] = _now()
    target["updated_at"] = _now()
    _save_servers(servers)
    return {"ok": not error, "error": error, "tools": tools, "server": _mask_server(target)}


def _tool_name(server_id: str, tool_name: str) -> str:
    clean = _TOOL_RE.sub("_", tool_name).strip("_")[:30] or "tool"
    return f"mcp_{server_id}_{clean}"[:60]


def _tool_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for server in _servers():
        if not server.get("enabled") or not server.get("tools"):
            continue
        for tool in server.get("tools") or []:
            name = _tool_name(server["id"], str(tool.get("name") or ""))
            out.setdefault(name, {"server": server, "tool": tool})
    return out


def tool_specs() -> list[dict]:
    out: list[dict] = []
    for name, entry in _tool_map().items():
        tool = entry["tool"]
        schema = tool.get("input_schema") or {}
        props_raw = schema.get("properties")
        props: dict = props_raw if isinstance(props_raw, dict) else {}
        out.append({
            "name": name,
            "args": list(props.keys()),
            "desc": f"[MCP:{entry['server']['name']}] {tool.get('description') or tool.get('name')}",
            "risk": entry["server"].get("risk", "read"),
            "server": entry["server"]["id"],
            "parameters": {
                "type": "object",
                "properties": props,
                "required": schema.get("required") or [],
            },
        })
    return out


def tool_policy(name: str) -> dict | None:
    entry = _tool_map().get(name)
    if not entry:
        return None
    server = entry["server"]
    return {
        "risk": server.get("risk", "read"),
        "allow_untrusted": bool(server.get("allow_untrusted")) and server.get("risk") != "write",
        "server": server["id"],
    }


def _content_text(result) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
        else:
            typ = getattr(item, "type", None) or type(item).__name__
            parts.append(f"[{typ}]")
    return "\n".join(parts).strip()


async def call_tool(name: str, args: dict) -> dict:
    entry = _tool_map().get(name)
    if not entry:
        return miss_result(name, "MCP 工具不存在，或服务器已停用。")
    server = entry["server"]
    tool = entry["tool"]
    if not available():
        return miss_result(name, f"MCP 依赖未安装：{_MCP_IMPORT_ERROR}")
    params = _params(server)
    timeout = float(server.get("timeout_s", 20))
    try:
        async def run():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(str(tool.get("name")), dict(args or {}))
                    is_error = bool(getattr(result, "isError", False))
                    return _content_text(result), is_error
        text, is_error = await asyncio.wait_for(run(), timeout=timeout)
    except asyncio.TimeoutError:
        return miss_result(name, "MCP 调用超时。", server=server["id"])
    except Exception as e:
        return miss_result(name, f"MCP 调用失败：{type(e).__name__}: {str(e)[:160]}",
                           server=server["id"])
    if is_error:
        return miss_result(name, text[:MAX_RESULT] or "MCP 工具返回错误。", server=server["id"])
    if not text:
        return miss_result(name, "MCP 工具没有返回文本内容。", server=server["id"])
    return ok_result(name, text[:MAX_RESULT], server=server["id"],
                     truncated=len(text) > MAX_RESULT)


def active_tools() -> dict:
    out: dict = {}
    for name in _tool_map():
        async def runner(_name=name, **kwargs):
            return await call_tool(_name, kwargs)
        out[name] = runner
    return out
