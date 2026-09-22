from typing import Any
from app.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "mock"

    async def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        return {"ok": True, "provider": self.name, "system": system[:80], "user": user[:160]}
