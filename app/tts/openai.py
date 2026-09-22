from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.tts.base import TTSProvider
from app.resilience.http import request_with_retry


class OpenAITTSProvider(TTSProvider):
    name = "openai_tts"

    def __init__(self, *, api_key: str, model: str | None = None, voice: str | None = None, instructions: str = "", base_url: str = "https://api.openai.com/v1", timeout_seconds: int = 180):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI TTS")
        self.api_key = api_key
        self.model = model or settings.tts_model or "gpt-4o-mini-tts"
        self.voice = voice or settings.tts_voice or "alloy"
        self.instructions = instructions
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def synthesize(self, text: str, output_path: Path, *, language: str = "en", voice: str | None = None, speed: float = 1.0) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("TTS input cannot be empty")
        if len(text) > 4096:
            raise ValueError("TTS input exceeds 4096 characters")
        payload: dict[str, Any] = {
            "model": self.model,
            "input": text,
            "voice": voice or self.voice,
            "response_format": "wav",
            "speed": max(0.25, min(4.0, speed)),
        }
        if self.instructions and self.model not in {"tts-1", "tts-1-hd"}:
            payload["instructions"] = self.instructions
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(
                f"{self.base_url}/audio/speech",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            ),
                max_retries=settings.llm_max_retries,
            )
            response.raise_for_status()
            output_path.write_bytes(response.content)
        return {"provider": self.name, "path": str(output_path), "language": language, "voice": voice or self.voice, "response_format": "wav"}
