"""内置浏览器自动化：用 Playwright 驱动本机 Chromium，保留一个页面会话。

设计边界：
- 只走 http/https，导航前后都过 url_guard；跳到内网/元数据地址立即中断；
- 不执行任意 JS，不读本机文件，不下载文件；
- 页面会话是进程级共享的：管理员连续调用 open/click/type 才能完成多步操作；
- 浏览器工具在 tools.py 里归入管理员工具，网页访客不能直接驱动。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from pathlib import Path

from core import paths, url_guard

log = logging.getLogger("cs.browser")

MAX_TEXT = 6000
DEFAULT_TIMEOUT_MS = 20_000
_pw = None
_browser = None
_context = None
_page = None
_lock: asyncio.Lock | None = None
_loop = None


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


async def _close_soft() -> None:
    global _pw, _browser, _context, _page, _lock
    for obj in (_context, _browser):
        try:
            if obj is not None:
                await obj.close()
        except Exception:
            pass
    try:
        if _pw is not None:
            await _pw.stop()
    except Exception:
        pass
    _pw = _browser = _context = _page = None
    _lock = None


async def _ensure_page():
    global _pw, _browser, _context, _page, _lock, _loop
    loop = asyncio.get_running_loop()
    # pytest / 多事件循环下旧对象不能复用，直接丢弃重开，避免 “Future attached to a different loop”。
    if _loop is not loop:
        _pw = _browser = _context = _page = None
        _lock = None
        _loop = loop
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        try:
            if _page is not None and not _page.is_closed() and _browser is not None \
                    and _browser.is_connected():
                return _page
        except Exception:
            await _close_soft()
        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            raise BrowserError("没装 Playwright，先执行 pip install playwright") from e
        await _close_soft()
        try:
            _pw = await async_playwright().start()
            launch_kwargs = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--lang=zh-CN"],
            }
            exe = _chromium_path()
            if exe:
                launch_kwargs["executable_path"] = exe
            _browser = await _pw.chromium.launch(**launch_kwargs)
            _context = await _browser.new_context(
                viewport={"width": 1366, "height": 900},
                locale="zh-CN",
                ignore_https_errors=True,
            )
            _page = await _context.new_page()
            _page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            _page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
            return _page
        except Exception as e:
            await _close_soft()
            raise BrowserError(f"Chromium 启动失败：{type(e).__name__}: {str(e)[:200]}") from e


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


async def browser_open(url: str, wait_until: str = "domcontentloaded",
                       timeout: str = "20", **_kw) -> dict:
    url = (url or "").strip()
    if not url:
        from core.tool_result import need_ctx
        return need_ctx("browser_open", "要打开的网址")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        safe = _check_url(url)
        page = await _ensure_page()
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


async def browser_read(selector: str = "body", max_chars: str = "4000", **_kw) -> dict:
    try:
        page = await _ensure_page()
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


async def browser_click(selector: str = "", text: str = "", timeout: str = "15", **_kw) -> dict:
    sel = (selector or "").strip()
    label = (text or "").strip()
    if not sel and not label:
        from core.tool_result import need_ctx
        return need_ctx("browser_click", "CSS 选择器或要点击的文字")
    try:
        page = await _ensure_page()
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


async def browser_type(selector: str = "", text: str = "", enter: str = "false", **_kw) -> dict:
    sel = (selector or "").strip()
    val = str(text or "")
    if not sel:
        from core.tool_result import need_ctx
        return need_ctx("browser_type", "输入框选择器")
    try:
        page = await _ensure_page()
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


async def browser_screenshot(full_page: str = "false", **_kw) -> dict:
    try:
        page = await _ensure_page()
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


async def browser_close(**_kw) -> dict:
    await _close_soft()
    return _ok("browser_close", "浏览器会话已关闭。", closed=True)
