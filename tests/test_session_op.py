"""会话写操作的统一入口：一次 op，五件事。

分成五个 URL 的问题是权限模型分裂：escalate/feedback 要 session secret，
take/reply/close 要 admin token。合并后按 op 判，规则集中在一处。
"""
from tests.conftest import create_web_session


def test_session_op_take_reply_close(client):
    sid, _ = create_web_session(client)
    r = client.post(f"/api/sessions/{sid}/op", json={"op": "take", "visitor_id": "op1"})
    assert r.status_code == 200 and r.json()["status"] == "agent_handled"

    r = client.post(f"/api/sessions/{sid}/op", json={"op": "reply", "content": "人工来处理"})
    assert r.status_code == 200 and r.json()["role"] == "operator"

    r = client.post(f"/api/sessions/{sid}/op", json={"op": "close"})
    assert r.status_code == 200 and r.json()["status"] == "closed"

    # 关闭后再接管必须 409，而不是静默成功
    assert client.post(f"/api/sessions/{sid}/op", json={"op": "take"}).status_code == 409


def test_session_op_escalate_needs_session_secret(client):
    sid, _ = create_web_session(client)
    # client fixture 里已带 X-Session-Secret，正常路径应成功
    r = client.post(f"/api/sessions/{sid}/op", json={"op": "escalate"})
    assert r.status_code == 200 and r.json()["status"] == "pending_agent"

    client.headers.pop("X-Session-Secret", None)
    assert client.post(f"/api/sessions/{sid}/op", json={"op": "escalate"}).status_code == 401


def test_session_op_unknown_op(client):
    sid, _ = create_web_session(client)
    assert client.post(f"/api/sessions/{sid}/op", json={"op": "删库"}).status_code == 400


def test_session_op_feedback_escalates_on_not_helpful(client):
    sid, _ = create_web_session(client)
    r = client.post(f"/api/sessions/{sid}/op", json={"op": "feedback", "rating": "not_helpful"})
    assert r.status_code == 200
    assert r.json()["rating"] == "not_helpful"
