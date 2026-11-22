"""内置浏览器自动化：Playwright 驱动本机 Chromium，按会话隔离页面上下文。

设计边界：
- 每个聊天会话一个独立 BrowserContext（Cookie / localStorage 不串），最多保留 4 个；
- 只走 http/https，导航前后都过 url_guard；跳到内网/元数据地址立即中断；
- 不执行任意 JS，不读本机文件，不下载文件；
- 浏览器工具在 tools.py 里归入管理员工具，网页访客不能直接驱动。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Any

from core import paths, url_guard

log = logging.getLogger("cs.browser")

MAX_TEXT = 6000
DEFAULT_TIMEOUT_MS = 20_000
MAX_SESSIONS = 4

_pw = None
_browser = None
_loop = None
_start_lock: asyncio.Lock | None = None
_entries: dict[str, dict] = {}
_locks: dict[str, asyncio.Lock] = {}


class BrowserError(RuntimeError):
    pass


def _chromium_path() -> str | None:
    raw = (os.environ.get("BIGROBOT_CHROMIUM") or "").strip()
    if raw:
        return raw
    for candidate in ("/usr/local/bin/chromium", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if Path(candidate).is_file():
            return candidate
    return None


def session_key(ctx=None, sid: str = "") -> str:
    """浏览器隔离键：网页会话按 session_id，QQ 按 chat_key，裸调用回落到 default。"""
    if sid:
        return f"session:{sid}"
    if ctx is not None:
        raw_sid = str(getattr(ctx, "session_id", "") or "").strip()
        if raw_sid:
            return f"session:{raw_sid}"
        vid = str(getattr(ctx, "visitor_id", "") or "").strip()
        if vid:
            return f"visitor:{vid}"
        chat = str(getattr(ctx, "chat_key", "") or "").strip()
        if chat:
            return f"chat:{chat}"
    return "default"


def _reset_after_loop_change() -> None:
    """pytest / 多事件循环下旧对象不能复用；跨循环不能 await，直接丢弃引用。"""
    global _pw, _browser, _loop, _start_lock, _entries, _locks
    _pw = _browser = None
    _start_lock = None
    _entries = {}
    _locks = {}


async def _close_entries() -> None:
    global _entries
    for entry in list(_entries.values()):
        try:
            await entry["context"].close()
        except Exception:
            pass
    _entries = {}


async def _close_browser() -> None:
    global _pw, _browser, _start_lock
    await _close_entries()
    try:
        if _browser is not None:
            await _browser.close()
    except Exception:
        pass
    try:
        if _pw is not None:
            await _pw.stop()
    except Exception:
        pass
    _pw = _browser = None
    _start_lock = None


def _lock_for(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def _ensure_browser():
    global _pw, _browser, _loop, _start_lock
    loop = asyncio.get_running_loop()
    if _loop is not loop:
        _reset_after_loop_change()
        _loop = loop
    if _start_lock is None:
        _start_lock = asyncio.Lock()
    async with _start_lock:
        try:
            if _browser is not None and _browser.is_connected():
                return _browser
        except Exception:
            await _close_browser()
        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            raise BrowserError("没装 Playwright，先执行 pip install playwright") from e
        await _close_browser()
        try:
            _pw = await async_playwright().start()
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--lang=zh-CN"],
            }
            exe = _chromium_path()
            if exe:
                launch_kwargs["executable_path"] = exe
            _browser = await _pw.chromium.launch(**launch_kwargs)
            return _browser
        except Exception as e:
            await _close_browser()
            raise BrowserError(f"Chromium 启动失败：{type(e).__name__}: {str(e)[:200]}") from e


async def _ensure_page(key: str):
    browser = await _ensure_browser()
    entry = _entries.get(key)
    try:
        if entry and not entry["page"].is_closed() and entry["context"].browser is browser:
            entry["last"] = time.time()
            return entry["page"]
    except Exception:
        await _drop_entry(key)
    # LRU：保留最近 4 个会话，防止管理员开几十个上下文把内存吃满
    while len(_entries) >= MAX_SESSIONS:
        oldest = min(_entries, key=lambda k: _entries[k]["last"])
        await _drop_entry(oldest)
    try:
        context = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
            ignore_https_errors=True,
        )
        page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        _entries[key] = {"context": context, "page": page, "last": time.time()}
        return page
    except Exception as e:
        await _drop_entry(key)
        raise BrowserError(f"浏览器会话创建失败：{type(e).__name__}: {str(e)[:200]}") from e


def _current_entry(key: str) -> dict | None:
    entry = _entries.get(key)
    if not entry:
        return None
    try:
        if entry["page"].is_closed():
            return None
    except Exception:
        return None
    return entry


async def _drop_entry(key: str) -> None:
    entry = _entries.pop(key, None)
    _locks.pop(key, None)
    if entry:
        try:
            await entry["context"].close()
        except Exception:
            pass


def _check_url(url: str) -> str:
    try:
        return url_guard.check_url(url)
    except url_guard.UnsafeUrl as e:
        raise BrowserError(str(e)) from e


async def _state(page, max_chars: int = 2000) -> dict:
    try:
        final = page.url
        # 公开页跳内网也算 SSRF；此时不要把正文/截图交出去。
        if final and final != "about:blank":
            _check_url(final)
    except BrowserError:
        try:
            await page.goto("about:blank")
        except Exception:
            pass
        raise
    title = ""
    text = ""
    try:
        title = await page.title()
    except Exception:
        pass
    try:
        text = await page.inner_text("body", timeout=5000)
    except Exception:
        pass
    return {"title": title, "url": page.url, "text": text[:max_chars]}


def _err(tool: str, msg: str) -> dict:
    from core.tool_result import miss_result
    return miss_result(tool, msg)


def _ok(tool: str, note: str, **kw) -> dict:
    from core.tool_result import ok_result
    return ok_result(tool, note, **kw)


async def browser_status(ctx=None, sid: str = "") -> dict:
    """给侧边栏用的轻状态：不启动浏览器，不抓正文。"""
    key = session_key(ctx, sid)
    entry = _current_entry(key)
    if not entry:
        return {"connected": False, "session": key, "url": "", "title": "",
                "sessions": len(_entries)}
    try:
        title = await entry["page"].title()
        url = entry["page"].url
        if url and url != "about:blank":
            _check_url(url)
        return {"connected": True, "session": key, "url": url, "title": title,
                "sessions": len(_entries)}
    except Exception:
        await _drop_entry(key)
        return {"connected": False, "session": key, "url": "", "title": "",
                "sessions": len(_entries)}


async def browser_open(url: str = "", wait_until: str = "domcontentloaded",
                       timeout: str = "20", ctx=None, **_kw) -> dict:
    url = (url or "").strip()
    if not url:
        from core.tool_result import need_ctx
        return need_ctx("browser_open", "要打开的网址")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    key = session_key(ctx)
    try:
        async with _lock_for(key):
            safe = _check_url(url)
            page = await _ensure_page(key)
            try:
                ms = max(5000, min(45000, int(str(timeout or "20")) * 1000))
            except ValueError:
                ms = DEFAULT_TIMEOUT_MS
            wu = wait_until if wait_until in {"load", "domcontentloaded", "networkidle", "commit"} else "domcontentloaded"
            resp = await page.goto(safe, wait_until=wu, timeout=ms)
            st = await _state(page, 2500)
            note = f"已打开：{st['title'] or '(无标题)'}\n{st['url']}"
            if st["text"].strip():
                note += "\n" + st["text"].strip()[:1200]
            return _ok("browser_open", note, title=st["title"], url=st["url"],
                       text=st["text"], status_code=(resp.status if resp else None))
    except BrowserError as e:
        return _err("browser_open", f"浏览器打不开这个地址：{e}")
    except Exception as e:
        return _err("browser_open", f"打开网页失败：{type(e).__name__}: {str(e)[:200]}")


async def browser_read(selector: str = "body", max_chars: str = "4000", ctx=None, **_kw) -> dict:
    key = session_key(ctx)
    try:
        async with _lock_for(key):
            entry = _current_entry(key)
            if not entry:
                raise BrowserError("当前会话还没有打开网页，先用 browser_open 打开一个地址。")
            page = entry["page"]
            sel = (selector or "body").strip()
            text = await page.inner_text(sel, timeout=5000)
            try:
                limit = max(200, min(12000, int(str(max_chars or "4000"))))
            except ValueError:
                limit = 4000
            st = await _state(page, 0)
            body = text.strip()[:limit]
            return _ok("browser_read", body or "这个选择器没有文字。", selector=sel,
                       title=st["title"], url=st["url"], text=body)
    except BrowserError as e:
        return _err("browser_read", str(e))
    except Exception as e:
        return _err("browser_read", f"读取失败：{type(e).__name__}: {str(e)[:200]}")


async def browser_click(selector: str = "", text: str = "", timeout: str = "15",
                        ctx=None, **_kw) -> dict:
    sel = (selector or "").strip()
    label = (text or "").strip()
    if not sel and not label:
        from core.tool_result import need_ctx
        return need_ctx("browser_click", "CSS 选择器或要点击的文字")
    key = session_key(ctx)
    try:
        async with _lock_for(key):
            entry = _current_entry(key)
            if not entry:
                raise BrowserError("当前会话还没有打开网页，先用 browser_open 打开一个地址。")
            page = entry["page"]
            try:
                ms = max(1000, min(30000, int(str(timeout or "15")) * 1000))
            except ValueError:
                ms = 15000
            if sel:
                await page.locator(sel).first.click(timeout=ms)
                clicked = sel
            else:
                await page.get_by_text(label, exact=False).first.click(timeout=ms)
                clicked = label
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            st = await _state(page, 1200)
            note = f"已点击：{clicked}\n现在：{st['title'] or '(无标题)'} {st['url']}"
            if st["text"].strip():
                note += "\n" + st["text"].strip()[:800]
            return _ok("browser_click", note, clicked=clicked,
                       title=st["title"], url=st["url"], text=st["text"])
    except BrowserError as e:
        return _err("browser_click", str(e))
    except Exception as e:
        return _err("browser_click", f"点击失败：{type(e).__name__}: {str(e)[:200]}")


async def browser_type(selector: str = "", text: str = "", enter: str = "false",
                       ctx=None, **_kw) -> dict:
    sel = (selector or "").strip()
    val = str(text or "")
    if not sel:
        from core.tool_result import need_ctx
        return need_ctx("browser_type", "输入框选择器")
    key = session_key(ctx)
    try:
        async with _lock_for(key):
            entry = _current_entry(key)
            if not entry:
                raise BrowserError("当前会话还没有打开网页，先用 browser_open 打开一个地址。")
            page = entry["page"]
            await page.locator(sel).first.fill(val, timeout=15000)
            if str(enter).lower() in {"1", "true", "yes", "on"}:
                await page.locator(sel).first.press("Enter", timeout=5000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
            st = await _state(page, 800)
            return _ok("browser_type", f"已向 {sel} 输入并提交。",
                       selector=sel, value=val, enter=str(enter).lower() in {"1", "true", "yes", "on"},
                       title=st["title"], url=st["url"], text=st["text"])
    except BrowserError as e:
        return _err("browser_type", str(e))
    except Exception as e:
        return _err("browser_type", f"输入失败：{type(e).__name__}: {str(e)[:200]}")


async def browser_screenshot(full_page: str = "false", ctx=None, **_kw) -> dict:
    key = session_key(ctx)
    try:
        async with _lock_for(key):
            entry = _current_entry(key)
            if not entry:
                raise BrowserError("当前会话还没有打开网页，先用 browser_open 打开一个地址。")
            page = entry["page"]
            out_dir = paths.data_dir() / "browser" / "screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / f"shot-{int(time.time() * 1000)}.jpg"
            await page.screenshot(path=str(p), type="jpeg", quality=82,
                                  full_page=str(full_page).lower() in {"1", "true", "yes", "on"})
            st = await _state(page, 0)
            data_url = ""
            try:
                if p.stat().st_size <= 2_000_000:
                    data_url = "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()
            except OSError:
                pass
            return _ok("browser_screenshot", f"已截图：{p.name}",
                       path=str(p), title=st["title"], url=st["url"],
                       image_data_url=data_url)
    except BrowserError as e:
        return _err("browser_screenshot", str(e))
    except Exception as e:
        return _err("browser_screenshot", f"截图失败：{type(e).__name__}: {str(e)[:200]}")


async def browser_close(ctx=None, **_kw) -> dict:
    key = session_key(ctx)
    async with _lock_for(key):
        await _drop_entry(key)
    return _ok("browser_close", "这个会话的浏览器已关闭。", closed=True, session=key)
