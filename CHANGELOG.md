# Changelog

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
- Approval-bound nodes are materialized into real approval requests when dependencies are ready.
- Learning evidence is generated from task outcomes and strategy changes are bounded to selection preference.
- Added planner event history and audit fields for risk tier, policy version and task linkage.
- Simplified operator UIs so humans approve/reject governance and learning proposals without impersonating workers.

## Historical releases

- 4.2.0 — Agent Learning & Self-Improvement
- 4.1.0 — Agent Planner & Dynamic Workflow Graph
- 4.0.0 — Autonomous Agent Runtime / Multi-Agent Orchestration
- 3.9.0 — Agent Governance & Human Oversight
- 3.8.0 — Autonomous Execution Controller
