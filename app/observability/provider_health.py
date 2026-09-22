from __future__ import annotations

import shutil
from dataclasses import dataclass, asdict
from app.config import settings


@dataclass
class ProviderHealth:
    provider: str
    service: str
    configured: bool
    available: bool
    mode: str
    detail: str


class ProviderHealthService:
    """Non-billable provider readiness checks.

    Deep network probes are intentionally not automatic because some providers charge
    for generation requests. HTTP providers are therefore checked for configuration
    only; connectivity is validated by actual workflow calls and request metrics.
    """

    def check(self) -> list[ProviderHealth]:
        result = [
            ProviderHealth(
                provider='llm',
                service='llm',
                configured=(settings.llm_provider == 'mock' or bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)),
                available=(settings.llm_provider == 'mock' or bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)),
                mode='configuration',
                detail='mock' if settings.llm_provider == 'mock' else ('credentials/base URL configured' if (settings.llm_base_url and settings.llm_api_key and settings.llm_model) else 'credentials/base URL missing'),
            ),
            ProviderHealth(
                provider='research',
                service='research',
                configured=(settings.research_provider == 'mock' or bool(settings.research_endpoint)),
                available=(settings.research_provider == 'mock' or bool(settings.research_endpoint)),
                mode='configuration',
                detail='mock' if settings.research_provider == 'mock' else ('endpoint configured' if settings.research_endpoint else 'endpoint missing'),
            ),
            ProviderHealth(
                provider='youtube-research',
                service='research',
                configured=bool(settings.youtube_research_api_key),
                available=bool(settings.youtube_research_api_key),
                mode='configuration',
                detail='API key configured' if settings.youtube_research_api_key else 'API key missing',
            ),
            ProviderHealth(
                provider='tts',
                service='tts',
                configured=(settings.tts_provider == 'mock' or shutil.which('espeak') is not None),
                available=(settings.tts_provider == 'mock' or shutil.which('espeak') is not None),
                mode='local-binary',
                detail='espeak available' if settings.tts_provider != 'mock' and shutil.which('espeak') else ('mock' if settings.tts_provider == 'mock' else 'espeak not found'),
            ),
            ProviderHealth(
                provider='visual',
                service='visual',
                configured=(settings.visual_provider == 'mock_png' or bool(settings.visual_endpoint)),
                available=(settings.visual_provider == 'mock_png' or bool(settings.visual_endpoint)),
                mode='configuration',
                detail='mock_png' if settings.visual_provider == 'mock_png' else ('endpoint configured' if settings.visual_endpoint else 'endpoint missing'),
            ),
        ]
        return result

    def payload(self) -> dict:
        checks = self.check()
        return {
            'providers': [asdict(item) for item in checks],
            'all_configured': all(item.configured for item in checks if item.provider not in {'youtube-research'}),
        }
