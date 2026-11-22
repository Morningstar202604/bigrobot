"""浏览器自动化工具注册：Playwright 驱动本机 Chromium。

工具本身是无状态入口，页面会话在 core/browser.py 里进程级共享。
全部归入管理员工具（tools.py 的 PRIVILEGED_TOOLS），避免网页访客驱动浏览器。
"""
from __future__ import annotations

from core import browser

ASYNC_TOOLS = {
    "browser_open": browser.browser_open,
    "browser_read": browser.browser_read,
    "browser_click": browser.browser_click,
    "browser_type": browser.browser_type,
    "browser_screenshot": browser.browser_screenshot,
    "browser_close": browser.browser_close,
}

TOOL_META_EXTRA = {
    "browser_open": {
        "name": "打开网页", "desc": "内置 Chromium 打开一个 http/https 页面，保留会话",
        "args": {"url": "string", "wait_until": "string", "timeout": "string"},
    },
    "browser_read": {
        "name": "读取网页", "desc": "读取当前浏览器页面的正文或指定 CSS 选择器文字",
        "args": {"selector": "string", "max_chars": "string"},
    },
    "browser_click": {
        "name": "点击网页元素", "desc": "按 CSS 选择器或可见文字点击当前页面",
        "args": {"selector": "string", "text": "string", "timeout": "string"},
    },
    "browser_type": {
        "name": "网页输入", "desc": "向当前页面输入框填字，可选回车提交",
        "args": {"selector": "string", "text": "string", "enter": "string"},
    },
    "browser_screenshot": {
        "name": "网页截图", "desc": "截当前页面，返回本地路径和可预览图片",
        "args": {"full_page": "string"},
    },
    "browser_close": {
        "name": "关闭浏览器", "desc": "关闭内置 Chromium 会话，释放内存",
        "args": {},
    },
}
