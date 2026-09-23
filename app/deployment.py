from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings
from app.db.migrations import MIGRATIONS


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]


def validate_production_settings() -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if settings.app_env != "production":
        return issues

    if not settings.app_encryption_key:
        issues.append(ValidationIssue("missing_encryption_key", "APP_ENCRYPTION_KEY is required"))
    if settings.auth_dev_fallback:
        issues.append(ValidationIssue("dev_auth_enabled", "AUTH_DEV_FALLBACK must be false in production"))
    if not settings.auth_cookie_name.startswith("__Host-"):
        issues.append(ValidationIssue("weak_auth_cookie_name", "AUTH_COOKIE_NAME must use the __Host- prefix in production"))
    if not settings.cors_origins.strip() or "*" in settings.cors_origins:
        issues.append(ValidationIssue("wildcard_cors", "CORS_ORIGINS must be explicit in production"))
    parsed_public = urlparse(settings.public_base_url)
    if parsed_public.scheme != "https":
        issues.append(ValidationIssue("public_url_not_https", "PUBLIC_BASE_URL must use https in production"))
    parsed_frontend = urlparse(settings.frontend_url)
    if parsed_frontend.scheme != "https":
        issues.append(ValidationIssue("frontend_url_not_https", "FRONTEND_URL must use https in production"))
    if settings.billing_return_url and urlparse(settings.billing_return_url).scheme != "https":
        issues.append(ValidationIssue("billing_return_url_not_https", "BILLING_RETURN_URL must use https in production"))
    origins = settings.allowed_origins
    if any("localhost" in origin or "127.0.0.1" in origin for origin in origins):
        issues.append(ValidationIssue("localhost_cors", "CORS_ORIGINS cannot include localhost in production"))
    if settings.database_url.startswith("postgresql+asyncpg://postgres:postgres@"):
        issues.append(ValidationIssue("default_database_credentials", "DATABASE_URL uses development credentials"))
    google_config_valid = False
    if settings.google_client_secrets_json.strip():
        try:
            raw = json.loads(settings.google_client_secrets_json)
            config = raw.get("web") or raw.get("installed") or raw if isinstance(raw, dict) else {}
            google_config_valid = isinstance(config, dict) and bool(config.get("client_id")) and bool(config.get("client_secret"))
        except json.JSONDecodeError:
            google_config_valid = False
    else:
        google_config_valid = Path(settings.google_client_secrets_file).exists()
    if not google_config_valid:
        issues.append(ValidationIssue("missing_google_client_secret", "Google OAuth client secret configuration is missing or invalid"))
    if settings.billing_provider == "mock":
        issues.append(ValidationIssue("mock_billing_provider", "BILLING_PROVIDER must be a real provider in production"))
    if not (settings.billing_webhook_secret or settings.billing_webhook_secrets):
        issues.append(ValidationIssue("missing_billing_webhook_secret", "A billing webhook signing secret is required in production"))
    placeholder_values = {
        "public_base_url": settings.public_base_url,
        "frontend_url": settings.frontend_url,
        "billing_return_url": settings.billing_return_url,
        "video_endpoint": settings.video_endpoint,
    }
    for field, value in placeholder_values.items():
        lowered = str(value or "").lower()
        if "example.com" in lowered or "replace-with" in lowered:
            issues.append(ValidationIssue("placeholder_config", f"{field} contains a production placeholder"))

    if settings.billing_provider == "stripe":
        if not settings.stripe_secret_key:
            issues.append(ValidationIssue("missing_stripe_secret_key", "STRIPE_SECRET_KEY is required in production"))
        elif settings.stripe_secret_key.startswith("sk_test_"):
            issues.append(ValidationIssue("stripe_test_key_in_production", "STRIPE_SECRET_KEY must be a live key in production"))
        for code, value in (("creator", settings.stripe_price_creator), ("pro", settings.stripe_price_pro), ("studio", settings.stripe_price_studio)):
            if not value:
                issues.append(ValidationIssue(f"missing_stripe_price_{code}", f"STRIPE_PRICE_{code.upper()} is required in production"))

    if settings.creative_intelligence_enabled:
        if settings.vision_provider == "mock":
            issues.append(ValidationIssue("mock_vision_provider", "VISION_PROVIDER must be real when creative intelligence is enabled in production"))
        elif settings.vision_provider in {"openai", "openai_responses_vision"} and not (settings.vision_api_key or settings.llm_api_key):
            issues.append(ValidationIssue("missing_vision_key", "VISION_API_KEY or LLM_API_KEY is required for the configured vision provider"))

    # v3.0 production must not silently fall back to demo AI/media providers.
    if settings.workflow_enabled:
        if settings.llm_provider == "mock":
            issues.append(ValidationIssue("mock_llm_provider", "LLM_PROVIDER must be a real provider in production"))
        elif settings.llm_provider == "openai_compatible":
            if not settings.llm_base_url or not settings.llm_api_key or not settings.llm_model:
                issues.append(ValidationIssue("incomplete_llm_provider", "LLM_BASE_URL, LLM_API_KEY and LLM_MODEL are required for openai_compatible in production"))

        if settings.research_provider == "mock":
            issues.append(ValidationIssue("mock_research_provider", "RESEARCH_PROVIDER must be real in production"))
        elif settings.research_provider == "youtube_data" and not settings.youtube_research_api_key:
            issues.append(ValidationIssue("missing_youtube_research_key", "YOUTUBE_RESEARCH_API_KEY is required for youtube_data research in production"))
        elif settings.research_provider == "http_json" and not settings.research_endpoint:
            issues.append(ValidationIssue("missing_research_endpoint", "RESEARCH_ENDPOINT is required for http_json research in production"))

        if settings.image_provider == "mock_png" or settings.visual_provider == "mock_png":
            issues.append(ValidationIssue("mock_image_provider", "IMAGE_PROVIDER/VISUAL_PROVIDER must not use mock_png in production"))
        elif settings.image_provider in {"openai_image"} and not (settings.image_api_key or settings.llm_api_key):
            issues.append(ValidationIssue("missing_image_key", "IMAGE_API_KEY or LLM_API_KEY is required for openai_image in production"))
        elif settings.image_provider == "stability_image" and not settings.stability_api_key:
            issues.append(ValidationIssue("missing_stability_api_key", "STABILITY_API_KEY is required for stability_image in production"))
        elif settings.image_provider == "pexels_photo" and not settings.pexels_api_key:
            issues.append(ValidationIssue("missing_pexels_api_key", "PEXELS_API_KEY is required for pexels_photo in production"))
        elif settings.image_provider == "http_image" and not settings.image_endpoint:
            issues.append(ValidationIssue("missing_image_endpoint", "IMAGE_ENDPOINT is required for http_image in production"))

        if settings.video_provider == "mock_video":
            issues.append(ValidationIssue("mock_video_provider", "VIDEO_PROVIDER must be a real provider in production"))
        elif settings.video_provider == "runway" and not (settings.runway_api_key or settings.video_api_key):
            issues.append(ValidationIssue("missing_runway_api_key", "RUNWAY_API_KEY or VIDEO_API_KEY is required for the runway provider in production"))
        elif settings.video_provider == "pexels_video" and not settings.pexels_api_key:
            issues.append(ValidationIssue("missing_pexels_api_key", "PEXELS_API_KEY is required for pexels_video in production"))
        elif settings.video_provider == "http_video" and not settings.video_endpoint:
            issues.append(ValidationIssue("missing_video_endpoint", "VIDEO_ENDPOINT is required for http_video in production"))

        if settings.tts_provider == "elevenlabs" and not (settings.elevenlabs_api_key or settings.tts_api_key):
            issues.append(ValidationIssue("missing_elevenlabs_api_key", "ELEVENLABS_API_KEY or TTS_API_KEY is required for the elevenlabs provider in production"))
        elif settings.tts_provider == "elevenlabs" and not (settings.elevenlabs_voice_id or settings.tts_voice):
            issues.append(ValidationIssue("missing_elevenlabs_voice", "ELEVENLABS_VOICE_ID or TTS_VOICE is required for the elevenlabs provider in production"))
        elif settings.tts_provider == "openai_tts" and not (settings.tts_api_key or settings.llm_api_key):
            issues.append(ValidationIssue("missing_tts_key", "TTS_API_KEY or LLM_API_KEY is required for openai_tts in production"))

    return issues


def assert_production_settings() -> None:
    issues = validate_production_settings()
    if issues:
        raise RuntimeError("Production configuration invalid: " + "; ".join(i.message for i in issues))
