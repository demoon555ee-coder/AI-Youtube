# Creative Intelligence v3.4

Creative Intelligence analyzes rendered media at scene level. The deterministic layer uses ffprobe/FFmpeg and lightweight frame signatures; an optional vision provider evaluates relevance, clarity and narration↔visual alignment.

## Production

Set `CREATIVE_INTELLIGENCE_ENABLED=true` and use a real `VISION_PROVIDER` in production. The default production example uses `openai_responses_vision`; staging can use the mock provider.

## Targeted re-edit

`POST /api/v1/creative/projects/{project_id}/reedit` creates an immutable content revision. The source project's rendered file is never overwritten. Only requested scene ranges receive replacement visuals; the original audio is preserved and subtitles are re-applied when present.

## Guardrails

The re-edit endpoint requires `content:write`. Replacement paths must remain inside the configured output directory. The source revision remains immutable.
