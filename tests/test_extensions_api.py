"""扩展包安装/执行与 MCP 客户端接入的端到端测试。"""
from __future__ import annotations

import asyncio
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import config, extensions, mcp_client, tools as tools_mod, url_guard


def _manifest(base_url: str, version: str = "0.0.1") -> dict:
    return {
        "id": "demo-http",
        "name": "Demo HTTP",
        "version": version,
        "description": "测试用声明式扩展",
        "kind": "http",
        "base_url": base_url,
        "allow_private": True,
        "allow_untrusted": True,
        "tools": [{
            "name": "demo_echo",
            "description": "回显文本",
            "method": "GET",
            "path": "/echo",
            "risk": "read",
            "params": {"text": {"type": "string", "required": True, "in": "query"}},
        }],
        "skills": [{"name": "Demo 技能", "description": "测试技能", "guide": "先 echo 再回答。"}],
    }


def _zip(manifest: dict, guide: str = "# guide") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        z.writestr("skills/guide.md", guide)
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server 的固定接口
        if self.path.startswith("/echo"):
            body = json.dumps({"ok": True, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args):
        pass


def _server() -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def test_extension_install_execute_toggle_delete(client):
    srv, base = _server()
    try:
        data = _zip(_manifest(base))
        r = client.post("/api/extensions/upload", files={"file": ("demo.zip", data, "application/zip")})
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item["id"] == "demo-http"
        assert item["tools"][0]["name"] == "demo_echo"
        assert item["skills"][0]["name"] == "Demo 技能"
        assert "Demo 技能" in extensions.render_skills()

        # 工具进入 Agent 的可用清单，并且真的能执行
        cfg = config.get_config()
        assert "demo_echo" in tools_mod.active_tools(cfg)
        assert any(t["name"] == "demo_echo" for t in tools_mod.tool_schema_block(cfg))
        result = asyncio.run(tools_mod.invoke("demo_echo", {"text": "hi"}))
        assert result["found"] is True
        assert "hi" in result["note"]
        # 管线实际走的是 invoke_with(registry)；这里也锁住动态工具的签名适配。
        result = asyncio.run(tools_mod.invoke_with(tools_mod.active_tools(cfg), "demo_echo", {"text": "again"}))
        assert result["found"] is True
        assert "again" in result["note"]

        # 关闭后立即从工具清单消失
        r = client.post("/api/extensions/demo-http/toggle", json={"enabled": False})
        assert r.status_code == 200, r.text
        cfg = config.get_config()
        assert "demo_echo" not in tools_mod.active_tools(cfg)

        # 删除
        r = client.delete("/api/extensions/demo-http")
        assert r.status_code == 200, r.text
        assert client.get("/api/extensions").json()["items"] == []
    finally:
        srv.shutdown()


def test_extension_install_from_url(client, monkeypatch):
    """公网直链与上传走同一套落盘/校验；本地回环仅测试时显式放行。"""
    data = _zip(_manifest("http://example.com"))

    class ZipHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/ext.zip":
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *_args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), ZipHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(url_guard, "check_url", lambda url: url)
        url = f"http://127.0.0.1:{srv.server_port}/ext.zip"
        r = client.post("/api/extensions/install", json={"url": url})
        assert r.status_code == 200, r.text
        assert r.json()["item"]["id"] == "demo-http"
        assert extensions.get_item("demo-http") is not None
    finally:
        srv.shutdown()


def test_extension_rollback_keeps_previous_version(client):
    srv, base = _server()
    try:
        v1 = _zip(_manifest(base, "0.0.1"))
        v2 = _zip(_manifest(base, "0.0.2"))
        assert client.post("/api/extensions/upload", files={"file": ("v1.zip", v1, "application/zip")}).status_code == 200
        assert client.post("/api/extensions/upload", files={"file": ("v2.zip", v2, "application/zip")}).status_code == 200
        assert extensions.get_item("demo-http")["version"] == "0.0.2"
        r = client.post("/api/extensions/demo-http/rollback")
        assert r.status_code == 200, r.text
        assert r.json()["item"]["version"] == "0.0.1"
    finally:
        srv.shutdown()


def test_extension_manifest_rejects_python_and_traversal(client):
    srv, base = _server()
    try:
        bad = _manifest(base)
        bad["kind"] = "python"
        r = client.post("/api/extensions/upload", files={"file": ("bad.zip", _zip(bad), "application/zip")})
        assert r.status_code == 400
        assert "HTTP 扩展" in r.json()["detail"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../escape.txt", "x")
            z.writestr("manifest.json", json.dumps(_manifest(base)))
        r = client.post("/api/extensions/upload", files={"file": ("bad.zip", buf.getvalue(), "application/zip")})
        assert r.status_code == 400
    finally:
        srv.shutdown()


def test_mcp_server_lifecycle_and_call(client):
    if not mcp_client.available():
        return
    fixture = Path(__file__).resolve().parent / "fixtures" / "mcp_echo.py"
    r = client.post("/api/mcp/servers", json={
        "id": "echo",
        "name": "Echo MCP",
        "command": "python3",
        "args": [str(fixture)],
        "env": {},
        "risk": "read",
        "allow_untrusted": True,
        "timeout_s": 30,
    })
    assert r.status_code == 200, r.text
    assert r.json()["server"]["tools_count"] == 0

    r = client.post("/api/mcp/servers/echo/test")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True, data
    assert data["tools"][0]["name"] == "echo"

    cfg = config.get_config()
    assert "mcp_echo_echo" in tools_mod.active_tools(cfg)
    assert any(t["name"] == "mcp_echo_echo" for t in tools_mod.tool_schema_block(cfg))
    result = asyncio.run(tools_mod.invoke("mcp_echo_echo", {"text": "hi"}))
    assert result["found"] is True
    assert "echo:hi" in result["note"]

    r = client.post("/api/mcp/servers/echo/toggle", json={"enabled": False})
    assert r.status_code == 200, r.text
    assert "mcp_echo_echo" not in tools_mod.active_tools(config.get_config())

    r = client.delete("/api/mcp/servers/echo")
    assert r.status_code == 200, r.text
