from abc import ABC, abstractmethod
from typing import Any


class VisualAssetProvider(ABC):
    name: str

    @abstractmethod
    async def generate_scene_asset(
        self,
        *,
        prompt: str,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
        duration_seconds: float = 5.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError
