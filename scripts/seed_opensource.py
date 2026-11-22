#!/usr/bin/env python3
"""把 assets/opensource 下的开源素材装进运行时：表情、扩展、知识库、MCP。

幂等：已有条目/文件不重复写；MCP 只补缺失的 server id，不覆盖用户改过的配置。
不下载网络资源；需要重新拉取上游时单独跑维护脚本。用法：
    python scripts/seed_opensource.py
    python scripts/seed_opensource.py --test-mcp
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "assets" / "opensource"


def seed_emotes() -> int:
    src = ASSETS / "emotes" / "noto"
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    dst = Path.home() / "napcat" / "emotes"
    dst.mkdir(parents=True, exist_ok=True)
    index_path, tags_path = dst / "index.json", dst / "tags.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    except ValueError:
        index = []
    if isinstance(index, dict):
        index = index.get("items") or []
    if not isinstance(index, list):
        index = []
    try:
        tags = json.loads(tags_path.read_text(encoding="utf-8")) if tags_path.exists() else {}
    except ValueError:
        tags = {}
    tags = tags if isinstance(tags, dict) else {}
    existing = {str(x.get("data")) for x in index if isinstance(x, dict)}
    added = 0
    for item in manifest:
        name = str(item.get("file") or "")
        if not name.endswith(".png"):
            continue
        shutil.copyfile(src / name, dst / name)
        path = str(dst / name)
        tags[path] = str(item.get("tags") or name)
        if path not in existing:
            index.append({"kind": "image", "summary": tags[path], "data": path,
                          "group": "opensource-noto", "ts": time.time() + added})
            added += 1
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tags_path.write_text(json.dumps(tags, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def seed_extensions() -> int:
    root = ROOT / "data" / "extensions"
    root.mkdir(parents=True, exist_ok=True)
    n = 0
    for pack in (ASSETS / "extensions").iterdir():
        if not (pack / "manifest.json").is_file():
            continue
        target = root / pack.name
        if target.exists():
            continue
        shutil.copytree(pack, target)
        n += 1
    return n


def seed_kb() -> int:
    data = json.loads((ASSETS / "kb" / "entries.json").read_text(encoding="utf-8"))
    from core import kb_store, retrieval

    def op(collections, items):
        col = data["collection"]
        if not any(c.get("id") == col["id"] for c in collections):
            collections.append(col)
        titles = {str(x.get("title")) for x in items}
        added = [e for e in data["items"] if str(e.get("title")) not in titles]
        return {"added": len(added)}, collections, items + added

    result, _, _ = kb_store.store.mutate_collections(op)
    retrieval.clear_cache()
    return int(result.get("added") or 0)


def seed_mcp(test: bool = False) -> int:
    from core import mcp_client

    catalog = json.loads((ASSETS / "mcp" / "servers.json").read_text(encoding="utf-8"))
    existing = {s.get("id") for s in mcp_client.list_servers(mask=False)}
    added = 0
    for item in catalog["servers"]:
        if item["id"] in existing:
            continue
        mcp_client.upsert_server({**item, "enabled": True, "allow_untrusted": False, "env": {}})
        added += 1
    if test:
        import asyncio
        for item in catalog["servers"]:
            try:
                r = asyncio.run(mcp_client.test_server(item["id"]))
                print(f"MCP {item['id']}: ok={r['ok']} tools={len(r['tools'])} {r.get('error') or ''}")
            except Exception as e:
                print(f"MCP {item['id']}: {type(e).__name__}: {e}")
    return added


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--test-mcp", action="store_true", help="安装后逐个拉起 MCP 服务器测试")
    args = p.parse_args()
    print(f"emotes added: {seed_emotes()}")
    print(f"extensions added: {seed_extensions()}")
    print(f"kb entries added: {seed_kb()}")
    print(f"mcp servers added: {seed_mcp(args.test_mcp)}")


if __name__ == "__main__":
    main()
