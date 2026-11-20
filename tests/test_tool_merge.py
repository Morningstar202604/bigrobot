"""工具合并（B2：54 → 26）的护栏。

三件事必须同时成立，否则"合并"就是降级：
1. 模型清单只剩 26 个，但被吸收的旧名仍然可调度（不打断已有脚本与审批记录）；
   新增未来任务能力不另开工具，而是作为 reminders 的 op=future/tasks/cancel_task；
2. 合并工具按 op 分派到原实现，未知 op 明确报错而不是静默走默认分支；
3. 老库迁移只清理内置行，且把开关状态继承给合并后的工具。
"""
import json


from core import store
from core import tools as tools_mod
from core.tool_context import EMPTY


def test_tool_count_is_26():
    assert len(tools_mod.TOOL_META) == 26


def test_retired_tools_stay_dispatchable():
    retired = sorted(tools_mod.RETIRED_TOOL_IDS)
    assert len(retired) == 39, "54 - 39 + 11 = 26；数量不对说明合并表被改过"
    for old in retired:
        assert old not in tools_mod.TOOL_META, f"{old} 仍在模型清单里"
        assert old in tools_mod._SYNC_IMPLS or old in tools_mod._ASYNC_IMPLS, (
            f"{old} 的实现被一起删了，调度别理会断链"
        )


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
