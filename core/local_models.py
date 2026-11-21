"""本地小模型：模型目录、断点下载、llama.cpp 托管与一键启用。

小模型不是「把云端模型名换掉」就能用：工具清单、人设和上下文预算都会把
0.5B—1B 的注意力挤爆。这里除了下载与启动，还提供 small_model_mode()，
让上层自动切到短人设 + 核心工具 + 小预算。
"""
from __future__ import annotations

import json
import os
import platform
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

# 模型目录分两类：
# - 生产档：用户可选，按本机 CPU / 内存 / 显卡只标注能否运行；
# - 测试档：1B 以下，只用于工具链路、低配兼容和回归测试，不进入用户可选目录。
# 评测只写模型卡公开可查的结论；文件大小用 Q4_K_M 的实际字节数。
CATALOG: list[dict] = [
    {
        "id": "qwen3.5-9b",
        "name": "Qwen3.5-9B",
        "params_b": 9.0,
        "repo": "unsloth/Qwen3.5-9B-GGUF",
        "file": "Qwen3.5-9B-Q4_K_M.gguf",
        "size": 5_680_522_464,
        "quant": "Q4_K_M",
        "context": 262_144,
        "license": "Apache-2.0",
        "tool_calling": True,
        "chinese": True,
        "released": "2026-03",
        "badge": "16G 质量档",
        "tagline": "9B 主力档：262K 上下文，中文、代码和长文明显比 1B 稳；16GB 内存起步。",
        "why": "Qwen3.5 原生 262K 上下文，Q4_K_M 约 5.7GB；16GB 机器留出系统余量后可长期跑，适合日常问答、代码和复杂工具链。",
        "best_for": ["日常主力", "代码", "长文", "复杂 Agent"],
        "ram_gb": 16,
        "min_ram_gb": 15.0,
        "test_only": False,
        "default_ctx": 8192,
        "chat_template_kwargs": {"enable_thinking": False},
    },
    {
        "id": "qwen3.5-4b",
        "name": "Qwen3.5-4B",
        "params_b": 4.0,
        "repo": "unsloth/Qwen3.5-4B-GGUF",
        "file": "Qwen3.5-4B-Q4_K_M.gguf",
        "size": 2_740_937_888,
        "quant": "Q4_K_M",
        "context": 262_144,
        "license": "Apache-2.0",
        "tool_calling": True,
        "chinese": True,
        "released": "2026-03",
        "badge": "8G 主力",
        "tagline": "4B 通用主力：262K 上下文，8GB 内存可跑，中文/代码/Agent 比 1B 稳一档。",
        "why": "Qwen3.5 原生 262K 上下文，Q4_K_M 约 2.7GB；8GB 机器留出系统余量后可当日常主力，是低于 16GB 的首选。",
        "best_for": ["通用问答", "代码", "长文", "Agent"],
        "ram_gb": 8,
        "min_ram_gb": 7.5,
        "test_only": False,
        "default_ctx": 8192,
        "chat_template_kwargs": {"enable_thinking": False},
    },
    {
        "id": "minicpm5-2b",
        "name": "MiniCPM5-2B",
        "params_b": 2.5,
        "repo": "openbmb/MiniCPM5-2B-GGUF",
        "file": "MiniCPM5-2B-Q4_K_M.gguf",
        "size": 1_561_318_368,
        "quant": "Q4_K_M",
        "context": 131_072,
        "license": "Apache-2.0",
        "tool_calling": True,
        "chinese": True,
        "released": "2026-05-19",
        "badge": "2B 级",
        "tagline": "MiniCPM5 系列 2B 级：总参 2.52B，128K 上下文，Q4 约 1.56GB；工具与 Agent 能力是同尺寸重点。",
        "why": "官方总参数 2,516,756,480（非 embedding 1.98B），定位 2B 级端侧模型；128K 原生上下文，工具调用、代码、数学和长文是同尺寸重点。4GB 内存可跑，适合做本地全功能验证。",
        "best_for": ["2B 级", "全功能验证", "工具调用", "4GB 低配"],
        "ram_gb": 4,
        "min_ram_gb": 3.5,
        "test_only": False,
        # 2B 级在 2 核/4GB 机器上仍吃不下 27 个工具的长提示：保留短人设+核心工具，
        # 结构化能力由 pipeline 的确定性路由兜底，避免 prompt eval 拖到 100 秒。
        "compact": True,
        "default_ctx": 8192,
        "chat_template_kwargs": {"enable_thinking": False},
    },
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
        "released": "2026-05-19",
        "badge": "测试 / 低配",
        "tagline": "1B 级开源 SOTA，128K 上下文；用于低配体验、工具链路和回归测试，不作为内置产品模型。",
        "why": "官方定位 1B 级开源 SOTA，Agent 工具调用、代码和困难推理领先同尺寸；但 1B 的知识密度和长文稳定性有限，只适合 4GB 级机器或测试。",
        "best_for": ["4GB 低配", "工具链路测试", "长上下文验证"],
        "ram_gb": 2,
        "min_ram_gb": 2,
        "test_only": True,
        "default_ctx": 8192,
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
        "released": "2026-11-11",
        "badge": "测试 / 工具",
        "tagline": "0.8B 工具调用特化，体积最小、响应最快；只用于工具回归，不作为日常主力。",
        "why": "在 BFCL v4、ACEBench、τ-bench、ToolSandbox 等工具/Agent 评测中很强；但通用知识和长文弱，保留为小模型工具链测试件。",
        "best_for": ["工具回归", "极低内存", "提醒/天气验证"],
        "ram_gb": 1.5,
        "min_ram_gb": 1.5,
        "test_only": True,
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
        "badge": "测试 / 基线",
        "tagline": "原厂 0.8B 基线，原生 256K 上下文；用于对照测试，不作为日常主力。",
        "why": "BotPsy 的基座模型，长上下文和中文对话扎实；能力上限受 0.8B 限制，保留为最低配对照。",
        "best_for": ["对照测试", "最低内存", "长上下文验证"],
        "ram_gb": 1.5,
        "min_ram_gb": 1.5,
        "test_only": True,
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


def local_model_params(cfg: dict) -> float:
    """当前本地模型的参数量；手工接 Ollama 时从模型名里读。"""
    llm = (cfg or {}).get("llm") or {}
    mid = str(llm.get("local_model_id") or "")
    for item in CATALOG:
        if item["id"] == mid:
            return float(item["params_b"])
    m = re.search(r"(\d+(?:\.\d+)?)b", str(llm.get("model") or ""), re.I)
    return float(m.group(1)) if m else 0.0


def small_model_mode(cfg: dict) -> bool:
    """本地端点或显式 local_model_id → 自动收紧提示词。

    不只看 8K：用户手工接 Ollama 也应当走短提示词；云端模型不受影响。
    """
    llm = (cfg or {}).get("llm") or {}
    if llm.get("local_compact") is False:
        return False
    mid = str(llm.get("local_model_id") or "")
    for item in CATALOG:
        if item["id"] == mid and item.get("compact"):
            return True
    # 4B/9B 本地模型有足够参数吃完整人设和工具清单，不该再按 1B 收紧。
    if local_model_params(cfg) > 2.0:
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
    elif status.get("pid_alive"):
        # 进程还活着但健康检查没通过：先收尸，绝不能再起一个占第二份内存。
        stop_server()
        time.sleep(1)
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


def resume_server() -> dict:
    """应用重启后按已保存配置把本地模型拉回来。

    之前模型是 uvicorn 的子进程，主进程退出后它也死；但 config 里
    local_model_id 还在，下一次聊天会打到 18082 的死端口。这里在 lifespan
    启动时补一次恢复，用户不需要再点「启用」。
    """
    cfg = config.get_config()
    llm = cfg.get("llm") or {}
    mid = str(llm.get("local_model_id") or "").strip()
    if not mid:
        return {"running": False, "resumed": False, "reason": "no local model configured"}
    try:
        item = _entry(mid)
    except KeyError:
        return {"running": False, "resumed": False, "reason": f"unknown model {mid}"}
    if not is_installed(item):
        return {"running": False, "resumed": False, "reason": "model file missing"}
    status = server_status()
    if status.get("running") and status.get("model_id") == mid:
        return {**status, "resumed": False}
    ctx = int(llm.get("context_window") or 0)
    server = start_server(mid, n_ctx=ctx or None)
    config.update_config({"llm": {
        "base_url": server["base_url"], "model": mid, "api_key": "local",
        "protocol": "openai-compatible",
        "context_window": int(server.get("n_ctx") or 8192),
        "max_output": 1024 if item["params_b"] > 2 else 512,
        "tool_calling": True, "supports_vision": False,
        "local_model_id": mid,
        "local_compact": bool(item.get("compact")) or item["params_b"] <= 2.0,
    }})
    return {**server, "resumed": True}


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
            "max_output": 1024 if item["params_b"] > 2 else 512,
            "tool_calling": True,
            "supports_vision": False,
            "local_model_id": item["id"],
            # 4B/9B 用完整人设和全量工具；1B 才进精简模式。
            "local_compact": bool(item.get("compact")) or item["params_b"] <= 2.0,
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

def _total_ram_gb() -> float:
    """跨平台读物理内存；读不到就按 0 处理，绝不猜。"""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class _Memory(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem = _Memory()
            mem.dwLength = ctypes.sizeof(_Memory)
            windll = getattr(ctypes, "windll", None)
            if windll and windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                return round(mem.ullTotalPhys / 1024**3, 1)
        except (AttributeError, OSError, ValueError):
            pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * size / 1024**3, 1)
    except (AttributeError, OSError, ValueError):
        return 0.0


def _cpu_name() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.lower().startswith(("model name", "hardware")):
                    return line.split(":", 1)[-1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def _gpu_profile() -> dict:
    """NVIDIA 优先；Apple Silicon 按统一内存处理；其他核显不虚报显存。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            rows = [line.split(",") for line in out.stdout.strip().splitlines() if line.strip()]
            names = [r[0].strip() for r in rows]
            vram = 0.0
            for r in rows:
                try:
                    vram += float(r[1].strip()) / 1024
                except (IndexError, ValueError):
                    pass
            return {"name": " / ".join(names), "vram_gb": round(vram, 1), "unified": False}
    except (OSError, subprocess.SubprocessError):
        pass
    if platform.system() == "Darwin" and platform.machine().lower() in ("arm64", "aarch64"):
        return {"name": "Apple Silicon", "vram_gb": 0.0, "unified": True}
    return {"name": "", "vram_gb": 0.0, "unified": False}


def system_profile() -> dict:
    gpu = _gpu_profile()
    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu": _cpu_name(),
        "cpu_cores": os.cpu_count() or 1,
        "ram_gb": _total_ram_gb(),
        "gpu": gpu["name"],
        "vram_gb": gpu["vram_gb"],
        "unified_memory": gpu["unified"],
    }


def _min_ram(item: dict) -> float:
    return float(item.get("min_ram_gb") or item.get("ram_gb") or 0)


def _fit_label(item: dict, system: dict) -> dict:
    if item.get("test_only"):
        return {"state": "test", "label": "测试模型，仅用于能力验证"}
    if system["ram_gb"] < _min_ram(item):
        return {"state": "no", "label": f"内存不足：建议 {item['ram_gb']:g}GB"}
    return {"state": "ok", "label": "本机可跑"}


def overview() -> dict:
    cfg = config.get_config()
    active_id = ((cfg.get("llm") or {}).get("local_model_id") or "")
    server = server_status()
    disk = shutil.disk_usage(models_root())
    sysinfo = system_profile()
    items = []
    for item in CATALOG:
        got = installed_bytes(item)
        installed = is_installed(item)
        items.append({
            **{k: item[k] for k in (
                "id", "name", "params_b", "quant", "context", "license", "tool_calling",
                "chinese", "badge", "tagline", "why", "best_for", "ram_gb",
                "repo", "file", "size", "default_ctx")},
            **({"released": item["released"]} if item.get("released") else {}),
            "min_ram_gb": _min_ram(item),
            "test_only": bool(item.get("test_only")),
            "fit": _fit_label(item, sysinfo),
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
        "system": sysinfo,
        "server": server,
        "active_model_id": active_id,
        "jobs": jobs,
        "disk": {"free": disk.free, "total": disk.total, "free_label": _human(disk.free)},
        "root": str(models_root()),
        "llama_available": _llama_available(),
        "install_hint": "pip install -r requirements-local.txt",
    }
