"""内置浏览器自动化的最小护栏：SSRF 拦截 + 注册/权限边界。"""
import asyncio

from core import browser, tools


def test_browser_tools_registered_and_privileged():
    for name in ("browser_open", "browser_read", "browser_click",
                 "browser_type", "browser_screenshot", "browser_close"):
        assert name in tools.TOOL_META
        assert name in tools._ASYNC_IMPLS
        assert name in tools.PRIVILEGED_TOOLS


def test_browser_blocks_private_url_before_launch():
    r = asyncio.run(browser.browser_open("http://127.0.0.1:8014/healthz"))
    assert r.get("found") is False
    assert "内网" in str(r.get("note") or "")
