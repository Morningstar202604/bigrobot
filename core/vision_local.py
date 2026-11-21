"""本地看图：MiniCPM-V 1B GGUF + mtmd，跑在 CPU 上，不依赖云端 Key。

llama_cpp.server 的 OpenAI 端点不会把 image_url 送进视觉编码器（实测 prompt
只有 24 tokens，模型根本没看到图）。这里直接用 Llama + MiniCPMv26ChatHandler，
把图片真正编码后再生成，供 tool_describe_image 在本地视觉模式调用。
"""
from __future__ import annotations

import asyncio
import re
import threading

_MODEL = None
_LOAD_LOCK = threading.Lock()
_GEN_LOCK = threading.Lock()


def _load(model_path: str, mmproj_path: str):
    global _MODEL
    with _LOAD_LOCK:
        if _MODEL is not None:
            return _MODEL
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import MiniCPMv26ChatHandler

        _MODEL = Llama(
            model_path=model_path,
            chat_handler=MiniCPMv26ChatHandler(clip_model_path=mmproj_path),
            n_ctx=2048,
            n_threads=2,
            verbose=False,
        )
        return _MODEL


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"</?think>", "", text)
    return text.strip()


def _describe_sync(b64: str, question: str, model_path: str, mmproj_path: str) -> str:
    llm = _load(model_path, mmproj_path)
    data_url = b64 if b64.startswith("data:") else f"data:image/jpeg;base64,{b64}"
    with _GEN_LOCK:
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            max_tokens=256,
            temperature=0.2,
        )
    return _clean((out.get("choices") or [{}])[0].get("message", {}).get("content") or "")


async def describe(b64: str, question: str, model_path: str, mmproj_path: str) -> str:
    return await asyncio.to_thread(_describe_sync, b64, question, model_path, mmproj_path)
