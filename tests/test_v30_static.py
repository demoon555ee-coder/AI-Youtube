from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v30_provider_files_exist():
    expected = [
        "app/media/openai_image.py",
        "app/media/http_video.py",
        "app/media/runway_video.py",
        "app/media/mock_video.py",
        "app/tts/openai.py",
        "app/tts/elevenlabs.py",
        "app/models/media_job.py",
    ]
    for item in expected:
        assert (ROOT / item).exists(), item


def test_v30_migration_present():
    text = (ROOT / "app/db/migrations.py").read_text()
    assert '018_v30_real_ai_production' in text


def test_v30_orchestration_routes_real_media_and_tts():
    text = (ROOT / "app/services/orchestrator.py").read_text()
    assert 'production_video' in text
    assert 'tts_route' in text
    assert '_record_actual_usage' in text


def test_v30_current_configuration_is_versioned():
    config = (ROOT / "app/config.py").read_text()
    assert 'app_version: str = "4.2.1"' in config
    env = (ROOT / ".env.example").read_text()
    assert 'VIDEO_PROVIDER=' in env
    assert 'TTS_PROVIDER=' in env


def test_v30_routing_supports_native_real_media_defaults():
    from app.routing.service import DEFAULTS, SETTINGS_PROVIDER
    assert any(item["provider"] == "openai_image" for item in DEFAULTS["image"])
    assert any(item["provider"] == "http_image" for item in DEFAULTS["image"])
    assert any(item["provider"] == "http_video" for item in DEFAULTS["video"])
    assert any(item["provider"] == "openai_tts" for item in DEFAULTS["tts"])
    assert SETTINGS_PROVIDER["image"]() == SETTINGS_PROVIDER["image"]()
    assert "video" in SETTINGS_PROVIDER


def test_v30_asset_factory_supports_separate_image_and_video_routes():
    text = (ROOT / "app/media/service.py").read_text()
    assert "image_provider" in text
    assert "video_provider" in text
    assert "_is_motion_asset" in text
    assert "get_video_provider" in text



def test_v30_routed_research_uses_separate_llm_provider_config():
    text = (ROOT / "app/agents/factory.py").read_text()
    assert 'cfg.get("llm_provider")' in text
    assert 'cfg.get("llm_config")' in text
    assert 'get_llm(llm_provider, llm_config)' in text


def test_v30_video_download_auth_requires_explicit_opt_in():
    text = (ROOT / "app/media/http_video.py").read_text()
    assert "forward_auth_to_download: bool = False" in text
    assert "self.forward_auth_to_download" in text


def test_v30_production_validator_blocks_demo_ai_providers(monkeypatch, tmp_path):
    from app.deployment import validate_production_settings
    from app.config import settings as runtime_settings
    secret_file = tmp_path / "client_secret.json"
    secret_file.write_text("{}")
    monkeypatch.setattr(runtime_settings, "app_env", "production")
    monkeypatch.setattr(runtime_settings, "app_encryption_key", "real")
    monkeypatch.setattr(runtime_settings, "auth_dev_fallback", False)
    monkeypatch.setattr(runtime_settings, "auth_cookie_name", "__Host-youtube_ai_session")
    monkeypatch.setattr(runtime_settings, "cors_origins", "https://app.example.com")
    monkeypatch.setattr(runtime_settings, "public_base_url", "https://api.example.com")
    monkeypatch.setattr(runtime_settings, "frontend_url", "https://app.example.com")
    monkeypatch.setattr(runtime_settings, "billing_return_url", "https://app.example.com/billing")
    monkeypatch.setattr(runtime_settings, "database_url", "postgresql+asyncpg://youtube_ai:strong@db:5432/youtube_ai")
    monkeypatch.setattr(runtime_settings, "google_client_secrets_file", str(secret_file))
    monkeypatch.setattr(runtime_settings, "billing_provider", "stripe")
    monkeypatch.setattr(runtime_settings, "billing_webhook_secret", "secret")
    monkeypatch.setattr(runtime_settings, "stripe_secret_key", "sk_test_placeholder")
    monkeypatch.setattr(runtime_settings, "stripe_price_creator", "price_creator")
    monkeypatch.setattr(runtime_settings, "stripe_price_pro", "price_pro")
    monkeypatch.setattr(runtime_settings, "stripe_price_studio", "price_studio")
    monkeypatch.setattr(runtime_settings, "workflow_enabled", True)
    monkeypatch.setattr(runtime_settings, "llm_provider", "mock")
    monkeypatch.setattr(runtime_settings, "research_provider", "mock")
    monkeypatch.setattr(runtime_settings, "image_provider", "mock_png")
    monkeypatch.setattr(runtime_settings, "visual_provider", "mock_png")
    monkeypatch.setattr(runtime_settings, "video_provider", "mock_video")
    codes = {item.code for item in validate_production_settings()}
    assert {"mock_llm_provider", "mock_research_provider", "mock_image_provider", "mock_video_provider"}.issubset(codes)


def test_v30_production_env_uses_non_mock_ai_defaults():
    env = (ROOT / ".env.production.example").read_text()
    assert "LLM_PROVIDER=openai_compatible" in env
    assert "RESEARCH_PROVIDER=youtube_data" in env
    assert "IMAGE_PROVIDER=openai_image" in env
    assert ("VIDEO_PROVIDER=http_video" in env or "VIDEO_PROVIDER=runway" in env)
    assert ("TTS_PROVIDER=openai_tts" in env or "TTS_PROVIDER=elevenlabs" in env)
    assert "RUNWAY_API_KEY=" in env
    assert "ELEVENLABS_API_KEY=" in env



def test_v30_production_validator_rejects_stripe_test_key_and_placeholders(monkeypatch, tmp_path):
    from app.deployment import validate_production_settings
    from app.config import settings as runtime_settings
    secret_file = tmp_path / "client_secret.json"
    secret_file.write_text("{}")
    values = {
        "app_env": "production", "app_encryption_key": "real",
        "auth_dev_fallback": False, "auth_cookie_name": "__Host-youtube_ai_session",
        "cors_origins": "https://app.example.com", "public_base_url": "https://api.example.com",
        "frontend_url": "https://app.example.com", "billing_return_url": "https://app.example.com/billing",
        "database_url": "postgresql+asyncpg://youtube_ai:strong@db:5432/youtube_ai",
        "google_client_secrets_file": str(secret_file), "billing_provider": "stripe",
        "billing_webhook_secret": "live-secret", "stripe_secret_key": "sk_test_x",
        "stripe_price_creator": "price_creator", "stripe_price_pro": "price_pro", "stripe_price_studio": "price_studio",
        "llm_provider": "openai_compatible", "llm_base_url": "https://api.example.com/v1",
        "llm_api_key": "key", "llm_model": "model", "research_provider": "youtube_data",
        "youtube_research_api_key": "key", "image_provider": "openai_image", "visual_provider": "openai_image",
        "image_api_key": "key", "video_provider": "http_video", "video_endpoint": "https://video.example.com/generate",
        "tts_provider": "openai_tts", "tts_api_key": "key",
    }
    for key, value in values.items():
        monkeypatch.setattr(runtime_settings, key, value)
    codes = {item.code for item in validate_production_settings()}
    assert "stripe_test_key_in_production" in codes
    assert "placeholder_config" in codes

    
def test_v30_production_validator_accepts_runway_and_elevenlabs(monkeypatch, tmp_path):
    from app.deployment import validate_production_settings
    from app.config import settings as runtime_settings

    secret_file = tmp_path / "client_secret.json"
    secret_file.write_text('{"web":{"client_id":"id","client_secret":"secret"}}')
    values = {
        "app_env": "production",
        "app_encryption_key": "real",
        "auth_dev_fallback": False,
        "auth_cookie_name": "__Host-youtube_ai_session",
        "cors_origins": "https://app.example.com",
        "public_base_url": "https://api.example.com",
        "frontend_url": "https://app.example.com",
        "billing_return_url": "https://app.example.com/billing",
        "database_url": "postgresql+asyncpg://youtube_ai:strong@db:5432/youtube_ai",
        "google_client_secrets_file": str(secret_file),
        "google_client_secrets_json": "",
        "billing_provider": "stripe",
        "billing_webhook_secret": "live-secret",
        "stripe_secret_key": "sk_live_x",
        "stripe_price_creator": "price_creator",
        "stripe_price_pro": "price_pro",
        "stripe_price_studio": "price_studio",
        "llm_provider": "openai_compatible",
        "llm_base_url": "https://api.example.com/v1",
        "llm_api_key": "key",
        "llm_model": "model",
        "research_provider": "youtube_data",
        "youtube_research_api_key": "key",
        "image_provider": "openai_image",
        "visual_provider": "openai_image",
        "image_api_key": "key",
        "video_provider": "runway",
        "runway_api_key": "key",
        "video_model": "gen4.5",
        "tts_provider": "elevenlabs",
        "elevenlabs_api_key": "key",
        "elevenlabs_voice_id": "voice",
    }
    for key, value in values.items():
        monkeypatch.setattr(runtime_settings, key, value)

    codes = {item.code for item in validate_production_settings()}
    assert "missing_runway_api_key" not in codes
    assert "missing_elevenlabs_api_key" not in codes
    assert "missing_elevenlabs_voice" not in codes
