from __future__ import annotations
import base64
import json
import mimetypes
from pathlib import Path
from typing import Any
import httpx
from app.config import settings
from app.resilience.http import request_with_retry
from app.vision.base import VisionProvider


class OpenAIChatVisionProvider(VisionProvider):
    """Vision provider for OpenAI-style /chat/completions APIs.

    Some OpenAI-compatible backends (for example the Gemini OpenAI
    compatibility layer) do not implement the /responses endpoint. This
    provider sends images as image_url content parts to /chat/completions
    and keeps the same JSON contract as the responses-based provider.
    """

    name = "openai_chat_vision"

    def __init__(self, *, api_key: str, base_url: str | None = None, model: str | None = None, timeout_seconds: int | None = None):
        self.api_key = api_key
        self.base_url = (base_url or settings.vision_base_url).rstrip("/")
        self.model = model or settings.vision_model
        self.timeout_seconds = timeout_seconds or settings.vision_timeout_seconds

    def _data_url(self, image_path: str) -> str:
        raw = Path(image_path).read_bytes()
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")

    async def _analyze(self, *, image_paths: list[str], prompt: str) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            content.append({"type": "image_url", "image_url": {"url": self._data_url(image_path)}})
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            # Reasoning-capable models burn tokens on thinking; keep headroom.
            "max_tokens": 2048,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers),
                max_retries=2,
            )
        response.raise_for_status()
        body = response.json()
        message = ((body.get("choices") or [{}])[0].get("message") or {})
        text = message.get("content")
        if isinstance(text, list):
            text = "".join(str(part.get("text") or "") for part in text if isinstance(part, dict))
        text = str(text or "").strip()
        if not text:
            raise ValueError("Vision provider returned an empty response")
        result = json.loads(text)
        result.setdefault("_provider", self.name)
        result.setdefault("_model", self.model)
        return result

    async def analyze_multimodal(self, *, image_paths: list[str], prompt: str) -> dict[str, Any]:
        return await self._analyze(image_paths=image_paths, prompt=prompt)

    async def analyze_frame(self, *, image_path: str, prompt: str) -> dict[str, Any]:
        return await self._analyze(image_paths=[image_path], prompt=prompt)