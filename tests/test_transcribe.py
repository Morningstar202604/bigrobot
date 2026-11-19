"""语音转写：未配置要 503，配置后要回填正文。"""
from core import store, transcribe
from tests.conftest import create_web_session


def _voice_message(client):
    sid, _ = create_web_session(client)
    mid = store.add_message(sid, "visitor", "[语音]", refs=["https://x/1.wav"],
                            external_id="v1", source="platform")
    return sid, mid


def test_transcribe_not_configured(client, monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    sid, mid = _voice_message(client)
    r = client.post(f"/api/sessions/{sid}/messages/{mid}/transcribe")
    assert r.status_code == 503


def test_transcribe_backfills_content(client, monkeypatch):
    async def fake(url, language="zh-CN"):
        assert url == "https://x/1.wav"
        return "明天十点开会"

    monkeypatch.setattr(transcribe, "transcribe_url", fake)
    sid, mid = _voice_message(client)
    r = client.post(f"/api/sessions/{sid}/messages/{mid}/transcribe")
    assert r.status_code == 200 and r.json()["text"] == "明天十点开会"
    msg = next(m for m in store.get_messages(sid) if m["id"] == mid)
    assert msg["content"] == "明天十点开会"
    assert msg["refs"] == ["https://x/1.wav"]   # 音频地址保留


def test_message_without_audio_is_400(client):
    sid, _ = create_web_session(client)
    mid = store.add_message(sid, "visitor", "普通文本")
    r = client.post(f"/api/sessions/{sid}/messages/{mid}/transcribe")
    assert r.status_code == 400
