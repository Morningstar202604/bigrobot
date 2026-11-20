"""扩展包与 MCP 客户端的管理 API。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core import extensions, mcp_client
from core.api.deps import require_admin, require_id

router = APIRouter(prefix="/api", tags=["extensions"])


class InstallUrlIn(BaseModel):
    url: str


class ToggleIn(BaseModel):
    enabled: bool = True


class McpServerIn(BaseModel):
    id: str | None = None
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str = ""
    enabled: bool = True
    allow_untrusted: bool = False
    risk: str = "read"
    timeout_s: int = 20


def _as_http_error(e: Exception) -> HTTPException:
    if isinstance(e, KeyError):
        return HTTPException(404, "对象不存在")
    return HTTPException(400, str(e)[:300])


@router.get("/extensions", dependencies=[Depends(require_admin)])
def list_extensions():
    return {"items": extensions.list_items()}


@router.post("/extensions/install", dependencies=[Depends(require_admin)])
async def install_extension(body: InstallUrlIn):
    try:
        item = await extensions.install_from_url(body.url.strip())
    except Exception as e:  # 下载/校验/解压失败都转成可读 400
        raise _as_http_error(e) from e
    return {"item": item}


@router.post("/extensions/upload", dependencies=[Depends(require_admin)])
async def upload_extension(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "扩展包超过 20MB")
    try:
        item = await asyncio.to_thread(extensions.install_zip, data, f"upload:{file.filename or ''}")
    except Exception as e:
        raise _as_http_error(e) from e
    return {"item": item}


@router.post("/extensions/{ext_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_extension(ext_id: str, body: ToggleIn):
    ext_id = require_id(ext_id, "ext_id").lower()
    try:
        return {"item": extensions.set_enabled(ext_id, body.enabled)}
    except Exception as e:
        raise _as_http_error(e) from e


@router.post("/extensions/{ext_id}/rollback", dependencies=[Depends(require_admin)])
def rollback_extension(ext_id: str):
    ext_id = require_id(ext_id, "ext_id").lower()
    try:
        return {"item": extensions.rollback(ext_id)}
    except Exception as e:
        raise _as_http_error(e) from e


@router.delete("/extensions/{ext_id}", dependencies=[Depends(require_admin)])
def delete_extension(ext_id: str):
    ext_id = require_id(ext_id, "ext_id").lower()
    try:
        extensions.uninstall(ext_id)
    except Exception as e:
        raise _as_http_error(e) from e
    return {"ok": True}


# ---------------- MCP ----------------

@router.get("/mcp/servers", dependencies=[Depends(require_admin)])
def list_mcp_servers():
    return {"items": mcp_client.list_servers(), "available": mcp_client.available()}


@router.post("/mcp/servers", dependencies=[Depends(require_admin)])
def create_mcp_server(body: McpServerIn):
    try:
        return {"server": mcp_client.upsert_server(body.model_dump())}
    except Exception as e:
        raise _as_http_error(e) from e


@router.put("/mcp/servers/{server_id}", dependencies=[Depends(require_admin)])
def update_mcp_server(server_id: str, body: McpServerIn):
    server_id = require_id(server_id, "server_id").lower()
    try:
        return {"server": mcp_client.upsert_server({**body.model_dump(), "id": server_id})}
    except Exception as e:
        raise _as_http_error(e) from e


@router.post("/mcp/servers/{server_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_mcp_server(server_id: str, body: ToggleIn):
    server_id = require_id(server_id, "server_id").lower()
    try:
        return {"server": mcp_client.set_enabled(server_id, body.enabled)}
    except Exception as e:
        raise _as_http_error(e) from e


@router.post("/mcp/servers/{server_id}/test", dependencies=[Depends(require_admin)])
async def test_mcp_server(server_id: str):
    server_id = require_id(server_id, "server_id").lower()
    try:
        return await mcp_client.test_server(server_id)
    except Exception as e:
        raise _as_http_error(e) from e


@router.delete("/mcp/servers/{server_id}", dependencies=[Depends(require_admin)])
def delete_mcp_server(server_id: str):
    server_id = require_id(server_id, "server_id").lower()
    try:
        mcp_client.delete_server(server_id)
    except Exception as e:
        raise _as_http_error(e) from e
    return {"ok": True}
