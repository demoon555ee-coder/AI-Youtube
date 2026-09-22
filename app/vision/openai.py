from __future__ import annotations
import base64
import json
from pathlib import Path
from typing import Any
import httpx
from app.config import settings
from app.resilience.http import request_with_retry
from app.vision.base import VisionProvider


class OpenAIResponsesVisionProvider(VisionProvider):
    name = "openai_responses_vision"

    def __init__(self, *, api_key: str, base_url: str | None = None, model: str | None = None, timeout_seconds: int | None = None):
        self.api_key = api_key
        self.base_url = (base_url or settings.vision_base_url).rstrip("/")
        self.model = model or settings.vision_model
        self.timeout_seconds = timeout_seconds or settings.vision_timeout_seconds

    async def analyze_multimodal(self, *, image_paths: list[str], prompt: str) -> dict[str, Any]:
        contents = [{"type": "input_text", "text": prompt}]
        for image_path in image_paths:
            raw = Path(image_path).read_bytes()
            data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
            contents.append({"type": "input_image", "image_url": data_url, "detail": "low"})
        payload = {
            "model": self.model,
            "input": [{"role": "user", "content": contents}],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(f"{self.base_url}/responses", json=payload, headers=headers),
                max_retries=2,
            )
        response.raise_for_status()
        body = response.json()
        text = str(body.get("output_text") or "").strip()
        if not text:
            for item in body.get("output") or []:
                for content in item.get("content") or []:
                    if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and content.get("text"):
                        text += str(content["text"])
        result = json.loads(text)
        result.setdefault("_provider", self.name)
        result.setdefault("_model", self.model)
        return result

    async def analyze_frame(self, *, image_path: str, prompt: str) -> dict[str, Any]:
        raw = Path(image_path).read_bytes()
        data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
        payload = {
            "model": self.model,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url, "detail": "low"},
                ],
            }],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(f"{self.base_url}/responses", json=payload, headers=headers),
                max_retries=2,
            )
        response.raise_for_status()
        body = response.json()
        text = str(body.get("output_text") or "").strip()
        if not text:
            for item in body.get("output") or []:
                for content in item.get("content") or []:
                    if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and content.get("text"):
                        text += str(content["text"])
        import json
        result = json.loads(text)
        result.setdefault("_provider", self.name)
        result.setdefault("_model", self.model)
        return result
