# Changelog

## 4.2.4 — Release synchronization and runtime hardening

- Aligned production media-provider credential aliases for Runway readiness and execution.
- Removed deprecated naive UTC helper usage from the worker and portfolio services while preserving compatibility with existing timestamp columns.
- Documented production media-provider credential names and updated the environment examples to the 4.2.4 application version.

## 4.2.4 — Final media pipeline hardening

- Added server-side Remotion rendering with FFmpeg fallback and real staging runtime smoke coverage.
- Added Scene Director motion, transition and caption-style directives to the render contract.
- Added machine-readable caption tracks and persistent render timeline artifacts.
- Added deterministic thumbnail experiment variants and artifact registration.
- Production Compose includes a dedicated workflow worker for durable execution, autopilot scheduling, post-publish monitoring, recovery and maintenance loops.

## 4.2.4 — Provider Runtime Visibility
- Added a read-only runtime-availability API that reports effective provider candidates without exposing API keys.
- Added routing UI visibility for provider readiness so unavailable credentials are visible before starting production.
- Added regression coverage for Pexels runtime availability with and without a configured key.

## 4.2.3 — Capability-aware Media Routing
- Prevented stock providers from being selected for ordinary generative production and thumbnail tasks.
- Added per-scene stock routing for `broll` scenes with automatic fallback to the generative route when stock media is unavailable.
- Preserved Pexels image formats returned by the API instead of forcing JPEG output.
- Added regression coverage for capability-aware routing and stock B-roll selection.

## 4.2.2 — Pexels Stock Media Routing
- Added Pexels photo and video providers with search, media selection, download validation and retry handling.
- Added 24-hour in-process search caching to reduce repeated Pexels API calls.
- Added stock B-roll routing capability while keeping Stability/Runway available for generative production paths.
- Preserved Pexels source URLs and creator attribution in the asset manifest for downstream publishing.
- Added production validation for PEXELS_API_KEY and regression/static coverage for the new providers.

## 4.2.1 — Agent Control Plane Correction
- Corrected the v4.0–v4.2 control-plane lifecycle after a full logic audit.
- Agent task admission now uses the same governance authority at creation and immediately before execution.
- Approval decisions update the actual task state; stale approvals are rechecked against the current policy version.
- Lease tokens are mandatory for worker lifecycle mutations.
- Added safe task lineage and dependency validation.
- Planner and runtime states are synchronized so completed tasks unlock downstream nodes.
