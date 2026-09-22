# v3.0 Production AI Providers

The production content factory is provider-neutral. Configure providers through environment variables or tenant-scoped `ProviderProfile` records, while keeping secrets in environment/secret-manager references rather than database plaintext.

## LLM
Use `LLM_PROVIDER=openai_compatible` with `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. The adapter uses an OpenAI-compatible `/chat/completions` JSON contract.

## Research
`RESEARCH_PROVIDER=youtube_data` uses public YouTube Data API search/statistics with `YOUTUBE_RESEARCH_API_KEY`. `http_json` remains available for an external research service.

## Images
Set `IMAGE_PROVIDER=openai_image` (or `VISUAL_PROVIDER=openai_image`) with `IMAGE_API_KEY` or `LLM_API_KEY`, plus an optional `IMAGE_MODEL`. The native adapter writes returned image bytes to the project asset directory.

## Video
Use `VIDEO_PROVIDER=http_video` with a provider endpoint. The generic adapter supports asynchronous `POST → status_url → download_url` jobs, allowlisted remote hosts, bounded polling, and optional `Idempotency-Key` forwarding. API credentials are not forwarded to output/CDN URLs unless `forward_auth_to_download=true` is explicitly configured.

## TTS
Use `TTS_PROVIDER=openai_tts` with `TTS_API_KEY` or `LLM_API_KEY`, `TTS_MODEL`, `TTS_VOICE`, and optional instructions. Long scene narration is chunked before synthesis so provider input limits do not fail the entire render.

## Production validation
Production configuration rejects mock LLM, research, image and video providers when workflow execution is enabled. Staging may continue using deterministic mock providers for E2E tests.

## Media audit
Video generation jobs are persisted after successful asynchronous provider completion in `media_generation_jobs`. Cost events are recorded after workflow state is committed so a billing-ledger failure cannot roll back a successful render.

## Provider failover
Provider routing happens per workflow step. If the selected provider fails, the retry path excludes the previously chosen provider and re-routes.
