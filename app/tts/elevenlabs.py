from __future__ import annotations

import base64
import wave
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.resilience.http import request_with_retry
from app.tts.base import TTSProvider


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs direct TTS adapter normalized to WAV for the renderer."""

    name = "elevenlabs"

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model: str = "eleven_flash_v2_5",
        base_url: str = "https://api.elevenlabs.io/v1",
        timeout_seconds: int = 180,
    ):
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY or TTS_API_KEY is required for ElevenLabs")
        if not voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID or TTS_VOICE is required for ElevenLabs")
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model or "eleven_flash_v2_5"
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        language: str = "en",
        voice: str | None = None,
        speed: float = 1.0,
    ) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("TTS input cannot be empty")
        if len(text) > 5000:
            raise ValueError("TTS input exceeds the provider request limit")

        voice_id = voice or self.voice_id
        payload: dict[str, Any] = {
            "text": text,
            "model_id": self.model,
        }
        if language and language != "en":
            payload["language_code"] = language
        if speed != 1.0:
            payload["voice_settings"] = {"speed": max(0.7, min(1.2, float(speed)))}

        query = "?output_format=pcm_16000"
        url = f"{self.base_url}/text-to-speech/{quote(voice_id, safe='')}{query}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/pcm",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(url, json=payload, headers=headers),
                max_retries=settings.llm_max_retries,
            )
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pcm = response.content
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm)

        return {
            "provider": self.name,
            "path": str(output_path),
            "language": language,
            "voice": voice_id,
            "model": self.model,
            "response_format": "wav",
            "duration_seconds": round(len(pcm) / (16000 * 2), 3),
        }
