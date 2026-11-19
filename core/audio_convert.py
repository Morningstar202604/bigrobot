"""把 QQ 的语音转成 Azure 能吃的 wav。

不自己写解码器：silk 交给生态里的 `pilk`（可选依赖），amr/ogg 交给 ffmpeg。
两个都没装就返回 None，上层如实报"识别不了"，不假装成功。
"""
from __future__ import annotations

import io
import shutil
import subprocess


def to_wav_bytes(data: bytes, suffix: str) -> bytes | None:
    """返回 wav 字节；无法转换返回 None。"""
    ext = (suffix or "").lower().lstrip(".")

    if ext in {"wav", "wave"}:
        return data

    if ext in {"amr", "ogg", "opus", "mp3", "m4a", "aac", "silk"} and shutil.which("ffmpeg"):
        try:
            proc = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
                input=data, capture_output=True, timeout=30, check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except (OSError, subprocess.SubprocessError):
            return None

    if ext == "silk":
        try:                      # 可选依赖：装了才用，不装不影响其他格式
            import pilk           # type: ignore[import-not-found]
        except ImportError:
            return None
        try:
            out = io.BytesIO()
            pilk.decode(io.BytesIO(data), out, pcm_rate=16000)
            return out.getvalue() or None
        except Exception:         # noqa: BLE001 - 第三方解码失败一律当"转不了"
            return None

    return None
