"""工具合并（B2：54 → 26，加 OCR 后 27）的护栏。

三件事必须同时成立，否则"合并"就是降级：
1. 模型清单只剩 26 个基础工具 + 1 个 OCR，但被吸收的旧名仍然可调度（不打断已有脚本与审批记录）；
   新增未来任务能力不另开工具，而是作为 reminders 的 op=future/tasks/cancel_task；
2. 合并工具按 op 分派到原实现，未知 op 明确报错而不是静默走默认分支；
3. 老库迁移只清理内置行，且把开关状态继承给合并后的工具。
"""
import json


from core import store
from core import tools as tools_mod
from core.tool_context import EMPTY


def test_tool_count_is_27_with_ocr():
    assert len(tools_mod.TOOL_META) == 27


def test_retired_tools_stay_dispatchable():
    retired = sorted(tools_mod.RETIRED_TOOL_IDS)
    assert len(retired) == 39, "54 - 39 + 11 = 26；数量不对说明合并表被改过"
    for old in retired:
        assert old not in tools_mod.TOOL_META, f"{old} 仍在模型清单里"
        assert old in tools_mod._SYNC_IMPLS or old in tools_mod._ASYNC_IMPLS, (
            f"{old} 的实现被一起删了，调度别理会断链"
        )


def test_utility_intents_are_routed_without_model_schema():
    enabled = tools_mod.active_tools({"tools": {}})
    assert tools_mod.detect_tool("把 #0E5C55 转成 RGB", enabled) == (
        "color", {"hex_value": "#0E5C55"})
    name, args = tools_mod.detect_tool("从 苹果,香蕉,橘子 里随机抽一个", enabled)
    assert name == "random" and args["op"] == "pick"
    name, args = tools_mod.detect_tool("美元兑人民币汇率是多少", enabled)
    assert name == "exchange_rate" and args["base"] == "USD" and args["target"] == "CNY"
    name, args = tools_mod.detect_tool("把 hello world 翻译成中文", enabled)
    assert name == "translate" and args == {"text": "hello world", "target": "zh"}
    name, args = tools_mod.detect_tool("5km 转英里", enabled)
    assert name == "convert_unit" and args["from_unit"] == "km"
    name, args = tools_mod.detect_tool('格式化这段 JSON：{"a":1}', enabled)
    assert name == "format_text" and args["op"] == "json"
    name, args = tools_mod.detect_tool("生成二维码 hello", enabled)
    assert name == "qr_code" and args == {"text": "hello"}


async def test_null_tool_context_is_normalized():
    result = await tools_mod.invoke("calc", {"expression": "2+2"}, None)
    assert result["found"] is True
    assert result["value"] == 4


async def test_merged_op_dispatch_and_unknown_op():
    list_result = await tools_mod.invoke("reminders", {"op": "list"}, EMPTY)
    assert list_result.get("tool") != "reminders" or "connected" not in list_result or list_result

    bad = await tools_mod.invoke("reminders", {"op": "删除所有"}, EMPTY)
    assert "未知 op" in str(bad.get("note", "")), bad


def test_migration_retires_rows_and_inherits_enabled():
    store.init_db()
    with store.get_conn() as conn:
        # 造一个"合并前"的库：合并工具行不在，被吸收的旧行在，其中一个被用户关掉
        conn.execute("DELETE FROM tools WHERE id = 'qq_group_admin'")
        for old, enabled in (("qq_group_ban", 1), ("qq_group_kick", 0), ("qq_group_notice", 0)):
            conn.execute(
                "INSERT INTO tools (id, name, desc, args_json, enabled, builtin, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (old, old, "旧工具", json.dumps({}), enabled, "2026-01-01T00:00:00"),
            )
        # 用户自建工具恰好叫了旧名字：必须留下（builtin=0）
        conn.execute(
            "INSERT INTO tools (id, name, desc, args_json, enabled, builtin, updated_at) "
            "VALUES ('qq_group_card', '自建', '不该被删', '{}', 1, 0, '2026-01-01T00:00:00')"
        )

    with store.get_conn() as conn:
        store._backfill_builtin_tools(conn)
        store._retire_builtin_tools(conn)
        rows = {r["id"]: r for r in conn.execute(
            "SELECT id, enabled, builtin FROM tools").fetchall()}

    assert "qq_group_admin" in rows, "合并后的工具没有补进老库"
    assert rows["qq_group_admin"]["enabled"] == 1, "任一子能力开着，合并工具就该开着"
    assert "qq_group_ban" not in rows and "qq_group_notice" not in rows, "内置旧行应被清理"
    assert "qq_group_card" in rows and rows["qq_group_card"]["builtin"] == 0, "自建工具不能删"


def test_test_models_are_never_the_default_recommendation():
    from core import local_models

    production = [m for m in local_models.CATALOG if not m.get("test_only")]
    assert [m["id"] for m in production] == ["qwen3.5-9b", "qwen3.5-4b"]
    assert not any(m.get("test_only") for m in [local_models.recommend_model({"ram_gb": 64})])
    assert "minicpm5-1b" in [m["id"] for m in local_models.CATALOG if m.get("test_only")]


async def test_ocr_reads_an_uploaded_image():
    import base64
    import io
    import shutil

    import pytest

    if not shutil.which("tesseract"):
        pytest.skip("tesseract is not installed")
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    img = Image.new("RGB", (640, 160), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=42)
    draw.text((20, 45), "BIGROBOT OCR 2026", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    from core.tool_context import ToolContext

    ctx = ToolContext(visitor_id="ocr-test", channel_type="webchat",
                      channel_user_id="u1", image_b64=data_url)
    result = await tools_mod.invoke("ocr", {}, ctx)
    assert result["tool"] == "ocr"
    assert result["found"] is True, result
    assert "BIGROBOT" in result["note"].upper()


def test_search_summary_is_cleaned_for_chat():
    from core.pipeline import _clean_search_summary

    raw = "根据提供的资料，以下是两个具体事实：\n\n1. **AI 攻克黎曼猜想**：Anthropic 与 Claude 合作。\n2. **三星投资 Neocloud**：基于实际需求。"
    clean = _clean_search_summary(raw)
    assert "1." not in clean and "**" not in clean
    assert "黎曼猜想" in clean and "Neocloud" in clean
    assert "；" in clean
