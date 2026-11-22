"""技能（Skills）：把「一组能力 + 使用指南」注入系统提示词。

与工具的区别：
- 工具（tools）是模型可以**调用**的函数；
- 技能（skills）是告诉模型**什么时候该用哪个工具、按什么流程做**的说明书。
  模型不会因为注册了 read_file 就知道「先读目录再读文件」，技能补的正是这一层。

配置存 config.skills.items（数组），每项：
  {id, name, description, guide, enabled, builtin}

内置技能永远存在（可停用、不可删除），自定义技能可增删。
"""
from __future__ import annotations

import re
import uuid

BUILTIN_SKILLS: list[dict] = [
    {
        "id": "builtin-web-research",
        "name": "联网查证",
        "description": "需要实时信息、新闻、价格、版本号时先搜再答",
        "guide": (
            "遇到时效性问题（新闻/价格/版本/政策变动）先用 web_search，"
            "需要细节再对最相关的一两条用 read_source。只引用你真正读到过的内容，"
            "搜不到就直说没查到，不要用记忆里的旧数据冒充最新。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-file-ops",
        "name": "文件操作",
        "description": "读写本机文件时先看目录再动手",
        "guide": (
            "涉及本机文件时：先用 list_files 看清目录结构，再用 read_file 读具体文件；"
            "写文件前若不确定目标是否存在，先 read_file 确认。路径必须落在执行器允许的根目录内，"
            "被策略拒绝就如实说明，不要换个路径硬试。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-reminder",
        "name": "日程提醒",
        "description": "把「几点做什么」落成一条真实提醒",
        "guide": (
            "用户提到要在某个时间做某事时，调用 remind 建提醒，"
            "把相对时间（10 分钟后 / 明天 9 点）原样传给 when，由系统统一解析。"
            "建完用一句话确认具体时间，不要只回「好的」。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-memory",
        "name": "长期记忆",
        "description": "值得跨会话记住的偏好与事实才写入",
        "guide": (
            "只在用户表达了稳定偏好或长期事实（口味、住址、称呼、工作习惯）时调用 remember；"
            "一次性的临时信息不要写。回答前可用 recall_memory 查一下有没有相关记录，"
            "有就自然带出，别复述「根据我的记忆」这种机制腔。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-doc",
        "name": "文档解析",
        "description": "PDF/Word/Excel 先解析再回答",
        "guide": (
            "用户给了 PDF/DOCX/XLSX 路径或链接时，用 parse_document 取正文再回答；"
            "解析失败要说清是格式不支持还是文件加密，别假装读过。"
        ),
        "builtin": True,
    },

    # ---- 以下来自 Apache-2.0 的 anthropics/skills，按 BigRobot 的工具名做了改写 ----
    {
        "id": "builtin-docx-pro",
        "name": "Word 文档",
        "description": "创建/编辑 .docx，保留样式、表格、目录和修订",
        "guide": (
            "处理 .docx 先判断是新建、改写还是只读取：新建用 docx-js 或 python-docx 生成段落/表格，"
            "改已有文件先解包改 word/document.xml 再打包，只读可用 pandoc 转 Markdown。"
            "表格要同时设列宽和单元格宽度；标题用内置 Heading 样式，目录才会收录；"
            "不要在正文里手打项目符号或换行符，分别用 numbering 和独立段落。"
            "输出后至少打开检查页数、表格宽度和中文断行。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-pdf-pro",
        "name": "PDF 处理",
        "description": "读取、合并、拆分、加水印、填表单和 OCR",
        "guide": (
            "PDF 先分清文本型和扫描型：文本型用 pypdf 提取文字/页数，扫描型先 OCR 再回答。"
            "合并、拆分、旋转用 pypdf 的 PdfReader/PdfWriter；加水印先做单页模板再 merge；"
            "填 AcroForm 用 pypdf 的 get_fields/update_page_form_field_values。"
            "加密或损坏的 PDF 要如实报错，不要假装读到了内容。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-pptx-pro",
        "name": "演示文稿",
        "description": "创建、读取和修改 .pptx，控制版式与母版",
        "guide": (
            "做 PPT 先定版式和叙事顺序，再写 pptxgenjs 脚本；先设 `pres.layout` 再加页，"
            "否则默认 10×5.625 英寸会把右侧内容裁掉。改已有 PPT 先解包改 slideN.xml，"
            "不要用新建脚本覆盖模板。每页只放一个主结论，图表和文字要有来源；"
            "导出后检查溢出、字体缺失和图片比例。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-xlsx-pro",
        "name": "电子表格",
        "description": "创建/编辑 xlsx，公式、格式、清洗和图表",
        "guide": (
            "表格任务先确认交付物是 xlsx 还是 CSV；新建/改格式用 openpyxl，批量数据用 pandas。"
            "公式要写成 `=SUM(B2:B9)` 而不是 Python 算好的硬编码值；openpyxl 不计算公式，"
            "写完必须重算并检查错误值。改已有文件要沿用它的字体、列宽和输入区标记，"
            "不要重新设计一套格式。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-mcp-builder",
        "name": "MCP 开发",
        "description": "按官方规范设计、实现和测试 MCP 服务器",
        "guide": (
            "做 MCP 服务器先明确要暴露的 tools/resources/prompts，再选 Python FastMCP 或 TS SDK。"
            "工具名用 `服务_动作` 前缀，描述写清参数、返回和错误；返回要分页/截断，"
            "错误信息要告诉调用方下一步怎么改。stdio 服务器 stdout 只能走 JSON-RPC，日志写 stderr；"
            "默认只读，写操作加确认和审计。上线前用 MCP Inspector 或客户端实际 list/call 一遍。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-webapp-testing",
        "name": "网页验收",
        "description": "用 Playwright 跑本地 Web 应用的真实交互",
        "guide": (
            "验收本地网页优先写 Playwright 脚本，不要只看 HTML 源码：先起服务，"
            "`page.goto` 后等 networkidle，截图/读 DOM 找选择器，再执行点击、输入、提交。"
            "每个关键路径至少覆盖成功、空数据、错误三种状态；失败时保存截图和控制台日志，"
            "不要用“看起来应该没问题”代替真实点击。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-frontend-design",
        "name": "前端设计",
        "description": "做出有明确视觉主张、不像模板的前端",
        "guide": (
            "先确定产品主题、受众和页面唯一任务，再从主题里提取颜色、字体和结构，"
            "不要直接套通用渐变卡片。标题字体承担性格，正文控制行长；编号/分割线只在内容真的有顺序时用。"
            "动效只保留一个开场或一个关键交互，不要给每张卡都加悬浮动画。"
            "交付前检查亮暗主题、移动端断点和真实中文长文本。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-algorithmic-art",
        "name": "生成艺术",
        "description": "用 p5.js 做可复现的算法艺术，而不是随机噪点",
        "guide": (
            "生成艺术先写一段“算法哲学”：它研究什么力量、如何在时间里生长，再把它翻译成 p5.js。"
            "用固定 seed 保证可复现，参数面板暴露粒子数、噪声尺度、配色等关键变量；"
            "输出 HTML 交互页和独立 JS，不要只交一张截图。"
            "避免直接复制在世艺术家的构图，参考算法思想而不是作品。"
        ),
        "builtin": True,
    },
    {
        "id": "builtin-skill-creator",
        "name": "技能编写",
        "description": "把重复流程写成可触发、可评估的 Skill",
        "guide": (
            "写技能先定“什么时候触发、做完什么算成功”，再写步骤和边界；"
            "描述里放用户会说的原话关键词，正文只写模型不知道的领域知识，不要复述通用常识。"
            "给 3~5 个真实测试提示，跑一遍看是否该触发、是否按步骤完成；"
            "失败就改描述或步骤，不要靠加更多形容词。技能文件保持短，脚本放同目录。"
        ),
        "builtin": True,
    },
 ]


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return base or f"skill-{uuid.uuid4().hex[:6]}"


def normalize_items(items) -> list[dict]:
    """校验并补全技能定义：内置项缺失就补回，字段类型错误按默认值修。"""
    out: list[dict] = []
    seen: set[str] = set()
    for raw in items if isinstance(items, list) else []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        sid = str(raw.get("id") or "").strip() or _slug(name)
        if sid in seen:
            continue
        seen.add(sid)
        out.append({
            "id": sid,
            "name": name[:40],
            "description": str(raw.get("description") or "")[:200],
            "guide": str(raw.get("guide") or "")[:2000],
            "enabled": False if raw.get("enabled") is False or raw.get("enabled") == 0 else True,
            "builtin": bool(raw.get("builtin")),
        })
    # 内置技能必须存在（用户可以停用，但删不掉）：缺哪个补哪个
    for b in BUILTIN_SKILLS:
        if not any(x["id"] == b["id"] for x in out):
            out.append(dict(b, enabled=True))
    return out


def render(cfg: dict, allowed_ids: set[str] | None = None) -> str:
    """把启用的技能渲染成提示词片段；allowed_ids=None 表示不按角色收缩。"""
    items = normalize_items((cfg.get("skills") or {}).get("items"))
    active = [s for s in items if s["enabled"] and (s["guide"] or s["description"])
              and (allowed_ids is None or s["id"] in allowed_ids)]
    if not active:
        return ""
    lines = ["【可用技能】按场景选用，不要为了用技能而用："]
    for s in active:
        body = s["guide"] or s["description"]
        lines.append(f"- {s['name']}：{body}")
    return "\n".join(lines)


def names(cfg: dict) -> list[str]:
    return [s["name"] for s in normalize_items((cfg.get("skills") or {}).get("items"))
            if s["enabled"]]
