"""开源小工具的纯函数回归：不联网、不碰真实文件。"""
import asyncio

from core import tools
from core.tool_context import ToolContext


def _call(name, **args):
    return asyncio.run(tools.invoke(name, args, ToolContext()))


def test_uuid_gen_count():
    r = _call("uuid_gen", count="3")
    assert r["connected"] is True
    assert len(r["values"]) == 3
    assert all(len(x) == 36 for x in r["values"])


def test_slugify_keeps_chinese_and_folds_punctuation():
    r = _call("slugify", text="BigRobot：开源资源 / 2026!", max_length="30")
    assert r["slug"].startswith("bigrobot-")
    assert "开源资源" in r["slug"]
    assert "：" not in r["slug"]


def test_diff_text_reports_changed_lines():
    r = _call("diff_text", old="a\nb", new="a\nc")
    assert r["changed"] is True
    assert r["changed_lines"] >= 2


def test_json_query_nested_path():
    r = _call("json_query", data='{"a":[{"b":1}]}', path="$.a[0].b")
    assert r["note"] == "1"


def test_csv_to_json_headers():
    r = _call("csv_to_json", text="name,score\n零,99")
    assert r["rows"] == [{"name": "零", "score": "99"}]


def test_toml_to_json():
    r = _call("toml_to_json", text='title = "BigRobot"\n[owner]\nname = "zero"')
    assert r["json"]["title"] == "BigRobot"
    assert r["json"]["owner"]["name"] == "zero"


def test_jwt_decode_does_not_claim_verified():
    token = "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjMifQ."
    r = _call("jwt_decode", token=token)
    assert r["verified"] is False
    assert r["payload"]["sub"] == "123"


def test_markdown_toc_nested_headings():
    r = _call("markdown_toc", text="# A\n## B\n### C", max_level="2")
    assert "- [A](#a)" in r["note"]
    assert "  - [B](#b)" in r["note"]
    assert "C" not in r["note"]


def test_plugin_package_queries_route_to_api_not_web_search():
    from core import tools as tm
    enabled = {"pypi_package_info", "npm_package_info", "github_repo_info", "web_search"}
    cases = {
        "查一下 PyPI 上 fastapi 的最新版本和许可证。": ("pypi_package_info", {"name": "fastapi"}),
        "查一下 npm 上 react 的最新版本。": ("npm_package_info", {"name": "react"}),
        "查一下 GitHub 上 modelcontextprotocol/servers 的 stars。":
            ("github_repo_info", {"owner": "modelcontextprotocol", "repo": "servers"}),
    }
    for q, expected in cases.items():
        assert tm.detect_tool(q, enabled) == expected


def test_plugin_json_is_formatted_for_chat():
    import json
    from core.pipeline import _format_plugin_note
    pypi = json.dumps({"info": {"version": "0.1.0", "license": "MIT",
                                "requires_python": ">=3.9", "summary": "fast api"}})
    assert "0.1.0" in _format_plugin_note("pypi_package_info", pypi)
    assert "MIT" in _format_plugin_note("pypi_package_info", pypi)
    npm = json.dumps({"dist-tags": {"latest": "19.3.1"}, "license": "MIT",
                       "description": "React"})
    assert "19.3.1" in _format_plugin_note("npm_package_info", npm)
    gh = json.dumps({"full_name": "a/b", "stargazers_count": 10,
                      "language": "Python", "license": {"spdx_id": "MIT"}})
    out = _format_plugin_note("github_repo_info", gh)
    assert "10 stars" in out and "MIT" in out


def test_extension_formatters_use_latest_and_license_expression():
    from core.extensions import _fmt_npm, _fmt_pypi
    assert "19.3.1" in _fmt_npm({"version": "19.3.1", "license": "MIT"})
    assert "MIT" in _fmt_pypi({"info": {"version": "1.0", "license_expression": "MIT"}})


def test_tieba_and_dark_emote_routing():
    from core import intent
    from core.tools import tool_search_emote
    from core.tool_context import EMPTY
    assert intent.classify("发个贴吧滑稽").name == intent.INTENT_EMOTE
    assert intent.emote_keyword("发个贴吧滑稽") == "贴吧 滑稽"
    assert intent.emote_keyword("发个黑化冷笑") == "黑化 冷笑"
    res = tool_search_emote(EMPTY, keyword="黑化 冷笑")
    assert res.get("sample_path", "").endswith("dark_heihua_lengxiao.png")


def test_naiwa_emote_routing():
    from core import intent
    from core.tools import tool_search_emote
    from core.tool_context import EMPTY
    assert intent.classify("发个奶蛙大笑").name == intent.INTENT_EMOTE
    assert intent.emote_keyword("发个奶蛙大笑") == "奶蛙 大笑"
    assert intent.classify("奶蛙躺平").name == intent.INTENT_EMOTE
    res = tool_search_emote(EMPTY, keyword="奶蛙 大笑")
    assert res.get("sample_path", "").endswith("naiwa_laugh.gif")
