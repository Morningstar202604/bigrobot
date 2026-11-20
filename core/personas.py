"""角色预设注册表。

每个预设只保留「元数据」（名字、分类、图标、卖点、温度、推荐渠道、标签）；
**人设正文不在这里手写**，而是由 `core/data/characters/<id>.json` 渲染，
资料卡是唯一事实源。这样改一个角色的癖好只动卡片，不会出现两处文案打架。

默认角色「零」仍然是出厂人设 `core.persona.DEFAULT_PERSONA`——它要保证
未配置任何角色时也有一份完整、可离线工作的提示词。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.character import render_for
from core.persona import DEFAULT_PERSONA


@dataclass(frozen=True)
class PersonaPreset:
    id: str
    name: str
    category: str
    icon: str
    description: str
    persona: str
    temperature: float
    channels: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self, *, with_persona: bool = True) -> dict:
        out = {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "icon": self.icon,
            "description": self.description,
            "temperature": self.temperature,
            "channels": list(self.channels),
            "tags": list(self.tags),
            "persona_chars": len(self.persona),
        }
        if with_persona:
            out["persona"] = self.persona
        return out


def _from_card(preset_id: str, fallback: str) -> str:
    """卡片优先；卡片缺失时回退到一句最小行为约束，不让预设整体失效。"""
    return render_for(preset_id) or fallback


CATEGORIES: tuple[str, ...] = ("通用", "专业", "教育", "创意", "生活", "社群")

# (id, 名字, 分类, 图标, 一句话卖点, 温度, 渠道, 标签)
_META = (
    ("zero", "零", "社群", "Zap", "夜班看板娘：群聊现场处置，毒舌但护短", 0.8,
     ("qq_group", "qq_private"), ("默认", "群聊", "人格化")),
    ("secretary", "白", "通用", "Briefcase", "所长：账号接管、权限边界、最坏情况先说", 0.3,
     (), ("账号", "权限")),
    ("minimal", "剪", "通用", "MessageCircle", "极简派：能一个字说完就不用两个", 0.2,
     (), ("短回复", "效率")),
    ("presale", "岚", "专业", "Sparkles", "提案：把参数翻译成对方能听懂的场景", 0.5,
     (), ("提案", "销售")),
    ("tech", "椋", "专业", "Wrench", "运维：先看日志再猜原因，每步都有预期结果", 0.15,
     (), ("排障", "运维")),
    ("analyst", "数", "专业", "BarChart3", "分析：先定口径，再谈数字和因果", 0.2,
     (), ("数据", "口径")),
    ("researcher", "砚", "专业", "FlaskConical", "档案侦探：没有出处的句子不算资料", 0.25,
     (), ("核查", "出处")),
    ("socratic", "问", "教育", "GraduationCap", "导师：不直接给答案，用问题带你走一遍", 0.4,
     (), ("教学", "启发")),
    ("study-coach", "岸", "教育", "CalendarCheck", "备考教练：今天能做完的才叫计划", 0.3,
     (), ("备考", "计划")),
    ("interview-coach", "影", "教育", "UserCheck", "面试官：把「参与过」和「负责过」分开", 0.3,
     (), ("面试", "简历")),
    ("creative", "栗", "创意", "Lightbulb", "脑洞：先给十个方向，再挑一个", 0.9,
     (), ("发散", "点子")),
    ("copywriter", "棠", "创意", "PenLine", "文案：这句话，人会读第二遍吗", 0.7,
     (), ("文案", "标题")),
    ("schedule", "时", "生活", "CalendarClock", "时间管家：模糊的时间等于没有时间", 0.2,
     (), ("日程", "提醒")),
    ("companion", "澜", "生活", "HeartHandshake", "倾听：先听完，再说话", 0.6,
     (), ("倾听", "支持")),
    ("warm", "满", "生活", "Heart", "日常：好意不用大声说，做出来就行", 0.5,
     (), ("日常", "琐事")),
)

_FALLBACK = (
    "你是BigRobot 的角色。按资料卡里的身份、方法与边界回答；"
    "资料没写到的事直接说不知道，不编人名、不编链接、不编数字。"
)

PRESETS: tuple[PersonaPreset, ...] = tuple(
    PersonaPreset(
        id=pid,
        name=name,
        category=cat,
        icon=icon,
        description=desc,
        persona=(DEFAULT_PERSONA if pid == "zero" else _from_card(pid, _FALLBACK)),
        temperature=temp,
        channels=channels,
        tags=tags,
    )
    for pid, name, cat, icon, desc, temp, channels, tags in _META
)

_BY_ID = {p.id: p for p in PRESETS}


def all_presets() -> list[PersonaPreset]:
    return list(PRESETS)


def get(preset_id: str) -> PersonaPreset | None:
    return _BY_ID.get((preset_id or "").strip())


def default() -> PersonaPreset:
    return _BY_ID["zero"]


def list_public(*, with_persona: bool = True) -> dict:
    """API 出参：分类顺序固定，前端无需自己排序。"""
    order = {c: i for i, c in enumerate(CATEGORIES)}
    items = sorted(PRESETS, key=lambda p: (order.get(p.category, 99), p.name))
    return {
        "categories": list(CATEGORIES),
        "presets": [p.as_dict(with_persona=with_persona) for p in items],
        "default_id": default().id,
    }


def match_persona(text: str) -> PersonaPreset | None:
    """按完整提示词反查预设（控制台高亮「当前用的是哪个预设」）。"""
    t = (text or "").strip()
    if not t:
        return None
    for p in PRESETS:
        if p.persona.strip() == t:
            return p
    return None
