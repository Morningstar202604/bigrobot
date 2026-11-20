"""渠道会话映射：QQ 群/私聊等渠道按 chat 维度复用会话，空闲超过 TTL 自动新建。

TTL 语义：从「最后一次活动」（读取或写入该渠道映射）起算的空闲时长，不是会话总寿命。
并发原语分工：
- claim_channel_session：首次创建时原子认领，主键冲突即失败（输家复用赢家）
- replace_channel_session：TTL 过期换新会话时覆盖（必须能盖掉旧行）
- touch_channel_session：复用成功后刷新最后活动时间，否则 TTL 永远不滚动
"""
import os
import uuid
from datetime import datetime, timezone

from core import store


def idle_ttl() -> int:
    # 默认 12 小时：原来 30 分钟就换新会话，群友隔一会儿回来问「刚才那事」，
    # 机器人已经"失忆"，用户体感就是「老是记不住、回顾不了」。
    return int(os.environ.get("SESSION_IDLE_TTL", "43200"))


def _is_fresh(row: dict | None) -> bool:
    """映射是否存在、会话是否仍 ongoing、空闲时长是否在 TTL 内。"""
    if not row:
        return False
    sess = store.get_session(row["session_id"])
    # 转人工/坐席处理中仍然是同一个会话：如果这里只认 ongoing，
    # 访客被接管后再发消息会静默新建会话，坐席台看不到，机器人还会抢答（已复现）。
    if not sess or sess["status"] not in ("ongoing", "pending_agent", "agent_handled"):
        return False
    try:
        updated = datetime.fromisoformat(row["updated_at"])
    except (TypeError, ValueError):
        return False
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    return age <= idle_ttl()


def canonical_account(channel: str, account_id: str | None) -> str | None:
    """把网关给的裸账号号补成账号表的主键形态：10001 -> qq:10001。

    网关 payload 里的 self_id 是纯数字，而 accounts 表主键是「渠道:号」。
    两边不统一时，按账号筛选永远查不到会话（已复现）。
    """
    if not account_id:
        return None
    if ":" in account_id:
        prefix, _, uid = account_id.partition(":")
        # qq_group:10001 / qq_private:10001 都归一到账号表的 qq:10001
        if prefix in ("qq_group", "qq_private", "onebot"):
            return f"qq:{uid}"
        return account_id
    ch = (channel or "").split("_", 1)[0]
    return f"{ch}:{account_id}" if ch else account_id


def scoped_visitor(visitor_id: str, channel: str, account_id: str | None) -> str:
    """访客身份按机器人账号分桶：同一用户在两个号上的记忆/档案不混。

    没有账号时保持原样，网页与老网关调用不受影响。
    """
    acct = canonical_account(channel, account_id)
    return f"{visitor_id}#{acct}" if acct else visitor_id


def resolve_session(channel: str, visitor_id: str, account_id: str | None = None) -> str:
    """按 (channel, account_id) 复用/创建会话。

    同一群被两个机器人监听时，channel 相同但 account 不同，必须各有一条映射。
    旧库的映射在 account_id='' 桶里：首次以具体账号进入时，如果旧会话本身没有
    归属或正好属于这个账号，就把它认领过来，避免升级后突然丢上下文。
    """
    account_id = canonical_account(channel, account_id)
    acct = account_id or ""
    row = store.get_channel_session(channel, acct)

    if row is not None and _is_fresh(row):
        store.touch_channel_session(channel, row["session_id"], acct)
        return row["session_id"]

    # 兼容老库：把无账号的旧映射迁移到当前账号，仅当会话没有归属或归属一致。
    if row is None and acct:
        legacy = store.get_channel_session(channel, "")
        if legacy is not None and _is_fresh(legacy):
            legacy_sess = store.get_session(legacy["session_id"])
            legacy_acct = (legacy_sess or {}).get("account_id")
            legacy_acct = canonical_account(channel, legacy_acct) if legacy_acct else None
            if legacy_acct in (None, "", acct):
                store.set_channel_session(channel, legacy["session_id"], acct)
                store.drop_channel_session(channel, "")
                return legacy["session_id"]

    sid = uuid.uuid4().hex
    store.create_session(sid, visitor_id, account_id=account_id)

    if row is None:
        if store.claim_channel_session(channel, sid, acct):
            return sid
        winner = store.get_channel_session(channel, acct)
        winner_sid = winner["session_id"] if winner else ""
        if _is_fresh(winner):
            store.discard_session(sid)
            return winner_sid
        store.replace_channel_session(channel, sid, acct)
        return sid

    old_sid = (row or {}).get("session_id") if row else None
    if old_sid:
        store.close_session(old_sid)
    if store.replace_channel_session(channel, sid, acct):
        return sid
    winner = store.get_channel_session(channel, acct)
    winner_sid = winner["session_id"] if winner else ""
    if _is_fresh(winner):
        store.discard_session(sid)
        return winner_sid
    return sid
