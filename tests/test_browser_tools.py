"""内置浏览器自动化的最小护栏：SSRF、会话隔离键、注册/权限边界。"""
import asyncio

from core import browser, tools
from core.tool_context import ToolContext


def test_browser_tools_registered_and_privileged():
    for name in ("browser_open", "browser_read", "browser_click",
                 "browser_type", "browser_screenshot", "browser_close"):
        assert name in tools.TOOL_META
        assert name in tools._ASYNC_IMPLS
        assert name in tools.PRIVILEGED_TOOLS


def test_browser_session_keys_are_isolated():
    a = browser.session_key(ToolContext(session_id="sess-a"))
    b = browser.session_key(ToolContext(session_id="sess-b"))
    assert a == "session:sess-a"
    assert b == "session:sess-b"
    assert a != b
    assert browser.session_key(ToolContext(visitor_id="v-1")) == "visitor:v-1"
    assert browser.session_key(None) == "default"


def test_browser_blocks_private_url_before_launch():
    r = asyncio.run(browser.browser_open("http://127.0.0.1:8014/healthz"))
    assert r.get("found") is False
    assert "内网" in str(r.get("note") or "")


def test_read_without_open_does_not_launch_browser():
    r = asyncio.run(browser.browser_read(ctx=ToolContext(session_id="never-opened")))
    assert r.get("found") is False
    assert "还没有打开网页" in str(r.get("note") or "")
