import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import local_models


def _tiny_server(payload: bytes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_catalog_has_production_and_test_tiers():
    production = [m for m in local_models.CATALOG if not m.get("test_only")]
    tests = [m for m in local_models.CATALOG if m.get("test_only")]
    assert [m["id"] for m in production] == ["qwen3.5-9b", "qwen3.5-4b"]
    assert tests and all(m["params_b"] < 2.0 for m in tests)
    for item in local_models.CATALOG:
        assert item["context"] >= 131_072
        assert item["file"].endswith(".gguf")
        assert item["size"] > 0
        assert item["min_ram_gb"] > 0


def test_small_model_mode_only_for_local(monkeypatch):
    assert local_models.small_model_mode({
        "llm": {"base_url": "http://127.0.0.1:18080/v1", "context_window": 8192}
    })
    assert not local_models.small_model_mode({
        "llm": {"base_url": "https://api.deepseek.com/v1", "context_window": 8192}
    })
    assert local_models.small_model_mode({
        "llm": {"base_url": "https://api.deepseek.com/v1", "local_model_id": "botpsy-0.8b"}
    })
    assert not local_models.small_model_mode({
        "llm": {"base_url": "http://127.0.0.1:18080/v1", "local_compact": False}
    })


def test_compact_persona_keeps_identity_and_drops_life_story():
    text = "你是「零」，一只三花猫娘看板娘。\n下面是一大段童年经历。" + "很长的设定" * 100
    compact = local_models.compact_persona(text)
    assert compact.startswith("你是「零」")
    assert len(compact) < 200
    assert "童年经历" not in compact


def test_download_resumes_and_installs(monkeypatch, tmp_path):
    payload = b"gguf" + bytes(range(256)) * 20
    item = {
        "id": "tiny-0.8b", "name": "Tiny", "params_b": 0.8, "repo": "x/y",
        "file": "tiny.gguf", "size": len(payload), "quant": "Q4", "context": 131072,
        "license": "MIT", "tool_calling": True, "chinese": True, "recommended": False,
        "badge": "test", "tagline": "", "why": "", "best_for": [], "ram_gb": 1,
        "default_ctx": 2048,
    }
    srv = _tiny_server(payload)
    monkeypatch.setenv("BIGROBOT_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(local_models, "CATALOG", [item])
    monkeypatch.setattr(local_models, "_endpoints", lambda: [f"http://127.0.0.1:{srv.server_port}"])
    local_models._JOBS.clear()
    try:
        # 预置半截文件，验证 Range 续传路径
        part = local_models._part_path(item)
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(payload[:1000])
        job = local_models.start_download("tiny-0.8b")
        deadline = time.time() + 8
        while time.time() < deadline:
            row = next(j for j in local_models.list_jobs() if j["job_id"] == job["job_id"])
            if row["status"] in ("installed", "error"):
                break
            time.sleep(0.1)
        assert row["status"] == "installed", row
        assert local_models.is_installed(item)
        assert local_models._final_path(item).read_bytes() == payload
        meta = json.loads((local_models._model_dir("tiny-0.8b") / "model.json").read_text())
        assert meta["size"] == len(payload)
    finally:
        srv.shutdown()


def test_reminder_uses_user_original_text_not_model_args():
    from core import store, tools
    from core.tool_context import ToolContext

    ctx = ToolContext(
        visitor_id="v-local-test",
        channel_type="webchat",
        channel_user_id="u1",
        message_text="帮我设个明天早上九点的提醒，提醒我喝水",
    )
    result = tools.tool_remind(ctx, text="的 ， 喝水", when="明天下午五点")
    assert result["found"] is True, result
    assert "09:00" in result["note"]
    assert "喝水" in result["note"]
    assert "明天下午五点" not in result["note"]
    entries = store.reminder_list("v-local-test")
    assert entries and entries[-1]["text"] == "喝水"


def test_recommendation_follows_machine_ram_not_a_hardcoded_model():
    assert local_models.recommend_model({"ram_gb": 3.9}) is None
    assert local_models.recommend_model({"ram_gb": 7.8})["id"] == "qwen3.5-4b"
    assert local_models.recommend_model({"ram_gb": 15.6})["id"] == "qwen3.5-9b"
    assert local_models.recommend_model({"ram_gb": 64})["id"] == "qwen3.5-9b"
    assert all(
        not m.get("test_only") for m in [local_models.recommend_model({"ram_gb": 64})]
    )


def test_large_local_models_do_not_run_in_compact_mode():
    assert local_models.small_model_mode({
        "llm": {"base_url": "http://127.0.0.1:18080/v1", "local_model_id": "qwen3.5-4b"}
    }) is False
    assert local_models.small_model_mode({
        "llm": {"base_url": "http://127.0.0.1:18080/v1", "local_model_id": "minicpm5-1b"}
    }) is True


def test_overview_recommendation_uses_detected_ram(monkeypatch, tmp_path):
    monkeypatch.setenv("BIGROBOT_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(local_models, "system_profile", lambda: {
        "os": "Linux", "arch": "x86_64", "cpu": "test", "cpu_cores": 4,
        "ram_gb": 8.0, "gpu": "", "vram_gb": 0.0, "unified_memory": False,
    })
    d = local_models.overview()
    assert d["recommendation"]["model_id"] == "qwen3.5-4b"
    assert [m["id"] for m in d["models"] if m["recommended"]] == ["qwen3.5-4b"]
    assert all(not m["recommended"] for m in d["models"] if m["test_only"])
