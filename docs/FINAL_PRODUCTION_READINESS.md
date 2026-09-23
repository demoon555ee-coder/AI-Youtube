# Final production readiness

## Current release

- Application version: 4.2.4
- Main branch verification: CI run #165 passed for commit 0641dc8.
- Production schema observed at boot: 036_enforce_content_version_timestamps.
- Production API and Web deployments for 0641dc8 completed successfully.

## End-to-end production path

The canonical video path is:

`Idea/Content → Research → Script → Storyboard → Scene Director → Asset Routing → TTS → Remotion/FFmpeg Render → Thumbnail Variants → Quality Gate → Governed Publish → YouTube Analytics → Post-publish Monitoring → Optimization Proposal → Human Approval → Next Strategy/Plan`

## Runtime responsibilities

### API
Serves the HTTP API, authentication, governance, project state, routing, content intelligence, analytics, publishing and dashboard.

### Worker
Runs the durable workflow queue and background loops:

- WorkflowWorker
- AgentTaskWorker
- Autopilot scheduler
- Research scheduler
- Media recovery
- Post-publish monitoring
- Billing webhook processing
- Privacy/retention maintenance

### Renderer
- FFmpeg remains the safe default.
- Remotion is available through `RENDER_ENGINE=remotion`.
- `RENDER_ENGINE=auto` attempts Remotion first and records a fallback reason before using FFmpeg.

### Media intelligence
- Scene Director produces motion, transition and caption directives.
- Provider routing separates generative media from stock B-roll.
- Pexels is routed only to stock-capable scenes.
- Runway is reserved for generative video capability.
- Remotion renders machine-readable captions and scene motion/transition instructions.

### Packaging
Thumbnail generation produces a control variant plus deterministic title-only and hook-only variants under a single-axis experiment contract.

### Governance
Publishing remains subject to the central governance admission/recheck contract. Unknown actions fail closed. Optimization proposals do not mutate published artifacts in place and require the configured quality/permission guardrails.

## Provider readiness

The platform exposes runtime provider readiness without exposing secrets. Real provider credentials are deployment inputs and must be supplied and rotated through Railway secrets when ready. Missing or invalid credentials must result in explicit readiness/fallback behavior rather than fabricated configuration.

## Final infrastructure gate

Railway must contain three application services in production:

- api-release
- web-release
- worker-release

The worker must use the same Dockerfile/runtime as the API and start with:

`python -m app.workflows.worker`

Worker health is observable through:

`GET /api/v1/observability/workers`

A worker with a stale heartbeat is considered unhealthy for production operations.

## Safe operating defaults

`GOVERNANCE_ENABLED=true`

`GOVERNANCE_DEFAULT_MODE=approve`

`GOVERNANCE_GLOBAL_KILL_SWITCH=false`

`OPTIMIZATION_AUTO_EXECUTE=false`

These defaults keep autonomous execution bounded until the operator deliberately enables a broader policy.

## Definition of done

The project is operationally ready when the worker-release deployment is SUCCESS and its heartbeat is fresh, while API/Web remain healthy and the required external provider credentials are valid. The remaining provider credential swaps are deployment configuration, not application-code blockers.
