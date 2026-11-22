"""开源工具补充：从 MCP 官方参考服务器与常见开源 CLI 的「纯函数」能力里挑出来的轻量工具。

只收不碰网络、不执行 shell、不读写任意路径的工具，避免为了“工具数量”把攻击面放大：
- uuid_gen：生成 UUID（对应常见 uuid 工具）
- slugify：标题转 slug（对应 slugify / python-slugify）
- diff_text：两段文本的 unified diff（对应 diff）
- json_query：点路径取 JSON 字段（对应 jq 的常用子集）
- toml_to_json：TOML → JSON（Python 3.11 标准库 tomllib）
- csv_to_json：CSV → JSON（标准库 csv）
- jwt_decode：只解码 JWT，不验签（对应 jwt-cli 的 decode）
- markdown_toc：Markdown 标题生成目录（对应 doctoc 的常用子集）
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import re
import tomllib
import unicodedata
import uuid

from core.tool_result import miss_result, need_ctx, ok_result


def tool_uuid_gen(count: str = "1", upper: str = "false", **_kw) -> dict:
    try:
        n = max(1, min(20, int(str(count or "1").strip())))
    except ValueError:
        return need_ctx("uuid_gen", "生成数量（1–20）")
    vals = [str(uuid.uuid4()) for _ in range(n)]
    if str(upper).lower() in {"1", "true", "yes", "on"}:
        vals = [v.upper() for v in vals]
    return ok_result("uuid_gen", "\n".join(vals), values=vals, count=n)


def tool_slugify(text: str = "", separator: str = "-", max_length: str = "80", **_kw) -> dict:
    raw = (text or "").strip()
    if not raw:
        return need_ctx("slugify", "要转换的标题或文本")
    try:
        limit = max(8, min(200, int(str(max_length or "80"))))
    except ValueError:
        limit = 80
    sep = (separator or "-")[:3]
    # 保留中文、字母、数字；其余折叠成单个分隔符
    s = unicodedata.normalize("NFKC", raw).lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", sep, s, flags=re.UNICODE).strip(sep)
    s = re.sub(re.escape(sep) + r"{2,}", sep, s)[:limit].strip(sep)
    if not s:
        return miss_result("slugify", "这段文本没有可用的字母、数字或汉字")
    return ok_result("slugify", s, slug=s)


def tool_diff_text(old: str = "", new: str = "", context: str = "3", **_kw) -> dict:
    a, b = old or "", new or ""
    if not a and not b:
        return need_ctx("diff_text", "要比较的两段文本")
    try:
        ctx = max(0, min(20, int(str(context or "3"))))
    except ValueError:
        ctx = 3
    lines = list(difflib.unified_diff(
        a.splitlines(), b.splitlines(), fromfile="old", tofile="new", n=ctx, lineterm=""))
    if not lines:
        return ok_result("diff_text", "两段文本没有差异。", changed=False)
    out = "\n".join(lines)
    changed = sum(1 for x in lines if x.startswith(("+", "-")) and not x.startswith(("+++", "---")))
    return ok_result("diff_text", out[:12000], changed=True, changed_lines=changed,
                     truncated=len(out) > 12000)


def _json_get(obj, path: str):
    # 支持 $.a.b[0].c 和 a.b[0].c；数组下标单独解析
    p = (path or "").strip()
    if p in {"", "$", "."}:
        return obj
    if p.startswith("$"):
        p = p[1:]
    if p.startswith("."):
        p = p[1:]
    cur = obj
    for key, idx in re.findall(r"([^\.\[\]]+)|\[(\d+)\]", p):
        if key:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            elif isinstance(cur, list) and key.isdigit() and int(key) < len(cur):
                cur = cur[int(key)]
            else:
                raise KeyError(key)
        elif idx:
            if not isinstance(cur, list) or int(idx) >= len(cur):
                raise IndexError(idx)
            cur = cur[int(idx)]
    return cur


def tool_json_query(data: str = "", path: str = "$", **_kw) -> dict:
    raw = (data or "").strip()
    if not raw:
        return need_ctx("json_query", "JSON 文本")
    try:
        obj = json.loads(raw)
    except ValueError as e:
        return miss_result("json_query", f"JSON 解析失败：{e}")
    try:
        val = _json_get(obj, path)
    except (KeyError, IndexError) as e:
        return miss_result("json_query", f"路径 `{path}` 不存在（{type(e).__name__}: {e}）")
    text = json.dumps(val, ensure_ascii=False, indent=2) if isinstance(val, (dict, list)) else str(val)
    return ok_result("json_query", text[:12000], value=val, path=path)


def tool_toml_to_json(text: str = "", **_kw) -> dict:
    raw = text or ""
    if not raw.strip():
        return need_ctx("toml_to_json", "TOML 文本")
    try:
        obj = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        return miss_result("toml_to_json", f"TOML 解析失败：{e}")
    out = json.dumps(obj, ensure_ascii=False, indent=2)
    return ok_result("toml_to_json", out[:16000], json=obj)


def tool_csv_to_json(text: str = "", delimiter: str = ",", max_rows: str = "200", **_kw) -> dict:
    raw = text or ""
    if not raw.strip():
        return need_ctx("csv_to_json", "CSV 文本")
    try:
        limit = max(1, min(2000, int(str(max_rows or "200"))))
    except ValueError:
        limit = 200
    try:
        reader = csv.DictReader(io.StringIO(raw), delimiter=(delimiter or ",")[:1])
        rows = []
        for i, row in enumerate(reader):
            if i >= limit:
                break
            rows.append({str(k or ""): (v if isinstance(v, str) else str(v)) for k, v in row.items()})
    except csv.Error as e:
        return miss_result("csv_to_json", f"CSV 解析失败：{e}")
    out = json.dumps(rows, ensure_ascii=False, indent=2)
    return ok_result("csv_to_json", out[:16000], rows=rows, count=len(rows),
                     truncated=len(rows) >= limit)


def tool_jwt_decode(token: str = "", **_kw) -> dict:
    raw = (token or "").strip()
    if not raw:
        return need_ctx("jwt_decode", "JWT 字符串")
    parts = raw.split(".")
    if len(parts) != 3:
        return miss_result("jwt_decode", "不是标准 JWT（应为 header.payload.signature 三段）")
    import base64

    def dec(seg: str):
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg.encode()).decode("utf-8"))

    try:
        header, payload = dec(parts[0]), dec(parts[1])
    except Exception as e:
        return miss_result("jwt_decode", f"JWT 解码失败：{type(e).__name__}")
    out = json.dumps({"header": header, "payload": payload}, ensure_ascii=False, indent=2)
    return ok_result("jwt_decode",
                     out + "\n\n注意：只解码，未验证签名；不要据此认定 token 有效。",
                     header=header, payload=payload, verified=False)


def tool_markdown_toc(text: str = "", max_level: str = "3", **_kw) -> dict:
    raw = text or ""
    if not raw.strip():
        return need_ctx("markdown_toc", "Markdown 文本")
    try:
        top = max(1, min(6, int(str(max_level or "3"))))
    except ValueError:
        top = 3
    lines = []
    for line in raw.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not m:
            continue
        level, title = len(m.group(1)), m.group(2).strip()
        if level > top:
            continue
        anchor = re.sub(r"[^\w\u4e00-\u9fff -]+", "", title).strip().lower().replace(" ", "-")
        lines.append(f"{'  ' * (level - 1)}- [{title}](#{anchor})")
    if not lines:
        return miss_result("markdown_toc", f"没有找到 1–{top} 级 Markdown 标题")
    return ok_result("markdown_toc", "\n".join(lines), toc=lines, count=len(lines))


SYNC_TOOLS = {
    "uuid_gen": tool_uuid_gen,
    "slugify": tool_slugify,
    "diff_text": tool_diff_text,
    "json_query": tool_json_query,
    "toml_to_json": tool_toml_to_json,
    "csv_to_json": tool_csv_to_json,
    "jwt_decode": tool_jwt_decode,
    "markdown_toc": tool_markdown_toc,
}

TOOL_META_EXTRA = {
    "uuid_gen": {"name": "生成 UUID", "desc": "生成 1–20 个 UUID v4",
                 "args": {"count": "string", "upper": "string"}},
    "slugify": {"name": "标题转 slug", "desc": "把标题转成 URL/文件名友好的 slug，保留中文",
                "args": {"text": "string", "separator": "string", "max_length": "string"}},
    "diff_text": {"name": "文本对比", "desc": "比较两段文本，返回 unified diff",
                  "args": {"old": "string", "new": "string", "context": "string"}},
    "json_query": {"name": "取 JSON 字段", "desc": "按 $.a.b[0] 路径取 JSON 里的值",
                   "args": {"data": "string", "path": "string"}},
    "toml_to_json": {"name": "TOML 转 JSON", "desc": "把 TOML 配置转成 JSON",
                     "args": {"text": "string"}},
    "csv_to_json": {"name": "CSV 转 JSON", "desc": "把 CSV 文本转成 JSON 数组",
                    "args": {"text": "string", "delimiter": "string", "max_rows": "string"}},
    "jwt_decode": {"name": "解 JWT", "desc": "只解码 JWT 头和载荷，不验签",
                   "args": {"token": "string"}},
    "markdown_toc": {"name": "生成目录", "desc": "从 Markdown 标题生成带锚点的目录",
                     "args": {"text": "string", "max_level": "string"}},
}
