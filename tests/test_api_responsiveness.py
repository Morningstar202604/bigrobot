"""事件循环不被同步调用卡死：文档导入期间 /healthz 必须仍然秒回。

这是对一类真实缺陷的回归护栏：`async def` 路由里直接跑同步解析/落库，
会把整个事件循环占住——实测导入 291 段 docx 时 /healthz 峰值 2218ms（空闲 p50 1.48ms），
整站在导入期间不可用。修复手段是 starlette 的 run_in_threadpool，
本用例用最朴素的方式验证：一个慢请求进行中，另一个请求能否按时返回。
"""
import io
import time

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("docx")

ASGI_HEADERS = {"X-Admin-Token": "test-admin-token"}


def _docx_bytes(paragraphs: int = 291) -> bytes:
    from docx import Document

    doc = Document()
    for i in range(paragraphs):
        doc.add_heading(f"第 {i + 1} 节 退换货与时效说明", level=2)
        doc.add_paragraph(
            f"问：订单已签收 {i + 1} 天，包装破损还能退吗？"
            "答：签收 7 天内支持无理由退货，破损需上传开箱视频，运费由商家承担。"
        )
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def _poll_healthz(client, samples: int, running) -> list[float]:
    """在长任务进行中持续打 /healthz，返回每次耗时（ms）。"""
    latencies: list[float] = []
    for _ in range(samples):
        if not running():
            break
        t0 = time.perf_counter()
        r = await client.get("/healthz")
        latencies.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
        await __import__("asyncio").sleep(0.01)
    return latencies


async def test_healthz_responsive_during_document_import(app):
    import asyncio

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/healthz")  # 预热（第一次要建连接池/读 KB）

        done = False
        latencies: list[float] = []

        async def do_import():
            nonlocal done
            try:
                files = {"file": ("handbook.docx", _docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
                r = await client.post("/api/kb/import/document", files=files, headers=ASGI_HEADERS, timeout=60)
                assert r.status_code == 200, r.text
            finally:
                done = True

        task = asyncio.create_task(do_import())
        latencies = await _poll_healthz(client, samples=80, running=lambda: not done)
        await task

    assert len(latencies) >= 5, "长任务太快结束，没采到足够样本"
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
    # 看 p50/p95 而不是 max：局部 C 调用（lxml 解压/GC）仍可能短暂占住 GIL，
    # 单次尖峰不代表事件循环被长期卡死；修复前是 p50≈2200ms，一眼就能区分。
    assert p50 < 20, f"导入期间 /healthz p50 {p50:.0f}ms，事件循环被同步调用占住了"
    assert p95 < 100, f"导入期间 /healthz p95 {p95:.0f}ms，同步调用占住了事件循环"
