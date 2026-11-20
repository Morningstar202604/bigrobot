"""知识库路由：多知识库集合 / CRUD / 批量导入 / 文档导入 / 试召回 / 导出。

从 core/main.py 抽出（原文件把 110 个路由塞在一个 create_app 闭包里，
无法单独测试、无法按职责审阅，也无法做路由级限流）。

本模块只做「参数校验 + 调用 store」，不碰文件锁与原子写——
那是 core/kb_store.py 的职责。
"""
from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from core import config, docparse, kb_store, personas, retrieval
from core.api.deps import require_admin

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


class KbIn(BaseModel):
    # id 为空 = 坐席回流/快速保存：自动编号追加；id 非空 = 指定 ID 插入（已存在则 400）
    id: str = ""
    text: str = ""
    title: str = ""
    answer: str = ""
    tags: list[str] = []
    collection: str = ""
    source: str = ""


class KbImportIn(BaseModel):
    text: str
    replace: bool = False
    collection: str = ""


class KbTestIn(BaseModel):
    query: str
    collection: str = ""


class KbCollectionIn(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    persona_ids: list[str] = []
    enabled: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _collection_counts() -> list[dict]:
    entries = retrieval.load_kb()
    counts = Counter(str(e.get("collection") or retrieval.DEFAULT_COLLECTION) for e in entries)
    out = []
    for c in retrieval.load_collections():
        out.append({**c, "entry_count": counts.get(c["id"], 0)})
    return out


def _require_collection(collection_id: str) -> str:
    cid = (collection_id or "").strip() or retrieval.DEFAULT_COLLECTION
    if not any(c["id"] == cid for c in retrieval.load_collections()):
        raise HTTPException(404, f"知识库「{cid}」不存在")
    return cid


def _validate_collection(body: KbCollectionIn) -> None:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "知识库名称不能为空")
    if len(name) > 40:
        raise HTTPException(400, "知识库名称最多 40 个字符")
    for pid in body.persona_ids:
        if personas.get(pid) is None:
            raise HTTPException(400, f"未知角色预设：{pid}")


def _new_collection_id(name: str, existing: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:24]
    base = slug or "kb"
    if base == retrieval.DEFAULT_COLLECTION:
        base = "kb"
    cid = base
    while cid in existing:
        cid = f"{base}_{uuid.uuid4().hex[:6]}"
    return cid


@router.get("", dependencies=[Depends(require_admin)])
def kb_list(collection: str = ""):
    emb_flag = config.get_config().get("retrieval", {}).get("embedding", "auto")
    available = retrieval.embedding_available()
    entries = retrieval.load_kb()
    if collection:
        cid = _require_collection(collection)
        entries = [e for e in entries if (e.get("collection") or retrieval.DEFAULT_COLLECTION) == cid]
    return {
        "kb": entries,
        "collections": _collection_counts(),
        "embedding": {
            "available": available,
            "enabled": emb_flag,
            "model": retrieval.BGE_MODEL if available else "",
        },
    }


# ---- 知识库集合管理：必须放在 /{kb_id} 之前，否则 collections 会被当成条目 id ----


@router.get("/collections", dependencies=[Depends(require_admin)])
def list_collections():
    return {"collections": _collection_counts()}


@router.post("/collections", dependencies=[Depends(require_admin)])
def create_collection(body: KbCollectionIn):
    _validate_collection(body)
    requested = (body.id or "").strip()
    if requested and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", requested):
        raise HTTPException(400, "知识库 ID 只能用小写字母/数字/下划线/短横线，2–41 个字符")

    def op(collections, items):
        existing = {c["id"] for c in collections}
        cid = requested or _new_collection_id(body.name.strip(), existing)
        if cid in existing:
            raise HTTPException(400, f"知识库「{cid}」已存在")
        collections.append({
            "id": cid,
            "name": body.name.strip()[:40],
            "description": (body.description or "").strip()[:300],
            "persona_ids": list(dict.fromkeys(body.persona_ids)),
            "enabled": bool(body.enabled),
        })
        return {"collection": collections[-1]}, collections, items

    result, _, _ = kb_store.store.mutate_collections(op)
    return result


@router.put("/collections/{collection_id}", dependencies=[Depends(require_admin)])
def update_collection(collection_id: str, body: KbCollectionIn):
    _validate_collection(body)

    def op(collections, items):
        found = next((c for c in collections if c["id"] == collection_id), None)
        if found is None:
            raise HTTPException(404, "知识库不存在")
        if body.id and body.id.strip() != collection_id:
            raise HTTPException(400, "知识库 ID 不可修改")
        found.update({
            "name": body.name.strip()[:40],
            "description": (body.description or "").strip()[:300],
            "persona_ids": list(dict.fromkeys(body.persona_ids)),
            "enabled": bool(body.enabled),
        })
        return {"collection": found}, collections, items

    result, _, _ = kb_store.store.mutate_collections(op)
    return result


@router.post("/collections/{collection_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_collection(collection_id: str, body: dict):
    enabled = bool(body.get("enabled", True))

    def op(collections, items):
        found = next((c for c in collections if c["id"] == collection_id), None)
        if found is None:
            raise HTTPException(404, "知识库不存在")
        found["enabled"] = enabled
        return {"collection": found}, collections, items

    result, _, _ = kb_store.store.mutate_collections(op)
    return result


@router.delete("/collections/{collection_id}", dependencies=[Depends(require_admin)])
def delete_collection(collection_id: str, move_to: str = retrieval.DEFAULT_COLLECTION):
    if collection_id == retrieval.DEFAULT_COLLECTION:
        raise HTTPException(400, "默认知识库不能删除，可以改名或停用")
    target = _require_collection(move_to)

    def op(collections, items):
        found = next((c for c in collections if c["id"] == collection_id), None)
        if found is None:
            raise HTTPException(404, "知识库不存在")
        if target == collection_id:
            raise HTTPException(400, "迁移目标不能是自己")
        collections = [c for c in collections if c["id"] != collection_id]
        moved = 0
        for e in items:
            if (e.get("collection") or retrieval.DEFAULT_COLLECTION) == collection_id:
                e["collection"] = target
                moved += 1
        return {"deleted": collection_id, "moved": moved, "move_to": target}, collections, items

    result, _, _ = kb_store.store.mutate_collections(op)
    return result


@router.post("", dependencies=[Depends(require_admin)])
def add_kb(body: KbIn):
    """新增一条知识：带 id 走「指定 ID 插入」，不带 id 走「自动编号追加」。"""
    cid = _require_collection(body.collection)
    text = (body.text or "").strip()
    if body.id:
        def op_in(items):
            if any(e["id"] == body.id for e in items):
                raise HTTPException(400, "知识库条目 ID 已存在")
            now = _now()
            entry = {
                "id": body.id, "text": body.text, "title": body.title,
                "answer": body.answer, "tags": body.tags, "collection": cid,
                "source": body.source or "manual",
                "created_at": now, "updated_at": now,
            }
            items.append(entry)
            return None, items

        _, items = kb_store.store.mutate(op_in)
        entry = next((e for e in items if e["id"] == body.id), None)
        return {"entry": entry, "kb": items, "collections": _collection_counts()}

    if not text:
        raise HTTPException(400, "内容不能为空")
    title = (body.title or text.strip().splitlines()[0] or text[:30]).strip()[:80]

    def op_append(items):
        now = _now()
        entry = {
            "id": f"KB{kb_store.next_base(items) + 1}",
            "title": title,
            "text": f"{title} {text}"[:300],
            "answer": body.answer or text,
            "tags": body.tags or ["坐席回流"],
            "collection": cid,
            "source": body.source or "manual",
            "created_at": now,
            "updated_at": now,
        }
        items.append(entry)
        return entry, items

    entry, items = kb_store.store.mutate(op_append)
    return {
        "entry": entry, "total": len(items), "kb": items,
        "collections": _collection_counts(),
    }


@router.put("/{kb_id}", dependencies=[Depends(require_admin)])
def update_kb(kb_id: str, body: KbIn):
    cid = (body.collection or "").strip()
    if cid:
        cid = _require_collection(cid)

    def op(items):
        for i, e in enumerate(items):
            if e["id"] == kb_id:
                old = e
                items[i] = {
                    "id": kb_id, "text": body.text, "title": body.title,
                    "answer": body.answer, "tags": body.tags,
                    "collection": cid or old.get("collection") or retrieval.DEFAULT_COLLECTION,
                    "source": body.source or old.get("source") or "manual",
                    "created_at": old.get("created_at") or _now(),
                    "updated_at": _now(),
                }
                return None, items
        raise HTTPException(404, "知识库条目不存在")

    _, items = kb_store.store.mutate(op)
    return {"kb": items, "collections": _collection_counts()}


@router.delete("/{kb_id}", dependencies=[Depends(require_admin)])
def delete_kb(kb_id: str):
    def op(items):
        new = [e for e in items if e["id"] != kb_id]
        if len(new) == len(items):
            raise HTTPException(404, "知识库条目不存在")
        return None, new

    _, new = kb_store.store.mutate(op)
    return {"kb": new, "collections": _collection_counts()}


@router.post("/import", dependencies=[Depends(require_admin)])
def import_kb(body: KbImportIn):
    """批量导入：自动识别「## 标题」或空行分块两种格式，条目 id 自动编号（KB101 起）。

    replace=True 只清空目标知识库，不清空其它库——多库场景下整库重建的语义
    必须限定在当前集合，否则导一个 FAQ 会把角色资料一起抹掉。
    """
    cid = _require_collection(body.collection)
    from core.api import deps as deps_mod

    # 每次请求读模块属性而不是 import 时快照：测试与运维都靠 monkeypatch 调这个上限
    limit = deps_mod.MAX_KB_IMPORT_ITEMS
    blocks = kb_store.parse_blocks(body.text)
    if not blocks:
        raise HTTPException(400, "未能解析出任何条目：用「## 标题」开头，或用空行分隔「标题/正文」块")
    if len(blocks) > limit:
        raise HTTPException(413, f"单次导入条目过多（{len(blocks)} > {limit}），请分批导入")

    def op(items):
        if body.replace:
            items = [e for e in items
                     if (e.get("collection") or retrieval.DEFAULT_COLLECTION) != cid]
        base = kb_store.next_base(items)
        now = _now()
        for title, answer in blocks:
            base += 1
            items.append({
                "id": f"KB{base}",
                "title": title[:80],
                "text": f"{title} {answer}"[:300],
                "answer": answer or title,
                "tags": [],
                "collection": cid,
                "source": "import",
                "created_at": now,
                "updated_at": now,
            })
        return None, items

    _, items = kb_store.store.mutate(op)
    return {
        "added": len(blocks), "total": len(items), "kb": items,
        "collections": _collection_counts(),
    }


@router.post("/import/document", dependencies=[Depends(require_admin)])
async def import_kb_document(file: UploadFile, collection: str = Form("")):
    """文档导入：PDF/Word/Excel/Markdown → 解析 → 标题/段落分块 → KB 条目（追加语义）。"""
    cid = _require_collection(collection)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "文档超过 10MB 上限")
    fname = file.filename or "doc"

    def _parse() -> list[tuple[str, str]]:
        try:
            text = docparse.extract_text(fname, data)
            return docparse.chunk_document(text, fname.rsplit(".", 1)[0])
        except RuntimeError as e:  # 可选依赖缺失/文件损坏：转可读 400
            raise HTTPException(400, str(e)) from e

    # 文档解析是纯 CPU + 同步 IO（实测 291 段 docx 要 2.2s）：
    # 留在事件循环里会卡死整站（期间 /healthz 峰值 2.2s），必须下线程池。
    blocks = await run_in_threadpool(_parse)
    if not blocks:
        raise HTTPException(400, "未能从文档中解析出内容")

    def op(items):
        base = kb_store.next_base(items)
        now = _now()
        for title, chunk in blocks:
            base += 1
            items.append({
                "id": f"KB{base}",
                "title": title[:80],
                "text": f"{title} {chunk}"[:300],
                "answer": chunk,
                "tags": ["文档"],
                "collection": cid,
                "source": fname[:160],
                "created_at": now,
                "updated_at": now,
            })
        return None, items

    _, items = await run_in_threadpool(kb_store.store.mutate, op)
    return {
        "added": len(blocks), "total": len(items), "file": fname,
        "collections": _collection_counts(),
    }


@router.post("/test", dependencies=[Depends(require_admin)])
def kb_test(body: KbTestIn):
    """试召回：按当前生效配置（top-K/门槛/向量开关）跑一次检索，返回命中与分数。"""
    q = (body.query or "").strip()
    if not q:
        raise HTTPException(400, "检索词不能为空")
    cid = _require_collection(body.collection) if body.collection else ""
    cfg = config.get_config()
    top_k = cfg.get("retrieval", {}).get("kb_top_k", 4)
    min_overlap = cfg.get("retrieval", {}).get("min_overlap", 0.0)
    emb_flag = cfg.get("retrieval", {}).get("embedding", "auto")
    use_emb = None if emb_flag == "auto" else (emb_flag == "on")
    hits = retrieval.retrieve_scored(
        q, top_k, min_overlap, use_embedding=use_emb,
        collections={cid} if cid else None,
    )
    return {
        "query": q,
        "collection": cid,
        "top_k": top_k,
        "min_overlap": min_overlap,
        "embedding": emb_flag,
        "hits": [
            {"id": e["id"], "title": e["title"], "score": round(s, 3),
             "answer": (e["answer"] or "")[:120]}
            for s, e in hits
        ],
    }


@router.get("/export", dependencies=[Depends(require_admin)])
def export_kb(format: str = "markdown", collection: str = ""):
    """导出为 Markdown（可再次导入，形成备份闭环）；format=json 保留多库元数据。"""
    entries = retrieval.load_kb()
    if collection:
        cid = _require_collection(collection)
        entries = [e for e in entries if (e.get("collection") or retrieval.DEFAULT_COLLECTION) == cid]
    if format == "json":
        return JSONResponse(
            {"version": 2, "kb": entries, "collections": _collection_counts()},
            headers={"Content-Disposition": "attachment; filename=bigrobot-kb.json"},
        )
    return PlainTextResponse(
        kb_store.export_markdown(entries),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bigrobot-kb.md"},
    )
