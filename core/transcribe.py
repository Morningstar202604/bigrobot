"""语音转写：走微软 Azure 语音识别（有免费额度），没配凭据就明确返回未配置。

配置：AZURE_SPEECH_KEY / AZURE_SPEECH_REGION（例如 eastasia）。
只用标准 REST，不引入 SDK——一个 httpx 调用就够，避免多装一套依赖。
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("cs.events")


class NotConfigured(RuntimeError):
    """没有配置语音识别凭据。上层应提示用户去配置，而不是当失败处理。"""


def configured() -> bool:
    return bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


async def transcribe_url(audio_url: str, *, language: str = "zh-CN") -> str:
    """下载音频并转写。返回文本；未配置抛 NotConfigured，识别失败返回空串。"""
    if not configured():
        raise NotConfigured("未配置 AZURE_SPEECH_KEY / AZURE_SPEECH_REGION")
    key = os.environ["AZURE_SPEECH_KEY"]
    region = os.environ["AZURE_SPEECH_REGION"]
    endpoint = (
        f"https://{region}.stt.speech.microsoft.com/speech/recognition/"
        f"conversation/cognitiveservices/v1?language={language}"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        audio = await client.get(audio_url)
        if audio.status_code != 200:
            logger.warning("transcribe download failed %s", audio.status_code)
            return ""
        # Azure 直接吃 wav/pcm；amr/ogg 需要先转码，这里如实返回空串而不是假装识别成功
        ctype = audio.headers.get("content-type", "audio/wav")
        r = await client.post(
            endpoint,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": ctype,
                "Accept": "application/json",
            },
            content=audio.content,
        )
    if r.status_code != 200:
        logger.warning("transcribe failed %s: %s", r.status_code, r.text[:120])
        return ""
    data = r.json()
    return str(data.get("DisplayText") or "").strip()
