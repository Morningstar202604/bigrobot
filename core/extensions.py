"""声明式扩展包：把外部 HTTP 工具接进 Agent，而不把任意 Python 代码放进核心进程。

为什么先做 HTTP 扩展，而不是直接兼容 AstrBot 插件：
- AstrBot 插件在宿主 Python 环境执行，官方也明确提示市场插件不保证安全；
- BigRobot 的核心价值是「接管账号 + 可审计」，不能为了生态把执行面打开；
- 大多数生态插件本质是「调一个外部 API / 读一个文件 / 发一条消息」，声明式 HTTP
  已经覆盖其中很大一部分，而且权限、审计、回滚都更容易做。

扩展包目录（data/extensions/<id>/）：
    manifest.json
    skills/*.md       可选，给模型看的能力说明
    README.md         可选

manifest.json 只允许声明式 HTTP 工具，不支持 Python 入口：
{
  "id": "weather-http",
  "name": "Weather",
  "version": "0.0.1",
  "description": "查天气",
  "kind": "http",
  "base_url": "https://api.example.com",
  "allow_private": false,
  "allow_untrusted": false,
  "tools": [
    {
      "name": "weather_now",
      "description": "查某城市当前天气",
      "method": "GET",
      "path": "/weather",
      "risk": "read",
      "params": {
        "city": {"type": "string", "required": true, "in": "query", "description": "城市名"}
      },
      "headers": {"Authorization": "Bearer ${ENV:WEATHER_KEY}"}
    }
  ],
  "skills": [
    {"name": "天气查询", "description": "先查再答", "file": "skills/weather.md"}
  ]
}

安全边界：
- 只允许 http/https；
- 默认拒绝内网/回环地址，`allow_private=true` 需要管理员显式打开（本地开发 API 用）；
- 云元数据地址永远拒绝；
- 不跟随重定向；
- 响应截断，超时上限 30 秒；
- 写操作（risk=write）永远要求可信主体，不能靠 `allow_untrusted` 放开。
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urljoin, urlparse

import httpx

from core import config_store, paths, url_guard
from core.tool_result import miss_result, ok_result

MANIFEST = "manifest.json"
MAX_ZIP_BYTES = int(os.environ.get("EXTENSION_MAX_ZIP_BYTES", str(20 * 1024 * 1024)))
MAX_FILES = int(os.environ.get("EXTENSION_MAX_FILES", "300"))
MAX_UNCOMPRESSED = int(os.environ.get("EXTENSION_MAX_UNCOMPRESSED", str(60 * 1024 * 1024)))
MAX_RESPONSE = int(os.environ.get("EXTENSION_MAX_RESPONSE", "60000"))
MAX_BACKUPS = 3

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_ENV_RE = re.compile(r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    raw = os.environ.get("BIGROBOT_EXTENSIONS_DIR", "").strip()
    root = Path(raw) if raw else paths.data_dir() / "extensions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _trash_dir() -> Path:
    d = _root() / ".trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_dir() -> Path:
    d = _root() / ".backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"manifest 读不出来：{e}") from e
    if not isinstance(data, dict):
        raise ValueError("manifest 必须是 JSON 对象")
    return data


def _validate_id(raw: str) -> str:
    sid = (raw or "").strip().lower()
    if not _ID_RE.match(sid):
        raise ValueError("扩展 id 只能是小写字母、数字、下划线或短横线（2–41 字符）")
    return sid


def _validate_tool_name(raw: str) -> str:
    name = (raw or "").strip()
    if not _TOOL_RE.match(name):
        raise ValueError(f"工具名不合法：{name!r}（只允许小写字母开头的 a-z0-9_）")
    return name


def _validate_url(raw: str, allow_private: bool) -> str:
    url = (raw or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("base_url 只支持 http/https")
    if not parsed.hostname:
        raise ValueError("base_url 缺少主机名")
    if url_guard.is_metadata_host(parsed.hostname):
        raise ValueError("拒绝云元数据地址")
    if not allow_private:
        # 安装时只做形状检查，真正请求时再 check_url（避免离线安装失败）。
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("内网/回环地址需要 allow_private=true")
    return url


def _normalize_params(raw) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("params 必须是对象")
    out: dict = {}
    for name, spec in raw.items():
        key = str(name).strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$", key):
            raise ValueError(f"参数名不合法：{key}")
        if not isinstance(spec, dict):
            spec = {"type": "string"}
        typ = str(spec.get("type") or "string").lower()
        if typ not in {"string", "integer", "number", "boolean"}:
            typ = "string"
        where = str(spec.get("in") or "query").lower()
        if where not in {"query", "path", "body"}:
            where = "query"
        out[key] = {
            "type": typ,
            "description": str(spec.get("description") or "")[:200],
            "required": bool(spec.get("required")),
            "in": where,
        }
    return out


def _normalize_tools(raw, allow_private: bool, allow_untrusted: bool) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("扩展至少需要一个工具")
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("tools 的每一项必须是对象")
        name = _validate_tool_name(str(item.get("name") or ""))
        if name in seen:
            raise ValueError(f"工具名重复：{name}")
        seen.add(name)
        method = str(item.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ValueError(f"{name}: v1 只支持 GET/POST")
        path = str(item.get("path") or "/").strip()
        if not path.startswith("/"):
            path = "/" + path
        risk = str(item.get("risk") or "read").lower()
        if risk not in {"read", "write"}:
            risk = "read"
        params = _normalize_params(item.get("params"))
        headers = item.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError(f"{name}: headers 必须是对象")
        fmt = str(item.get("format") or "").strip().lower()
        if fmt not in {"", "pypi", "npm", "github"}:
            raise ValueError(f"{name}: 不支持的 format={fmt}")
        timeout_s = item.get("timeout_s", 15)
        try:
            timeout_s = max(3, min(30, int(timeout_s)))
        except (TypeError, ValueError):
            timeout_s = 15
        out.append({
            "name": name,
            "description": str(item.get("description") or "")[:300],
            "method": method,
            "path": path,
            "risk": risk,
            "params": params,
            "headers": {str(k): str(v) for k, v in headers.items()},
            "timeout_s": timeout_s,
            "format": fmt,
            "allow_untrusted": bool(allow_untrusted) and risk == "read",
            "allow_private": bool(allow_private),
        })
    return out


def _skill_path_ok(file_name: str) -> bool:
    if not file_name or file_name.startswith("/") or "\\" in file_name:
        return False
    return ".." not in PurePosixPath(file_name).parts


def _read_skill(base: Path, raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    guide = str(raw.get("guide") or "").strip()
    file_name = str(raw.get("file") or "").strip()
    if file_name and not guide:
        if not _skill_path_ok(file_name):
            return None
        candidate = base / file_name
        try:
            if candidate.is_file() and candidate.stat().st_size <= 16_000:
                guide = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            guide = ""
    return {
        "name": name[:40],
        "description": str(raw.get("description") or "")[:200],
        "guide": guide[:2000],
    }


def _validate_manifest(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("manifest 必须是对象")
    sid = _validate_id(str(raw.get("id") or ""))
    if str(raw.get("kind") or "http").lower() != "http":
        raise ValueError("v1 只支持声明式 HTTP 扩展（kind=http）；Python 插件入口暂不开放")
    name = str(raw.get("name") or sid).strip()[:80]
    version = str(raw.get("version") or "0.0.1").strip()[:40]
    allow_private = bool(raw.get("allow_private"))
    allow_untrusted = bool(raw.get("allow_untrusted"))
    base_url = _validate_url(str(raw.get("base_url") or ""), allow_private)
    tools = _normalize_tools(raw.get("tools"), allow_private, allow_untrusted)
    skills_raw = raw.get("skills") or []
    if not isinstance(skills_raw, list):
        skills_raw = []
    skills = []
    for s in skills_raw:
        if not isinstance(s, dict):
            continue
        sname = str(s.get("name") or "").strip()
        if not sname:
            continue
        file_name = str(s.get("file") or "").strip()
        if file_name and not _skill_path_ok(file_name):
            raise ValueError(f"技能文件路径越界：{file_name}")
        skills.append({
            "name": sname[:40],
            "description": str(s.get("description") or "")[:200],
            "guide": str(s.get("guide") or "")[:2000],
        })
    host = urlparse(base_url).hostname or ""
    return {
        "id": sid,
        "name": name,
        "version": version,
        "description": str(raw.get("description") or "")[:500],
        "author": str(raw.get("author") or "")[:80],
        "kind": "http",
        "base_url": base_url,
        "allow_private": allow_private,
        "allow_untrusted": allow_untrusted,
        "tools": tools,
        "skills": skills,
        "permissions": list(raw.get("permissions") or [f"net:{host}"]),
        "raw": raw,
    }


def _load_item(directory: Path, enabled: bool = True, source: str = "") -> dict | None:
    manifest_path = directory / MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        raw = _read_json(manifest_path)
        manifest = _validate_manifest(raw)
    except ValueError as e:
        return {
            "id": directory.name,
            "name": directory.name,
            "version": "",
            "description": "",
            "author": "",
            "kind": "invalid",
            "enabled": False,
            "source": source,
            "error": str(e)[:300],
            "tools": [],
            "skills": [],
            "permissions": [],
            "installed_at": _mtime(directory),
        }
    # 文件型技能：安装后再读一次，确保路径基于实际扩展目录。
    skills = []
    for s in raw.get("skills") or []:
        item = _read_skill(directory, s)
        if item:
            skills.append(item)
    manifest["skills"] = skills
    return {
        "id": manifest["id"],
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "kind": manifest["kind"],
        "enabled": bool(enabled),
        "source": source,
        "allow_private": manifest["allow_private"],
        "allow_untrusted": manifest["allow_untrusted"],
        "tools": [
            {
                "name": t["name"], "description": t["description"], "risk": t["risk"],
                "method": t["method"], "params": t["params"],
            }
            for t in manifest["tools"]
        ],
        "skills": manifest["skills"],
        "permissions": manifest["permissions"],
        "installed_at": _mtime(directory),
        "_manifest": manifest,
    }


def _mtime(directory: Path) -> str:
    try:
        return datetime.fromtimestamp(directory.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return ""


def _config() -> dict:
    cfg = config_store.get_config().get("extensions") or {}
    return {
        "enabled": dict(cfg.get("enabled") or {}),
        "sources": dict(cfg.get("sources") or {}),
    }


def _save_config(enabled: dict, sources: dict) -> None:
    config_store.set_config({"extensions": {"enabled": enabled, "sources": sources}})


def list_items() -> list[dict]:
    cfg = _config()
    out: list[dict] = []
    for directory in sorted(_root().iterdir()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        item = _load_item(
            directory,
            enabled=cfg["enabled"].get(directory.name, True),
            source=cfg["sources"].get(directory.name, ""),
        )
        if item:
            out.append(item)
    return out


def get_item(ext_id: str) -> dict | None:
    for item in list_items():
        if item["id"] == ext_id:
            return item
    return None


def _backup_existing(ext_id: str, target: Path) -> Path | None:
    if not target.exists():
        return None
    backup = _backup_dir() / f"{ext_id}-{int(time.time())}"
    if backup.exists():
        backup = _backup_dir() / f"{ext_id}-{int(time.time())}-{uuid.uuid4().hex[:4]}"
    shutil.move(str(target), str(backup))
    # 每个扩展最多保留 3 份，按名字排序（时间戳天然可排）
    olds = sorted(_backup_dir().glob(f"{ext_id}-*"))
    for old in olds[:-MAX_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return backup


def _safe_extract(zf: zipfile.ZipFile, destination: Path) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise ValueError(f"压缩包文件太多（上限 {MAX_FILES}）")
    total = 0
    for info in infos:
        name = info.filename
        if not name or name.startswith("/") or "\\" in name:
            raise ValueError(f"压缩包路径不合法：{name}")
        parts = PurePosixPath(name).parts
        if ".." in parts:
            raise ValueError(f"压缩包路径越界：{name}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise ValueError(f"压缩包不允许符号链接：{name}")
        total += max(0, info.file_size)
        if total > MAX_UNCOMPRESSED:
            raise ValueError(f"解压后体积超过上限 {MAX_UNCOMPRESSED} 字节")
        if info.is_dir():
            continue
        target = destination.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def _find_manifest_root(base: Path) -> Path:
    if (base / MANIFEST).is_file():
        return base
    children = [p for p in base.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / MANIFEST).is_file():
        return children[0]
    raise ValueError("压缩包里没有 manifest.json（根目录或唯一子目录）")


def _assert_names_free(manifest: dict) -> None:
    """扩展工具不能和内置/其它扩展重名；否则模型看到的名字会被静默覆盖。"""
    own = {t["name"] for t in manifest["tools"]}
    try:
        from core import tools as tools_mod
        reserved = set(tools_mod.TOOL_META) | set(tools_mod._SYNC_IMPLS) | set(tools_mod._ASYNC_IMPLS)
    except Exception:
        reserved = set()
    clash = own & reserved
    if clash:
        raise ValueError("工具名和内置工具冲突：" + "、".join(sorted(clash)))
    for item in list_items():
        if item.get("id") == manifest["id"]:
            continue
        clash = own & {t["name"] for t in item.get("tools") or []}
        if clash:
            raise ValueError("工具名和已安装扩展冲突：" + "、".join(sorted(clash)))


def install_zip(data: bytes, source: str = "") -> dict:
    if not data:
        raise ValueError("扩展包为空")
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError(f"扩展包超过上限 {MAX_ZIP_BYTES} 字节")
    root = _root()
    temp = Path(tempfile.mkdtemp(prefix=".tmp-", dir=str(root)))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            _safe_extract(zf, temp)
            src_root = _find_manifest_root(temp)
            manifest = _validate_manifest(_read_json(src_root / MANIFEST))
            _assert_names_free(manifest)
            target = root / manifest["id"]
            backup = _backup_existing(manifest["id"], target)
            try:
                shutil.move(str(src_root), str(target))
            except Exception:
                # 新版本没落盘成功：把旧版本放回去，避免扩展目录凭空消失。
                if backup and backup.exists() and not target.exists():
                    shutil.move(str(backup), str(target))
                raise
        cfg = _config()
        cfg["enabled"][manifest["id"]] = True
        cfg["sources"][manifest["id"]] = source[:500]
        _save_config(cfg["enabled"], cfg["sources"])
        item = get_item(manifest["id"])
        if item is None:
            raise ValueError("安装后读不到扩展")
        return item
    finally:
        shutil.rmtree(temp, ignore_errors=True)


async def install_from_url(url: str) -> dict:
    target = url_guard.check_url(url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=True) as client:
        resp = await client.get(target)
        for hop in resp.history:
            url_guard.check_url(str(hop.url))
        url_guard.check_url(str(resp.url))
        if resp.status_code != 200:
            raise ValueError(f"下载失败：HTTP {resp.status_code}")
        data = resp.content
        if len(data) > MAX_ZIP_BYTES:
            raise ValueError(f"扩展包超过上限 {MAX_ZIP_BYTES} 字节")
    return await asyncio.to_thread(install_zip, data, url)


def set_enabled(ext_id: str, enabled: bool) -> dict:
    if get_item(ext_id) is None:
        raise KeyError(ext_id)
    cfg = _config()
    cfg["enabled"][ext_id] = bool(enabled)
    _save_config(cfg["enabled"], cfg["sources"])
    item = get_item(ext_id)
    if item is None:
        raise KeyError(ext_id)
    return item


def uninstall(ext_id: str) -> None:
    target = _root() / ext_id
    if not target.exists():
        raise KeyError(ext_id)
    trash = _trash_dir() / f"{ext_id}-{int(time.time())}"
    shutil.move(str(target), str(trash))
    cfg = _config()
    cfg["enabled"].pop(ext_id, None)
    cfg["sources"].pop(ext_id, None)
    _save_config(cfg["enabled"], cfg["sources"])


def rollback(ext_id: str) -> dict:
    backups = sorted(_backup_dir().glob(f"{ext_id}-*"))
    if not backups:
        raise KeyError("没有可回滚的版本")
    latest = backups[-1]
    target = _root() / ext_id
    if target.exists():
        trash = _trash_dir() / f"{ext_id}-{int(time.time())}"
        shutil.move(str(target), str(trash))
    shutil.move(str(latest), str(target))
    item = get_item(ext_id)
    if item is None:
        raise ValueError("回滚后读不到扩展")
    return item


def _resolve_env(value: str) -> tuple[str, str]:
    """替换 ${ENV:NAME}；返回 (结果, 缺失变量名)。"""
    missing = ""

    def repl(match: re.Match) -> str:
        nonlocal missing
        name = match.group(1)
        val = os.environ.get(name, "")
        if not val:
            missing = name
        return val

    return _ENV_RE.sub(repl, value or ""), missing


def _coerce(value, typ: str):
    if typ == "integer":
        return int(value)
    if typ == "number":
        return float(value)
    if typ == "boolean":
        return str(value).lower() in {"1", "true", "yes", "on"}
    return str(value)


def _tool_map() -> dict[str, dict]:
    """name → {manifest, tool}；只收启用扩展。"""
    out: dict[str, dict] = {}
    for item in list_items():
        if not item.get("enabled") or item.get("error"):
            continue
        manifest = item.get("_manifest") or {}
        for tool in manifest.get("tools") or []:
            out.setdefault(tool["name"], {"manifest": manifest, "tool": tool, "item": item})
    return out


def tool_specs() -> list[dict]:
    out: list[dict] = []
    for name, entry in _tool_map().items():
        tool = entry["tool"]
        params = tool["params"]
        props = {
            k: {"type": v["type"], "description": v["description"]}
            for k, v in params.items()
        }
        required = [k for k, v in params.items() if v.get("required")]
        out.append({
            "name": name,
            "args": list(params.keys()),
            "desc": tool["description"] or f"{entry['manifest']['name']}：{name}",
            "risk": tool["risk"],
            "extension": entry["manifest"]["id"],
            "parameters": {"type": "object", "properties": props, "required": required},
        })
    return out


def tool_policy(name: str) -> dict | None:
    entry = _tool_map().get(name)
    if not entry:
        return None
    tool = entry["tool"]
    return {
        "risk": tool["risk"],
        "allow_untrusted": bool(tool["allow_untrusted"]),
        "extension": entry["manifest"]["id"],
    }


async def _invoke(name: str, args: dict, ctx) -> dict:
    entry = _tool_map().get(name)
    if not entry:
        return miss_result(name, "扩展没启用，或工具已经不存在。")
    manifest = entry["manifest"]
    tool = entry["tool"]
    base_url = manifest["base_url"]
    path = tool["path"]
    query: dict = {}
    body: dict = {}
    missing_path: list[str] = []
    missing_args = [k for k, v in tool["params"].items()
                    if v.get("required") and k not in (args or {})]
    if missing_args:
        return miss_result(name, "缺少参数：" + "、".join(missing_args))
    for key, spec in tool["params"].items():
        if key not in args or args.get(key) in (None, ""):
            if spec.get("required") and spec["in"] == "path":
                missing_path.append(key)
            continue
        val = args[key]
        if spec["in"] == "path":
            path = path.replace("{" + key + "}", quote(str(val), safe=""))
        elif tool["method"] == "GET":
            query[key] = str(val)
        else:
            body[key] = _coerce(val, spec["type"])
    if missing_path:
        return miss_result(name, "缺少路径参数：" + "、".join(missing_path))
    if "{" in path:
        return miss_result(name, "路径模板还有未替换的参数。")
    url = urljoin(base_url + "/", path.lstrip("/"))
    headers: dict[str, str] = {"Accept": "application/json"}
    for key, value in tool.get("headers", {}).items():
        resolved, missing = _resolve_env(str(value))
        if missing:
            return miss_result(name, f"缺少环境变量：{missing}")
        headers[key] = resolved
    try:
        if not tool.get("allow_private"):
            url_guard.check_url(url)
        elif url_guard.is_metadata_host(urlparse(url).hostname or ""):
            return miss_result(name, "拒绝云元数据地址")
    except url_guard.UnsafeUrl as e:
        return miss_result(name, f"地址不安全：{e}")
    timeout = httpx.Timeout(float(tool.get("timeout_s", 15)))
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(
                tool["method"], url,
                params=query or None,
                json=body if tool["method"] == "POST" else None,
                headers=headers,
            )
            # JSON 必须先完整解析再截断：PyPI/npm 的元数据动辄上百 KB，
            # 先截到 4000 字节会变成坏 JSON，格式化器只能退回原始串。
            raw = resp.content[:2_000_000]
    except httpx.TimeoutException:
        return miss_result(name, "扩展请求超时。")
    except httpx.HTTPError as e:
        return miss_result(name, f"扩展请求失败：{type(e).__name__}")
    text = raw.decode("utf-8", errors="replace")
    if resp.status_code >= 400:
        return miss_result(name, f"扩展返回 HTTP {resp.status_code}：{text[:200]}",
                           status_code=resp.status_code)
    if 300 <= resp.status_code < 400:
        return miss_result(name, f"扩展返回重定向 HTTP {resp.status_code}，v1 不跟随。",
                           status_code=resp.status_code)
    content_type = (resp.headers.get("content-type") or "").lower()
    if "json" in content_type:
        try:
            parsed = json.loads(text)
            formatted = _format_payload(str(tool.get("format") or ""), parsed)
            text = formatted or json.dumps(parsed, ensure_ascii=False, indent=2)
        except ValueError:
            pass
    truncated = len(text) > 4000 or len(resp.content) > MAX_RESPONSE
    return ok_result(name, text[:4000], status_code=resp.status_code,
                     extension=manifest["id"], truncated=truncated)


_FORMATTERS = {
    "pypi": lambda d: _fmt_pypi(d),
    "npm": lambda d: _fmt_npm(d),
    "github": lambda d: _fmt_github(d),
}


def _fmt_pypi(data: dict) -> str:
    info = data.get("info") or {}
    bits = [f"PyPI 最新版 {info.get('version') or '未知'}"]
    lic = info.get("license") or info.get("license_expression")
    if not lic:
        for c in info.get("classifiers") or []:
            if str(c).startswith("License ::"):
                lic = str(c).split("::")[-1].strip()
                break
    if lic:
        bits.append("许可证：" + str(lic)[:80])
    if info.get("requires_python"):
        bits.append("Python " + str(info["requires_python"]))
    if info.get("summary"):
        bits.append(str(info["summary"])[:180].rstrip("。. "))
    return "；".join(bits) + "。"


def _fmt_npm(data: dict) -> str:
    latest = (data.get("dist-tags") or {}).get("latest") or data.get("version") or "未知"
    bits = [f"npm 最新版 {latest}"]
    if data.get("license"):
        bits.append("许可证：" + str(data["license"]))
    if data.get("description"):
        bits.append(str(data["description"])[:180].rstrip("。. "))
    return "；".join(bits) + "。"


def _fmt_github(data: dict) -> str:
    lic = (data.get("license") or {}).get("spdx_id") or "未声明"
    bits = [f"{data.get('full_name') or '仓库'}：{data.get('stargazers_count', 0)} stars",
            f"主语言 {data.get('language') or '未知'}", f"许可证 {lic}"]
    if data.get("description"):
        bits.append(str(data["description"])[:180].rstrip("。. "))
    return "；".join(bits) + "。"


def _format_payload(fmt: str, data) -> str | None:
    fn = _FORMATTERS.get(fmt)
    if not fn or not isinstance(data, dict):
        return None
    try:
        return fn(data)
    except Exception:
        return None


def active_tools() -> dict:
    """扩展工具名 → 异步执行器。返回的 callable 兼容 tools.invoke_with。"""
    out: dict = {}
    for name in _tool_map():
        async def runner(_name=name, **kwargs):
            return await _invoke(_name, kwargs, None)
        out[name] = runner
    return out


def skill_items() -> list[dict]:
    out: list[dict] = []
    for item in list_items():
        if not item.get("enabled") or item.get("error"):
            continue
        for idx, skill in enumerate(item.get("skills") or []):
            out.append({
                "id": f"ext-{item['id']}-{idx}",
                "name": skill["name"],
                "description": skill.get("description") or "",
                "guide": skill.get("guide") or skill.get("description") or "",
                "enabled": True,
                "builtin": False,
            })
    return out


def render_skills(allowed_extensions: set[str] | None = None,
                  allowed_skill_ids: set[str] | None = None) -> str:
    """渲染扩展技能；两个参数都为 None 时保持全局行为。"""
    items = []
    for s in skill_items():
        if allowed_skill_ids is not None and s["id"] not in allowed_skill_ids:
            continue
        if allowed_extensions is not None:
            ext_id = s["id"][4:].rsplit("-", 1)[0] if s["id"].startswith("ext-") else ""
            if ext_id not in allowed_extensions:
                continue
        if s.get("guide") or s.get("description"):
            items.append(s)
    if not items:
        return ""
    lines = ["【扩展技能】这些是外部扩展提供的能力说明，按场景选用："]
    for s in items:
        body = s["guide"] or s["description"]
        lines.append(f"- {s['name']}：{body[:1200]}")
    return "\n".join(lines)
