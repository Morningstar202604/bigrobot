"""真接口功能冒烟：直接打 HTTP，验证读、写、改、删四条链路。

用法: ADMIN_TOKEN=xxx python3 scripts/api_smoke.py http://127.0.0.1:8010
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
TOK = os.environ.get("ADMIN_TOKEN", "")


def call(method, path, body=None, token=None, extra=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token or TOK:
        req.add_header("X-Admin-Token", token or TOK)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return 0, str(e)[:200]


CASES = []


def case(name, method, path, body=None, expect=(200, 201, 202, 204), check=None, extra=None):
    st, resp = call(method, path, body, extra=extra)
    ok = st in expect
    detail = ""
    if check and ok:
        try:
            ok = bool(check(resp))
            detail = "" if ok else f"check failed: {str(resp)[:120]}"
        except Exception as e:
            ok, detail = False, f"check err: {e}"
    if not ok:
        detail = detail or f"{st} {str(resp)[:120]}"
    CASES.append({"name": name, "method": method, "path": path, "status": st, "ok": ok, "detail": detail})
    print(f"{'OK  ' if ok else 'FAIL'} {name:<28} {method:<5} {path:<46} {st}")
    return resp if ok else None


def main():
    print("== 基础 ==")
    case("健康检查", "GET", "/healthz")
    case("就绪检查", "GET", "/readyz", expect=(200, 503))
    case("适配器列表", "GET", "/api/channels/adapters", check=lambda r: "adapters" in r or isinstance(r, list))
    case("账号列表", "GET", "/api/accounts")
    case("运营概览", "GET", "/api/observe/overview")
    case("配置读取", "GET", "/api/config", check=lambda r: "llm" in r.get("config", r))

    print("\n== 写入链路 ==")
    sid = f"smoke-{int(time.time())}"
    created = case("建会话", "POST", "/api/sessions", {"visitor_id": "smoke-" + str(int(time.time()))},
                   check=lambda r: r.get("session_id"))
    sid = created["session_id"] if isinstance(created, dict) else sid
    secret = created.get("session_secret", "") if isinstance(created, dict) else ""
    case("访客发消息", "POST", f"/api/sessions/{sid}/messages",
         {"content": "冒烟：这单什么时候发货？"}, extra={"X-Session-Secret": secret})
    case("消息已落库", "GET", f"/api/sessions/{sid}/messages",
         check=lambda r: "发货" in json.dumps(r, ensure_ascii=False),
         extra={"X-Session-Secret": secret})
    case("会话列表含新会话", "GET", "/api/admin/sessions?limit=20",
         check=lambda r: sid in json.dumps(r))
    case("导出会话", "GET", f"/api/sessions/{sid}/export", extra={"X-Session-Secret": secret})
    case("转人工", "POST", f"/api/sessions/{sid}/op", {"op": "escalate"}, extra={"X-Session-Secret": secret})
    case("接管", "POST", f"/api/sessions/{sid}/op", {"op": "take", "visitor_id": "smoke-op"})
    case("人工回复", "POST", f"/api/sessions/{sid}/op", {"op": "reply", "content": "冒烟：客服已接入。"})
    case("关闭会话", "POST", f"/api/sessions/{sid}/op", {"op": "close"})

    print("\n== 知识库 ==")
    case("知识库条目", "GET", "/api/kb")
    case("知识库检索", "POST", "/api/kb/test", {"query": "物流"})

    print("\n== 运维与观测 ==")
    case("实例状态", "GET", "/api/channel/qq/deploy-status")
    case("动作目录", "GET", "/api/actions/catalog")
    case("运行列表", "GET", "/api/agent/runs")
    case("提醒列表", "GET", "/api/reminders")
    case("日志", "GET", "/api/observe/logs?limit=20")
    case("标注列表", "GET", "/api/annotations")
    case("审计校验", "GET", "/api/admin/audit/verify")
    case("人格列表", "GET", "/api/personas")
    case("表情列表", "GET", "/api/emotes")

    print("\n== 模型探测 ==")
    case("模型连通性", "POST", "/api/admin/llm-test", {}, expect=(200, 400, 429, 502))

    ok = sum(1 for c in CASES if c["ok"])
    print(f"\n合计 {len(CASES)} 项，通过 {ok}，失败 {len(CASES)-ok}")
    for c in CASES:
        if not c["ok"]:
            print(f"  FAIL {c['name']} {c['method']} {c['path']} -> {c['detail']}")
    with open("artifacts/e2e/api_smoke.json", "w", encoding="utf-8") as f:
        json.dump(CASES, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
