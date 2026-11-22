"""手机远程控制：一次性配对链接 + 临时访问令牌。

参考 ZCode Remote Control 的边界：
- 链接只负责「配对」，本身短时有效、用完即焚；
- 配对后换成本机持有的临时访问令牌，关闭弹窗不断开，点「停止」才失效；
- 同一时间只允许一台手机；刷新二维码会踢掉旧手机；
- 默认走 localhost.run 反向外连隧道，手机不需要和电脑同一局域网；
- 隧道由第三方终止 TLS，链接等同于临时钥匙，面板里必须明确提示。
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import io
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit

PAIR_TTL = 300
SESSION_TTL = 12 * 3600
MAX_SESSIONS = 1

_lock = threading.RLock()
_pair: dict | None = None
_sessions: dict[str, dict] = {}
_state: dict = {"base_url": "", "mode": "", "warning": ""}
_tunnel_proc: subprocess.Popen | None = None
_tunnel_url = ""
_tunnel_error = ""
_tunnel_lock = threading.Lock()
_reader: threading.Thread | None = None


def _hash(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def _audit(action: str, data: dict) -> None:
    try:
        from core import store
        store.append_audit("admin", action, data)
    except Exception:
        pass


def _prune() -> None:
    global _pair
    now = time.time()
    if _pair and _pair["expires"] <= now:
        _pair = None
    for k, s in list(_sessions.items()):
        if s["expires"] <= now:
            _sessions.pop(k, None)


def _lan_ip() -> str:
    """挑一个手机能访问的本机地址；跳过回环和 169.254 链路本地地址。"""
    candidates: list[str] = []
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            if name == "lo":
                continue
            for a in addrs:
                if getattr(a, "family", None) == socket.AF_INET:
                    candidates.append(a.address)
    except Exception:
        try:
            candidates.extend(socket.gethostbyname_ex(socket.gethostname())[2])
        except Exception:
            pass
    good = [ip for ip in candidates
            if ip and not ip.startswith(("127.", "169.254.", "0."))]
    for ip in good:
        if ip.startswith(("192.168.", "10.")) or ip.startswith("172."):
            return ip
    if good:
        return good[0]
    return "127.0.0.1"


def _direct_base(request_base: str, host: str, port: int) -> str:
    env = (os.environ.get("BIGROBOT_PUBLIC_URL") or "").strip().rstrip("/")
    if env:
        return env
    hostname = (urlsplit(f"//{host}").hostname or "").strip().lower()
    if hostname and hostname not in {"127.0.0.1", "localhost", "::1"}:
        base = request_base.rstrip("/")
        return base
    scheme = (os.environ.get("BIGROBOT_REMOTE_SCHEME") or "http").strip()
    return f"{scheme}://{_lan_ip()}:{port}"


def _drain(proc: subprocess.Popen) -> None:
    if not proc.stdout:
        return
    try:
        for _ in proc.stdout:
            pass
    except Exception:
        pass


def _start_tunnel(port: int) -> str:
    """启动 localhost.run 反向外连隧道，返回 https 公网地址。"""
    global _tunnel_proc, _tunnel_url, _tunnel_error, _reader
    with _tunnel_lock:
        if _tunnel_proc and _tunnel_proc.poll() is None and _tunnel_url:
            return _tunnel_url
        _tunnel_error = ""
        cmd = [
            "ssh", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=10",
            "-R", f"80:127.0.0.1:{port}", "nokey@localhost.run",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True,
            )
        except Exception as e:
            _tunnel_error = f"无法启动隧道：{e}"
            raise RuntimeError(_tunnel_error) from e
        _tunnel_proc = proc
        _tunnel_url = ""
        deadline = time.time() + 20
        found = ""
        while time.time() < deadline:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            m = re.search(r"https://[a-z0-9-]+\.(?:app\.lhr\.life|lhr\.life)", line, re.I)
            if m:
                found = m.group(0).rstrip(".,)")
                break
        if not found:
            try:
                proc.terminate()
                proc.wait(timeout=4)
            except Exception:
                pass
            _tunnel_proc = None
            _tunnel_error = "localhost.run 没返回公网地址，可能被网络策略拦截"
            raise RuntimeError(_tunnel_error)
        _tunnel_url = found
        _reader = threading.Thread(target=_drain, args=(proc,), daemon=True)
        _reader.start()
        return found


def _stop_tunnel() -> None:
    global _tunnel_proc, _tunnel_url, _tunnel_error
    with _tunnel_lock:
        proc = _tunnel_proc
        _tunnel_proc = None
        _tunnel_url = ""
        _tunnel_error = ""
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def tunnel_active() -> bool:
    global _tunnel_url
    if _tunnel_proc is None or _tunnel_proc.poll() is not None:
        _tunnel_url = ""
        return False
    return bool(_tunnel_url)


def qr_png(url: str) -> str:
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=9, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def start(request_base: str, host: str, port: int, mode: str = "auto") -> dict:
    """生成新的配对二维码；旧二维码与已连接手机立即失效。"""
    global _pair, _sessions, _state
    mode = (mode or "auto").strip().lower()
    if mode not in {"auto", "direct", "tunnel"}:
        mode = "auto"
    warning = ""
    base = ""
    tunnel = False
    if mode in {"auto", "direct"}:
        base = _direct_base(request_base, host, port)
    if mode == "tunnel" or (mode == "auto" and not (os.environ.get("BIGROBOT_PUBLIC_URL") or "").strip()
                            and os.environ.get("BIGROBOT_REMOTE_TUNNEL", "1") != "0"):
        try:
            base = _start_tunnel(port)
            tunnel = True
            warning = "当前走 localhost.run 公网隧道，TLS 在该服务端终止；链接等同于临时钥匙。"
        except Exception as e:
            if mode == "tunnel":
                raise
            warning = f"公网隧道不可用，已回退局域网直连：{e}"
    if not base:
        base = _direct_base(request_base, host, port)
    if mode == "direct":
        h = (urlsplit(base).hostname or "").lower()
        if h in {"127.0.0.1", "localhost", "::1"} or h.startswith("169.254."):
            warning = "直连地址是本机回环/链路本地地址，手机可能访问不到；建议改用自动公网隧道。"
    with _lock:
        _pair = {"hash": "", "raw_expires": time.time() + PAIR_TTL, "created": time.time(),
                 "ip": "", "base": base, "mode": mode, "tunnel": tunnel}
        # 先清旧会话，再签发一次性配对串
        _sessions.clear()
        raw = secrets.token_urlsafe(32)
        _pair["hash"] = _hash(raw)
        _pair["expires"] = time.time() + PAIR_TTL
        _state = {"base_url": base, "mode": mode, "warning": warning}
    url = f"{base}/remote#t={raw}"
    _audit("remote.started", {"mode": mode, "tunnel": tunnel, "base": base})
    return {
        "url": url,
        "qr": qr_png(url),
        "expires_in": PAIR_TTL,
        "mode": mode,
        "tunnel": tunnel,
        "warning": warning,
        "base_url": base,
    }


def pair(raw: str, device: str = "", ip: str = "") -> tuple[str | None, str]:
    """用一次性配对串换临时访问令牌；成功即作废旧二维码。"""
    global _pair, _sessions
    now = time.time()
    with _lock:
        _prune()
        if not _pair or _pair.get("expires", 0) <= now:
            return None, "二维码已过期，请在电脑上刷新"
        if not secrets.compare_digest(_hash(raw or ""), _pair.get("hash", "")):
            return None, "配对码不对"
        base = _pair["base"]
        _pair = None
        if len(_sessions) >= MAX_SESSIONS:
            _sessions.clear()
        token = secrets.token_urlsafe(40)
        _sessions[_hash(token)] = {
            "name": (device or "手机")[:80],
            "ip": ip[:80],
            "connected": now,
            "last_seen": now,
            "expires": now + SESSION_TTL,
            "base": base,
        }
    _audit("remote.paired", {"device": device[:80], "ip": ip[:80]})
    return token, base


def validate(raw: str) -> bool:
    if not raw:
        return False
    with _lock:
        _prune()
        s = _sessions.get(_hash(raw))
        if not s:
            return False
        s["last_seen"] = time.time()
        return True


def status() -> dict:
    with _lock:
        _prune()
        pair_left = max(0, int(_pair["expires"] - time.time())) if _pair else 0
        clients = [{
            "name": s["name"],
            "ip": s["ip"],
            "connected_at": int(s["connected"]),
            "last_seen": int(s["last_seen"]),
            "expires_in": max(0, int(s["expires"] - time.time())),
        } for s in _sessions.values()]
        active = bool(_pair) or bool(clients)
        warning = _state.get("warning", "")
        base = _state.get("base_url", "")
        if base and ".lhr.life" in base and not tunnel_active():
            warning = "公网隧道已断开，手机端会无法继续访问；请刷新二维码重新建立。"
        return {
            "active": active,
            "waiting": bool(_pair),
            "pair_expires_in": pair_left,
            "connected": len(clients),
            "clients": clients,
            "base_url": _state.get("base_url", ""),
            "mode": _state.get("mode", ""),
            "tunnel": tunnel_active(),
            "warning": warning,
        }


def stop() -> dict:
    global _pair, _sessions, _state
    with _lock:
        had = bool(_pair) or bool(_sessions)
        _pair = None
        _sessions.clear()
        _state = {"base_url": "", "mode": "", "warning": ""}
    _stop_tunnel()
    _audit("remote.stopped", {"had_session": had})
    return {"ok": True, "active": False}


atexit.register(_stop_tunnel)
