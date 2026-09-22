from __future__ import annotations
import os
from app.config import settings
from app.vision.base import VisionProvider
from app.vision.mock import MockVisionProvider
from app.vision.openai import OpenAIResponsesVisionProvider
from app.vision.openai_chat import OpenAIChatVisionProvider


def get_vision_provider(provider_name: str | None = None, config: dict | None = None) -> VisionProvider:
    cfg = config or {}
    name = provider_name or settings.vision_provider
    if name == "mock" or cfg.get("kind") == "mock":
        return MockVisionProvider()
    if name in {"openai_chat", "openai_chat_vision"} or cfg.get("kind") == "openai_chat_vision":
        api_key = os.getenv(str(cfg.get("api_key_env")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.vision_api_key or settings.llm_api_key)
        if not api_key:
            raise RuntimeError("VISION_API_KEY or LLM_API_KEY is required for vision provider")
        return OpenAIChatVisionProvider(
            api_key=api_key,
            base_url=str(cfg.get("base_url") or settings.vision_base_url),
            model=str(cfg.get("model") or settings.vision_model),
            timeout_seconds=int(cfg.get("timeout_seconds") or settings.vision_timeout_seconds),
        )
    if name in {"openai", "openai_responses_vision"} or cfg.get("kind") == "openai_responses_vision":
        api_key = os.getenv(str(cfg.get("api_key_env")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.vision_api_key or settings.llm_api_key)
        if not api_key:
            raise RuntimeError("VISION_API_KEY or LLM_API_KEY is required for vision provider")
        return OpenAIResponsesVisionProvider(
            api_key=api_key,
            base_url=str(cfg.get("base_url") or settings.vision_base_url),
            model=str(cfg.get("model") or settings.vision_model),
            timeout_seconds=int(cfg.get("timeout_seconds") or settings.vision_timeout_seconds),
        )
    raise ValueError(f"Unknown vision provider: {name}")
