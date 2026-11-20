"""真机全页点击巡检：逐页进入、逐个点按钮、监听错误。

用法:
  PLAYWRIGHT_BROWSERS_PATH=/home/user/pw python3 scripts/e2e_ui_walk.py http://127.0.0.1:8010

只点"安全"按钮：导航、筛选、查看、展开、刷新、切换 tab。
不点：删除/清空/重置/停止/移除/保存/提交/退出/关闭会话，避免改坏现场。
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
START = int(sys.argv[2]) if len(sys.argv) > 2 else 1
END = int(sys.argv[3]) if len(sys.argv) > 3 else len(PAGES)
TOKEN = os.environ.get("ADMIN_TOKEN", "")
OUT = Path("artifacts/e2e")
SHOT = OUT / "shots"
SHOT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("实例", "/instances"),
    ("会话", "/sessions"),
    ("提醒", "/reminders"),
    ("能力", "/capabilities"),
    ("策略", "/policy"),
    ("观测", "/observe"),
    ("设置", "/settings"),
    ("能力-知识库", "/capabilities/kb"),
    ("能力-人格", "/capabilities/persona"),
    ("能力-表情", "/capabilities/emotes"),
    ("能力-卡片", "/capabilities/cards"),
    ("能力-日志", "/logs"),
    ("观测-运行", "/runs"),
    ("观测-动作", "/actions"),
    ("观测-标注", "/annotations"),
    ("设置-参数", "/settings/params"),
]

# 破坏性/写入性按钮不点
SKIP_WORDS = ["删除", "清空", "重置", "停止", "移除", "保存", "提交", "退出",
              "关闭会话", "注销", "解绑", "撤销", "禁用", "下线", "重置密码",
              "Delete", "Remove", "Reset", "Stop", "Save"]

results = []


def walk(page, label, path, index):
    rec = {"page": label, "path": path, "ok": True, "errors": [], "http_bad": [],
           "clicked": [], "skipped": []}
    bad = []

    def on_resp(r):
        try:
            if r.url.startswith(BASE) and r.status >= 400 and "/api/" in r.url:
                bad.append(f"{r.status} {r.request.method} {r.url}")
        except Exception:
            pass

    def on_err(e):
        rec["errors"].append(str(e))

    page.on("response", on_resp)
    page.on("pageerror", on_err)
    try:
        page.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOT / f"{index:02d}-{label}.png"), full_page=False)

        buttons = page.locator("button:visible, a:visible")
        n = min(buttons.count(), 14)
        for i in range(n):
            b = buttons.nth(i)
            try:
                text = (b.inner_text() or "").strip().replace("\n", " ")[:28]
            except Exception:
                continue
            if not text:
                continue
            if any(w in text for w in SKIP_WORDS):
                rec["skipped"].append(text)
                continue
            try:
                b.click(timeout=1200)
                page.wait_for_timeout(120)
                rec["clicked"].append(text)
                page.keyboard.press("Escape")
                page.wait_for_timeout(80)
            except Exception as e:
                rec["errors"].append(f"click[{text}]: {str(e)[:80]}")
        # 点完重新载入，避免状态污染下一轮
        page.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        rec["ok"] = False
        rec["errors"].append(f"page: {str(e)[:120]}")
    rec["http_bad"] = sorted(set(bad))
    if rec["http_bad"] or rec["errors"]:
        rec["ok"] = False
    page.remove_listener("response", on_resp)
    page.remove_listener("pageerror", on_err)
    results.append(rec)
    return rec


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1512, "height": 982})
        page = ctx.new_page()
        page.add_init_script(
            "localStorage.setItem('cs_admin_token', %s)" % json.dumps(TOKEN)
        )
        for i, (label, path) in list(enumerate(PAGES, 1))[START-1:END]:
            r = walk(page, label, path, i)
            print(f"[{i}/{len(PAGES)}] {label:<12} {'OK ' if r['ok'] else 'FAIL'} "
                  f"click={len(r['clicked'])} bad={len(r['http_bad'])} err={len(r['errors'])}", flush=True)
            (OUT / f"part-{START}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()

    (OUT / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    fails = [r for r in results if not r["ok"]]
    print(f"\n合计 {len(results)} 页，失败 {len(fails)} 页")
    for r in fails:
        print(f"\n## {r['page']} ({r['path']})")
        for k in ("http_bad", "errors"):
            for m in r[k][:6]:
                print(f"  - {m}")


if __name__ == "__main__":
    main()
