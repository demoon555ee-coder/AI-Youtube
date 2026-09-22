from __future__ import annotations

import asyncio
import json
import re
from typing import Any
import httpx
from app.providers.base import LLMProvider
from app.config import settings
from app.resilience.http import request_with_retry


class OpenAICompatibleLLMProvider(LLMProvider):
    """Provider for OpenAI-style /chat/completions APIs with retry/backoff."""

    name = "openai_compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: int | None = None, max_retries: int | None = None, use_json_mode: bool | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        # Some OpenAI-compatible backends (notably Gemini's compatibility layer)
        # reject or region-block requests that carry response_format. When
        # disabled, JSON is requested via the system prompt instead.
        self.use_json_mode = settings.llm_json_mode if use_json_mode is None else use_json_mode

    async def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        last_error: Exception | None = None
        for attempt in range(1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await request_with_retry(
                        lambda: client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers),
                        max_retries=self.max_retries,
                    )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                if isinstance(content, dict):
                    content.setdefault("_provider_usage", data.get("usage") or {})
                    content.setdefault("_provider", self.name)
                    content.setdefault("_model", self.model)
                    return content
                parsed = _parse_json_object(str(content))
                if not isinstance(parsed, dict):
                    raise ValueError("LLM response must be a JSON object")
                parsed.setdefault("_provider_usage", data.get("usage") or {})
                parsed.setdefault("_provider", self.name)
                parsed.setdefault("_model", self.model)
                return parsed
            except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
        raise RuntimeError(f"LLM provider failed after retries: {last_error}") from last_error


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object out of a model response.

    Some backends wrap JSON in markdown fences or prepend prose. Try the raw
    text first, then the first balanced {...} block as a fallback.
    """
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{", stripped)
    while match:
        start = match.start()
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(stripped[start : i + 1])
                        return value if isinstance(value, dict) else None
                    except json.JSONDecodeError:
                        break
        match = re.search(r"\{", stripped[start + 1 :])
        if match:
            match = re.compile(r"\{").search(stripped, start + 1)
    return None
