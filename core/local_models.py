"""本地小模型：推荐目录、断点下载、llama.cpp 托管与一键启用。

小模型不是「把云端模型名换掉」就能用：工具清单、人设和上下文预算都会把
0.5B—1B 的注意力挤爆。这里除了下载与启动，还提供 small_model_mode()，
让上层自动切到短人设 + 核心工具 + 小预算。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

from core import config, paths

# 只推荐明确低于 2B、可商用、GGUF 可直接落地的模型。
# 评测数字只写模型卡公开可查的结论，不在这里编「最强」。
CATALOG: list[dict] = [
    {
        "id": "minicpm5-1b",
        "name": "MiniCPM5-1B",
        "params_b": 1.08,
        "repo": "openbmb/MiniCPM5-1B-GGUF",
        "file": "MiniCPM5-1B-Q4_K_M.gguf",
        "size": 688_065_920,
        "quant": "Q4_K_M",
        "context": 131_072,
        "license": "Apache-2.0",
        "tool_calling": True,
        "chinese": True,
        "recommended": True,
        "released": "2026-05-19",
        "badge": "1B 推荐",
        "tagline": "2026 年 1B 级开源 SOTA：128K 上下文，Agent 工具调用、代码与困难推理领先同尺寸。",
        "why": "官方模型卡：1,080,632,832 参数、131,072 上下文、Apache-2.0；对比 Qwen3-0.6B/0.8B、LFM2.5-1.2B 在 MMLU、Coding、Agentic、BFCLv4 等评测领先。llama.cpp 下由 BigRobot 做 XML 工具适配，默认关闭 thinking 以适配 CPU。",
        "best_for": ["Agent 工具调用", "长上下文", "中英双语", "通用问答"],
        "ram_gb": 3,
        "default_ctx": 8192,
        # 默认模板会先吐一长段 <think>，把 max_tokens 吃光；本地 CPU 关掉思考。
        "chat_template_kwargs": {"enable_thinking": False},
    },
    {
        "id": "botpsy-0.8b",
        "name": "BotPsy-0.8B",
        "params_b": 0.8,
        "repo": "qvac/BotPsy-0.8B-GGUFs",
        "file": "botpsy-0.8b-q4_k_m-imat.gguf",
        "size": 529_296_960,
        "quant": "Q4_K_M",
        "context": 262_144,
        "license": "Apache-2.0",
        "tool_calling": True,
        "chinese": True,
        "recommended": False,
        "released": "2026-11-11",
        "badge": "工具专精",
        "tagline": "0.8B 工具调用特化，体积最小、响应最快；通用知识与长文弱于 MiniCPM5。",
        "why": "在 BFCL v4、ACEBench、τ-bench、ToolSandbox 等六项工具/Agent 评测中领先 1.2B 以下同级模型；适合把提醒、天气、文件这类多步任务压到最低内存。",
        "best_for": ["极低内存", "工具调用", "日程提醒"],
        "ram_gb": 2,
        "default_ctx": 8192,
    },
    {
        "id": "qwen3.5-0.8b",
        "name": "Qwen3.5-0.8B",
        "params_b": 0.8,
        "repo": "unsloth/Qwen3.5-0.8B-GGUF",
        "file": "Qwen3.5-0.8B-Q4_K_M.gguf",
        "size": 532_517_120,
        "quant": "Q4_K_M",
        "context": 262_144,
        "license": "Apache-2.0",
        "tool_calling": True,
        "chinese": True,
        "recommended": False,
        "badge": "通用基线",
        "tagline": "原生 256K 上下文，中文稳，工具调用是通用水平。",
        "why": "BotPsy 的基座模型，长上下文与中文对话扎实；需要原厂通用能力时选它，但复杂 Agent 任务不如 MiniCPM5。",
        "best_for": ["中文对话", "长上下文", "通用问答"],
        "ram_gb": 2,
        "default_ctx": 8192,
    },
]

CORE_TOOLS = (
    "now", "remind", "reminders", "weather", "remember", "recall_memory",
    "calc", "web_search",
)

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_PROC: subprocess.Popen | None = None
_SERVER: dict = {}
_SERVER_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# 路径与目录
# ---------------------------------------------------------------------------

def models_root() -> Path:
    raw = (os.environ.get("BIGROBOT_MODELS_DIR") or "").strip()
    root = Path(raw).expanduser() if raw else paths.data_dir() / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_id(model_id: str) -> str:
    value = (model_id or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value):
        raise ValueError("模型 id 不合法")
    return value


def _entry(model_id: str) -> dict:
    mid = _safe_id(model_id)
    for item in CATALOG:
        if item["id"] == mid:
            return item
    raise ValueError("未知模型")


def _human(n: int | float) -> str:
    size = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit != "GB" else f"{size:.1f} GB"
        size /= 1024
    return f"{size:.1f} GB"


def _model_dir(model_id: str) -> Path:
    return models_root() / _safe_id(model_id)


def _final_path(item: dict) -> Path:
    return _model_dir(item["id"]) / item["file"]


def _part_path(item: dict) -> Path:
    return _final_path(item).with_name(_final_path(item).name + ".part")


def installed_bytes(item: dict) -> int:
    final = _final_path(item)
    if final.is_file():
        return final.stat().st_size
    part = _part_path(item)
    return part.stat().st_size if part.is_file() else 0


def is_installed(item: dict) -> bool:
    final = _final_path(item)
    return final.is_file() and final.stat().st_size >= int(item.get("size") or 0) * 0.98


def small_model_mode(cfg: dict) -> bool:
    """本地端点或显式 local_model_id → 自动收紧提示词。

    不只看 8K：用户手工接 Ollama 也应当走短提示词；云端模型不受影响。
    """
    llm = (cfg or {}).get("llm") or {}
    if llm.get("local_compact") is False:
        return False
    if llm.get("local_model_id"):
        return True
    base = str(llm.get("base_url") or "").lower()
    host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
    if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return False
    ctx = int(llm.get("context_window") or 0)
    return bool(ctx and ctx <= 32_768)


def compact_persona(text: str) -> str:
    """保留第一句身份，丢掉长履历；小模型没有预算演完整个人生。"""
    first = re.split(r"[。\n]", (text or "").strip(), maxsplit=1)[0].strip()
    if not first or len(first) > 120:
        return "你是 BigRobot，一个直接、可靠的中文助理。先给结论，少说废话，不自称 AI。"
    return first + "。说话简短、直接，先给结论；不自称 AI、助手程序或语言模型。"


def _server_state_path() -> Path:
    return models_root() / "server.json"


def _save_server_state(state: dict) -> None:
    tmp = _server_state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _server_state_path())


def _load_server_state() -> dict:
    try:
        return json.loads(_server_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _health(base_url: str) -> bool:
    try:
        r = httpx.get(base_url.rstrip("/") + "/models", timeout=2.5)
        return r.status_code < 400
    except Exception:
        return False


def server_status() -> dict:
    global _PROC
    with _SERVER_LOCK:
        state = _SERVER or _load_server_state()
        if not state:
            return {"running": False}
        pid = int(state.get("pid") or 0)
        alive = bool(_PROC and _PROC.poll() is None) or _pid_alive(pid)
        base = state.get("base_url") or f"http://127.0.0.1:{state.get('port')}/v1"
        running = alive and _health(base)
        if not running and alive:
            # 端口还没起完或进程僵住：以 health 为准，不谎报 running。
            running = False
        return {**state, "running": running, "pid_alive": alive}


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------

def _endpoints() -> list[str]:
    env = (os.environ.get("BIGROBOT_HF_ENDPOINT") or "").strip()
    out = []
    if env:
        out.append(env.rstrip("/"))
    out.extend(["https://hf-mirror.com", "https://huggingface.co"])
    seen: set[str] = set()
    result: list[str] = []
    for url in out:
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _download_url(base: str, item: dict) -> str:
    return f"{base}/{item['repo']}/resolve/main/{item['file']}?download=true"


def _probe(base: str, item: dict) -> bool:
    headers = {"Range": "bytes=0-0"}
    token = (os.environ.get("HF_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as c:
            r = c.get(_download_url(base, item), headers=headers)
            return r.status_code in (200, 206)
    except Exception:
        return False


def _job_public(job: dict) -> dict:
    total = int(job.get("total") or 0)
    got = int(job.get("bytes") or 0)
    pct = (got / total * 100) if total else 0
    return {
        "job_id": job["job_id"], "model_id": job["model_id"], "status": job["status"],
        "bytes": got, "total": total, "percent": round(min(100, max(0, pct), 1)),
        "speed_bps": int(job.get("speed") or 0), "eta_s": int(job.get("eta") or 0),
        "error": job.get("error") or "", "path": job.get("path") or "",
    }


def list_jobs() -> list[dict]:
    with _JOBS_LOCK:
        return [_job_public(j) for j in _JOBS.values()]


def start_download(model_id: str) -> dict:
    item = _entry(model_id)
    if is_installed(item):
        return {"job_id": "", "model_id": item["id"], "status": "installed",
                "bytes": installed_bytes(item), "total": item["size"], "percent": 100,
                "speed_bps": 0, "eta_s": 0, "error": "", "path": str(_final_path(item))}
    with _JOBS_LOCK:
        for job in _JOBS.values():
            if job["model_id"] == item["id"] and job["status"] in ("queued", "downloading", "verifying"):
                return _job_public(job)
        job = {
            "job_id": uuid.uuid4().hex, "model_id": item["id"], "status": "queued",
            "bytes": installed_bytes(item), "total": int(item["size"]),
            "speed": 0, "eta": 0, "error": "", "path": "", "cancel": threading.Event(),
            "started": time.time(), "last": (time.time(), installed_bytes(item)),
        }
        _JOBS[job["job_id"]] = job
    threading.Thread(target=_download_worker, args=(item, job), name="local-model-download", daemon=True).start()
    return _job_public(job)


def cancel_job(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise ValueError("下载任务不存在")
        if job["status"] in ("installed", "error", "cancelled"):
            return _job_public(job)
        job["cancel"].set()
        job["status"] = "cancelling"
        return _job_public(job)


def _download_worker(item: dict, job: dict) -> None:
    part = _part_path(item)
    headers: dict[str, str] = {}
    token = (os.environ.get("HF_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = next((u for u in _endpoints() if _probe(u, item)), "")
    if not base:
        job.update(status="error", error="下载源不可达：请检查网络或设置 BIGROBOT_HF_ENDPOINT")
        return
    start = part.stat().st_size if part.is_file() else 0
    if start < 0 or start > int(item["size"]) * 1.05:
        start = 0
    if start:
        headers["Range"] = f"bytes={start}-"
    job["status"] = "downloading"
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=15, read=90, write=30, pool=15),
                          follow_redirects=True) as client:
            with client.stream("GET", _download_url(base, item), headers=headers) as r:
                if r.status_code not in (200, 206):
                    raise RuntimeError(f"下载源返回 HTTP {r.status_code}")
                length = int(r.headers.get("Content-Length") or 0)
                if r.status_code == 200:
                    # 服务端不认 Range：从头写，不能在半截文件后面续。
                    start = 0
                    part.parent.mkdir(parents=True, exist_ok=True)
                    part.write_bytes(b"")
                total = int(item["size"]) or (start + length)
                job["total"] = total
                mode = "ab" if start else "wb"
                done = start
                job["bytes"] = done
                with open(part, mode) as fh:
                    for chunk in r.iter_bytes(64 * 1024):
                        if job["cancel"].is_set():
                            job.update(status="cancelled", speed=0, eta=0)
                            return
                        if not chunk:
                            continue
                        fh.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        last_t, last_b = job["last"]
                        if now - last_t >= 0.5:
                            speed = (done - last_b) / max(0.001, now - last_t)
                            job.update(bytes=done, speed=speed,
                                       eta=int((total - done) / speed) if speed > 0 and total > done else 0,
                                       last=(now, done))
        if job["cancel"].is_set():
            job.update(status="cancelled", speed=0, eta=0)
            return
        job["status"] = "verifying"
        got = part.stat().st_size if part.is_file() else 0
        if got < int(item["size"]) * 0.98:
            raise RuntimeError(f"文件不完整（{_human(got)} / {_human(item['size'])}）")
        os.replace(part, _final_path(item))
        (_model_dir(item["id"]) / "model.json").write_text(json.dumps({
            "id": item["id"], "name": item["name"], "repo": item["repo"], "file": item["file"],
            "size": got, "source": base, "installed_at": int(time.time()),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        job.update(status="installed", bytes=got, percent=100, speed=0, eta=0,
                   path=str(_final_path(item)), error="")
    except Exception as exc:  # noqa: BLE001 - 后台线程必须自己留下可读错误
        job.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:300]}", speed=0, eta=0)


# ---------------------------------------------------------------------------
# 本地服务
# ---------------------------------------------------------------------------

def _find_port(start: int = 18080, end: int = 18120) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("没有可用的本地端口")


def _llama_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("llama_cpp") is not None


def start_server(model_id: str, n_ctx: int | None = None) -> dict:
    global _PROC, _SERVER
    item = _entry(model_id)
    if not is_installed(item):
        raise RuntimeError("模型尚未下载完成")
    status = server_status()
    if status.get("running"):
        if status.get("model_id") == item["id"]:
            return status
        # 同一时间只留一个本地模型：切模型先停旧的，避免两个进程抢 CPU 和内存。
        stop_server()
    with _SERVER_LOCK:
        if not _llama_available():
            raise RuntimeError("未安装 llama-cpp-python：pip install -r requirements-local.txt")
        port = _find_port()
        ctx = int(n_ctx or item.get("default_ctx") or 8192)
        ctx = max(2048, min(ctx, 32768))
        log_path = models_root() / "llama-server.log"
        cmd = [
            sys.executable, "-m", "llama_cpp.server",
            "--model", str(_final_path(item)),
            "--model_alias", item["id"],
            # 2 核机器用 1 线程会把 prompt 解析拖到 12ms/token；给满可用核心，
            # 上限 4，既跑得动也不把控制台饿死。
            "--n_ctx", str(ctx), "--n_threads", str(max(1, min(4, os.cpu_count() or 4))),
            "--n_threads_batch", str(max(1, min(4, os.cpu_count() or 4))),
            "--host", "127.0.0.1", "--port", str(port),
            # 不关 logits，llama-cpp-python 会按 n_ctx × vocab 分配一个 7.6GB 的
            # float32 数组（4GB 机器必 OOM，实测启动即崩）。8K 上下文下必须显式关。
            "--logits_all", "false",
        ]
        if item.get("chat_template_kwargs"):
            cmd.extend(["--chat_template_kwargs", json.dumps(item["chat_template_kwargs"], ensure_ascii=False)])
        log = open(log_path, "ab")
        # llama_cpp.server 的 uvicorn.run 会读环境变量 PORT/HOST，而 BigRobot
        # 自己的服务也用 PORT；不剥离就会让本地模型抢占同一端口（实测 8012 冲突）。
        child_env = {k: v for k, v in os.environ.items() if k not in ("PORT", "HOST", "CONFIG_FILE")}
        kwargs: dict = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL,
                        "env": child_env}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True
        _PROC = subprocess.Popen(cmd, **kwargs)  # noqa: S603 - 参数固定，无 shell
        base_url = f"http://127.0.0.1:{port}/v1"
        deadline = time.time() + 100
        while time.time() < deadline:
            if _PROC.poll() is not None:
                tail = ""
                try:
                    tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
                except OSError:
                    pass
                raise RuntimeError(f"本地模型启动失败（退出码 {_PROC.returncode}）：{tail[:600]}")
            if _health(base_url):
                _SERVER = {"model_id": item["id"], "port": port, "pid": _PROC.pid,
                           "base_url": base_url, "n_ctx": ctx, "started": int(time.time())}
                _save_server_state(_SERVER)
                return {**server_status(), "running": True}
            time.sleep(1)
        try:
            _PROC.terminate()
        except Exception:
            pass
        raise RuntimeError("本地模型 100 秒内没有就绪；请查看 data/models/llama-server.log")


def stop_server() -> dict:
    global _PROC, _SERVER
    with _SERVER_LOCK:
        state = _SERVER or _load_server_state()
        proc = _PROC
        pid = int(state.get("pid") or 0)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
        elif pid and _pid_alive(pid):
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        _PROC = None
        _SERVER = {}
        try:
            _server_state_path().unlink()
        except OSError:
            pass
    return {"running": False}


def activate(model_id: str, n_ctx: int | None = None) -> dict:
    item = _entry(model_id)
    server = start_server(item["id"], n_ctx=n_ctx)
    config.update_config({
        "llm": {
            "base_url": server["base_url"],
            "model": item["id"],
            "api_key": "local",
            "protocol": "openai-compatible",
            "context_window": int(server.get("n_ctx") or 8192),
            "max_output": 512,
            "tool_calling": True,
            "supports_vision": False,
            "local_model_id": item["id"],
            "local_compact": True,
        },
    })
    return {"ok": True, "model_id": item["id"], "server": server}


def remove_model(model_id: str) -> dict:
    item = _entry(model_id)
    status = server_status()
    if status.get("running") and status.get("model_id") == item["id"]:
        raise RuntimeError("模型正在运行，请先停止再删除")
    root = _model_dir(item["id"])
    if not root.exists():
        return {"ok": True, "removed": False}
    shutil.rmtree(root)
    return {"ok": True, "removed": True, "freed_bytes": item["size"]}


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def overview() -> dict:
    cfg = config.get_config()
    active_id = ((cfg.get("llm") or {}).get("local_model_id") or "")
    server = server_status()
    disk = shutil.disk_usage(models_root())
    items = []
    for item in CATALOG:
        got = installed_bytes(item)
        installed = is_installed(item)
        items.append({
            **{k: item[k] for k in (
                "id", "name", "params_b", "quant", "context", "license", "tool_calling",
                "chinese", "recommended", "badge", "tagline", "why", "best_for", "ram_gb",
                "repo", "file", "size", "default_ctx")},
            **({"released": item["released"]} if item.get("released") else {}),
            "installed": installed, "bytes": got,
            "size_label": _human(item["size"]), "bytes_label": _human(got),
            "active": bool(installed and active_id == item["id"] and server.get("running")),
            "download_url": _download_url(_endpoints()[-1], item),
        })
    jobs = list_jobs()
    # 已结束的旧任务不占 UI：只回传正在跑的和最近一次失败。
    jobs = [j for j in jobs if j["status"] in ("queued", "downloading", "verifying", "cancelling")]
    return {
        "models": items,
        "server": server,
        "active_model_id": active_id,
        "jobs": jobs,
        "disk": {"free": disk.free, "total": disk.total, "free_label": _human(disk.free)},
        "root": str(models_root()),
        "llama_available": _llama_available(),
        "install_hint": "pip install -r requirements-local.txt",
    }
