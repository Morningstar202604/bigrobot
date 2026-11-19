"""渠道适配器注册表：core 侧唯一事实源。

为什么不用 `adapters/*/manifest.toml` 自动发现：core 与 gateway 是两个进程，
动态扫描在打包后会指向不存在的目录。这里用一张显式表，谁接了什么一目了然，
也不会出现"扫描为空却假装有渠道"的情况。

能力（capabilities）是控制台渲染的依据：界面按能力出按钮，不按平台写死。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Adapter:
    key: str                 # 渠道标识，写进 sessions.channel
    label: str               # 展示名
    capabilities: tuple[str, ...] = ()   # 例如 group.member_list
    transport: str = ""      # onebot / webhook / builtin
    note: str = ""


ADAPTERS: tuple[Adapter, ...] = (
    Adapter(
        key="webchat",
        label="网页访客",
        capabilities=("chat.stream", "session.op", "kb"),
        transport="builtin",
        note="内置，无需部署",
    ),
    Adapter(
        key="qq",
        label="QQ（OneBot）",
        capabilities=(
            "group.history", "direct.history", "group.member_list",
            "group.files", "group.notice", "friend.list",
            "message.send", "group.admin", "voice.transcribe",
        ),
        transport="onebot",
        note="需本地协议端，部署与登录见 DEPLOY.md",
    ),
)


def catalog() -> list[dict]:
    return [
        {
            "key": a.key,
            "label": a.label,
            "transport": a.transport,
            "capabilities": list(a.capabilities),
            "note": a.note,
        }
        for a in ADAPTERS
    ]


def capabilities_of(key: str) -> set[str]:
    for a in ADAPTERS:
        if a.key == key:
            return set(a.capabilities)
    return set()


def supports(key: str, capability: str) -> bool:
    return capability in capabilities_of(key)

