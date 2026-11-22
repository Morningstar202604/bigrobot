"""开源资源填充目录：把工具/图片/技能/表情/知识库/插件/MCP 的来源与当前数量汇总。

只做只读统计与目录展示，不负责安装：安装动作分别落在 tools、skills、extensions、
mcp_client、KB store 和表情目录，避免这里变成第二个写入入口。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core import extensions, mcp_client, paths, retrieval, skills


TOOL_NAMES = [
    "uuid_gen", "slugify", "diff_text", "json_query",
    "toml_to_json", "csv_to_json", "jwt_decode", "markdown_toc",
]
UPSTREAM_SKILL_IDS = [
    "builtin-docx-pro", "builtin-pdf-pro", "builtin-pptx-pro", "builtin-xlsx-pro",
    "builtin-mcp-builder", "builtin-webapp-testing", "builtin-frontend-design",
    "builtin-algorithmic-art", "builtin-skill-creator",
]


def _images_dir() -> Path:
    raw = os.environ.get("BIGROBOT_OPENSOURCE_IMAGES", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "assets" / "opensource" / "images" / "avatars"


def _emote_dir() -> Path:
    raw = os.environ.get("GATEWAY_EMOTE_DIR", "").strip()
    return Path(raw) if raw else Path.home() / "napcat" / "emotes"


def _emote_count() -> int:
    p = _emote_dir() / "index.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return 0
        return sum(1 for i in items if isinstance(i, dict)
                   and str(i.get("group") or "").startswith("opensource"))
    except (OSError, ValueError):
        return 0


def _kb_count() -> int:
    return sum(1 for e in retrieval.load_kb()
               if str(e.get("collection") or "") == "opensource-docs")


def _skill_count() -> int:
    items = skills.normalize_items((__import__("core.config", fromlist=["get_config"]).get_config()
                                   .get("skills") or {}).get("items"))
    return sum(1 for s in items if s.get("id") in UPSTREAM_SKILL_IDS)


def _mcp_count() -> int:
    return sum(1 for s in mcp_client.list_servers() if s.get("enabled") and s.get("tools"))


def status() -> dict:
    items = [
        {
            "id": "tools", "name": "内置工具", "count": len(TOOL_NAMES),
            "summary": "UUID / slug / diff / JSON 路径 / TOML / CSV / JWT / Markdown 目录",
            "source": "https://github.com/modelcontextprotocol/servers",
            "license": "MIT / Apache-2.0",
            "detail": "纯函数实现，无网络、无 shell、无任意文件路径。",
        },
        {
            "id": "images", "name": "图片素材", "count": len(list(_images_dir().glob("*.png"))),
            "summary": "12 个开源机器人头像（256×256 PNG）",
            "source": "https://github.com/dicebear/dicebear",
            "license": "DiceBear MIT；Bottts 个人/商用免费",
            "detail": "放在 assets/opensource/images/avatars，可作为角色头像或占位素材。",
            "files": [p.name for p in sorted(_images_dir().glob("*.png"))],
        },
        {
            "id": "skills", "name": "技能", "count": _skill_count(),
            "summary": "Word / PDF / PPT / Excel / MCP 开发 / 网页验收 / 前端设计 / 生成艺术 / 技能编写",
            "source": "https://github.com/anthropics/skills",
            "license": "Apache-2.0",
            "detail": "上游 SKILL.md 已快照到 assets/opensource/skills/anthropic；提示词按 BigRobot 工具名改写。",
        },
        {
            "id": "emotes", "name": "表情库", "count": _emote_count(),
            "summary": "Noto 42 张 + 贴吧经典 54 张 + 黑化/网络梗 14 张",
            "source": "https://github.com/googlefonts/noto-emoji / https://github.com/walinejs/emojis / 本地生成",
            "license": "Noto Apache-2.0；贴吧 GPL-3.0-or-later（原图版权归百度）；黑化/梗图原创",
            "detail": "分组 opensource-noto / opensource-tieba / opensource-meme；标签在 napcat/emotes/tags.json。",
        },
        {
            "id": "kb", "name": "知识库", "count": _kb_count(),
            "summary": "Python / FastAPI / Git / Docker / SQL / HTTP / 安全 / MCP 共 40 条原创摘要",
            "source": "https://docs.python.org / https://fastapi.tiangolo.com / https://owasp.org / https://modelcontextprotocol.io",
            "license": "按来源标注（PSF / MIT / Apache-2.0 / CC-BY-SA-4.0 等）",
            "detail": "集合 opensource-docs；每条保留 source 和 license 字段，可按主题召回。",
        },
        {
            "id": "plugins", "name": "插件", "count": len([x for x in extensions.list_items() if x.get("enabled")]),
            "summary": "Open-Meteo 天气 / GitHub 仓库 / PyPI 包 / npm 包",
            "source": "https://api.open-meteo.com / https://docs.github.com/rest / https://pypi.org / https://registry.npmjs.org",
            "license": "各 API 服务条款；扩展代码 MIT",
            "detail": "只读 GET，固定公网 base_url；已装进 data/extensions。",
        },
        {
            "id": "mcp", "name": "MCP", "count": _mcp_count(),
            "summary": "Sequential Thinking / Memory Graph / Time / Fetch",
            "source": "https://github.com/modelcontextprotocol/servers",
            "license": "MIT / Apache-2.0",
            "detail": "stdio 方式接入；Memory 标为 write，其余只读。",
        },
    ]
    return {"items": items, "total": sum(int(x["count"]) for x in items)}
