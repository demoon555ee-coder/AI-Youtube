from __future__ import annotations
import os
from app.config import settings
from app.providers.base import LLMProvider
from app.providers.mock import MockLLMProvider
from app.providers.http_llm import OpenAICompatibleLLMProvider


def get_llm(provider_name: str | None = None, config: dict | None = None) -> LLMProvider:
    name = provider_name or settings.llm_provider
    cfg = config or {}
    if name == "mock" or cfg.get("kind") == "mock":
        return MockLLMProvider()
    if name == "openai_compatible" or cfg.get("kind") == "openai_compatible":
        base_url = str(cfg.get("base_url") or settings.llm_base_url)
        api_key = str((os.getenv(str(cfg["api_key_env"])) if cfg.get("api_key_env") else settings.llm_api_key) or "")
        model = str(cfg.get("model") or settings.llm_model)
        if not base_url or not api_key or not model:
            raise RuntimeError("OpenAI-compatible provider requires base_url, api_key and model")
        return OpenAICompatibleLLMProvider(base_url=base_url, api_key=api_key, model=model)
    raise ValueError(f"Unknown LLM provider: {name}")
