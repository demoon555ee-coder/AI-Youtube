from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class TTSProvider(ABC):
    name: str

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: Path,
        *,
        language: str = "en",
        voice: str | None = None,
        speed: float = 1.0,
    ) -> dict[str, Any]:
        raise NotImplementedError
