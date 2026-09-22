from __future__ import annotations

import os

from app.config import settings
from app.tts.base import TTSProvider
from app.tts.espeak import EspeakTTSProvider
from app.tts.openai import OpenAITTSProvider


def get_tts(provider_name: str | None = None, config: dict | None = None) -> TTSProvider:
    cfg = config or {}
    name = provider_name or settings.tts_provider
    kind = str(cfg.get("kind") or name)
    if name == "espeak" or kind == "espeak":
        return EspeakTTSProvider()
    if name == "openai_tts" or kind == "openai_tts":
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.tts_api_key or settings.llm_api_key)
        base_url = str(cfg.get("base_url") or cfg.get("endpoint") or settings.tts_endpoint or "https://api.openai.com/v1")
        return OpenAITTSProvider(
            api_key=api_key,
            model=str(cfg.get("model") or settings.tts_model),
            voice=str(cfg.get("voice") or settings.tts_voice),
            instructions=str(cfg.get("instructions") or settings.tts_instructions),
            base_url=base_url,
        )
    raise ValueError(f"Unsupported TTS provider: {name}")
