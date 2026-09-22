# Multimodal Production Graph

The v3.6 graph is a pre-render and post-render intelligence layer. It links script, storyboard, scene intent, assets, audio, subtitles, timeline and sampled visual evidence into one persisted graph.

## Pre-render
The orchestrator runs a deterministic preflight before asset generation. `MULTIMODAL_PREFLIGHT_HARD_FAIL=true` stops production when a high-risk contradiction is found, such as missing visual intent, scene-number gaps or an estimated narration overrun.

## Post-render
After rendering, the service probes the actual media, reads the subtitle file, collects audio volume data, samples frames and sends multiple images plus the textual context to the configured Responses-compatible vision provider in one multimodal request. The result is persisted separately from the source project.

## Controls
- `MULTIMODAL_GRAPH_ENABLED`: enable graph generation.
- `MULTIMODAL_VISION_ENABLED`: allow multimodal vision calls; disabling it keeps deterministic graphing.
- `MULTIMODAL_MAX_FRAMES`: maximum sampled frames per post-render vision pass.
- `MULTIMODAL_PREFLIGHT_HARD_FAIL`: block asset generation on high-risk preflight conflicts.

The graph is advisory after rendering. Vision provider outages are recorded as `vision_mode=error` and do not invalidate a successful render.
