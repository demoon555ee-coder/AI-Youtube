from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    async def generate_json(self, *, system: str, user: str) -> dict[str, Any]:
        raise NotImplementedError
