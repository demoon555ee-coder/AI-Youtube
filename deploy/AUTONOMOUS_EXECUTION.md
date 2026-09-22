# Autonomous Execution Controller — v3.8

## Purpose

The Autonomous Execution Controller converts approved optimization decisions into bounded actions while enforcing tenant, permission, budget, quality and revision guardrails.

## Modes

- `auto`: execute immediately when all guardrails pass.
- `approve`: reserve budget and require an explicit execute call.
- `defer`: persist the decision without starting production.
- `block`: prevent execution and release any prior reservation.

## Executable scopes

Only the following decision scopes are executable:

- `scene_reedit`
- `packaging_experiment`
- `blueprint_replan`
- `full_rebuild`

`no_action` and any unknown scope are never executed.

## Guardrails

Every execution checks:

1. Controller is enabled.
2. Caller has `content:write` permission.
3. Decision is actionable and above the configured confidence threshold.
4. Source project belongs to the same tenant/channel boundary.
5. Source project is in an executable lifecycle state.
6. A passing latest Quality Gate exists when `EXECUTION_REQUIRE_QUALITY_GATE=true`.
7. Daily revision limit is not exceeded.
8. Portfolio/budget reservation succeeds before expensive execution.
9. Idempotency key prevents duplicate execution of the same decision.

## Targeted scene re-edit

`scene_reedit` creates an immutable content revision and sets `evolution.execution_mode=targeted_scene_reedit`. The worker uses the targeted re-edit path and does not silently fall back to a full rebuild.

## Workflow reconciliation

The worker reconciles execution runs after workflow completion. Successful runs become `SUCCEEDED`; failures become `FAILED` and active reservations are released.

## Operations

Inspect execution runs through:

```text
GET /api/v1/execution/projects/{project_id}/runs
GET /api/v1/execution/channels/{channel_id}/runs
```

Dispatch:

```text
POST /api/v1/execution/decisions/{decision_id}/dispatch
```

Explicitly execute an approved run:

```text
POST /api/v1/execution/runs/{run_id}/execute
```

Defer a pending run:

```text
POST /api/v1/execution/runs/{run_id}/defer
```

## Production policy

Recommended production defaults:

```text
EXECUTION_CONTROLLER_ENABLED=true
EXECUTION_REQUIRE_QUALITY_GATE=true
EXECUTION_DEFAULT_RESERVATION_TTL_MINUTES=120
EXECUTION_MAX_REVISIONS_PER_DAY=5
OPTIMIZATION_AUTO_EXECUTE=false
```

Keep `OPTIMIZATION_AUTO_EXECUTE=false` until the channel owner has reviewed the observed behavior and the staging integration suite is green.
