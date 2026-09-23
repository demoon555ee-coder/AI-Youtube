from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_version: str = "4.2.4"
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/youtube_ai"
    public_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    google_client_secrets_file: str = "/app/secrets/client_secret.json"
    google_client_secrets_json: str = ""
    oauth_redirect_path: str = "/api/v1/youtube/oauth/callback"
    google_auth_redirect_path: str = "/api/v1/auth/google/callback"
    oauth_state_ttl_seconds: int = 600
    app_encryption_key: str = ""
    auth_dev_fallback: bool = True
    auth_session_ttl_days: int = 30
    auth_cookie_name: str = "youtube_ai_session"
    csrf_token_header: str = "X-CSRF-Token"
    app_encryption_key_previous: str = ""
    api_key_default_ttl_days: int = 365
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    upload_chunk_mb: int = 8
    analytics_lookback_days: int = 28
    output_dir: str = "./data/output"
    render_engine: str = "ffmpeg"
    remotion_node_bin: str = "node"
    remotion_project_dir: str = "/app/app/remotion"
    remotion_concurrency: int = 2
    workflow_poll_seconds: float = 1.0
    workflow_lease_seconds: int = 1800
    workflow_enabled: bool = True
    research_scheduler_enabled: bool = True
    research_scheduler_poll_seconds: float = 30.0
    research_scheduler_batch_size: int = 3
    research_scheduler_lease_minutes: int = 20
    metrics_public: bool = False
    metrics_auth_token_file: str = "/app/secrets/metrics_token"
    readiness_timeout_seconds: float = 3.0
    provider_health_enabled: bool = True
    auto_migrate: bool = True
    schema_gate_enabled: bool = True
    release_id: str = "local"
    deployment_env: str = "development"
    trusted_proxy_count: int = 0
    audit_retention_days: int = 730
    usage_retention_days: int = 400
    auth_session_retention_days: int = 90
    login_rate_limit_retention_days: int = 2
    privacy_request_retention_days: int = 730
    billing_retention_days: int = 2555
    privacy_export_max_events: int = 10000
    maintenance_poll_seconds: int = 300
    billing_provider: str = "mock"
    billing_currency: str = "USD"
    billing_webhook_secret: str = ""
    billing_webhook_secrets: str = ""
    billing_return_url: str = "http://localhost:3000/billing"
    billing_webhook_tolerance_seconds: int = 300
    stripe_secret_key: str = ""
    stripe_api_base_url: str = "https://api.stripe.com"
    stripe_timeout_seconds: int = 20
    stripe_price_creator: str = ""
    stripe_price_pro: str = ""
    stripe_price_studio: str = ""

    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 3
    llm_json_mode: bool = True
    provider_failure_threshold: int = 3
    provider_circuit_cooldown_seconds: int = 60
    provider_half_open_seconds: int = 30
    provider_retry_base_seconds: float = 1.0
    provider_retry_max_seconds: float = 30.0
    media_recovery_enabled: bool = True
    media_recovery_poll_seconds: float = 10.0
    postpublish_poll_seconds: float = 60.0
    postpublish_enabled: bool = True
    media_recovery_batch_size: int = 5
    media_recovery_lease_seconds: int = 120
    media_job_max_attempts: int = 5
    workflow_dead_letter_enabled: bool = True
    creative_intelligence_enabled: bool = True
    creative_frame_interval_seconds: float = 3.0
    creative_max_frames: int = 12
    creative_similarity_threshold: float = 0.08
    multimodal_graph_enabled: bool = True
    multimodal_vision_enabled: bool = True
    multimodal_max_frames: int = 8
    multimodal_preflight_hard_fail: bool = True
    optimization_ai_enabled: bool = True
    optimization_min_confidence: float = 0.60
    optimization_default_max_actions: int = 3
    optimization_auto_execute: bool = False
    execution_controller_enabled: bool = True
    execution_require_quality_gate: bool = True
    execution_default_reservation_ttl_minutes: int = 120
    execution_max_revisions_per_day: int = 5
    governance_enabled: bool = True
    governance_approval_timeout_minutes: int = 120
    governance_default_mode: str = "approve"
    governance_global_kill_switch: bool = False
    planner_max_retries: int = 3
    learning_min_observations: int = 5
    vision_provider: str = "mock"
    vision_base_url: str = "https://api.openai.com/v1"
    vision_api_key: str = ""
    vision_model: str = "gpt-5.6-luna"
    vision_timeout_seconds: int = 60

    research_provider: str = "mock"
    research_endpoint: str = ""
    research_api_key: str = ""
    research_timeout_seconds: int = 30
    youtube_research_api_key: str = ""
    youtube_research_region_code: str = "US"
    youtube_research_language: str = "en"
    youtube_research_order: str = "viewCount"

    tts_provider: str = "espeak"
    visual_provider: str = "mock_png"
    visual_endpoint: str = ""
    visual_api_key: str = ""
    visual_model: str = ""
    stability_api_key: str = ""
    pexels_api_key: str = ""
    image_provider: str = "mock_png"
    image_endpoint: str = ""
    image_api_key: str = ""
    image_model: str = "gpt-image-2"
    runway_api_key: str = ""
    video_provider: str = "mock_video"
    video_endpoint: str = ""
    video_api_key: str = ""
    video_model: str = ""
    video_poll_seconds: float = 5.0
    video_timeout_seconds: int = 900
    thumbnail_provider: str = "pillow"
    thumbnail_image_provider: str = "mock_png"
    tts_endpoint: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    tts_api_key: str = ""
    tts_model: str = ""
    tts_voice: str = "alloy"
    tts_instructions: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def oauth_redirect_uri(self) -> str:
        return self.public_base_url.rstrip("/") + self.oauth_redirect_path

    @property
    def google_auth_redirect_uri(self) -> str:
        return self.public_base_url.rstrip("/") + self.google_auth_redirect_path

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
