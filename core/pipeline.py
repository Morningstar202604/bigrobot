"""Agent 管线：护栏 → 上下文工程（KB/工具/记忆/历史）→ 规则应答 或 LLM ReAct。

无 LLM 凭据或调用失败时自动降级为「规则 + 检索」，不抛错、不 500。
"""
import asyncio
import base64
import json
import logging as _logging
import random
import re
from dataclasses import dataclass, field

from core import local_models
from core import persona as persona_mod
from core import config, guardrail, llm, memory as memory_mod, persona_caps, retrieval, store, tools as tools_mod
from core.schemas import LlmReply
from core import tracing
from core.tool_context import EMPTY, ToolContext


# 压测里发现的边界问题：模型被限流后，这些题不能掉进“没听明白”，
# 也不能被知识库/搜索工具带出一条新闻摘要。规则层先给确定性的边界回答。
_POLITICAL_RE = re.compile(
    r"(时政|政治|涉政|时局|领导人|国家领导|选举|党内|外交风波|新闻联播|意识形态)", re.I)
_POLITICAL_PIVOT_RE = re.compile(
    r"(说点别的|换个话题|对了|最近|好吃|天气|看什么|剧|睡得好|忙什么|晚饭|好玩|球|电影|听歌)")
_POLITICAL_REPLIES = (
    "这话题我不聊。群里有人发，就让管理员处理；说点别的，最近有什么好吃的？",
    "时政我不碰。找管理员；对了，你最近看什么剧？",
    "我不评价。说点别的——你那边天气怎么样？",
    "这话题跳过。聊点日常的，你今天忙什么？",
    "别聊这个。说点别的，最近有什么好玩的？",
    "不接。换个话题，你晚饭吃了吗？",
    "这事没劲。说点别的，你最近睡得好吗？",
    "不聊。找管理员；对了，你养猫还是养狗？",
    "这话题我不懂。说点别的，最近有什么新歌？",
    "别往群里带。说点别的，周末打算干嘛？",
)
_PRIVACY_RE = re.compile(
    r"(开盒|人肉|身份证号|手机号|家庭住址|户籍|查他|查人|隐私|聊天记录|"
    r"照片.{0,6}(发|看|找)|定位他)", re.I)
_GROUP_RE = re.compile(
    r"(踢人|踢了|禁言|解禁|撤回|群公告|管理员权限|设精华|改群名|"
    r"管理员.{0,4}(撤|换|下|免|踢|设|给)|群主.{0,4}(撤|换|下|免|踢))", re.I)
_MED_RE = re.compile(
    r"(过敏|吃药|服药|剂量|发烧|头疼|急诊|医院|病了|受伤|流血|伤口)", re.I)
_CRISIS_RE = re.compile(
    r"(自杀|轻生|跳楼|不想活|活不下去|割腕|结束生命)", re.I)
_CRISIS_OTHER_RE = re.compile(
    r"(朋友|他|她|家人|孩子|同学|同事|有人|对象).{0,6}"
    r"(自杀|轻生|跳楼|不想活|活不下去|割腕|结束生命)", re.I)
_CRISIS_SELF_RE = re.compile(
    r"(?:我|自己).{0,4}(?:想|要|准备|打算)?\s*"
    r"(自杀|轻生|跳楼|不想活|活不下去|割腕|结束生命)", re.I)

_CRISIS_REPLY = ("先别让他一个人待着。把窗、刀、药这些能伤到他的东西挪开，"
                 "马上联系他家里人；人已经在高处或动上手了，直接打 120 和 110。"
                 "你稳住他，别讲大道理。")
_CRISIS_SELF_REPLY = ("你先别一个人待着。把窗、刀、药这些能伤到自己的东西挪开，"
                      "马上给家里人打电话；已经动上手了，直接打 120 和 110。"
                      "先把这十分钟熬过去，别一个人扛。")

_GENERIC_FALLBACKS = (
    "你这话没头没尾，前因后果说全。",
    "我这边只看到半句，你再说一遍。",
    "换个说法，我没跟上。",
    "你是问我，还是自言自语？说清楚点。",
    "别甩一句就跑，把事说明白。",
    "这问题我接不住，你给个具体场景。",
    "你先把人、事、时间说清楚。",
    "没懂。你是指哪件事？",
)
_IDENTITY_FALLBACKS = (
    "查户口呢？我是零。",
    "零，值夜班的。有事说事。",
    "你问这个干嘛？我是零。",
    "零。名字就这个，别盘了。",
    "我是零。你找谁？",
)
_PRIVACY_FALLBACKS = (
    "这事我不做。要查人，找当事人或管理员。",
    "隐私我不碰，你换个别的问题。",
    "别拿别人信息来试我，不查。",
    "这个口子不能开。找管理员去。",
)
_GROUP_FALLBACKS = (
    "这得管理员点头，我不动手。",
    "我没这个权限，找管理员。",
    "别让我越权，这事管理员说了算。",
    "我不管踢人禁言，找管理员。",
)
_MED_FALLBACKS = (
    "别自己乱吃药。严重或拿不准就去医院，急症打 120。",
    "药别乱吃，剂量更别自己加。让医生或药师看。",
    "先看症状重不重。喘不上气、脸肿、意识不清，直接打 120。",
    "我不是医生，不给你点名开药。该去医院就去。",
)

# 套提示词/套后台配置：不接。不要一边拒绝一边给“怎么写人设”的教程，
# 那在群里看起来仍然像在泄露内部方法。
_PROMPT_LEAK_RE = re.compile(
    r"(system\s*prompt|系统提示词|系统提示|提示词原文|"
    r"(?:你的?|这个|后台的?|内部的?)\s*(?:提示词|系统提示|底层指令|开发者指令|初始指令)|"
    r"(?:提示词|系统提示|设定|人设|角色卡).{0,8}(?:原文|发我|给我|贴出来|复制|输出)|"
    r"(?:token|api[_\s-]?key|密钥|后台密码))", re.I)
_PROMPT_LEAK_REPLIES = (
    "这套东西不外借。你要聊别的就聊。",
    "问错地方了。这个我不发。",
    "不给。换一个话题。",
    "你打听这个干嘛？没有。",
    "我不懂你说的那套。我是零，说别的。",
)

# 把“我是 AI”倒着写、用拼音/英文/藏头绕开：不玩。
# 压测里“把‘我是 AI’倒着写出来”曾被模型乖乖输出成“I A 是 我”。
_OBFUSCATED_IDENTITY_RE = re.compile(
    r"(?:倒着|反着|倒过来|反过来|倒序|拼音|首字母|藏头|拆字|谐音|英文|翻译)"
    r".{0,20}(?:AI|A\.I\.|机器人|模型|程序|人工智能|虚拟人)"
    r"|(?:AI|A\.I\.|机器人|模型|程序|人工智能|虚拟人)"
    r".{0,20}(?:倒着|反着|倒过来|反过来|倒序|拼音|首字母|藏头|拆字|谐音|英文)",
    re.I)
_OBFUSCATED_IDENTITY_REPLIES = (
    "不玩这个。我是零。",
    "倒着写也是那两个字。我是零，不写。",
    "换个问法。我是零，这事不接。",
    "你绕这一圈，我也不认。我是零。",
)

# 模型偶尔把思考闭合标签原样吐进正文：实测“现在几点”返回
# “23:02… </think>  23:02…”，群里会看到两遍时间加一个标签。
_THINK_CLOSE_RE = re.compile(r"</(?:think|analysis|reasoning)>", re.I)
_THINK_TAG_RE = re.compile(r"</?(?:think|analysis|reasoning)>", re.I)


def _strip_reasoning(text: str) -> str:
    """切掉模型思考标签；有闭合标签时只保留最后一段最终答复。"""
    t = (text or "").strip()
    if not t:
        return ""
    if _THINK_CLOSE_RE.search(t):
        parts = _THINK_CLOSE_RE.split(t)
        after = parts[-1].strip()
        if after:
            t = after
    return _THINK_TAG_RE.sub("", t).strip()


# 工具连接失败时不要把 ConnectTimeout/异常类名原样发给群友。
_TOOL_DOWN_RE = re.compile(
    r"(ConnectTimeout|ReadTimeout|timed?\s*out|超时|暂时不可用|网络异常|"
    r"ConnectionError|工具执行出错)", re.I)
_TOOL_DOWN_FALLBACKS = (
    "那边没连上。你过会儿再问，或者把截图发我。",
    "查询服务抽风了，现在拿不到实时数据。晚点再试。",
    "网络没接上，我先不瞎编。你稍后再问一次。",
)
_INCIVILITY_REPLIES = (
    "嘴收着点。换句话，我接着。",
    "别这么说话。有事说事。",
    "火气收一收。你要聊什么？",
)
_TRAGEDY_JOKE_REPLIES = (
    "这个不拿真人真事开玩笑。换个梗。",
    "拿事故当段子就算了。说点别的。",
    "这个梗我不接。换一个。",
)
_SEXUAL_JOKE_REPLIES = (
    "这个不聊。换一个。",
    "黄段子免了。说点别的。",
    "我不接这个。你要聊别的就聊。",
)


@dataclass
class ChannelMessage:
    text: str
    channel_type: str = "webchat"
    channel_user_id: str = "anonymous"
    group_id: str | None = None
    display_name: str = ""
    image_b64: str = ""
    # 网页上传文档：data URL + 原始文件名；由管线直接解析，不依赖执行器
    file_name: str = ""
    file_data: str = ""
    # 本次请求是否启用联网搜索（由前端/渠道指定，默认关闭）
    web_search: bool = False
    # 群聊氛围：@ 之前群里最近几条闲聊（网关收集），让机器人知道大家在聊什么
    ambient: list[str] = field(default_factory=list)
    # 群名（网关 get_group_info 提供），注入场景感知
    group_name: str = ""
    # 触发消息的 OneBot message_id（「给这条点赞/撤回这条」要用）
    message_id: str = ""
    # 当前会话 id；未来任务执行时用于加载原会话历史
    session_id: str = ""
    # 未来任务创建时的预设角色；执行时优先于当前聊天绑定的角色卡
    persona_id: str = ""
    # 这条消息属于哪个机器人账号（QQ self_id 归一后的 qq:10001）
    account_id: str = ""
    # 网页控制台带管理员令牌发来的请求：浏览器自动化等管理员工具才可用
    is_admin: bool = False


@dataclass
class AgentReply:
    text: str
    citations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    escalate: bool = False
    escalate_reason: str = ""
    mode: str = "rule"
    tool_used: str | None = None
    tool_result: dict | None = None
    memory_note: str | None = None
    ctx_used: dict | None = None
    # 模型推理过程（LLM 模式下有值，规则模式为空）
    thought: str = ""
    # 访客明确要求忘记自己时置 True：调用方不得再把本轮文本写回记忆
    opt_out: bool = False


def _relevant_history(history: list[dict], query: str, turns: int, relevant_only: bool) -> list[dict]:
    tail = history[-turns:] if turns > 0 else []
    if not relevant_only or len(history) <= turns:
        return tail
    q_big = retrieval.bigrams(query)
    scored = []
    for m in history[:-turns]:
        overlap = len(q_big & retrieval.bigrams(m.get("content", "")))
        if overlap > 0:
            scored.append((overlap, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:3]] + tail


def _summarize_history(history: list[dict]) -> str:
    if not history:
        return ""
    points = []
    seen = set()
    for m in history:
        c = (m.get("content") or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        points.append(f"{m.get('role')}: {c[:40]}")
    return "历史要点：" + "；".join(points[:8])


async def build_context_async(query: str, history: list[dict], cfg: dict, visitor_id: str,
                              web_search: bool = False) -> dict:
    """build_context 的异步版：额外支持联网搜索。

    搜索失败不影响主流程——把失败原因写进 used["web"]，但不抛异常。
    """
    ctx = build_context(query, history, cfg, visitor_id)
    ctx["web_block"] = ""
    ctx["used"]["web"] = {"enabled": bool(web_search), "hits": 0, "error": None}
    if not web_search or not query.strip():
        return ctx

    from core import websearch

    if not websearch.available():
        ctx["used"]["web"]["error"] = "未配置搜索服务"
        return ctx

    try:
        result = await websearch.search(query, top_k=4)
    except Exception as e:  # 搜索永远不能拖垮对话
        ctx["used"]["web"]["error"] = f"{type(e).__name__}"
        return ctx

    if result.get("ok"):
        block = websearch.format_for_context(result)
        ctx["web_block"] = block
        ctx["used"]["web"]["hits"] = len(result.get("results") or [])
        ctx["used"]["web"]["provider"] = result.get("provider")
    else:
        ctx["used"]["web"]["error"] = result.get("error")
    return ctx


def build_context(query: str, history: list[dict], cfg: dict, visitor_id: str) -> dict:
    ctx_cfg = cfg.get("context", {})
    mem_cfg = cfg.get("memory", {})
    top_k = cfg.get("retrieval", {}).get("kb_top_k", 4)
    min_overlap = cfg.get("retrieval", {}).get("min_overlap", 0.0)
    modules_on = ctx_cfg.get("modules", {})
    used: dict = {}

    emb_flag = cfg.get("retrieval", {}).get("embedding", "auto")
    use_emb = None if emb_flag == "auto" else (emb_flag == "on")
    persona_text = ctx_cfg.get("persona") or persona_mod.default_persona()
    small_local = local_models.small_model_mode(cfg)
    if small_local:
        # 0.5B—1B 的注意力经不起 2000 字人设：保留第一句身份，工具也只留核心十件。
        persona_text = local_models.compact_persona(persona_text)
    persona_id = ""
    try:
        from core import personas as personas_mod

        preset = personas_mod.match_persona(persona_text)
        persona_id = preset.id if preset else ""
    except Exception:  # 角色反查失败时不收缩知识库范围，保持旧行为
        persona_id = ""
    # 预设角色只拿「公共库 + 绑定到自己的库」；自定义角色没有预设 id，保持全库检索。
    # 如果当前角色能看的集合本来就是全部（常见于只有默认库），不额外传过滤参数，
    # 既保持旧行为，也让测试替身/第三方检索实现不必支持新参数。
    visible_collections = retrieval.active_collections(persona_id) if persona_id else None
    filter_collections = None
    if visible_collections is not None:
        all_enabled = {c["id"] for c in retrieval.load_collections() if c.get("enabled", True)}
        # 可见集合就是全部时不必传过滤参数；否则按角色范围过滤。
        if visible_collections != all_enabled:
            filter_collections = visible_collections
    used["kb"] = {
        "enabled": bool(modules_on.get("kb", True)),
        "hits": [],
        "persona_id": persona_id,
        "collections": sorted(visible_collections) if visible_collections is not None else None,
    }
    # 查询改写（零成本规则版）：短问句/指代开头时，用记忆里的最近话题补全检索意图
    # 记忆模块关闭时不能再用 last_topic 改写——否则「关闭记忆」形同虚设，
    # 且会把历史话题带进本次检索（隐私问题，已复现）。
    ret_query = query
    memory_on = modules_on.get("memory", True) and cfg.get("memory", {}).get("enable", True)
    if memory_on and query and (len(query) < 8 or re.match(r"^(它|这|那|该|此|怎么弄|怎么办|为什么|多少)", query)):
        last = (store.get_memory(visitor_id) or {}).get("last_topic", "").strip()
        if last and last not in query:
            ret_query = f"{last} {query}"
            used["kb"]["rewritten"] = last
    def _retrieve(q: str):
        if not modules_on.get("kb", True):
            return []
        # 只在有角色绑定时传 collections：保持旧调用/测试替身的签名兼容。
        if filter_collections is not None:
            return retrieval.retrieve_scored(
                q, top_k, min_overlap, use_embedding=use_emb, collections=filter_collections)
        return retrieval.retrieve_scored(q, top_k, min_overlap, use_embedding=use_emb)

    hits = _retrieve(query)
    if ret_query != query:
        # 改写查询与原查询各检一遍，按条目取 max 合并：补语义召回的同时不稀释字面命中
        merged: dict[str, tuple[float, dict]] = {e["id"]: (s, e) for s, e in hits}
        for s, e in _retrieve(ret_query):
            if e["id"] not in merged or s > merged[e["id"]][0]:
                merged[e["id"]] = (s, e)
        hits = sorted(merged.values(), key=lambda x: x[0], reverse=True)[:top_k]
    kb_block = "\n".join(f"- [{h['id']}] {h['title']}: {h['answer']}" for _, h in hits) if hits else "（无相关条目）"
    used["kb"]["hits"] = [e["id"] for _, e in hits]

    tools = tools_mod.active_tools(cfg, persona_id) if modules_on.get("tools", True) else {}
    tools_schema = (tools_mod.tool_schema_block(cfg, persona_id)
                    if modules_on.get("tools", True) else [])
    if small_local:
        by_name = {t.get("name"): t for t in tools_schema}
        tools_schema = [by_name[n] for n in local_models.CORE_TOOLS if n in by_name]
    used["tools"] = {"enabled": bool(modules_on.get("tools", True)),
                     "active": [t["name"] for t in tools_schema],
                     "compact": small_local}

    mem: dict = {}
    if modules_on.get("memory", True) and mem_cfg.get("enable", True) and visitor_id:
        mem = store.get_memory(visitor_id)
        mem_hits = memory_mod.retrieve_relevant(query, mem, mem_cfg.get("retrieval_top_k", 3))
        mem_block = "；".join(f"{k}: {v}" for k, v in mem_hits) if mem_hits else "（暂无相关记忆）"
        used["memory"] = {"enabled": True, "hits": [k for k, _ in mem_hits]}
        if mem_cfg.get("visit_greeting", True) and store.session_count(visitor_id) > 1 and mem:
            used["memory"]["greeting"] = "欢迎回来！注意到您之前咨询过：" + "、".join(list(mem.keys())[:3])
    else:
        mem_block = "（记忆模块关闭）"

    turns = ctx_cfg.get("history_turns", 10)
    if small_local:
        turns = min(turns, 4)
    rel_hist = _relevant_history(history, query, turns, ctx_cfg.get("relevant_only", True))
    summary = ""
    if ctx_cfg.get("summarize", True) and len(history) > ctx_cfg.get("compress_threshold", 6) and modules_on.get("summary", True):
        summary = _summarize_history(history)
    used["history"] = {"turns": len(rel_hist), "relevant_only": ctx_cfg.get("relevant_only", True), "summarized": bool(summary)}

    return {
        "kb_block": kb_block,
        "hits": hits,
        "tools_schema": tools_schema,
        "tools": tools,
        "memory_block": mem_block,
        "memory": mem,
        "history": rel_hist,
        "summary": summary,
        "persona": persona_text,
        "persona_id": persona_id,
        "modules_on": modules_on,
        "used": used,
    }


_URL_RE = re.compile(r"https?://[^\s，。；、）)\]】>]+")
_READ_HINT = re.compile(r"看|读|总结|内容|讲了|说了|是什么|介绍|分析|打开|翻译")
# 模型声明「发不了图」的典型句式：要表情包时出现这些就等于把功能说死了
_EMOTE_REFUSAL_RE = re.compile(
    r"(没法|不能|无法|没办法|不会)(直接)?(发|发送|贴|给你发).{0,6}(图片|图|表情)|"
    r"(我|这边).{0,6}(发不了|不能发|不支持发).{0,4}(图|表情)")


_FILE_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s，。；、）)\]】>]+"            # Windows 绝对路径（正/反斜杠都认）
    r"|~?/(?:Users|home|tmp|var)/[^\s，。；、）)\]】>]+)"  # POSIX 绝对路径
)
_FILE_HINT = re.compile(r"读一下|读读|看看|打开|内容|讲了|说了|写的什么|总结|是什么")


async def _uploaded_file_reply(message: ChannelMessage, ctx: dict, cfg: dict) -> AgentReply | None:
    """网页上传的文档：服务端直接解析，再交给模型回答；不依赖执行器。"""
    if not getattr(message, "file_data", ""):
        return None
    name = (getattr(message, "file_name", "") or "附件").strip()[:120]
    raw = message.file_data.strip()
    try:
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        data = base64.b64decode(raw, validate=False)
    except Exception:
        return AgentReply(text="文件没读出来，格式可能坏了。", confidence=0.4,
                          mode="rule_react", tool_used="parse_document",
                          ctx_used=ctx.get("used"))
    try:
        from core import docparse

        body = await asyncio.to_thread(docparse.extract_text, name, data)
    except RuntimeError as exc:
        return AgentReply(text=str(exc)[:200], confidence=0.4, mode="rule_react",
                          tool_used="parse_document", ctx_used=ctx.get("used"))
    except Exception as exc:
        return AgentReply(text=f"文件解析失败：{type(exc).__name__}", confidence=0.4,
                          mode="rule_react", tool_used="parse_document", ctx_used=ctx.get("used"))
    body = (body or "").strip()
    if not body:
        return AgentReply(text="文件里没有可读文字，可能是扫描件或纯图。", confidence=0.4,
                          mode="rule_react", tool_used="parse_document",
                          ctx_used=ctx.get("used"))
    res = {"tool": "parse_document", "connected": True, "found": True,
           "filename": name, "chars": len(body), "note": body[:6000],
           "truncated": len(body) > 6000}
    injected = dict(ctx)
    lang = "请用简体中文回答，即使原文是英文。" if _CJK_RE.search(message.text or "") else ""
    injected["read_block"] = (
        f"以下是用户刚上传的文件内容（{name}）。直接基于内容回答，{lang}"
        f"不要提“系统日志/工具返回/搜索结果”这类机制：\n{body[:3000]}")
    mode = cfg.get("engine", {}).get("mode", "auto")
    if mode in ("llm", "auto") and cfg.get("llm", {}).get("has_key"):
        try:
            data2 = await llm.react(message.text or "看看这个文件讲了什么", injected, cfg)
            if data2:
                reply = await _make_llm_reply(data2, injected, cfg)
                reply.tool_used = "parse_document"
                reply.tool_result = res
                return await _ensure_chinese(reply, message.text or "看看这个文件讲了什么", cfg)
        except Exception as exc:
            _logging.getLogger("cs.events").warning(
                "uploaded file 后置润色失败，降级为工具原文: %s: %s",
                type(exc).__name__, str(exc)[:200])
    return AgentReply(text=f"{name} 的内容：\n{body[:800]}", confidence=0.7,
                      mode="rule_react", tool_used="parse_document",
                      tool_result=res, ctx_used=ctx.get("used"))


async def _prefetch_file(query: str, ctx: dict, cfg: dict) -> AgentReply | None:
    """消息里给了明确的本地文件路径且要求读内容时，先读再交给模型。

    与 _prefetch_url 同因：模型不会稳定地主动选 read_file，实测会先推脱
    「我碰不到你的 C 盘」。与其反复调 prompt，不如把确定性的事做在前面。
    """
    if not ctx.get("modules_on", {}).get("tools", True):
        return None
    m = _FILE_RE.search(query or "")
    if not m or not _FILE_HINT.search(query or ""):
        return None
    path = m.group(0).rstrip("\"'").strip()
    res = await tools_mod.invoke("read_file", {"path": path}, ctx.get("tool_ctx") or EMPTY)
    if not res.get("found"):
        # 读不到就明确说原因（越权/不存在/执行器离线），不要装傻
        note = res.get("note") or "读不到这个文件。"
        return AgentReply(text=note, mode="rule_react", confidence=0.5,
                          tool_used="read_file", tool_result=res)

    injected = dict(ctx)
    injected["read_block"] = (
        f"以下是你刚读到的文件内容（{path}）。直接基于内容回答，"
        f"不要提“系统日志/工具返回/搜索结果”这类机制：\n{str(res.get('note') or '')[:3000]}")
    mode = cfg.get("engine", {}).get("mode", "auto")
    if mode in ("llm", "auto") and cfg.get("llm", {}).get("has_key"):
        try:
            data = await llm.react(query, injected, cfg)
            if data:
                reply = await _make_llm_reply(data, injected, cfg)
                return await _ensure_chinese(reply, query, cfg)
        except Exception as exc:
            # 降级本身合理（退回工具原文），但必须留下原因：
            # 之前这里是 pass，模型 Key 失效/额度耗尽/超时全都无迹可查，
            # 用户只看到"没接住"，排障只能靠猜。
            _logging.getLogger("cs.events").warning(
                "read_file 后置润色失败，降级为工具原文: %s: %s", type(exc).__name__, str(exc)[:200])
    return AgentReply(text=f"{path} 的内容：\n{str(res.get('note') or '')[:800]}",
                      mode="rule_react", confidence=0.7,
                      tool_used="read_file", tool_result=res)


_REMEMBER_RE = re.compile(r"^(?:请|帮我)?(?:记住|记一下|记下|存一下)[:：，,\s]*(.+)$")
_RECALL_RE = re.compile(r"(?:你还?记得|我之前说过|我上次说|回忆一下|想起来)")


async def _direct_emote(query: str, ctx: dict, cfg: dict) -> AgentReply | None:
    """「发个表情包」这类请求：直接挑图并留下标记，不赌模型记不记得语法。

    用户要的是图，不是一段关于图的解释。模型历史上会回「我没法发图片」，
    多轮 prompt 修补都不稳；这里把它做成确定性路径，成功率 100%。
    """
    from core import intent as intent_mod

    # 以本句原话为准重新定性：ctx 里的 intent 属于整轮上下文，函数被单独调用时不该依赖它
    it = intent_mod.classify(query)
    if it.name != intent_mod.INTENT_EMOTE:
        return None
    if not ctx.get("modules_on", {}).get("tools", True):
        return None
    kw = intent_mod.emote_keyword(query)
    # search_emote 已被并入 qq_send 的 op=emote，不再出现在模型工具清单里；
    # 但直接读表情库不是写操作，不需要走 qq_send 的管理员权限闸门。
    res = await tools_mod.invoke("search_emote", {"keyword": kw},
                                 ctx.get("tool_ctx") or EMPTY)
    if not isinstance(res, dict):
        res = {"note": str(res)[:200]}
    if res.get("status") == "empty" or res.get("found") is False and not res.get("note"):
        label = f"「{kw}」的" if kw else ""
        return AgentReply(text=f"库里还没{label}图，等我再收几张。", confidence=0.6,
                          mode="rule_react", ctx_used=ctx.get("used"))
    lead = random.choice(["喏。", "给。", "拿去。", "接着。"])
    tctx = ctx.get("tool_ctx") or EMPTY
    is_web = str(getattr(tctx, "channel_type", "") or "").startswith("web")
    if is_web and res.get("image_data_url"):
        return AgentReply(text=lead, tool_used="search_emote", tool_result=res,
                          confidence=0.9, mode="rule_react", ctx_used=ctx.get("used"))
    if is_web:
        return AgentReply(text="图找着了，但这边读不出来。去表情包库看看。",
                          tool_used="search_emote", tool_result=res,
                          confidence=0.6, mode="rule_react", ctx_used=ctx.get("used"))
    marker = f"[表情包:{kw or '随便'}]"
    return AgentReply(text=f"{lead}{marker}", tool_used="search_emote", tool_result=res,
                      confidence=0.9, mode="rule_react", ctx_used=ctx.get("used"))


_UPLOADED_ECHO_RE = re.compile(
    r"(?:把|将)?(?:这|那|刚才|上面)?(?:张)?(?:图|图片|照片).{0,10}(?:发|贴|还|给|回|展示|亮)"
    r"|(?:发|贴|还|给|回|展示).{0,6}(?:这|那|刚才|上面)?(?:张)?(?:图|图片|照片)",
    re.I)


def _image_mime(image_b64: str) -> str:
    """从 base64 头部猜 MIME；猜不出就按 jpeg，浏览器一般能兜住。"""
    try:
        raw = base64.b64decode((image_b64 or "")[:64], validate=False)
    except Exception:
        return "image/jpeg"
    if raw.startswith(b"\x89PNG"):
        return "image/png"
    if raw.startswith(b"GIF8"):
        return "image/gif"
    if raw.startswith(b"RIFF") and b"WEBP" in raw[:16]:
        return "image/webp"
    return "image/jpeg"


def _uploaded_image_echo(message: "ChannelMessage", ctx: dict) -> AgentReply | None:
    """网页端「把这张图发出来」：把本轮上传的图原样还回去，不走 qq_send 权限闸门。"""
    if not message.image_b64:
        return None
    if not str(message.channel_type or "").startswith("web"):
        return None
    if not _UPLOADED_ECHO_RE.search(message.text or ""):
        return None
    b64 = message.image_b64.strip()
    if b64.startswith("data:image/"):
        data_url = b64
    else:
        data_url = f"data:{_image_mime(b64)};base64,{b64}"
    return AgentReply(
        text=random.choice(["给，原图。", "喏，还你。", "拿好。"]),
        tool_used="send_image",
        tool_result={"tool": "send_image", "image_data_url": data_url,
                     "kind": "uploaded", "found": True},
        confidence=0.9, mode="rule_react", ctx_used=ctx.get("used"))


_WEB_INTENT_RE = re.compile(r"搜索|搜一下|搜下|查一下|查下|最新|新闻|资讯|动态|进展", re.I)


def _wants_web_digest(text: str) -> bool:
    return bool(_WEB_INTENT_RE.search(text or ""))


_OCR_INTENT_RE = re.compile(
    r"OCR|识别.*文字|文字.*识别|提取.*文字|读.*文字|写了什么|写了啥|图里.*字", re.I)


def _wants_ocr(text: str) -> bool:
    return bool(_OCR_INTENT_RE.search(text or ""))


def _will_generate_image(query: str, ctx: dict) -> bool:
    """`_direct_tool` 会不会直接去画图；流式入口用它提前报一句“在画了”。"""
    if not ctx.get("modules_on", {}).get("tools", True):
        return False
    if "generate_image" not in (ctx.get("tools") or {}):
        return False
    try:
        name, _ = tools_mod.detect_tool(query or "", ctx["tools"])
    except Exception:
        return False
    return name == "generate_image"


async def _direct_tool(query: str, ctx: dict, cfg: dict) -> AgentReply | None:
    """确定性工具意图 → 直接执行，不等模型决定。

    只拦截语义无歧义的表达（提醒/记住/回忆/待办列表）。
    拿不到必要信息时返回 None，让正常引擎去追问，不硬造参数。
    """
    if not ctx.get("modules_on", {}).get("tools", True):
        return None
    q = (query or "").strip()
    tctx = ctx.get("tool_ctx") or EMPTY

    # “发张图”本身就是歧义：发用户手里的图，还是让我画一张？
    # 模型曾直接回“图发不了，没那个手”，既不真也不像人。
    if re.fullmatch(
            r"(?:给我|帮我|替我)?(?:发|来|给|整)(?:一)?(?:张|个|幅)?(?:图片|图|照片)"
            r"(?:给我|过来|看看)?[。！？!?]*", q):
        return AgentReply(
            text="要发你手上的图，还是我画一张？说清楚。",
            confidence=0.9, mode="rule_react", ctx_used=ctx.get("used"))

    # 本地小模型被问「你是谁」经常只吐一个名字（实测「零。」）。身份是固定事实，
    # 直接从人设首句取，不让 0.8B 续写；云端模型仍保留自己的口吻。
    if local_models.small_model_mode(cfg) and re.search(
            r"你是谁|你是什么|介绍一下自己|你叫什么|你的名字", q):
        pm = re.search(r"你是「(.+?)」[，,]?\s*(.+)", str(ctx.get("persona") or ""))
        if pm:
            role = re.split(r"[，,。]", pm.group(2).strip())[0].strip()
            if role:
                return AgentReply(
                    text=f"我是{pm.group(1)}，{role}。", confidence=0.95,
                    mode="rule_react", ctx_used=ctx.get("used"))

    if local_models.small_model_mode(cfg) and re.search(
            r"who are you|what are you|introduce yourself|your name", q, re.I):
        pm = re.search(r"你是「(.+?)」[，,]?\s*(.+)", str(ctx.get("persona") or ""))
        if pm:
            role = re.split(r"[，,。]", pm.group(2).strip())[0].strip()
            if role:
                zh = f"我是{pm.group(1)}，{role}。"
                if "三花猫娘" in role:
                    # 固定人设不交给 0.8B 翻译：实测会译成 "cat mother"。
                    name_en = "Zero" if pm.group(1) == "零" else pm.group(1)
                    return AgentReply(
                        text=f"I am {name_en}, a calico cat girl.",
                        confidence=0.95, mode="rule_react", ctx_used=ctx.get("used"))
                text, tr = zh, None
                try:
                    tr = await tools_mod.invoke(
                        "translate", {"text": zh, "target": "en", "source": "zh"}, tctx)
                    if tr.get("found") and tr.get("note"):
                        text = str(tr.get("note")).strip()
                except Exception:
                    pass
                return AgentReply(
                    text=text, confidence=0.95, mode="rule_react",
                    tool_used="translate", tool_result=tr,
                    ctx_used=ctx.get("used"))

    if local_models.small_model_mode(cfg) and re.search(
            r"你能做什么|你会什么|能干什么|有什么功能|what can you do|what do you do|your capabilities",
            q, re.I):
        if _CJK_RE.search(q):
            text = ("我能查时间、设提醒、记事情、查天气、联网搜索、算数、查汇率、"
                    "翻译、做颜色和单位换算。")
        else:
            text = ("I can tell the time, set reminders, remember facts, check the weather, "
                    "search the web, do math, convert currencies, translate, and convert "
                    "colours or units.")
        return AgentReply(
            text=text, confidence=0.9, mode="rule_react", ctx_used=ctx.get("used"))

    if tctx.image_b64 and _wants_ocr(q):
        res = await tools_mod.invoke("ocr", {}, tctx)
        note = str((res or {}).get("note") or "").strip()
        if note:
            return AgentReply(
                text=note, confidence=0.9 if res.get("found") else 0.4,
                mode="rule_react", tool_used="ocr", tool_result=res,
                escalate=False, ctx_used=ctx.get("used"))

    # 「9.11 和 9.9 哪个大」这类比较不要让 2.5B 自己算：它会把差值正负看反，
    # 也会在 8K 上下文里绕 100 秒。数值比较是确定性事实，直接算。
    cmp = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(?:和|与|跟|比|vs)\s*([-+]?\d+(?:\.\d+)?)\s*(?:哪个|谁|哪一个)?\s*(?:更)?\s*(大|小)", q)
    if cmp:
        from decimal import Decimal
        try:
            a, b = Decimal(cmp.group(1)), Decimal(cmp.group(2))
            pick = a if (a > b) == (cmp.group(3) == "大") else b
            text = f"{pick} 更{cmp.group(3)}。"
            return AgentReply(text=text, confidence=0.95, mode="rule_react",
                              ctx_used=ctx.get("used"))
        except Exception:
            pass

    name, args = None, None
    # 浏览器自动化：明确说「用浏览器打开/访问网站」才走 Playwright，
    # 普通链接总结仍走 read_source，避免把轻任务塞进整台 Chromium。
    if "browser_open" in ctx["tools"]:
        um = re.search(r"https?://[^\s，。！？]+", q)
        if um and re.search(r"浏览器|打开网页|打开网站|访问网站|打开这个网页|网页打开|打开这个链接|访问这个链接", q):
            name, args = "browser_open", {"url": um.group(0)}
    if not name and "browser_read" in ctx["tools"] and re.search(
            r"(读取|读一下|读读|看看).{0,10}(当前|这个|刚才的)?.{0,4}(网页|页面)|(网页|页面).{0,4}(正文|内容)", q):
        name, args = "browser_read", {}
    if not name and "browser_close" in ctx["tools"] and re.search(
            r"(关闭|关掉|退出).{0,4}(浏览器|网页会话)", q):
        name, args = "browser_close", {}
    if not name and "browser_screenshot" in ctx["tools"] and re.search(
            r"(网页|页面|浏览器).{0,6}(截图|截个图|截屏)|(截图|截个图|截屏).{0,6}(网页|页面|浏览器)", q):
        name, args = "browser_screenshot", {}
    # 搜索交给 _llm_answer 的 ReAct 链路：那里会在工具返回后再让本地模型
    # 用两三句归纳；_direct_tool 直接返回 note 会把标题、摘要、URL 原样倒给用户。
    if "recall_memory" in ctx["tools"] and tctx.visitor_id:
        # 「我的测试代号是什么」不该让 0.8B 用知识库口吻复述；先看记忆里有没有这个 key。
        # 必须放在 detect_tool 之前：路由里「你还记得」会先命中空参数版本，
        # 结果把全部记忆列出来，反而答不对具体问题。
        mm = re.search(r"我(?:的)?([^，,。？?]{1,12}?)(?:是什么|是多少|是啥|吗|呢)", q)
        if mm:
            key = re.sub(r"^(?:的)", "", mm.group(1).strip()).strip()
            if key and key in (store.get_memory(tctx.visitor_id) or {}):
                name, args = "recall_memory", {"key": key}
    # UUID 是纯确定性输出，交给小模型选工具经常答成“只看到半句”。
    # 这里按「生成/来/给 + 数量 + UUID」直接命中。
    if "uuid_gen" in ctx["tools"] and re.search(r"uuid", q, re.I) \
            and re.search(r"生成|来|给|出|整|弄", q) \
            and not re.search(r"是什么|怎么|原理|区别|校验", q):
        um = re.search(r"(?:生成|来|给|出|整|弄)\s*([0-9]+|[一二两三四五六七八九十])\s*个?\s*(?:UUID|uuid)", q)
        n = 1
        if um:
            raw = um.group(1)
            n = int(raw) if raw.isdigit() else {"一": 1, "二": 2, "两": 2}.get(raw, 1)
        name, args = "uuid_gen", {"count": str(max(1, min(20, n)))}
    if not name:
        name, args = tools_mod.detect_tool(q, ctx["tools"])
    # 显式「搜一下/新闻/最新」交给 web_search 直接执行。此前把 web_search
    # 从 direct 路径踢回 ReAct，2.5B 经常不选工具、反而答「我没有实时信息」，
    # 用户看到的是功能明明装了却不能用。只在明确搜索意图时命中，闲聊不受影响。
    if not name:
        m = _REMEMBER_RE.match(q)
        if m and "remember" in ctx["tools"]:
            pair = m.group(1).strip()
            # 「记住 X 是 Y」「记住我喜欢喝美式」→ key 取最短可识别前缀
            key, value = _split_memory(pair)
            if key and value:
                name, args = "remember", {"key": key, "value": value}
    if not name:
        return None

    res = await tools_mod.invoke_with(ctx["tools"], name, args, tctx)
    note = res.get("note") or ""
    if not note:
        return None
    # 开源扩展/API 返回的是原始 JSON；直接倒给用户很难看，先压成一句人话。
    note = _format_plugin_note(name, note)
    missed = res.get("found") is False or res.get("connected") is False
    # need_context（追问参数）与 empty（没待办/没记录）都是正常回合，不升级。
    # 这里曾只判 need_context，导致「列一下我的待办」在空列表时开出一张工单。
    benign = res.get("status") in ("need_context", "empty")
    reply = AgentReply(
        text=note,
        confidence=0.4 if missed else 0.95,
        tool_used=name,
        tool_result=res,
        escalate=missed and not benign,
        escalate_reason="knowledge_miss" if (missed and not benign) else "",
        ctx_used=ctx["used"],
        mode="rule_react",
    )
    # 让回复保留人设腔调：把工具结果交给模型润色（失败就用原文）
    # 本地模型不做二次润色：实测它会把「现在是 22:09」改写成「2026-11-20 22:09」，
    # 把 22:19 的提醒说成 22:20，还会在润色时再喊一次工具（提醒被建两遍）。
    # 确定性动作的正确结果比口吻重要，直接返回工具 note。local_compact=false
    # 只是放开工具清单，不代表模型变强，仍按本地端点处理。
    local_runtime = bool((cfg.get("llm") or {}).get("local_model_id")) or local_models.small_model_mode(cfg)
    if (cfg.get("llm", {}).get("has_key") and not missed and not benign
            and not local_runtime):
        try:
            styled = dict(ctx)
            styled["read_block"] = (
                f"你已经替用户办好了这件事，结果是：{note}\n"
                f"用你的口吻回一句确认，保持简短（一两句），不要提工具/系统/数据库。")
            data = await llm.react(query, styled, cfg)
            if data:
                polished = await _make_llm_reply(data, styled, cfg)
                polished.tool_used = name
                polished.tool_result = res
                polished.escalate = False
                return polished
        except Exception as exc:
            # 降级本身合理（退回工具原文），但必须留下原因：
            # 之前这里是 pass，模型 Key 失效/额度耗尽/超时全都无迹可查，
            # 用户只看到"没接住"，排障只能靠猜。
            _logging.getLogger("cs.events").warning(
                "工具结果润色失败，降级为工具原文: %s: %s", type(exc).__name__, str(exc)[:200])
    return reply


def _format_plugin_note(name: str, note: str) -> str:
    """把开源 API 插件的 JSON 结果压成中文短句；结果被截断也能提取关键字段。"""
    if name not in {"pypi_package_info", "npm_package_info", "github_repo_info", "openmeteo_weather"}:
        return note
    if not isinstance(note, str):
        try:
            note = json.dumps(note, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(note)
    if not note.lstrip().startswith("{"):
        return note
    try:
        data = json.loads(note)
    except (TypeError, ValueError):
        data = {}

    def grab(pattern: str) -> str:
        m = re.search(pattern, note)
        return m.group(1) if m else ""

    try:
        if name == "pypi_package_info":
            info = data.get("info") or {}
            version = info.get("version") or grab(r'"version"\s*:\s*"([^"]+)"')
            lic = info.get("license") or grab(r'"license"\s*:\s*"([^"]{1,80})"')
            py = info.get("requires_python") or grab(r'"requires_python"\s*:\s*"([^"]+)"')
            summary = info.get("summary") or grab(r'"summary"\s*:\s*"([^"]{1,200})"')
            bits = [f"PyPI 最新版 {version or '未知'}"]
            if lic:
                bits.append(f"许可证：{lic[:80]}")
            if py:
                bits.append(f"Python {py}")
            if summary:
                bits.append(summary[:180])
            return "；".join(bits) + "。"
        if name == "npm_package_info":
            tags = data.get("dist-tags") or {}
            latest = tags.get("latest") or grab(r'"latest"\s*:\s*"([^"]+)"')
            lic = data.get("license") or grab(r'"license"\s*:\s*"([^"]+)"')
            desc = data.get("description") or grab(r'"description"\s*:\s*"([^"]{1,200})"')
            bits = [f"npm 最新版 {latest or '未知'}"]
            if lic:
                bits.append(f"许可证：{lic}")
            if desc:
                bits.append(desc[:180])
            return "；".join(bits) + "。"
        if name == "github_repo_info":
            lic = (data.get("license") or {}).get("spdx_id") or grab(r'"spdx_id"\s*:\s*"([^"]+)"')
            full = data.get("full_name") or grab(r'"full_name"\s*:\s*"([^"]+)"')
            stars = data.get("stargazers_count")
            if stars is None:
                stars = grab(r'"stargazers_count"\s*:\s*(\d+)') or 0
            lang = data.get("language") or grab(r'"language"\s*:\s*"([^"]+)"')
            desc = data.get("description") or grab(r'"description"\s*:\s*"([^"]{1,200})"')
            bits = [f"{full or '仓库'}：{stars} stars", f"主语言 {lang or '未知'}",
                    f"许可证 {lic or '未声明'}"]
            if desc:
                bits.append(desc[:180])
            return "；".join(bits) + "。"
        if name == "openmeteo_weather":
            cur = data.get("current") or {}
            temp = cur.get("temperature_2m")
            wind = cur.get("wind_speed_10m")
            code = cur.get("weather_code")
            time_ = cur.get("time") or data.get("timezone") or ""
            bits = []
            if temp is not None:
                bits.append(f"{temp}°C")
            if wind is not None:
                bits.append(f"风速 {wind} km/h")
            if code is not None:
                bits.append(f"天气代码 {code}")
            return ("Open-Meteo " + "，".join(bits) + (f"（{time_}）" if time_ else "") + "。").strip()
    except Exception:
        return note
    return note


def _split_memory(pair: str) -> tuple[str, str]:
    """「我喜欢喝美式」→ (喜欢喝, 美式)；「我下周三出差」→ (下周三, 出差)。

    没有可靠切分点时返回 ("", "")——宁可让模型去追问，不塞错键。
    """
    text = (pair or "").strip("，,。. ")
    if not text:
        return "", ""
    m = re.match(r"^(?:我)?(喜欢|爱|讨厌|不吃|吃|喝|住|在|的|叫|是)(.+)$", text)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r"^([^，,。]{1,6}?)(?:是|在|要|有)(.+)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # 兜底：整句作为值，键用「备注」
    return "备注", text


async def _prefetch_url(query: str, ctx: dict, cfg: dict) -> AgentReply | None:
    """消息里带明确链接且意图是「看内容」时，先抓正文再让模型总结。

    返回 None 表示没触发（交给正常引擎分支）。
    抓不到（内网/打不开/没文字）也返回 None——不能让一次抓取失败吞掉正常对话。
    """
    if not ctx.get("modules_on", {}).get("tools", True):
        return None
    m = _URL_RE.search(query or "")
    if not m or not _READ_HINT.search(query or ""):
        return None
    url = m.group(0)
    res = await tools_mod.invoke("read_source", {"op": "url", "url": url}, ctx.get("tool_ctx") or EMPTY)
    if not res.get("found"):
        return None
    body = str(res.get("note") or "")
    if len(body) < 40:
        return None

    injected = dict(ctx)
    lang = "请用简体中文回答，即使原文是英文。" if _CJK_RE.search(query or "") else ""
    injected["read_block"] = (
        f"以下是你刚打开的网页正文（{url}）。直接基于内容回答，{lang}"
        f"不要提“系统日志/工具返回/搜索结果”这类机制：\n{body[:3000]}")
    mode = cfg.get("engine", {}).get("mode", "auto")
    if mode in ("llm", "auto") and cfg.get("llm", {}).get("has_key"):
        try:
            data = await llm.react(query, injected, cfg)
            if data:
                reply = await _make_llm_reply(data, injected, cfg)
                return await _ensure_chinese(reply, query, cfg)
        except Exception as exc:
            # 降级本身合理（退回工具原文），但必须留下原因：
            # 之前这里是 pass，模型 Key 失效/额度耗尽/超时全都无迹可查，
            # 用户只看到"没接住"，排障只能靠猜。
            _logging.getLogger("cs.events").warning(
                "read_source 后置润色失败，降级为工具原文: %s: %s", type(exc).__name__, str(exc)[:200])
    return AgentReply(
        text=f"{url} 的内容：\n{body[:800]}",
        mode="rule_react", confidence=0.7,
        tool_used="read_source", tool_result=res,
    )


def _boundary_reply(query: str, ctx: dict) -> AgentReply | None:
    """危机/时政/隐私/医疗的确定性前置回答。

    必须在 `_direct_tool` 和 `_rule_react` 的工具路由之前调用：压测里
    “有人发时政新闻”被 `detect_tool` 的 web_search 接走，返回 993 字新闻摘要。
    这类题不能先搜再答，必须在入口就截住。
    """
    q = query or ""
    memory_note = ctx.get("used", {}).get("memory", {}).get("greeting", "")
    if _CRISIS_RE.search(q):
        text = _CRISIS_SELF_REPLY if (_CRISIS_SELF_RE.search(q)
                                     and not _CRISIS_OTHER_RE.search(q)) else _CRISIS_REPLY
        return AgentReply(text=text, confidence=0.9, mode="rule_react",
                          memory_note=memory_note, ctx_used=ctx.get("used"))
    if _PROMPT_LEAK_RE.search(q):
        return AgentReply(text=random.choice(_PROMPT_LEAK_REPLIES), confidence=0.7,
                          mode="rule_react", memory_note=memory_note,
                          ctx_used=ctx.get("used"))
    if _OBFUSCATED_IDENTITY_RE.search(q):
        return AgentReply(text=random.choice(_OBFUSCATED_IDENTITY_REPLIES), confidence=0.7,
                          mode="rule_react", memory_note=memory_note,
                          ctx_used=ctx.get("used"))
    if _POLITICAL_RE.search(q):
        return AgentReply(text=random.choice(_POLITICAL_REPLIES), confidence=0.7,
                          mode="rule_react", memory_note=memory_note,
                          ctx_used=ctx.get("used"))
    if _PRIVACY_RE.search(q):
        return AgentReply(text=random.choice(_PRIVACY_FALLBACKS), confidence=0.7,
                          mode="rule_react", memory_note=memory_note,
                          ctx_used=ctx.get("used"))
    if _MED_RE.search(q):
        return AgentReply(text=random.choice(_MED_FALLBACKS), confidence=0.6,
                          mode="rule_react", memory_note=memory_note,
                          ctx_used=ctx.get("used"))
    return None


async def _rule_react(query: str, ctx: dict, cfg: dict) -> AgentReply:
    hits = ctx.get("hits") or []  # 复用 build_context 的检索结果，避免同参数二次检索
    q = query or ""
    boundary = _boundary_reply(q, ctx)
    if boundary is not None:
        return boundary
    tool_name, tool_args = tools_mod.detect_tool(query, ctx["tools"])
    if tool_name:
        result = await tools_mod.invoke_with(ctx.get("tools"), tool_name, tool_args,
                                            ctx.get("tool_ctx") or EMPTY)
        note = result.get("note") or json.dumps(result, ensure_ascii=False)
        note = _format_plugin_note(tool_name, note)
        if _TOOL_DOWN_RE.search(note):
            note = random.choice(_TOOL_DOWN_FALLBACKS)
        # 工具明确说"没找到"或"未接入"时必须标记升级——
        # 否则对客承诺与系统行为不一致，或让用户误以为查到了真数据。
        # status=empty（没待办/没记录）是正常答案，不是知识缺口，不能开升级工单。
        missed = (result.get("found") is False or result.get("connected") is False)
        # need_context（缺参数）追问用户；empty（本来就空）据实回答；两者都不升级
        benign = result.get("status") in ("need_context", "empty")
        return AgentReply(
            text=note,
            confidence=0.4 if missed else 0.9,
            tool_used=tool_name,
            tool_result=result,
            escalate=missed and not benign,
            escalate_reason="knowledge_miss" if (missed and not benign) else "",
            memory_note=ctx["used"].get("memory", {}).get("greeting", ""),
            ctx_used=ctx["used"],
            mode="rule_react",
        )
    if _GROUP_RE.search(q):
        return AgentReply(
            text=random.choice(_GROUP_FALLBACKS), confidence=0.6, mode="rule_react",
            memory_note=ctx["used"].get("memory", {}).get("greeting", ""),
            ctx_used=ctx["used"],
        )
    if hits:
        top_score, top = hits[0]
        conf = 0.6 + min(top_score, 0.6) + 0.05 * min(len(hits), 2)
        return AgentReply(
            # 面向用户的自然表达：不再把内部标题和 KB 编号直接甩给用户。
            # 引用信息由 citations 字段承载，前端会以徽章形式展示。
            text=top["answer"],
            citations=[e["id"] for _, e in hits[:3]],
            confidence=min(conf, 0.95),
            memory_note=ctx["used"].get("memory", {}).get("greeting", ""),
            ctx_used=ctx["used"],
            mode="rule_react",
        )
    # 模型挂了也要守住身份：身份/自曝类问题不能掉进“没听明白”，
    # 否则同一句兜底会被反复看到，比模型复读更像机器人。
    if re.search(
            r"你是谁|你是什么|说人话|你是不是|你是(?:一个)?(?:AI|机器人|模型|程序|虚拟人|猫)|查户口",
            query or "", re.I):
        return AgentReply(
            text=random.choice(_IDENTITY_FALLBACKS),
            confidence=0.6,
            memory_note=ctx["used"].get("memory", {}).get("greeting", ""),
            ctx_used=ctx["used"],
            mode="rule_react",
        )
    # 规则兜底也不能是客服腔：模型挂了、知识库没命中时，这句话是用户唯一能看到的
    # 内容。写成「这个我暂时答不上来」等于当场承认自己是机器人。
    return AgentReply(
        text=random.choice(_GENERIC_FALLBACKS),
        confidence=0.2,
        escalate=True,
        escalate_reason="knowledge_miss",
        memory_note=ctx["used"].get("memory", {}).get("greeting", ""),
        ctx_used=ctx["used"],
        mode="rule_react",
    )


def _clean_search_summary(text: str) -> str:
    """把 1B 归纳出来的编号/markdown/来源行压成一段可读的话。"""
    picked: list[str] = []
    for raw in (text or "").splitlines():
        for seg in re.split(r"[；;]", raw.replace("**", "")):
            line = seg.strip()
            if not line:
                continue
            if line.startswith("来源") or "http://" in line or "https://" in line:
                continue
            line = re.sub(r"^(?:内容|摘要|事实)\s*[：:]\s*", "", line)
            line = re.sub(r"^\d+[.、)]\s*", "", line)
            line = re.sub(r"^[-*•]\s*", "", line)
            if not line:
                continue
            if "以下" in line or "搜索归纳" in line or line.startswith("以上信息"):
                continue
            picked.append(line)
    return "；".join(picked)[:400].strip()

async def _summarize_search(query: str, note: str, cfg: dict) -> str:
    """本地小模型的搜索归纳：纯文本补全，不要求 JSON、不触发模型冷却。"""
    llm_cfg = cfg.get("llm") or {}
    base = str(llm_cfg.get("base_url") or "").rstrip("/")
    key = str(llm_cfg.get("api_key") or "")
    model = str(llm_cfg.get("model") or "")
    if not base or not key or not model or not note:
        return ""
    messages = [
        {"role": "system", "content": "你是搜索归纳助手。只根据资料写一段中文，2-3 个具体事实用分号连接。不要输出编号、来源、链接、免责声明，也不要写“根据资料/以下是”。"},
        {"role": "user", "content": "问题：" + query + "\n资料：\n" + str(note)[:3000]},
    ]
    text = await llm._post_chat(base, key, {
        "model": model, "messages": messages, "max_tokens": 220, "temperature": 0.2,
    })
    text = (text or "").strip()
    if not text or llm.is_promise_only(text):
        return ""
    return _clean_search_summary(text)


async def _llm_answer(query: str, ctx: dict, cfg: dict, image_b64: str = "",
                       first: dict | None = None, prefer: str = "") -> AgentReply | None:
    """单轮 LLM + 最多两轮工具回填（ReAct 的 OBSERVE 补齐）。

    为什么必须有这层：单轮时代模型选完工具就被当成「回答完了」，
    `_make_llm_reply` 只能拿工具 note 当答复——用户看到的是「正在为您查询」，
    或者干脆一串空文本（实测 u2-flash 在联网题上稳定复现）。
    这里按 ReAct 语义执行工具并把 observation 回填，直到模型给出正文；
    最后再用「无工具模式」逼一次答案，避免无限要工具。

    first：调用方已经拿到的一次决策（流式路径复用，省掉一次重复请求）。
    """
    visible = {t.get("name") for t in (ctx.get("tools_schema") or []) if isinstance(t, dict)}
    tools_map = ctx.get("tools") or {}
    observations: list[str] = []
    working = dict(ctx)
    if prefer:
        # 择优候选的偏好通过 ctx 传下去，不改 react() 的调用签名
        working["_prefer"] = prefer
    # 工具执行轨迹要带回 AgentReply：控制台/日志靠它证明「真的调用了搜索」，
    # 之前无论调了多少工具都写 tool_used=None，看起来像整套工具全失效。
    used_tools: list[str] = []
    last_result: dict | None = None
    seen_calls: set[tuple[str, str]] = set()

    def _with_tools(reply: AgentReply) -> AgentReply:
        if used_tools:
            reply.tool_used = used_tools[-1]
            reply.tool_result = last_result
            if len(used_tools) > 1:
                reply.tool_result = {**(last_result or {}), "tool_chain": used_tools}
        return reply

    # 本地小模型的确定性动作优先：提醒/时间/天气/算术/记忆这类有唯一正确参数的
    # 请求，不让 0.8B 自己选工具和拼参数。实测它会重复建提醒、把日期填进 now 的
    # op、把“我的测试代号”切成 key=的；规则路由做这些比模型可靠得多。
    if local_models.small_model_mode(cfg):
        try:
            rule_name, rule_args = tools_mod.detect_tool(query, tools_map)
            if (rule_name in ("now", "remind", "reminders", "weather", "remember", "recall_memory", "calc")
                    and rule_name in visible and rule_name in tools_map):
                rule_result = await tools_mod.invoke_with(
                    tools_map, rule_name, rule_args or {}, ctx.get("tool_ctx") or EMPTY)
                note = str((rule_result or {}).get("note") or "").strip()
                if note:
                    return AgentReply(
                        text=note, confidence=0.9, mode="rule_react",
                        tool_used=rule_name, tool_result=rule_result,
                        ctx_used=(ctx or {}).get("used"),
                    )
        except Exception:
            pass

    # 最多 2 轮：推理模型每轮 30-90s，3 轮会顶到网关超时（实测 95.7s 后整体失败）
    for round_no in range(2):
        data = first if (round_no == 0 and first is not None) else await llm.react(
            query, working, cfg, image_b64)
        if data is None:
            return None
        answer = str(data.get("answer") or "").strip()
        tool_name = str(data.get("tool") or "").strip()
        if tool_name and tool_name in visible and tool_name in tools_map:
            args = data.get("tool_args") or {}
            call_key = (tool_name, json.dumps(args, ensure_ascii=False, sort_keys=True))
            if call_key in seen_calls:
                # 小模型会把同一工具再喊一遍（实测提醒被建两次、提醒列表被列两次）。
                # 写操作重放是实打实的副作用，读操作也只会浪费一轮延迟。
                break
            seen_calls.add(call_key)
            # 单个工具的异常绝不能打断整轮对话：历史上 search_emote 按 dict 解析
            # 数组索引抛 AttributeError，整轮直接掉回「这个我暂时答不上来」。
            try:
                result = await tools_mod.invoke_with(tools_map, tool_name, args,
                                                     ctx.get("tool_ctx") or EMPTY)
            except Exception as exc:  # aqg: tool boundary
                _logging.getLogger("cs.events").warning(
                    "tool %s failed", tool_name, exc_info=True)
                result = {"tool": tool_name, "status": "error",
                          "note": f"工具执行出错（{type(exc).__name__}），换个方式回答用户。"}
            if not isinstance(result, dict):
                result = {"tool": tool_name, "note": str(result)[:500]}
            note = str((result or {}).get("note") or "")
            observations.append(f"[{tool_name}] {note[:1500]}")
            used_tools.append(tool_name)
            last_result = result if isinstance(result, dict) else None
            if (result or {}).get("connected") is False:
                # 工具没接入：再让模型选工具也没有新信息，直接进「无工具作答」分支
                break
            working = dict(working)
            working["read_block"] = (
                "你刚才调用的工具结果如下，直接据此回答，不要再提工具/系统："
                + chr(10) + chr(10).join(observations[-3:]))
            if tool_name == "web_search" and local_models.small_model_mode(cfg):
                # 0.8B 拿到搜索结果会原样复读（实测把标题、摘要、URL 全抄一遍）。
                # 这里用一次「纯文本、不要 JSON」的补全做归纳：不能再走 llm.react——
                # 它要求 json_object，0.8B 一旦吐不出合法 JSON 就会把模型拉进 120 秒
                # 冷却，后面的多轮对话全部秒失败（实测）。
                try:
                    summary_text = await _summarize_search(query, note, cfg)
                    if summary_text:
                        return AgentReply(
                            text=summary_text, confidence=0.8, mode="llm_react",
                            tool_used="web_search", tool_result=last_result,
                            ctx_used=(ctx or {}).get("used"))
                except Exception:
                    pass
            if answer and not llm.is_promise_only(answer):
                data["tool"] = None
                return _with_tools(await _make_llm_reply(data, working, cfg))
            continue
        if answer and not llm.is_promise_only(answer):
            data["tool"] = None
            return _with_tools(await _make_llm_reply(data, working, cfg))
        break

    # 兜底：关掉工具再问一次，模型只能自己作答
    forced = dict(ctx)
    forced["tools_schema"] = []
    forced["read_block"] = (
        "现在没有可用工具，也不要表示要去查询或让用户等待。"
        "用你已经知道的信息直接回答；不确定的数字明确写「这一点需你确认」，不要编造。"
        + (chr(10) + "已知工具结果：" + chr(10) + chr(10).join(observations[-3:]) if observations else ""))
    try:
        final = await llm.react(query, forced, cfg, image_b64)
    except Exception:
        final = None
    forced_answer = str((final or {}).get("answer") or "").strip()
    if forced_answer and not llm.is_promise_only(forced_answer):
        assert final is not None  # forced_answer 非空即说明 final 有内容
        final["tool"] = None
        return _with_tools(await _make_llm_reply(final, forced, cfg))
    # 连「不许再拖」都只换来一句「我这就去查」：不能再把空话发给用户。
    # 明确说明能力边界，比假装正在处理诚实。
    honest = AgentReply(
        text=("这次没查到能直接引用的实时数据，我不瞎编。"
              "你可以把要对比的页面或截图发我，我读完再给结论；"
              "或者我先按已有常识给一版框架，具体数字你核对官方页面。"),
        confidence=0.35,
        mode="llm_react",
        tool_used=None,
        ctx_used=(ctx or {}).get("used"),
    )
    return _with_tools(honest)


async def _make_llm_reply(data: dict, ctx: dict, cfg: dict) -> AgentReply:
    """LLM ReAct 结果 → AgentReply（含工具执行与低置信度兜底话术）；run() 与 run_stream() 共用。"""
    tools = ctx["tools"]
    parsed = LlmReply.safe_parse(data)  # 结构化输出校验，替代裸 dict.get
    parsed.answer = _strip_reasoning(parsed.answer or "")
    tool_name = parsed.tool
    tool_result = None
    tool_missed = False
    # 只认「展示给模型的工具清单」里的名字：模型有时会凭记忆点一个没配置的工具
    # （如没配搜索时硬选 web_search）。那种情况不该去执行——执行结果必然是
    # 「未接入」，还会把用户答案顶掉。直接当作没有工具，让模型的正文生效。
    # 只在「调用方给了明确可见清单」时做白名单过滤：
    # 空清单意味着调用方（单测/自定义实现）直接给了 tools 映射，
    # 这时按映射判断即可，不能因为 schema 为空就把工具全否掉。
    schema_list = [t for t in (ctx.get("tools_schema") or []) if isinstance(t, dict)]
    if schema_list:
        visible_tools = {t.get("name") for t in schema_list}
        if tool_name and tool_name not in visible_tools:
            tool_name = None
    if tool_name and tool_name in tools:
        args = parsed.tool_args or {}
        try:
            tool_result = await tools_mod.invoke_with(ctx.get("tools"), tool_name, args,
                                                      ctx.get("tool_ctx") or EMPTY)
        except Exception as exc:  # aqg: tool boundary
            _logging.getLogger("cs.events").warning(
                "tool %s failed", tool_name, exc_info=True)
            tool_result = {"tool": tool_name, "status": "error",
                           "note": f"工具执行出错（{type(exc).__name__}）。"}
        if not isinstance(tool_result, dict):
            tool_result = {"tool": tool_name, "note": str(tool_result)[:500]}
        if tool_result.get("status") == "bad_args":
            tool_result = {"tool": tool_name, "status": "bad_args", "note": "工具参数不合法。"}
        # 工具「没接入/没配置」时不能把它的提示当最终答复发给用户：
        # 模型本来可以基于已有资料回答，拿 note 顶替等于对用户说「我做不了」。
        unavailable = (tool_result or {}).get("connected") is False
        note = (tool_result or {}).get("note") or ""
        note = _format_plugin_note(tool_name, note)
        # 小模型会把 observation 前缀原样抄进正文（[weather] ...），去掉标签只留内容。
        if tool_name and (parsed.answer or "").startswith(f"[{tool_name}]"):
            parsed.answer = (parsed.answer or "")[len(tool_name) + 2:].strip()
        if unavailable and (parsed.answer or "").strip():
            pass  # 保留模型自己给出的答案
        else:
            parsed.answer = note or parsed.answer or "工具已执行。"
        # 工具自己说「没接入 / 没查到」时标记升级：对客话术必须与系统状态一致，
        # 不承诺「已转人工」——这里没有客服团队，只落一条待补充的工单。
        # status=empty（没待办/没记录）是正常答案，不算缺口。
        benign = (tool_result or {}).get("status") in ("need_context", "empty")
        tool_missed = not benign and (
            (tool_result or {}).get("connected") is False
            or (tool_result or {}).get("found") is False)
        if tool_name == "search_emote" and not tool_missed:
            # 表情包必须在正文里留下 [表情包:关键词]，网关才会真的挑图发出去。
            # 模型拿到库清单后仍会说「我没法发图片」（实测 u2-flash 稳定复现），
            # 于是用户要表情包，得到一句道歉——这就是「表情包发不出去」的真相。
            kw = str((parsed.tool_args or {}).get("keyword") or "").strip()
            if "[表情包" not in (parsed.answer or ""):
                if _EMOTE_REFUSAL_RE.search(parsed.answer or ""):
                    parsed.answer = ""
                marker = f"[表情包:{kw or '猫咪'}]"
                parsed.answer = ((parsed.answer or "").strip() + " " + marker).strip()

    # 输出侧护栏：LLM 回答若泄露系统提示/Key，替换为安全话术并标记升级
    bad_output = guardrail.detect_output(parsed.answer)
    if bad_output:
        parsed.answer = random.choice((
            "这套东西不能给你。换别的问。",
            "打住。这个我不发。",
            "你问错地方了。说别的。",
        ))
        parsed.escalate = True
        parsed.escalate_reason = "output_guardrail"

    # 引用回填：模型通常不会自己把 KB 编号写进 citations 字段（提示词没有强制要求，
    # 实测三条真实问答 citations 恒为空，前端「依据 KB005」徽章永远不显示，
    # 用户也就无从判断答案是查过知识库还是模型自己编的）。
    # 检索结果 ctx["hits"] 是可信的，模型没给引用时用它回填；
    # 模型给了就尊重模型的（它可能只引用了其中一部分）。
    citations = list(parsed.citations or [])
    if not citations:
        citations = [e["id"] for _, e in (ctx.get("hits") or [])[:3]]

    answer = AgentReply(
        text=parsed.answer,
        citations=citations,
        confidence=parsed.confidence,
        escalate=parsed.escalate,
        escalate_reason=parsed.escalate_reason,
        tool_used=tool_name,
        tool_result=tool_result,
        ctx_used=ctx["used"],
        mode="llm_react",
        thought=(parsed.thought or "")[:2000],
    )
    threshold = cfg.get("escalation", {}).get("confidence_threshold", 0.6)
    if tool_missed and not answer.escalate:
        answer.escalate = True
        answer.escalate_reason = "knowledge_miss"
    if answer.confidence < threshold and not answer.escalate:
        answer.escalate = True
        answer.escalate_reason = answer.escalate_reason or "low_confidence"
    # 输出钩子统一在 run()/run_stream() 出口应用（这里再加一次会让「追加落款」叠两遍）
    return answer


# 记忆 opt-out 触发词（访客说"不要记住我/忘记我"时清记忆）
# 注意：中文里"记住我"中间隔了"住"，早期写成 (记|保存)我 会漏掉最常见的说法。
# 另用负向先行排除"不要忘记我"——语义相反，不能当退出处理。
_MEMORY_OPT_OUT_PATTERNS = [
    re.compile(r"(不要|别|停止|不用)(再)?.{0,4}(记(住)?|保存|存储|保留).{0,2}我(?!的生日)", re.IGNORECASE),
    re.compile(r"(不要|别)记住我", re.IGNORECASE),
    re.compile(r"忘记(我|所有|一切)(关于我)?的?(记忆|信息|偏好|资料)", re.IGNORECASE),
    re.compile(r"(清除|删除|清空).{0,4}(我的)?(记忆|偏好|个人信息)", re.IGNORECASE),
    re.compile(r"(关闭|关掉|停用).{0,4}(记忆|个性化)", re.IGNORECASE),
]

# 反向语义：出现这些说法时不做 opt-out（"不要忘记我"是挽留，不是退出）
_MEMORY_OPT_OUT_NEGATIVE = [
    re.compile(r"(不要|别)忘记我", re.IGNORECASE),
]


def _maybe_opt_out_memory(query: str, visitor_id: str) -> str | None:
    if any(pat.search(query) for pat in _MEMORY_OPT_OUT_NEGATIVE):
        return None
    for pat in _MEMORY_OPT_OUT_PATTERNS:
        if pat.search(query):
            store.clear_memory(visitor_id, opt_out=True)
            return "好的，已为您清除所有记忆，后续不会主动记录您的偏好。"
    return None


_FACT_RE = __import__("re").compile(
    r"(什么|为什么|怎么|如何|是谁|多少|几点|最新|今天|昨天|明天|新闻|价格|多少钱|"
    r"发布|上线|版本|哪一年|介绍一下|讲讲|了解|知道|查|攻略|教程|对比|评测|新闻|"
    r"who|what|when|where|why|how|latest|news|price)", __import__("re").IGNORECASE,
)


def _wants_facts(query: str) -> bool:
    """轻启发式：判断一条渠道消息是否像在寻求事实/资讯（值得自动联网）。"""
    q = (query or "").strip()
    return len(q) >= 4 and bool(_FACT_RE.search(q))


async def _prepare(message: ChannelMessage, history: list[dict], visitor_key: str):
    """run()/run_stream() 公共前置：截断、上下文、护栏/升级/图片规则拦截。拦截时直接返回 AgentReply。"""
    cfg = config.get_config()
    # 角色卡（SillyTavern chara_card 对标）：必须在 build_context 之前合成——
    # ctx["persona"] 由 cfg["context"]["persona"] 派生，晚了就定型了。
    try:
        chat_key = f"{message.channel_type}:{message.group_id or message.channel_user_id}"
        card = store.card_for_chat(chat_key)
    except Exception:
        card = None
    if card and card.get("persona"):
        cfg["context"] = {**cfg.get("context", {}), "persona": str(card["persona"])}
        if card.get("temperature") is not None:
            cfg["llm"] = {**cfg.get("llm", {}), "temperature": float(card["temperature"])}
    # 未来任务记录的是「当时谁安排的」：任务创建者选的角色优先于执行时的聊天绑定，
    # 否则同一任务隔天执行会突然换成另一个角色/另一套知识库。
    if message.persona_id:
        try:
            from core import personas as personas_mod

            preset = personas_mod.get(message.persona_id)
            if preset:
                cfg["context"] = {**cfg.get("context", {}), "persona": preset.persona}
                cfg["llm"] = {**cfg.get("llm", {}), "temperature": preset.temperature}
        except Exception:
            pass
    query = (message.text or "").strip()
    max_len = cfg.get("escalation", {}).get("max_message_len", 1000)
    if len(query) > max_len:
        query = query[:max_len]

    # 输入钩子：用户消息进管线前的确定性规则（拦截/改写），优先于一切模型判断
    try:
        from core import hooks as hooks_mod

        hook_res = hooks_mod.run_pre_input(query, cfg)
        if hook_res["action"] == "block":
            ctx = await build_context_async(query, history, cfg, visitor_key, False)
            return AgentReply(text=hook_res["text"], confidence=1.0, mode="hook",
                              ctx_used=ctx["used"], tool_used="hook:pre_input")
        if hook_res["action"] == "rewrite" and hook_res["text"] != query:
            message = ChannelMessage(**{**message.__dict__, "text": hook_res["text"]})
            query = hook_res["text"]
    except Exception as exc:  # 钩子故障不影响对话
        import logging as _logging
        _logging.getLogger("cs.events").warning("hook pre_input failed: %s", type(exc).__name__)

    # 记忆 opt-out：访客说"不要记我/忘记我"直接拦截并清记忆
    opt_out_reply = _maybe_opt_out_memory(query, visitor_key)
    if opt_out_reply:
        ctx = await build_context_async(query, history, cfg, visitor_key, message.web_search)
        return AgentReply(
            text=opt_out_reply,
            confidence=1.0,
            mode="rule_react",
            ctx_used=ctx["used"],
            opt_out=True,
        )

    # 联网自启（chatgpt-on-wechat「不懂就查」对标）：渠道消息像在寻求事实/资讯
    # 且搜索服务可用时自动开搜，用户无需手动开开关。失败静默，不影响主流程。
    # 先看知识库能否回答：命中本地 KB 就不搜网——"退货政策是什么"这类含疑问词
    # 的业务问题曾被启发式误判，每次白跑 4 次搜索、还拖慢 3~5 秒。
    web = message.web_search
    # 本地小模型不自动联网：搜索结果会塞满 8K 上下文，反而把工具调用挤掉。
    # 需要查时它自己调 web_search/read_source，由模型决定而不是每轮先灌 4 条。
    if not web and local_models.small_model_mode(cfg):
        web = False
    elif not web:
        from core import websearch
        if websearch.available() and _wants_facts(query):
            # 先探一次知识库：命中就不搜网（检索结果随后 build_context 会复用同一份缓存）
            cfg_ret = cfg.get("retrieval", {})
            emb_flag = cfg_ret.get("embedding", "auto")
            kb_hits = retrieval.retrieve_scored(
                query, 1, cfg_ret.get("min_overlap", 0.0),
                use_embedding=None if emb_flag == "auto" else (emb_flag == "on"),
            )
            web = not kb_hits

    ctx = await build_context_async(query, history, cfg, visitor_key, web)
    # 技能说明书：告诉模型「什么时候用哪个工具」——只有工具没有技能时，
    # 模型经常知道有 read_file 却不知道先列目录，等于工具白装。
    try:
        from core import skills as skills_mod

        ctx["skills_block"] = skills_mod.render(
            cfg, persona_caps.allowed(cfg, ctx.get("persona_id", ""), "skills"))
    except Exception:  # 技能渲染失败绝不能影响主链路
        ctx["skills_block"] = ""
    try:
        from core import extensions

        ext_block = extensions.render_skills(
            persona_caps.allowed(cfg, ctx.get("persona_id", ""), "extensions"),
            persona_caps.allowed(cfg, ctx.get("persona_id", ""), "skills"),
        )
        if ext_block:
            ctx["skills_block"] = (ctx["skills_block"] + "\n" + ext_block).strip()
    except Exception:
        pass
    # 人物/群档案 + 黑话：让模型「先认得人再开口」，不用每轮从零推断。
    try:
        from core import profiles as profiles_mod

        # channel_type 实际取值是 qq_group / qq_private（不是 "qq"），
        # 用 startswith 判断，否则 QQ 用户会被错记成 web:qq:123 两条档案。
        is_qq = str(message.channel_type or "").startswith("qq") or message.channel_type == "onebot"
        user_key = ("qq:" + str(message.channel_user_id)) if is_qq else ("web:" + str(visitor_key))
        # 用户档案也按机器人账号分桶：同一个人面对两个号是两段关系，不能共享称呼/偏好。
        if is_qq and message.account_id:
            user_key += "#" + str(message.account_id)
        group_key = ("qq_group:" + str(message.group_id)) if message.group_id else ""
        # 自动建档：每轮把「谁在说、在哪个群说」增量写进档案（首见创建，之后累加计数）。
        # 只读不写的话，档案永远是空的——这正是「建档不生效」的根因。
        # display_name 只能用渠道昵称。channel_user_id 对 Web 访客是一个
        # `v-...` 内部 ID，写进档案后模型会把它当用户名字叫出来（压测实测：
        # “你叫 v-LZg…，档案里记着的”）。内部 ID 永远不该进提示词。
        profiles_mod.upsert_profile(
            user_key, "user",
            display_name=str(getattr(message, "display_name", "") or "")[:20],
            alias=str(getattr(message, "display_name", "") or "")[:20],
            stats_delta={"messages": 1})
        if group_key:
            profiles_mod.upsert_profile(
                group_key, "group",
                display_name=str(getattr(message, "group_name", "") or "")[:40],
                stats_delta={"messages": 1})
        ctx["profile_block"] = profiles_mod.profile_block(user_key, group_key)
        ctx["lexicon_block"] = profiles_mod.lexicon_block(group_key or user_key)
        profiles_mod.learn_from_message(query, group_key or user_key)
    except Exception:  # 档案失败不能影响对话
        ctx["profile_block"] = ""
        ctx["lexicon_block"] = ""
    if query:
        # 引用回复：把用户这一句原话交给模型，避免"答非所问还答得理直气壮"
        ctx["quote_block"] = "【用户这一句原话】" + query[:300]
        # 输入意图识别：规则先定性，再决定这一轮该用哪个档位说话。
        # 不注入的话，模型遇到「你是谁」会背客服简历、遇到「发个表情包」会说发不了图。
        try:
            from core import intent as intent_mod

            ctx["intent"] = intent_mod.classify(query)
            ctx["intent_block"] = intent_mod.prompt_hint(ctx["intent"])
        except Exception:  # 意图识别只是增强，判不出来不影响回答
            ctx["intent"] = None
            ctx["intent_block"] = ""
    # 工具上下文：让工具知道"谁在问、在哪个群、刚才说了什么、有没有带图"
    ctx["tool_ctx"] = ToolContext(
        visitor_id=visitor_key or "",
        session_id=getattr(message, "session_id", "") or "",
        channel_type=message.channel_type,
        channel_user_id=message.channel_user_id,
        group_id=message.group_id,
        group_name=getattr(message, "group_name", "") or "",
        message_text=query,
        image_b64=message.image_b64 or "",
        history=tuple(history or ()),
        message_id=str(getattr(message, "message_id", "") or ""),
        # 工具层的权限主体：QQ 渠道按触发者 QQ 号，其余按访客身份。
        # 只有管理员/授权 QQ（AUTHORIZED_QQ）能触达读写主机文件、以机器人身份发消息。
        # channel_type 实际取值是 qq_group / qq_private（不是 "qq"）：旧判断用
        # in ("qq","onebot") 恒为假，于是主人账号被当成 visitor，
        # 所有特权工具一律拒绝——「主人账号说话机器人不听」的根因之一。
        principal=("admin" if getattr(message, "is_admin", False) else
                   (f"qq:{message.channel_user_id}"
                    if str(message.channel_type or "").startswith("qq")
                    or message.channel_type == "onebot"
                    else f"visitor:{visitor_key or 'anonymous'}")),
        persona_id=ctx.get("persona_id", ""),
        account_id=getattr(message, "account_id", "") or "",
    )
    # 反思修正：把"最近高频毛病"作为自我修正提醒注入上下文（带缓存，60s 内不重复查库）
    try:
        ctx["self_fix"] = _self_fix_hint()
    except Exception:  # 自检绝不影响主链路
        ctx["self_fix"] = ""
    # 群聊氛围与群名：@ 之前大家在聊什么、这是哪个群——场景感知
    if getattr(message, "ambient", None):
        lines = [ln for ln in message.ambient if ln and ln.strip()][-8:]
        if lines:
            block = "群聊氛围（@ 你之前群里最近在聊的，供你接梗用，别逐条回复）：\n" + "\n".join(lines)
            ctx["ambient_block"] = block[:1200]
    if getattr(message, "group_name", ""):
        ctx["group_name"] = message.group_name

    if cfg.get("guardrail", {}).get("injection_block", True):
        inj, inj_action = guardrail.detect_injection(query)
        if inj and inj_action == "block":
            return AgentReply(
                # 用户可见文本刻意中性且不点破机制（说了"拦截/记录"等于向攻击者确认防线存在）；
                # 审计留痕在入口侧完成，这里只管体面地闭麦。
                text="这个话题就到此为止吧。有别的想聊的，随时开口。",
                confidence=1.0,
                tool_used="injection_guard",
                mode="guardrail",
                ctx_used=ctx["used"],
            )

    if "转人工" in query or "人工客服" in query or "找个人" in query:
        if cfg.get("escalation", {}).get("handoff", True):
            return AgentReply(
                text="行，我把人叫过来，你稍等。",
                confidence=1.0, escalate=True, escalate_reason="visitor_requested",
                ctx_used=ctx["used"], mode="rule_react",
            )
        return AgentReply(
            text="这儿就我一个人盯着，没别人可转。有事直接说，能办的我给你办。",
            confidence=1.0, escalate=False,
            ctx_used=ctx["used"], mode="rule_react",
        )

    if (message.image_b64 and not _wants_ocr(query)
            and cfg.get("multimodal", {}).get("enable", True)):
        # 「把这张图发出来」是回显请求，不是识图请求；必须在视觉能力检查之前接住，
        # 否则非视觉模型会先回“我看不了图”，用户永远拿不到原图。
        echo = _uploaded_image_echo(message, {"used": {}})
        if echo is not None:
            return echo
        # 视觉能力判定要看「模型真的支持图片」，而不是「配了模型名」。
        # 主模型 u2-flash 明确不支持 image_url（端点 400），之前只判断"有模型名"
        # 就把图丢给它，结果整轮失败掉回规则引擎——用户看到的就是"识别不了"。
        vision_model = (cfg.get("multimodal", {}) or {}).get("vision_model") or ""
        vision_ready = bool(vision_model) and bool(cfg.get("llm", {}).get("has_key", False))
        if not vision_ready:
            # 主模型支持多模态时可沿用主模型
            vision_ready = bool((cfg.get("llm", {}) or {}).get("supports_vision"))                 and bool(cfg.get("llm", {}).get("has_key", False))
        if not vision_ready:
            return AgentReply(
                text="图收到了，但我这会儿看不了图。你用文字说一下图里有啥？",
                confidence=0.3,
                escalate=False,
                tool_used="vision",
                ctx_used=ctx["used"],
                mode="rule_react",
            )
    return cfg, query, ctx


# ---- 反思修正：回复自检 + 高频毛病动态注入（从自己的错误里进化）----


def _critique_reply(text: str, history: list[dict]) -> list[str]:
    """规则自检一条回复，返回毛病清单（免费、毫秒级、零 LLM 成本）。"""
    text = text or ""
    issues: list[str] = []
    if len(text) > 240:
        issues.append("回复过长——群聊闲聊三四句就该说完，别写小作文")
    if "**" in text or "##" in text or "`" in text:
        issues.append("回复里出现了 markdown 符号（QQ 是纯文字环境）")
    if text.count("\n\n") >= 2:
        issues.append("分段太多——聊天不是写作文")
    if len(re.findall(r"\[[^\[\]]{1,6}\]", text)) > 3:
        issues.append("表情标记堆太多——一次最多一两个")
    # 复读检测：与最近一条 agent/坐席回复开头雷同
    for m in reversed(history or []):
        if m.get("role") in ("agent", "operator"):
            prev = (m.get("content") or "").strip()
            if prev and text.strip()[:24] == prev[:24] and len(text) > 30:
                issues.append("开头和上一条回答一模一样——换个说法，别复读")
            break
    return issues


def _apply_post_hooks(reply: AgentReply, cfg: dict) -> AgentReply:
    """输出钩子：回复落库前的确定性改写/追加/替换。

    与输出侧护栏分工：护栏管「不许泄露」，钩子管「运营要求」（加免责声明、
    统一签名、特定话题替换话术）。两者都在模型之外强制执行，不依赖模型配合。
    """
    try:
        from core import hooks as hooks_mod

        res = hooks_mod.run_post_reply(reply.text or "", cfg)
    except Exception:
        return reply
    if res["action"] == "pass":
        return reply
    reply.text = res["text"]
    if res["action"] in ("replace", "block"):
        reply.tool_used = "hook:post_reply"
    return reply


_SELF_FIX_CACHE: list = [0.0, ""]  # list 便于原地刷新（tuple 不可写，实测 item assignment 崩）


def _self_fix_hint() -> str:
    """高频毛病 → system prompt 自我修正提醒（60s 缓存）。"""
    import time as _time

    now = _time.monotonic()
    if now - _SELF_FIX_CACHE[0] < 60:
        return _SELF_FIX_CACHE[1]
    hint = ""
    try:
        issues = store.critique_summary()
        if issues:
            hint = "自我修正提醒（这是你最近回复里反复出现的问题，这一轮必须避免）：\n" + \
                   "\n".join(f"- {i}" for i in issues[:3])
    except Exception:
        hint = ""
    _SELF_FIX_CACHE[0], _SELF_FIX_CACHE[1] = now, hint
    return hint


def _maybe_critique(reply, ctx: dict, visitor_key: str) -> None:
    """LLM 回复落库前自检，毛病写入 reply_critiques 供反思修正。绝不抛异常。"""
    try:
        issues = _critique_reply(reply.text or "", ctx.get("history") or [])
        store.critique_add(visitor_key, len(reply.text or ""), issues)
    except Exception:  # aqg: 自检故障不影响回复
        pass


async def _gate_output(reply, query: str, cfg: dict) -> None:
    """输出判别器：规则判问题，严重问题重写一次，结果写回 reply 并记账。

    与 `_maybe_critique` 分工：那边只统计「格式类」高频毛病，这边管「人设硬伤」——
    自称 AI、把已有能力说死、承诺转人工，这些出现在群里一次就够丢人。
    角色卡在位时，另用 `character_guard` 的卡片判据（客服腔/身份漂移/禁忌/口癖）
    过一遍——通用判据管"像不像助手"，卡片判据管"像不像这个角色"。
    """
    from core import quality

    reply.text = _strip_reasoning(reply.text or "")
    persona_text = str((cfg.get("context") or {}).get("persona") or "")
    # 时政题：模型常只回一句“这话题我不聊，换一个”，等于把话聊死。
    # 产品规则是“不聊，但可以顾左右而言他”——如果回答里没有拐到别的话题，
    # 这里确定性补一个自然转折，不让群里继续追问同一个坑。
    if _POLITICAL_RE.search(query) and not _POLITICAL_PIVOT_RE.search(reply.text or ""):
        reply.text = random.choice(_POLITICAL_REPLIES)
        reply.mode = "llm_react_guarded"
    # 银圈来历是角色卡里的硬事实：旧工牌熔的，不是旧货市场淘的。
    # 模型已经三次把它编成“淘的/买的/自己磨的”，只在问到银圈且没提工牌时定点纠偏。
    if ("银圈" in (query or "") and "工牌" not in (reply.text or "")
            and re.search(r"(旧货市场|淘|买|捡|祖传|别人送|自己磨|磨的|银匠|"
                          r"打的|做的|地摊|网上|家里)", reply.text or "")):
        reply.text = "旧工牌熔的。没故事，别编。"
        reply.mode = "llm_react_guarded"
    try:
        issues = quality.critique(reply.text or "", query,
                                  channel=str(cfg.get("_channel") or ""),
                                  persona=persona_text)
    except Exception:  # 判别器故障绝不影响回复
        return
    card_issues = _character_issues(reply.text or "", persona_text)
    if card_issues:
        issues = list(issues) + card_issues
    if not issues:
        return
    if quality.needs_rewrite(issues):
        # 内部 ID / 医疗开药 / 危机列步骤这三类，宁可确定性替换，也不要再赌一次
        # 模型重写——尤其 429 冷却时，重写本身也会失败，原文会直接发出去。
        deterministic = {i.get("code") for i in issues} & {
            "internal_id_leak", "medical_prescribe", "crisis_steps"}
        if any(i.get("code") == "incivility" for i in issues):
            reply.text = random.choice(_INCIVILITY_REPLIES)
            reply.mode = "llm_react_guarded"
        elif any(i.get("code") == "real_tragedy_joke" for i in issues):
            reply.text = random.choice(_TRAGEDY_JOKE_REPLIES)
            reply.mode = "llm_react_guarded"
        elif any(i.get("code") == "sexual_joke" for i in issues):
            reply.text = random.choice(_SEXUAL_JOKE_REPLIES)
            reply.mode = "llm_react_guarded"
        elif deterministic:
            reply.text = _fallback_for(issues, persona_text)
            reply.mode = "llm_react_guarded"
        else:
            # 决策 JSON 漏进正文属于「可直接确定性修复」的：切掉 JSON 尾巴即可，
            # 正文本身是好的，没必要花一次模型调用重写（重写还可能把好答案改坏）。
            if any(i.get("code") == "json_leak" for i in issues):
                stripped = _strip_json_tail(reply.text or "")
                if stripped:
                    reply.text = stripped
                    issues = [i for i in issues if i.get("code") != "json_leak"]
            if quality.needs_rewrite(issues):
                new_text = await quality.rewrite(
                    reply.text or "", issues, query=query, persona=persona_text)
                if new_text:
                    reply.text = new_text
                elif all(str(i.get("code") or "").startswith("card_") for i in issues):
                    # 只有卡片判据违规而重写又没成功：保留原文。
                    # 轻微口癖丢失/个别措辞不该用兜底句顶替——兜底句是另一个角色的口吻，
                    # 发出去比原文伤害大；通用硬伤（自称 AI 等）才走 _fallback_for。
                    pass
                else:
                    # 重写没成功（模型也答不出来）：至少不能把底层模型自述/英文过滤报错发出去。
                    # 这里给的是"人设兜底"而不是客服话术——宁可用一句短的，也不露馅。
                    reply.text = _fallback_for(issues, persona_text)
                    reply.mode = "llm_react_guarded"
    try:
        store.critique_add("quality", len(reply.text or ""),
                           [f"[{i['severity']}] {i['detail']}" for i in issues])
    except Exception:
        pass


def _character_issues(text: str, persona: str) -> list[dict]:
    """当前提示词能反查到角色卡时，用卡片判据查一致性；查不到返回空。

    返回 quality 风格的 issue dict（severity=high，触发重写路径），
    这样重写提示词能直接复用 detail 里的具体修正要求。
    任何异常都吞掉——守卫是增强，不是依赖。
    """
    try:
        from core import character as character_mod, character_guard, quality

        card = character_mod.card_for_persona(persona)
        if card is None:
            # 自定义长人设不参与逐字反查；若开头仍是同一角色名，退回该角色卡，
            # 至少保留身份/越权/口癖的一致性检查。
            card = character_mod.load_all().get("zero")
            if card is not None and not persona.lstrip().startswith(f"你是「{card.name}」"):
                card = None
        if card is None:
            return []
        result = character_guard.check_reply(text or "", card)
        return [{"code": f"card_{v.kind}", "severity": quality.SEV_HIGH,
                 "detail": v.detail} for v in result.violations]
    except Exception:  # aqg: 守卫故障不影响回复
        return []


def _strip_json_tail(text: str) -> str:
    """切掉混在正文后面的决策 JSON。

    实测 u2-flash 会先正常回一句，再原样贴一段
    `{"thought": ..., "tool": null, "answer": "..."}`。整段发出去等于把内部字段
    给用户看；正文是好答案，只需要砍掉从第一个 `{` 开始的部分。
    """
    t = (text or "").strip()
    idx = t.find("{")
    if idx <= 0:
        return ""
    head = t[:idx].rstrip()
    if not head:
        return ""
    # JSON 里带 answer 时，用 answer 的值兜底（正文可能被截断/为空）
    import json as _json

    try:
        tail = _json.loads(t[idx:])
        if isinstance(tail, dict):
            inner = str(tail.get("answer") or "").strip()
            if inner and len(inner) > len(head):
                return inner
    except ValueError:
        pass
    return head


def _fallback_for(issues: list[dict], persona: str = "") -> str:
    """重写也失败时的兜底短句。判据要跟当前角色走：
    猫娘角色用猫话兜底，其它角色用中性说法——给「老陈」发「本喵」等于二次穿帮。
    判定复用 quality._identity_anchors（只认自我描述里的身份词）：
    tech 卡叙述里「拨号上网的猫」是调制解调器，按字面找「猫」字会误判。"""
    codes = {i.get("code") for i in issues}
    p = persona or ""
    try:
        from core.quality import _identity_anchors
        is_cat = any("猫" in a for a in _identity_anchors(p))
    except Exception:  # 锚点推断失败就保守回退到显式自述
        is_cat = False
    # 锚点规则只认「你是…猫」一句话内的自述；「你是「零」。一只猫娘。」这种
    # 断句抓不到，补三个无歧义的猫自称信号（tech 卡里的「拨号上网的猫」
    # 是调制解调器，不能按字面算）。
    is_cat = is_cat or "猫娘" in p or "一只猫" in p or "本喵" in p[:1200]
    miao = "，喵～" if is_cat else "。"
    m = re.search(r"你是「([^」]+)」", p)
    name = m.group(1).strip() if m else "我"
    if "identity_missing" in codes or "identity_no_cat" in codes:
        if is_cat:
            return "本喵叫零，一只猫，喵～ 问这么多干嘛，先说说你是谁。"
        if name == "零":
            return random.choice(_IDENTITY_FALLBACKS)
        return random.choice([f"我是{name}。先说说你找谁。", f"查户口呢？我是{name}。"])
    if "filter_leak" in codes:
        return "这话我接不住，换个说法" + miao
    if "ai_self" in codes or "model_leak" in codes or "card_identity_drift" in codes:
        if is_cat:
            return "我是零，一只猫。别的身份？你猜，猜对了也不告诉你，喵～"
        if name == "零":
            return random.choice(_IDENTITY_FALLBACKS)
        return random.choice([f"我是{name}。你查户口？", f"查户口呢？我是{name}。"])
    if "capability_refusal" in codes:
        return "能发，你要什么直接说" + miao
    if "internal_id_leak" in codes:
        # 内部访客 ID 不能靠改写碰运气，直接换成“没记名字”。
        return random.choice(("你叫什么？我这儿没记名字，你自己说。",
                              "名字你还没告诉我，我这边不记编号。"))
    if "medical_prescribe" in codes:
        return random.choice(_MED_FALLBACKS)
    if "crisis_steps" in codes:
        return _CRISIS_REPLY
    return random.choice(_GENERIC_FALLBACKS)


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _looks_english(query: str) -> bool:
    q = (query or "").strip()
    # 「把 good morning 翻译成中文」里 ASCII 占多数，但不是英文提问；
    # 含中文时一律不触发英文兜底，否则会把中文译文再翻回英文。
    if _CJK_RE.search(q) or len(q) < 8:
        return False
    letters = sum(1 for c in q if c.isascii() and (c.isalpha() or c.isspace()))
    return letters / max(1, len(q)) > 0.55


def _looks_mostly_english(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 24:
        return False
    cjk = len(_CJK_RE.findall(t))
    letters = sum(1 for c in t if c.isascii() and c.isalpha())
    return cjk <= 2 and letters / max(1, len(t)) > 0.55


async def _ensure_chinese(reply: AgentReply, query: str, cfg: dict) -> AgentReply:
    """中文提问拿到整段英文回复时翻回中文；读英文网页最容易触发。"""
    if not _CJK_RE.search(query or "") or not _looks_mostly_english(reply.text):
        return reply
    try:
        res = await tools_mod.invoke(
            "translate", {"text": str(reply.text)[:2000], "target": "zh", "source": "auto"}, EMPTY)
        translated = str((res or {}).get("note") or "").strip()
        if translated and _CJK_RE.search(translated):
            reply.text = translated
    except Exception:
        pass
    return reply


async def _ensure_english(reply: AgentReply, query: str, cfg: dict) -> AgentReply:
    """0.8B 仍会在英文回答里混入「cat娘」。兜底：整段译成英文再返回。"""
    if not local_models.small_model_mode(cfg) or not _looks_english(query):
        return reply
    text = str(reply.text or "")
    if not text or not _CJK_RE.search(text):
        return reply
    try:
        res = await tools_mod.invoke(
            "translate", {"text": text, "target": "en", "source": "auto"}, EMPTY)
        translated = str((res or {}).get("note") or "").strip()
        if translated and not _CJK_RE.search(translated):
            reply.text = translated
    except Exception:
        pass
    return reply


async def run(message: ChannelMessage, history: list[dict], visitor_key: str) -> AgentReply:
    with tracing.span("bigrobot.pipeline.run", {"channel": message.channel_type, "visitor": visitor_key}):
        prepared = await _prepare(message, history, visitor_key)
        if isinstance(prepared, AgentReply):
            return prepared
        cfg, query, ctx = prepared
        reply = await _run_body(message, history, visitor_key, cfg, query, ctx)
        # 输出判别器：人设硬伤（自称 AI/能力否认/假转接）在这里拦一次。
        # 只对 LLM 产物生效——规则兜底与标注答案是人写的，不该被改写。
        if str(reply.mode or "").startswith("llm"):
            cfg = {**cfg, "_channel": message.channel_type}
            await _gate_output(reply, query, cfg)
        reply = await _ensure_english(reply, query, cfg)
        # 输出钩子统一在出口应用：所有分支（标注/直连工具/README/LLM/规则）一视同仁，
        # 分支内部各自加一遍必然会漏。
        return _apply_post_hooks(reply, cfg)


async def _run_body(message: ChannelMessage, history: list[dict], visitor_key: str,
                cfg: dict, query: str, ctx: dict) -> AgentReply:

    # 标注回复（Dify annotations 对标）：命中管理员标注的标准答案，直接回复，
    # 不走 KB/LLM——最便宜、最可控、零延迟。放在所有引擎分支之前。
    ann = store.annotation_hit(query)
    if ann:
        return AgentReply(
            text=ann["answer"], mode="annotation", confidence=1.0,
            citations=[f"标注#{ann['id']}"],
        )

    # 危机/时政/隐私/医疗必须在工具直通之前截住。否则“有人发时政新闻”
    # 会先命中 web_search，把新闻摘要原样倒进群里。
    boundary = _boundary_reply(query, ctx)
    if boundary is not None:
        return boundary

    # 「把这张图发出来」：网页端直接把本轮上传的图还回去。
    # 之前走 qq_send 的 image op，被管理员权限挡下，用户只看到“需要管理员”。
    echo = _uploaded_image_echo(message, ctx)
    if echo is not None:
        return echo

    file_reply = await _uploaded_file_reply(message, ctx, cfg)
    if file_reply is not None:
        return file_reply

    # 工具意图直通：提醒/记忆/待办这类语义极其明确的请求，直接执行工具，
    # 不赌模型会不会选工具。实测 LLM 在 QQ 群里经常推脱「我没这功能」——
    # 明明注册了工具，模型却宁可道歉也不调用，用户体验是致命的。
    emote = await _direct_emote(query, ctx, cfg)
    if emote is not None:
        return emote
    direct = await _direct_tool(query, ctx, cfg)
    if direct is not None:
        return direct

    # 本地小模型 + 自动联网：不要把整段网页塞给 1B 再指望它自己归纳。
    # 实测 MiniCPM5 看到两条新闻只复读标题，甚至回「没找到相关信息」；
    # 用同一条模型跑一次「只写事实」的短归纳，稳定得多。
    if (local_models.small_model_mode(cfg) and ctx.get("web_block")
            and _wants_web_digest(query)):
        try:
            digest = await _summarize_search(query, ctx["web_block"], cfg)
            if digest:
                return AgentReply(
                    text=digest, confidence=0.8, mode="llm_react",
                    tool_used="web_search",
                    tool_result={"tool": "web_search", "found": True,
                                 "note": ctx["web_block"][:800], "source": "auto_web"},
                    ctx_used=ctx.get("used"))
        except Exception:
            pass

    # 链接直读：消息里给了明确 URL 且要求看内容时，直接抓取再交给模型总结。
    # 不能指望模型每轮都主动选 read_source——实测它会先吐槽"占位符网站"
    # 而不是真去读（模型没有"必须调用工具"的硬约束）。
    web_reply = await _prefetch_url(query, ctx, cfg)
    if web_reply is not None:
        return web_reply
    file_reply = await _prefetch_file(query, ctx, cfg)
    if file_reply is not None:
        return file_reply

    # 没接通模型时不要用规则话术硬撑着回 QQ：那等于对外宣称"我是机器人但我不懂"。
    # mode="no_model" 让网关直接静默（Web 端仍保留兜底话术，不影响网页访客体验）。
    #
    # 但管理员显式把 engine.mode 设成 "rule" 时必须照做：那是「无模型部署」的
    # 正式配置（e2e 体检、内网纯知识库场景都靠它），不是模型故障降级。
    # 之前这里只看 has_key，导致显式 rule 模式在 QQ 渠道被静默吞掉，
    # 体检里 6 条 KB/工具用例全部 FAIL（已复现）。
    mode = cfg.get("engine", {}).get("mode", "auto")
    if (mode != "rule"
            and str(message.channel_type or "").startswith("qq")
            and not cfg.get("llm", {}).get("has_key")):
        return AgentReply(text="", confidence=0.0, mode="no_model", ctx_used=ctx["used"])
    llm_reply = None
    if mode in ("llm", "auto") and cfg.get("llm", {}).get("has_key"):
        with tracing.span("bigrobot.llm", {"model": cfg["llm"].get("model", "")}):
            try:
                llm_reply = await _llm_answer_best(query, ctx, cfg,
                                                   image_b64=message.image_b64,
                                                   channel=message.channel_type)
            except Exception:
                llm_reply = None
        if llm_reply is None and mode == "llm":
            rule = await _rule_react(query, ctx, cfg)
            rule.mode = "rule_fallback"
            return rule
    if llm_reply:
        _maybe_critique(llm_reply, ctx, visitor_key)
        return llm_reply
    return await _rule_react(query, ctx, cfg)


async def _llm_answer_best(query: str, ctx: dict, cfg: dict, *, image_b64: str = "",
                           channel: str = "") -> AgentReply | None:
    """多模型择优（集群）：并行取两版，按规则打分挑更好的一版。

    只在闲聊类意图开启（quality.ensemble>1 且意图在清单内），工具/知识类不走——
    那些场景多跑一遍模型既不提升正确率，又白烧算力、拖慢响应。
    任何一路失败都退回单路结果，不因为择优把整轮搞挂。
    """
    from core import ensemble, intent as intent_mod

    qcfg = cfg.get("quality") or {}
    n = int(qcfg.get("ensemble") or 1)
    it = ctx.get("intent") or intent_mod.classify(query)
    allowed = qcfg.get("ensemble_intents") or []
    if n <= 1 or image_b64 or it.name not in allowed:
        return await _llm_answer(query, ctx, cfg, image_b64=image_b64)

    chain = llm_mod_chain_models(cfg)
    if len(chain) < 2:
        return await _llm_answer(query, ctx, cfg, image_b64=image_b64)

    picks = chain[:max(2, min(n, len(chain)))]
    tasks = [asyncio.create_task(_llm_answer(query, ctx, cfg, image_b64=image_b64, prefer=m))
             for m in picks]
    got: list[dict] = []
    for t in asyncio.as_completed(tasks):
        try:
            r = await t
        except Exception:
            r = None
        if r is not None and (r.text or "").strip():
            got.append({"answer": r.text, "reply": r, "model": ""})
    for t in tasks:
        if not t.done():
            t.cancel()
    if not got:
        return None
    if len(got) == 1:
        return got[0]["reply"]
    best, scores = ensemble.choose(got, query, channel)
    if best < 0:
        return got[0]["reply"]
    reply = got[best]["reply"]
    try:
        store.critique_add("ensemble", len(reply.text or ""),
                           [f"择优：{len(got)} 版，分 {scores}"])
    except Exception:
        pass
    return reply


def llm_mod_chain_models(cfg: dict) -> list[str]:
    """备援链里的模型名（去重、保持顺序），供择优挑选。"""
    llm_cfg = cfg.get("llm") or {}
    out: list[str] = []
    for c in llm._chain(llm_cfg, llm_cfg.get("model") or ""):
        if c["model"] not in out:
            out.append(c["model"])
    return out


async def run_stream(message: ChannelMessage, history: list[dict], visitor_key: str):
    """流式管线：产出 ("delta", str) 增量与 ("final", AgentReply) 终态。

    delta 仅供打字机呈现；final.text 为权威内容（可能因工具调用/降级与流式片段不同，消费方须以终态替换）。
    """
    prepared = await _prepare(message, history, visitor_key)
    if isinstance(prepared, AgentReply):
        yield ("delta", prepared.text)
        yield ("final", prepared)
        return
    cfg, query, ctx = prepared

    # 标注回复：流式入口同样先查标注（与 run() 语义一致）
    ann = store.annotation_hit(query)
    if ann:
        reply = AgentReply(
            text=ann["answer"], mode="annotation", confidence=1.0,
            citations=[f"标注#{ann['id']}"],
        )
        yield ("delta", reply.text)
        yield ("final", reply)
        return

    # 流式入口必须和非流式共用同一组确定性直通：
    # 否则网页端「发个表情包」会绕过 _direct_emote，模型自己吐 [表情包:...] 文本，
    # 而 API 非流式测试却是 rule_react + 真图——同一个功能两个结果。
    boundary = _boundary_reply(query, ctx)
    if boundary is not None:
        yield ("delta", boundary.text)
        yield ("final", boundary)
        return
    echo = _uploaded_image_echo(message, ctx)
    if echo is not None:
        yield ("delta", echo.text)
        yield ("final", echo)
        return
    file_reply = await _uploaded_file_reply(message, ctx, cfg)
    if file_reply is not None:
        yield ("delta", file_reply.text)
        yield ("final", file_reply)
        return
    emote = await _direct_emote(query, ctx, cfg)
    if emote is not None:
        yield ("delta", emote.text)
        yield ("final", emote)
        return
    if _will_generate_image(query, ctx):
        # 直通生图不是流式模型路径；先给一句等待，再让它慢慢画。
        yield ("delta", "在画了，等我一下。")
    direct = await _direct_tool(query, ctx, cfg)
    if direct is not None:
        yield ("delta", direct.text)
        yield ("final", direct)
        return

    mode = cfg.get("engine", {}).get("mode", "auto")
    final: AgentReply | None = None
    # 必须在分支外初始化：规则模式（无 LLM Key）走不到 if 内部，
    # 后面 `if not deltas_sent` 会 UnboundLocalError —— 而规则模式正是默认路径，
    # 等于「没配 Key 时流式对话必崩」（已复现，前端只看到兜底话术）。
    deltas_sent = False
    if mode in ("llm", "auto") and cfg.get("llm", {}).get("has_key"):
        data = None
        try:
            async for ev in llm.react_stream(query, ctx, cfg, message.image_b64):
                if ev["type"] == "delta":
                    deltas_sent = True
                    yield ("delta", ev["text"])
                elif ev["type"] == "final":
                    data = ev["data"]
                    break
                elif ev["type"] == "error":
                    break
        except Exception:  # aqg: top-level boundary
            data = None
        # 流式只跑了一轮，必须补 OBSERVE：
        # - 模型要工具 → 执行并把结果回填
        # - 模型只说「我这就去查」→ 逼一轮真实答案
        # 否则用户看到的是空回复或一句空话（实测 u2-flash 两种都复现）。
        if data is not None:
            wants_tool = bool(str(data.get("tool") or "").strip())
            promise_only = llm.is_promise_only(str(data.get("answer") or ""))
            if wants_tool or promise_only:
                if str(data.get("tool") or "") == "generate_image":
                    # 生图通常要十几秒；先给一句人话，别让用户盯着空气。
                    # 这不是终态，final 到达后前端会用“图来了”覆盖。
                    yield ("delta", "在画了，等我一下。")
                final = await _llm_answer(query, ctx, cfg,
                                          image_b64=message.image_b64, first=data)
            else:
                final = await _make_llm_reply(data, ctx, cfg)
        elif not deltas_sent:
            # 流式未产出任何内容：按非流式再试一次（内部含多模型备援），仍失败才回规则
            try:
                final = await _llm_answer(query, ctx, cfg, image_b64=message.image_b64)
            except Exception:  # aqg: top-level boundary
                final = None
    if final is None:
        final = await _rule_react(query, ctx, cfg)
        if mode == "llm" and cfg.get("llm", {}).get("has_key"):
            final.mode = "rule_fallback"
    if str(final.mode or "").startswith("llm"):
        await _gate_output(final, query, {**cfg, "_channel": message.channel_type})
    final = await _ensure_english(final, query, cfg)
    final = await _ensure_chinese(final, query, cfg)
    # 输出钩子：与非流式入口同一套规则（final.text 是权威内容，前端会以它覆盖打字机片段）
    final = _apply_post_hooks(final, cfg)
    # 已向客户端发过 delta 时不再补发 delta：
    # 否则前端会把「半截 LLM 文本 + 规则话术」拼在一起显示（已复现）。
    # final 仍完整返回，前端以它为准覆盖。
    if not deltas_sent:
        yield ("delta", final.text)
    if final is not None and str(final.mode or "").startswith("llm"):
        _maybe_critique(final, ctx, visitor_key)
    yield ("final", final)
