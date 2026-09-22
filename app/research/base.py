from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ResearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, *, query: str, max_results: int = 10) -> dict[str, Any]:
        raise NotImplementedError
